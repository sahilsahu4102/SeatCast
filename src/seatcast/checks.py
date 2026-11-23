import json
import subprocess
import time

import duckdb
import pandas as pd

from seatcast import OUT, RAW, WORK, cfg, gtfs

Z7 = r'C:\Program Files\7-Zip\7z.exe'
ARC = RAW / 'gps' / 'delhi-dtc-bus-gtfs-rt-2026-10.7z'
GD = WORK / 'gps'
IST_S = 19800
# defaults for gps keys missing in config.yaml (reported to the owner of config)
NEW = {'route_m': 200, 'route_sample': 0.01, 'route_min_share': 0.5, 'route_min_lift': 2.0, 'sched_min': 2,
       'top_routes': 50, 'alias_share': 0.7, 'alias_n': 20, 'alias_top': 30, 'board_m': [300, 500]}
NAMED = ['badarpur', 'shakarpur', 'madangir', 'telephone exchange', 'bawana', 'sarai rohella', 'health center']

MAC = f'''
CREATE OR REPLACE MACRO haversine_m(la1, lo1, la2, lo2) AS
  2 * 6371000 * asin(sqrt(pow(sin(radians(la2 - la1) / 2), 2)
  + cos(radians(la1)) * cos(radians(la2)) * pow(sin(radians(lo2 - lo1) / 2), 2)));
CREATE OR REPLACE MACRO ist_utc(t) AS CAST(epoch(t - INTERVAL 330 MINUTE) AS BIGINT);
CREATE OR REPLACE MACRO ist_day(t) AS DATE '1970-01-01' + CAST((t + {IST_S}) // 86400 AS INTEGER);
CREATE OR REPLACE MACRO ist_hour(t) AS CAST(((t + {IST_S}) % 86400) // 3600 AS INTEGER);
'''


def G():
    return {**NEW, **cfg()['gps']}


def db():
    con = duckdb.connect()
    con.execute('INSTALL sqlite; LOAD sqlite;')
    (WORK / 'tmp').mkdir(exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'tmp').as_posix()}'")
    con.execute(MAC)
    return con


def fname(d):
    return f'bus_movements_{d.replace("-", "_")}.db'


def extract(days):
    miss = [d for d in days if not (GD / fname(d)).exists()]
    if not miss:
        return 0.0
    GD.mkdir(parents=True, exist_ok=True)
    t = time.time()
    subprocess.run([Z7, 'x', str(ARC), f'-o{GD}', *map(fname, miss), '-y'], check=True, capture_output=True)
    return time.time() - t


def topq(con, d):
    p = WORK / f'gps_{d}.parquet'
    if p.exists():
        return p
    f = (GD / fname(d)).as_posix()
    con.execute(f'''COPY (SELECT v, lat, lon, route_id, trip_id, t_utc FROM (
        SELECT DISTINCT vehicle_id v, CAST(lat AS DOUBLE) lat, CAST(lng AS DOUBLE) lon,
          CAST(route_id AS BIGINT) route_id, trip_id, CAST(timestamp AS BIGINT) t_utc
        FROM sqlite_scan('{f}', 'vehicle_feed') WHERE vehicle_id IS NOT NULL) WHERE lat BETWEEN 27 AND 30
        AND lon BETWEEN 76 AND 78.5 ORDER BY v, t_utc) TO '{p.as_posix()}' (FORMAT parquet)''')
    return p


def one(con, q):
    return con.execute(q).fetchall()[0]


def asof(tix, gps, win):
    # last ping of the same vehicle at or before the ticket, at most win seconds earlier
    return f'''SELECT t.tid, g.lat, g.lon, g.route_id gr, t.t - g.t lag FROM {tix} t
        ASOF JOIN {gps} g ON t.v = g.v AND t.t >= g.t WHERE t.t - g.t <= {win}'''


def routestops(con, g):
    con.register('trips', g['trips'][['trip_id', 'route_id']])
    con.register('st', g['stop_times'][['trip_id', 'stop_id']])
    con.register('stops', g['stops'][['stop_id', 'stop_lat', 'stop_lon']])
    con.execute('''CREATE OR REPLACE TABLE rs AS SELECT DISTINCT CAST(r.route_id AS BIGINT) route_id, s.stop_lat la,
        s.stop_lon lo FROM trips r JOIN st USING (trip_id) JOIN stops s USING (stop_id)''')


def route_check(con, gp, k):
    # share of pings within route_m of a stop of their own route vs of another route (control)
    con.execute(f'''CREATE OR REPLACE TABLE pg AS SELECT row_number() OVER () i, * FROM (SELECT route_id, lat, lon
        FROM {gp} WHERE route_id IS NOT NULL USING SAMPLE {k['route_sample'] * 100} PERCENT (bernoulli, 1))''')
    con.execute('''CREATE OR REPLACE TABLE rl AS SELECT route_id, coalesce(lead(route_id) OVER (ORDER BY hash(route_id)),
        min(route_id) OVER ()) alt FROM (SELECT DISTINCT route_id FROM rs)''')
    q = '''SELECT count(*) n, median(d) med, avg((d <= %d)::INT) w, avg((d <= 500)::INT) w5 FROM (
        SELECT p.i, min(haversine_m(p.lat, p.lon, s.la, s.lo)) d FROM pg p %s JOIN rs s ON s.route_id = %s GROUP BY p.i)'''
    a = one(con, q % (k['route_m'], '', 'p.route_id'))
    b = one(con, q % (k['route_m'], 'JOIN rl ON rl.route_id = p.route_id', 'rl.alt'))
    ing = one(con, 'SELECT avg((route_id IN (SELECT route_id FROM rs))::INT) FROM pg')[0]
    r = {'n': a[0], 'in_gtfs': ing, 'median_m': a[1], 'within': a[2], 'within_500': a[3],
         'control_median_m': b[1], 'control_within': b[2]}
    r['ok'] = bool(a[2] >= k['route_min_share'] and a[2] >= k['route_min_lift'] * b[2])
    return r


def sched(con, g):
    # GTFS trips leaving their first stop per route, day type and hour
    cal = pd.DataFrame(g['calendar'])
    tr = g['trips'][['trip_id', 'route_id', 'service_id']]
    ok = pd.DataFrame([(s, t) for t, d in cfg()['daytypes'].items() for s in gtfs.services({'calendar': cal}, d)],
                      columns=['service_id', 'daytype'])
    con.register('tr', tr)
    con.register('ok', ok)
    con.register('st', g['stop_times'][['trip_id', 'stop_sequence', 'dep']])
    return con.sql('''SELECT CAST(tr.route_id AS BIGINT) route_id, ok.daytype, CAST(f.dep // 3600 % 24 AS INT) h, count(*) sched
        FROM (SELECT trip_id, arg_min(dep, stop_sequence) dep FROM st GROUP BY trip_id) f
        JOIN tr USING (trip_id) JOIN ok USING (service_id) GROUP BY ALL''').df()


def observed(con, gps):
    # distinct (vehicle, trip) by IST hour of its first ping
    return con.sql(f'''SELECT route_id, ist_day(f) d, ist_hour(f) h, count(*) obs FROM (
        SELECT route_id, v, trip_id, min(t_utc) f FROM {gps} WHERE route_id IS NOT NULL GROUP BY ALL) GROUP BY ALL''').df()


def delivery(con, g, gp, days):
    dt = {pd.Timestamp(d): ('weekday' if pd.Timestamp(d).weekday() < 5 else
                                   'saturday' if pd.Timestamp(d).weekday() == 5 else 'sunday') for d in days}
    ob = observed(con, gp)
    ob = ob.assign(d=pd.to_datetime(ob['d']))
    ob = ob[ob['d'].isin(dt)].assign(daytype=lambda x: x['d'].map(dt))
    dtc = set(ob['route_id'])
    sc = sched(con, g)
    sc = sc[sc['route_id'].isin(dtc)]
    rh = sc.merge(ob.groupby(['route_id', 'daytype', 'h'], as_index=False)['obs'].sum(), how='left',
                  on=['route_id', 'daytype', 'h']).fillna({'obs': 0})
    return rh, dt, dtc


def scale(rh, od, k):
    r = rh.groupby(['route_id', 'daytype'], as_index=False)[['sched', 'obs']].sum()
    r['ratio'] = r['obs'] / r['sched']
    r = r.merge(od, on='route_id', how='left').fillna({'pax': 0})
    return r.sort_values(['daytype', 'pax'], ascending=[True, False])


def ratio_stats(rh, k):
    x = rh[rh['sched'] >= k['sched_min']].assign(ratio=lambda d: d['obs'] / d['sched'])
    out = {}
    for t, d in x.groupby('daytype'):
        q = d['ratio'].quantile([.1, .25, .5, .75, .9]).round(3).tolist()
        a = rh[rh['daytype'] == t]
        out[t] = {'route_hours': len(d), 'q10_25_50_75_90': q, 'total_ratio': round(a['obs'].sum() / a['sched'].sum(), 3),
                  'share_below_0.5': round(float((d['ratio'] < .5).mean()), 3)}
    return out


def overlap(con, days, gps):
    con.execute(f'''CREATE OR REPLACE TABLE gv AS SELECT DISTINCT ist_day(t_utc) d, upper(trim(v)) v FROM {gps}''')
    con.execute(f'''CREATE OR REPLACE TABLE tv AS SELECT CAST(date AS DATE) d, upper(trim(v)) v, series, sum(pc) pax,
        count(*) n FROM '{(WORK / 'tickets.parquet').as_posix()}' WHERE v IS NOT NULL AND v <> 'NULL'
        AND CAST(date AS DATE) IN (SELECT unnest({[str(d) for d in days]}::DATE[])) GROUP BY ALL''')
    q = '''SELECT %s, count(*) veh, sum(pax) pax, sum(n) tix, sum((gv.v IS NOT NULL)::INT) veh_in,
        sum(CASE WHEN gv.v IS NOT NULL THEN pax END) pax_in, sum(CASE WHEN gv.v IS NOT NULL THEN n END) tix_in
        FROM tv LEFT JOIN gv ON tv.d = gv.d AND tv.v = gv.v GROUP BY %s'''
    tot = con.sql(q % ('1 k', '1')).df().iloc[0]
    ser = con.sql(q % ('series k', 'series')).df()
    any_ = one(con, 'SELECT avg((v IN (SELECT v FROM gv))::INT) FROM tv')[0]
    nul = one(con, f'''SELECT avg((v IS NULL OR v = 'NULL')::INT) FROM '{(WORK / 'tickets.parquet').as_posix()}'
        WHERE CAST(date AS DATE) IN (SELECT unnest({[str(d) for d in days]}::DATE[]))''')[0]
    r = {'ticket_vehicle_days': int(tot['veh']), 'tickets': int(tot['tix']), 'passengers': int(tot['pax']),
         'share_vehicle_days_in_gps': round(tot['veh_in'] / tot['veh'], 4),
         'share_tickets_in_gps': round(tot['tix_in'] / tot['tix'], 4),
         'share_passengers_in_gps': round(tot['pax_in'] / tot['pax'], 4),
         'share_vehicles_in_gps_any_day': round(any_, 4), 'share_tickets_null_vehicle': round(nul, 4),
         'by_series': {str(s): {'vehicle_days': int(v), 'share_passengers_in_gps': round(0 if p == 0 else (pi or 0) / p, 4)}
                       for s, v, p, pi in zip(ser['k'], ser['veh'], ser['pax'], ser['pax_in'])}}
    return r


def boardings(con, days, gps, win):
    # tickets of GPS days with a known vehicle, matched to the bus position at purchase
    con.execute(f'''CREATE OR REPLACE TABLE tx AS SELECT t.tid, upper(trim(t.v)) v, ist_utc(t.ts) t, t.pc,
        o.route_id, o.rung_b, o.rung_a, sb.lat lb, sb.lon ob, sa.lat la, sa.lon oa
        FROM '{(WORK / 'tickets.parquet').as_posix()}' t JOIN '{(WORK / 'od.parquet').as_posix()}' o USING (tid)
        JOIN '{(WORK / 'pattern_stops.parquet').as_posix()}' sb ON sb.pattern_id = o.pattern_id AND sb.k = o.b
        JOIN '{(WORK / 'pattern_stops.parquet').as_posix()}' sa ON sa.pattern_id = o.pattern_id AND sa.k = o.a
        WHERE t.v IS NOT NULL AND t.v <> 'NULL' AND CAST(t.date AS DATE) IN (SELECT unnest({[str(d) for d in days]}::DATE[]))''')
    con.execute(f'CREATE OR REPLACE TABLE gx AS SELECT upper(trim(v)) v, lat, lon, route_id, t_utc t FROM {gps}')
    con.execute('CREATE OR REPLACE TABLE am AS ' + asof('tx', 'gx', win))
    return con.sql('''SELECT tx.tid, tx.pc, tx.rung_b, tx.rung_a, a.lag, a.gr = tx.route_id same_route,
        haversine_m(a.lat, a.lon, tx.lb, tx.ob) d_board, haversine_m(a.lat, a.lon, tx.la, tx.oa) d_alight
        FROM tx JOIN am a USING (tid)''').df()


def dstats(d, ms):
    q = d.quantile([.5, .75, .9]).round(0).tolist()
    return {'n': len(d), 'median_m': q[0], 'p75_m': q[1], 'p90_m': q[2],
            **{f'within_{m}m': round(float((d <= m).mean()), 4) for m in ms}}


def board_stats(b, tot, ms):
    r = {'tickets_total': tot, 'matched': len(b), 'matched_share': round(len(b) / tot, 4),
         'lag_median_s': float(b['lag'].median()), 'board': dstats(b['d_board'], ms),
         'alight': dstats(b['d_alight'], ms), 'share_ping_on_ticket_route': round(float(b['same_route'].mean()), 4)}
    s = b[b['same_route']]
    r['board_same_route'] = dstats(s['d_board'], ms)
    r['by_rung_board'] = {k: dstats(d['d_board'], ms) for k, d in b.groupby('rung_b')}
    r['by_rung_board_same_route'] = {k: dstats(d['d_board'], ms) for k, d in s.groupby('rung_b')}
    r['by_rung_alight'] = {k: dstats(d['d_alight'], ms) for k, d in b.groupby('rung_a')}
    return r


def names(k):
    u = pd.read_csv(WORK / 'unmatched_stops.csv')
    top = u.groupby('name_n')['p'].sum().sort_values(ascending=False)
    keep = set(top.index[:k['alias_top']]) | (set(NAMED) & set(top.index))
    u = u[u['name_n'].isin(keep) & u['cand'].notna() & u['runner'].notna()]
    return u[['name_n', 'route', 'route_id', 'cand', 'runner']]


def alias_evidence(con, g, days, k, win):
    u = names(k)
    sn = g['stops'][['stop_id', 'stop_name', 'stop_lat', 'stop_lon']].copy()
    from seatcast.clean import norm
    sn['gn'] = sn['stop_name'].map(norm)
    ps = pd.read_parquet(WORK / 'pattern_stops.parquet')[['pattern_id', 'stop_id']]
    pt = pd.read_parquet(WORK / 'patterns.parquet')[['pattern_id', 'route_id']]
    rs = ps.merge(pt, on='pattern_id')[['route_id', 'stop_id']].drop_duplicates()
    rs = rs.assign(route_id=rs['route_id'].astype(int), stop_id=rs['stop_id'].astype(str))
    sn['stop_id'] = sn['stop_id'].astype(str)
    rs = rs.merge(sn, on='stop_id')
    c = pd.concat([u.assign(c=u['cand']), u.assign(c=u['runner'])]).drop_duplicates(['name_n', 'route', 'c'])
    c = c.assign(route_id=c['route_id'].astype(int)).merge(
        rs[['route_id', 'gn', 'stop_lat', 'stop_lon']].rename(columns={'gn': 'c'}), on=['route_id', 'c'])
    con.register('cand', c[['name_n', 'route', 'c', 'stop_lat', 'stop_lon']])
    con.register('uu', u[['name_n', 'route']].drop_duplicates())
    con.execute(f'''CREATE OR REPLACE TABLE ta AS SELECT t.tid, t.ss_n name_n, t.route_raw route, upper(trim(t.v)) v, ist_utc(t.ts) t
        FROM '{(WORK / 'tickets.parquet').as_posix()}' t JOIN uu ON uu.name_n = t.ss_n AND uu.route = t.route_raw
        WHERE t.v IS NOT NULL AND t.v <> 'NULL' AND CAST(t.date AS DATE) IN (SELECT unnest({[str(d) for d in days]}::DATE[]))''')
    con.execute('CREATE OR REPLACE TABLE aa AS ' + asof('ta', 'gx', win))
    return con.sql('''WITH d AS (SELECT ta.tid, ta.name_n, ta.route, c.c, min(haversine_m(a.lat, a.lon, c.stop_lat, c.stop_lon)) m
          FROM ta JOIN aa a USING (tid) JOIN cand c ON c.name_n = ta.name_n AND c.route = ta.route GROUP BY ALL),
        w AS (SELECT *, row_number() OVER (PARTITION BY tid ORDER BY m) r FROM d),
        n AS (SELECT name_n, route, count(DISTINCT tid) tot FROM d GROUP BY ALL)
        SELECT w.name_n name, w.route, w.c candidate, count(*) tickets, any_value(n.tot) tot,
          round(median(w.m)) median_m FROM w JOIN n USING (name_n, route) WHERE w.r = 1 GROUP BY w.name_n, w.route, w.c
        ORDER BY name, route, tickets DESC''').df().assign(share=lambda d: (d['tickets'] / d['tot']).round(3)).merge(
        c.groupby(['name_n', 'route'], as_index=False)['c'].nunique().rename(columns={'name_n': 'name', 'c': 'cands'}), on=['name', 'route'])


def propose(ev, k):
    ev = ev.assign(propose=(ev['cands'] >= 2) & (ev['share'] >= k['alias_share']) & (ev['tot'] >= k['alias_n']) & (ev['median_m'] <= cfg()['match_geo_m']))
    return ev.rename(columns={'tot': 'name_tickets', 'share': 'share_nearest'})


def top_od():
    return pd.read_parquet(WORK / 'od.parquet', columns=['route_id', 'pc']).groupby('route_id', as_index=False)['pc'].sum().rename(
        columns={'pc': 'pax'}).astype({'route_id': int})


def gps():
    t0, k = time.time(), G()
    days = cfg()['gps']['days']
    r = {'days': days, 'extract_s': round(extract(days), 1)}
    con = db()
    gp = [topq(con, d) for d in days]
    gl = "read_parquet(%s)" % [p.as_posix() for p in gp]
    g = gtfs.load()
    routestops(con, g)
    con.execute(f'CREATE OR REPLACE VIEW gv0 AS SELECT * FROM {gl}')
    r['pings'] = one(con, 'SELECT count(*) FROM gv0')[0]
    r['route_check'] = route_check(con, 'gv0', k)
    print('route check', r['route_check'], flush=True)
    if r['route_check']['ok']:
        rh, dt, dtc = delivery(con, g, 'gv0', days)
        sc = scale(rh, top_od(), k)
        sc.round(3).to_csv(WORK / 'service_scale.csv', index=False)
        r['delivery'] = {'dtc_routes_seen': len(dtc), **ratio_stats(rh, k)}
        top = sc[sc['pax'] > 0].groupby('daytype').head(k['top_routes'])
        w = top.sort_values(['daytype', 'ratio']).groupby('daytype').head(10)
        r['delivery']['worst_high_demand'] = {t: d[['route_id', 'sched', 'obs', 'ratio', 'pax']].round(3).to_dict('records')
                                              for t, d in w.groupby('daytype')}
        r['overlap'] = overlap(con, days, 'gv0')
        b = boardings(con, days, 'gv0', k['match_window_s'])
        tot = one(con, 'SELECT count(*) FROM tx')[0]
        r['boarding'] = board_stats(b, tot, k['board_m'])
        ev = propose(alias_evidence(con, g, days, k, k['match_window_s']), k)
        ev.to_csv(WORK / 'gps_alias_evidence.csv', index=False)
        r['alias_proposed'] = int(ev['propose'].sum())
    r['runtime_s'] = round(time.time() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'gps_checks.json').write_text(json.dumps(r, indent=1, default=float), encoding='utf-8')
    print(json.dumps({x: y for x, y in r.items() if x != 'overlap'}, indent=1, default=float)[:6000])
    return r
