import json
import math
import re
import subprocess
import time

import duckdb
import pandas as pd

from seatcast import OUT, RAW, ROOT, WORK, cfg, gtfs

Z7 = r'C:\Program Files\7-Zip\7z.exe'
ARC = RAW / 'gps' / 'delhi-dtc-bus-gtfs-rt-2026-10.7z'
GD = WORK / 'gps'
IST_S = 19800
# defaults for gps keys missing in config.yaml (reported to the owner of config)
NEW = {'route_m': 200, 'route_sample': 0.01, 'route_min_share': 0.5, 'route_min_lift': 2.0, 'sched_min': 2,
       'top_routes': 50, 'stop_m': 150, 'pass_gap_s': 900, 'ref_fracs': [0.4, 0.7], 'ref_win': 0.15,
       'pass_min_day': 5, 'km_dt': [1, 120], 'km_step': [10, 1000], 'alias_share': 0.7, 'alias_n': 20, 'alias_top': 30, 'board_m': [300, 500]}
ALL = ('2026-10-01', '2026-10-31')   # archive span
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
    con.execute("SET memory_limit='4GB'; SET threads=4")
    (WORK / 'tmp').mkdir(exist_ok=True)
    con.execute(f"SET temp_directory='{(WORK / 'tmp').as_posix()}'")
    con.execute(MAC)
    return con


def fname(d):
    return f'bus_movements_{d.replace("-", "_")}.db'


def extract(d):
    GD.mkdir(parents=True, exist_ok=True)
    subprocess.run([Z7, 'x', str(ARC), f'-o{GD}', fname(d), '-y'], check=True, capture_output=True)


def rmdb(d):
    for x in GD.glob(fname(d) + '*'):
        x.unlink()


def convert(con, days):
    # one .db on disk at a time; days with a parquet are skipped
    t = time.time()
    for d in days:
        if not (WORK / f'gps_{d}.parquet').exists():
            extract(d)
            topq(con, d)
            print('converted', d, round(time.time() - t), 's', flush=True)
        rmdb(d)
    return time.time() - t


def alldays():
    return [str(x.date()) for x in pd.date_range(ALL[0], ALL[1])]


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


def daytype(d, hol):
    d = pd.Timestamp(d)
    return 'sunday' if str(d.date()) in hol or d.weekday() == 6 else 'saturday' if d.weekday() == 5 else 'weekday'


def band(h, bands):
    return max(b for b in bands[:-1] if b <= h)


def shrunk(obs, sched, k):
    return (obs + k) / (sched + k)


def trips(con, gps):
    # one row per GPS (vehicle, trip): IST day and hour of its first ping, and its duration in seconds
    return con.sql(f'''SELECT route_id, ist_day(f) d, ist_hour(f) h, l - f dur FROM (
        SELECT route_id, v, trip_id, min(t_utc) f, max(t_utc) l FROM {gps} WHERE route_id IS NOT NULL GROUP BY ALL)''').df()


def count_obs(tr):
    return tr.groupby(['route_id', 'd', 'h']).size().rename('obs').reset_index()


def passq(near, gap):
    # a vehicle's near-stop pings form one pass; a gap above `gap` seconds starts a new one; the pass is timed by its closest ping
    return f'''WITH a AS (SELECT *, t - lag(t) OVER w g FROM {near} WINDOW w AS (PARTITION BY route_id, stop_id, v ORDER BY t)),
        b AS (SELECT *, sum((g IS NULL OR g > {gap})::INT) OVER (PARTITION BY route_id, stop_id, v ORDER BY t
          ROWS UNBOUNDED PRECEDING) p FROM a)
        SELECT route_id, stop_id, v, arg_min(t, m) t FROM b GROUP BY route_id, stop_id, v, p'''


def bands_at(g, bs):
    # per (route, stop): number of day-hour bands with a scheduled departure
    st = g['stop_times'][['trip_id', 'stop_id', 'dep']].assign(h=lambda x: (x['dep'] // 3600 % 24).astype(int))
    r = st.merge(g['trips'][['trip_id', 'route_id']], on='trip_id')[['route_id', 'stop_id', 'h']].drop_duplicates()
    r['b'] = r['h'].map(lambda h: band(h, bs))
    return r.groupby(['route_id', 'stop_id'])['b'].nunique().rename('nb').reset_index().astype({'route_id': int})


def refstops(g, k):
    # per GTFS route, stops near ref_fracs of its canonical pattern, preferring one with departures in most bands
    pt = pd.read_parquet(WORK / 'patterns.parquet')
    pt = pt[pt['canonical']].drop_duplicates('route_id')[['pattern_id', 'route_id']]
    ps = pd.read_parquet(WORK / 'pattern_stops.parquet').merge(pt, on='pattern_id')
    ps = ps.assign(route_id=ps['route_id'].astype(int), stop_id=ps['stop_id'].astype(str), f=ps['dist_m'] / ps.groupby('pattern_id')['dist_m'].transform('max'))
    nb = bands_at(g, k['bands']).assign(stop_id=lambda x: x['stop_id'].astype(str))
    ps = ps.merge(nb, on=['route_id', 'stop_id'], how='left').fillna({'nb': 0})
    out = []
    for f in k['ref_fracs']:
        c = ps.assign(dev=(ps['f'] - f).abs())
        c['near'] = c['dev'] <= k['ref_win']
        c = c.sort_values(['route_id', 'near', 'nb', 'dev'], ascending=[True, False, False, True])
        out.append(c.drop_duplicates('route_id')[['route_id', 'stop_id', 'lat', 'lon']])
    return pd.concat(out).drop_duplicates(['route_id', 'stop_id'])


def observed_passes(con, gps, refs, k):
    con.register('refs', refs)
    d = k['stop_m'] / 100000
    con.execute(f'''CREATE OR REPLACE TABLE near AS SELECT p.route_id, r.stop_id, p.v, p.t_utc t,
        haversine_m(p.lat, p.lon, r.lat, r.lon) m FROM {gps} p JOIN refs r ON p.route_id = r.route_id
        AND abs(p.lat - r.lat) < {d} AND abs(p.lon - r.lon) < {d} WHERE haversine_m(p.lat, p.lon, r.lat, r.lon) <= {k['stop_m']}''')
    return con.sql(f'SELECT route_id, ist_day(t) d, ist_hour(t) h, count(*) obs FROM ({passq("near", k["pass_gap_s"])}) GROUP BY ALL').df()


def sched_stops(con, g, refs):
    # GTFS departures at the reference stops per route, day type and hour
    cal = pd.DataFrame(g['calendar'])
    ok = pd.DataFrame([(s, t) for t, d in cfg()['daytypes'].items() for s in gtfs.services({'calendar': cal}, d)],
                      columns=['service_id', 'daytype'])
    con.register('ok', ok)
    con.register('tr2', g['trips'][['trip_id', 'route_id', 'service_id']].astype({'route_id': int}))
    con.register('st2', g['stop_times'][['trip_id', 'stop_id', 'dep']].astype({'stop_id': str}))
    con.register('refs2', refs[['route_id', 'stop_id']].astype({'stop_id': str}))
    return con.sql('''SELECT tr2.route_id, ok.daytype, CAST(st2.dep // 3600 % 24 AS INT) h, count(*) sched
        FROM st2 JOIN tr2 USING (trip_id) JOIN ok USING (service_id) JOIN refs2 ON refs2.route_id = tr2.route_id AND refs2.stop_id = st2.stop_id
        GROUP BY ALL''').df()


def delivery(ob, sc, seen, days, k, hol, method, lr=None):
    # route x daytype x band: sched = departures per day x days of that type, obs = pooled observations
    bs = k['bands']
    dt = {pd.Timestamp(d): daytype(d, hol) for d in days}
    nd = pd.Series(dt).value_counts()
    ob = ob.assign(d=pd.to_datetime(ob['d']))
    ob = ob[ob['d'].isin(dt)].assign(daytype=lambda x: x['d'].map(dt), band=lambda x: x['h'].map(lambda h: band(h, bs)))
    sc = sc.assign(band=sc['h'].map(lambda h: band(h, bs)))
    sc = sc.groupby(['route_id', 'daytype', 'band'], as_index=False)['sched'].sum()
    sc['ndays'] = sc['daytype'].map(nd)
    sc['sched'] = sc['sched'] * sc['ndays']
    cov = sc[sc['route_id'].isin(seen)]
    o = ob.groupby(['route_id', 'daytype', 'band'], as_index=False)['obs'].sum()
    rb = cov.merge(o, how='left', on=['route_id', 'daytype', 'band']).fillna({'obs': 0})
    rb['lr'] = rb['route_id'].map(lr) if lr is not None else 1.0
    rb['ratio'] = shrunk(rb['obs'], rb['sched'], k['shrink_trips'] * rb['lr'])
    rb['ratio_raw'] = rb['obs'] / rb['sched']
    rb['method'] = method
    return rb[COLS + ['lr']], sc, ob, dt


COLS = ['route_id', 'daytype', 'band', 'sched', 'obs', 'ndays', 'ratio', 'ratio_raw', 'method']


def top_od():
    return pd.read_parquet(WORK / 'od.parquet', columns=['route_id', 'pc']).groupby('route_id', as_index=False)['pc'].sum().rename(
        columns={'pc': 'pax'}).astype({'route_id': int})


def qs(x):
    return x.quantile([.1, .25, .5, .75, .9]).round(3).tolist()


def delivery_stats(rb, ob, dt, od, k, unc):
    out = {}
    for t, a in rb.groupby('daytype'):
        c = a[a['sched'] >= k['sched_min'] * a['lr']]
        rt = a.groupby('route_id', as_index=False).agg(sched=('sched', 'sum'), obs=('obs', 'sum'), lr=('lr', 'first'))
        rt['ratio'] = shrunk(rt['obs'], rt['sched'], k['shrink_trips'] * rt['lr'])
        rt = rt.merge(od, on='route_id', how='left').fillna({'pax': 0}).sort_values('pax', ascending=False)
        top = rt.head(k['top_routes']).assign(dev=lambda x: x['ratio'].map(math.log).abs()).sort_values('dev', ascending=False).head(10)
        days = [d for d, x in dt.items() if x == t]
        dd = ob[ob['d'].isin(days) & ob['route_id'].isin(a['route_id'])].groupby('d')['obs'].sum()
        per = (dd / (a['sched'].sum() / len(days))).round(3)
        out[t] = {'days': len(days), 'route_bands': len(c), 'sched': round(float(a['sched'].sum())), 'obs': round(float(a['obs'].sum())),
                  'total_ratio': round(a['obs'].sum() / a['sched'].sum(), 3), 'q10_25_50_75_90': qs(c['ratio']),
                  'share_below_0.8': round(float((c['ratio'] < .8).mean()), 3), 'share_above_1.2': round(float((c['ratio'] > 1.2).mean()), 3),
                  'sched_trips_no_gps_routes': unc[t],
                  'top_demand_largest_correction': top[['route_id', 'sched', 'obs', 'ratio', 'pax']].round(3).to_dict('records'),
                  'daily_network_ratio': {'mean': round(float(per.mean()), 3), 'std': round(float(per.std()), 3),
                                          'min': float(per.min()), 'max': float(per.max()), 'cv': round(float(per.std() / per.mean()), 3),
                                          'by_day': {str(x.date()): v for x, v in per.items()}}}
    return out


def kmq(src, k):
    # km driven per route, IST day and hour: steps between consecutive pings of one vehicle on an unchanged route_id
    a, b = k['km_dt']
    lo, hi = k['km_step']
    return f'''SELECT route_id, ist_day(t_utc) d, ist_hour(t_utc) h, sum(m) / 1000 km, count(*) steps FROM (
        SELECT route_id, t_utc, t_utc - lag(t_utc) OVER w dt, route_id = lag(route_id) OVER w same,
          haversine_m(lat, lon, lag(lat) OVER w, lag(lon) OVER w) m FROM {src} WINDOW w AS (PARTITION BY v ORDER BY t_utc))
        WHERE same AND dt BETWEEN {a} AND {b} AND m >= {lo} AND m < {hi} GROUP BY ALL'''


def obs_km(con, days, k):
    # per-day cache of the small km aggregate
    out = []
    for d in days:
        p = WORK / f'gps_km_{d}.parquet'
        if not p.exists():
            q = kmq(f"read_parquet('{(WORK / f'gps_{d}.parquet').as_posix()}')", k)
            con.execute(f"COPY ({q}) TO '{p.as_posix()}' (FORMAT parquet)")
        out.append(pd.read_parquet(p))
    km = pd.concat(out)
    km = km.assign(d=pd.to_datetime(km['d'])).groupby(['route_id', 'd', 'h'], as_index=False)['km'].sum().rename(columns={'km': 'obs'})
    return km.astype({'route_id': int})


def hopkm(con, st, tp, ps, tr, ok):
    # scheduled km per route, day type and departure hour of each hop, and the mean trip length per route
    st = st.assign(k=st.groupby('trip_id').cumcount())
    for n, x in (('st3', st), ('tp3', tp), ('ps3', ps), ('tr3', tr), ('ok3', ok)):
        con.register(n, x)
    con.execute('''CREATE OR REPLACE TABLE hop AS SELECT st3.trip_id, CAST(st3.dep // 3600 % 24 AS INT) h,
        lead(ps3.dist_m) OVER (PARTITION BY st3.trip_id ORDER BY st3.k) - ps3.dist_m hop
        FROM st3 JOIN tp3 USING (trip_id) JOIN ps3 ON ps3.pattern_id = tp3.pattern_id AND ps3.k = st3.k''')
    sc = con.sql('''SELECT CAST(tr3.route_id AS BIGINT) route_id, ok3.daytype, h, sum(hop) / 1000 sched FROM hop
        JOIN tr3 USING (trip_id) JOIN ok3 USING (service_id) WHERE hop IS NOT NULL GROUP BY ALL''').df()
    lr = con.sql('''SELECT CAST(route_id AS BIGINT) route_id, avg(l) lr FROM (SELECT trip_id, sum(hop) / 1000 l FROM hop GROUP BY 1)
        JOIN tr3 USING (trip_id) GROUP BY 1''').df().set_index('route_id')['lr']
    return sc, lr


def sched_km(con, g):
    cal = pd.DataFrame(g['calendar'])
    ok = pd.DataFrame([(s, t) for t, d in cfg()['daytypes'].items() for s in gtfs.services({'calendar': cal}, d)], columns=['service_id', 'daytype'])
    GD.mkdir(parents=True, exist_ok=True)
    _, ps, tp = gtfs.patterns(g=g, w=GD)
    for f in ('patterns.parquet', 'pattern_stops.parquet'):
        (GD / f).unlink()
    return hopkm(con, g['stop_times'][['trip_id', 'dep']], tp[['trip_id', 'pattern_id']], ps[['pattern_id', 'k', 'dist_m']],
                 g['trips'][['trip_id', 'route_id', 'service_id']], ok)


def vehicles(con, gps, dt, hol_ok=None):
    # distinct vehicles pinged per IST day, by day type (counts only)
    v = con.sql(f'SELECT ist_day(t_utc) d, count(DISTINCT v) n FROM {gps} GROUP BY 1').df()
    v = v.assign(daytype=pd.to_datetime(v['d']).map(dt)).dropna()
    return {t: {'mean': round(float(x['n'].mean())), 'min': int(x['n'].min()), 'max': int(x['n'].max())} for t, x in v.groupby('daytype')}


def runtimes(g):
    # median scheduled run time per route, seconds
    st = g['stop_times'].groupby('trip_id')['dep'].agg(lambda x: x.max() - x.min()).rename('run').reset_index()
    return st.merge(g['trips'][['trip_id', 'route_id']], on='trip_id').astype({'route_id': int}).groupby('route_id')['run'].median()


def validate(tr, rbt, rbp, rbk, g, routes, hol):
    # weekday: trip-count ratio, GPS/scheduled duration ratio, and the stop-pass ratio, per route
    run = runtimes(g)
    w = tr[tr['d'].map(lambda d: daytype(d, hol)) == 'weekday']
    dur = w.groupby('route_id')['dur'].median()
    out = {}
    for r in routes:
        x, y, z = [b[(b['route_id'] == r) & (b['daytype'] == 'weekday')] for b in (rbt, rbp, rbk)]
        if x.empty or y.empty or z.empty or r not in dur:
            out[str(r)] = None
            continue
        c, du = x['obs'].sum() / x['sched'].sum(), float(dur[r] / run[r])
        out[str(r)] = {'bus_km_ratio_raw': round(z['obs'].sum() / z['sched'].sum(), 2), 'bus_km_ratio': round(float((z['ratio'] * z['sched']).sum() / z['sched'].sum()), 2), 'count_ratio': round(c, 2), 'duration_ratio': round(du, 2), 'count_x_duration': round(c * du, 2),
                       'pass_ratio_raw': round(y['obs'].sum() / y['sched'].sum(), 2),
                       'pass_ratio_shrunk': round(shrunk(y['obs'].sum(), y['sched'].sum(), 10), 2), 'pass_sched_per_day': round(y['sched'].sum() / y['ndays'].iloc[0], 1)}
    return out


def coverage(rbp, k):
    # reference stops with few observed passes per day make the ratio unreliable
    w = rbp[rbp['daytype'] == 'weekday'].groupby('route_id')[['obs', 'sched']].sum()
    nd = rbp[rbp['daytype'] == 'weekday']['ndays'].iloc[0]
    pd_ = w['obs'] / nd
    low = pd_ < k['pass_min_day']
    return {'routes': len(w), 'routes_below_min_passes_per_day': int(low.sum()), 'share_routes': round(float(low.mean()), 3),
            'share_weekday_sched_passes': round(float(w['sched'][low].sum() / w['sched'].sum()), 3), 'min_passes_per_day': k['pass_min_day'],
            'passes_per_day_q10_25_50_75_90': qs(pd_)}


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


def alias_evidence(con, g, days, k, win, gps):
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
    con.execute(f'''CREATE OR REPLACE TABLE gx AS SELECT upper(trim(v)) v, lat, lon, route_id, t_utc t FROM {gps}
        WHERE (upper(trim(v)), ist_day(t_utc)) IN (SELECT v, ist_day(t) FROM ta)''')
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


def gps():
    t0, k = time.time(), G()
    c3 = cfg()['gps']['days']
    days, hol = alldays(), set(cfg()['holidays'])
    r = {'days': len(days), 'detail_days': c3}
    con = db()
    r['convert_s'] = round(convert(con, days), 1)
    pq = lambda ds: 'read_parquet(%s)' % [(WORK / f'gps_{d}.parquet').as_posix() for d in ds]
    g = gtfs.load()
    routestops(con, g)
    con.execute(f'CREATE OR REPLACE VIEW gv0 AS SELECT * FROM {pq(c3)}')
    con.execute(f'CREATE OR REPLACE VIEW gva AS SELECT * FROM {pq(days)}')
    r['pings'] = one(con, 'SELECT count(*) FROM gva')[0]
    r['route_check'] = route_check(con, 'gv0', k)
    print('route check', r['route_check'], flush=True)
    if r['route_check']['ok']:
        tr = trips(con, 'gva')
        scs = sched(con, g)
        seen = set(tr['route_id'])
        rbt, sct, obt, dt = delivery(count_obs(tr), scs, seen, days, k, hol, 'trip_count')
        unc = {t: int(sct[sct['daytype'] == t]['sched'].sum() - a['sched'].sum()) for t, a in rbt.groupby('daytype')}
        refs = refstops(g, k)
        rbp, _, obp, _ = delivery(observed_passes(con, 'gva', refs, k), sched_stops(con, g, refs), seen, days, k, hol, 'stop_pass')
        print('passes done', round(time.time() - t0), flush=True)
        sk, lr = sched_km(con, g)
        rbk, _, obk, _ = delivery(obs_km(con, days, k), sk, seen, days, k, hol, 'bus_km', lr)
        print('km done', round(time.time() - t0), flush=True)
        rbk[COLS].round(4).to_csv(WORK / 'service_scale.csv', index=False)
        od = top_od()
        vh = vehicles(con, 'gva', dt)
        r['delivery_all_days'] = {'method': 'bus_km', 'unit': 'km', 'dtc_routes_seen': int(rbk['route_id'].nunique()),
                                  **delivery_stats(rbk, obk, dt, od, k, unc)}
        for t, x in vh.items():
            x['riders_per_bus_per_day_central'] = round(cfg()['ridership_daily']['central'] / x['mean'])
        r['vehicles_per_day'] = {'note': 'distinct vehicle ids with any ping that IST day; compare [R3] about 756 riders per bus per day (DTC)', **vh}
        r['cross_check_stop_pass'] = {'note': 'frequency at two reference stops per route', **delivery_stats(rbp, obp, dt, od, k, unc)}
        r['cross_check_trip_count'] = {'note': 'distinct (vehicle, trip_id); inflated by fragmented trips', **delivery_stats(rbt, obt, dt, od, k, unc)}
        r['fragmentation'] = {'note': 'GPS trips run much shorter than scheduled run times, so one bus journey is split into several (vehicle, trip_id) fragments and trip counts overstate service; see duration_ratio_all_routes_q10_25_50_75_90 and validation_weekday.duration_ratio'}
        r['validation_weekday'] = validate(tr, rbt, rbp, rbk, g, [2031, 2140, 2174, 1931, 1932, 2183, 1151], hol)
        r['pass_coverage'] = coverage(rbp, k)
        d = tr.assign(w=tr['d'].map(lambda x: daytype(x, hol) == 'weekday'))
        d = d[d['w']].groupby('route_id')['dur'].median() / runtimes(g)
        r['duration_ratio_all_routes_q10_25_50_75_90'] = qs(d.dropna())
        r['overlap'] = overlap(con, c3, 'gv0')
        b = boardings(con, c3, 'gv0', k['match_window_s'])
        tot = one(con, 'SELECT count(*) FROM tx')[0]
        r['boarding'] = board_stats(b, tot, k['board_m'])
        ev = propose(alias_evidence(con, g, days, k, k['match_window_s'], 'gva'), k)
        ev.to_csv(WORK / 'gps_alias_evidence.csv', index=False)
        r['alias_proposed'] = int(ev['propose'].sum())
    r['runtime_s'] = round(time.time() - t0, 1)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'gps_checks.json').write_text(json.dumps(r, indent=1, default=float), encoding='utf-8')
    print(json.dumps({x: y for x, y in r.items() if x not in ('overlap', 'cross_check_trip_count', 'cross_check_stop_pass')}, indent=1, default=float)[:7000])
    return r


def ensure_gps():
    # without the 16 GB archive, use the shipped GPS aggregates (built from the Oct 2026 feed; no vehicle data)
    f, shipped = OUT / 'gps_checks.json', ROOT / 'config' / 'gps_checks.json'
    if not f.exists() and shipped.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        f.write_bytes(shipped.read_bytes())
        print('gps: using shipped config/gps_checks.json (run `gps` with the archive to rebuild)')


# ---------- technical note: every number comes from the outputs ----------

TOK = re.compile(r'\{\{\s*([\w.]+)\s*(?::([^}]*))?\}\}')


def dig(d, path):
    for k in path.split('.'):
        d = d[int(k)] if isinstance(d, list) else d[k]
    return d


def fill(src, v):
    return TOK.sub(lambda m: format(dig(v, m[1]), (m[2] or '').strip()), src)  # a missing key raises


def table(rows, cols, fmt=None):
    fmt = fmt or {}
    out = ['| ' + ' | '.join(h for h, _ in cols) + ' |', '|' + '---|' * len(cols)]
    for r in rows:
        out.append('| ' + ' | '.join(format(r[k], fmt.get(k, '')) for _, k in cols) + ' |')
    return '\n'.join(out)


def derived(cov, gps):
    t = pd.read_parquet(WORK / 'tickets.parquet', columns=['pc', 'fare_class', 'f_zero'])
    L = cov['load']
    rung = gps['boarding']['by_rung_board']
    slab = cov['match']['fare_slab']['km_by_slab']
    return {
        'tickets': len(t), 'std_pct': 100 * t.loc[t['fare_class'] == 'std', 'pc'].sum() / t['pc'].sum(),
        'zero_fare': int(t['f_zero'].sum()),
        'app_share_pct': 100 * L['D_daily'] / L['ridership_daily']['central'],
        'bus_km_ratio': L['service']['weekday_bus_km'] / L['service']['weekday_bus_km_sched'],
        'rung_table': table([{'rung': k, **v} for k, v in rung.items()],
                            [('stop-match rule', 'rung'), ('tickets', 'n'), ('median m', 'median_m'),
                             ('within 500 m', 'within_500m')], {'n': ',', 'median_m': '.0f', 'within_500m': '.0%'}),
        'calib_table': table(L['calib_analysis'],
                             [('quantile', 'quantile'), ('crush x total', 'crush'), ('routes over cap', 'routes_over_cap'),
                              ('their riders %', 'routes_over_cap_pax_pct'), ('carried if cut %', 'carried_cut_only_pct'),
                              ('max carried at cap %', 'max_carried_pct')]),
        'slab_table': table(slab, [('AC', 'ac'), ('fare per passenger (Rs)', 'fare_pp'), ('passengers', 'pax'),
                                   ('km p10', 'km_p10'), ('km p50', 'km_p50'), ('km p90', 'km_p90')], {'pax': ','}),
    }


def note():
    ensure_gps()
    cov = json.loads((OUT / 'coverage.json').read_text(encoding='utf-8'))
    gps = json.loads((OUT / 'gps_checks.json').read_text(encoding='utf-8'))
    v = {'cov': cov, 'gps': gps, 'cfg': cfg(), 'x': derived(cov, gps)}
    src = (ROOT / 'docs' / 'TECH_NOTE.tmpl.md').read_text(encoding='utf-8')
    out = fill(src, v)
    (ROOT / 'docs' / 'TECH_NOTE.md').write_text(out, encoding='utf-8')
    print('note: docs/TECH_NOTE.md written')


# ---------- docs/CHECKS.md and charts: every number comes from the outputs ----------

IMG = ROOT / 'docs' / 'img'
DTC = {'weekday': '#2a78d6', 'saturday': '#eb6834', 'sunday': '#1baf7a'}
INK, GRID = '#222222', '#dddddd'
CELLS, TIX = f"'{(OUT / 'cells.parquet').as_posix()}'", f"'{(WORK / 'tickets.parquet').as_posix()}'"
DAILY = f"'{(WORK / 'daily.csv').as_posix()}'"


def q1(p):
    return f"'{p.as_posix()}'"


def sql(con, q):
    return con.sql(q).df()


def axes(title, xl, yl):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=100)
    ax.set_title(title, loc='left', fontsize=11, color=INK)
    ax.set_xlabel(xl, color=INK)
    ax.set_ylabel(yl, color=INK)
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#999999')
    ax.tick_params(colors=INK, labelsize=9)
    return fig, ax


def save(fig, name):
    import matplotlib.pyplot as plt
    IMG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(IMG / name)
    plt.close(fig)


def img(alt, name):
    return f'![{alt}](img/{name})'


def hourly(con, nd):
    # weekday mean passengers per hour from the ticket file, flagged days excluded
    h = sql(con, f'''SELECT slot // 2 h, sum(pc) / {nd} pax FROM {TIX} WHERE daytype = 'weekday'
        AND date NOT IN (SELECT CAST(date AS DATE) FROM read_csv({DAILY}) WHERE flag) GROUP BY 1 ORDER BY 1''')
    return h.set_index('h')['pax'].reindex(range(24), fill_value=0)


def hourly_chart(h, pk):
    fig, ax = axes('Digital passengers per weekday hour (mean of weekdays, IST)', 'hour of day', 'passengers per day')
    ax.plot(h.index, h.values, color=DTC['weekday'], lw=2, label='weekday')
    for x in pk:
        ax.annotate(f'{x}:00', (x, h[x]), textcoords='offset points', xytext=(0, 7), ha='center', fontsize=9, color=INK)
    ax.set_xticks(range(0, 24, 2))
    ax.legend(frameon=False)
    save(fig, 'weekday_hourly.png')


def daily_chart(d):
    fig, ax = axes('Digital passengers per day, October 2026, by day type', 'date', 'passengers per day')
    for t, c in DTC.items():
        x = d[d['daytype'] == t]
        ax.bar(pd.to_datetime(x['date']), x['pax'], color=c, width=0.7, label=t)
    ax.set_xticks(pd.to_datetime(d['date'][::3]))
    ax.set_xticklabels([str(x)[5:] for x in d['date'][::3]], fontsize=8)
    ax.set_ylim(0, d['pax'].max() * 1.15)
    ax.legend(frameon=False, ncol=3, loc='upper left')
    save(fig, 'daily_totals.png')


def rho_chart(r, hi):
    fig, ax = axes('Week-to-week Spearman rho per route-direction', 'rho', 'route-directions')
    ax.hist(r['rho'], bins=30, range=(-0.2, 1.0), color=DTC['weekday'], edgecolor='white', lw=0.5)
    ax.axvline(hi, color=INK, lw=1, ls='--')
    ax.annotate(f'high-confidence threshold {hi}', (hi, ax.get_ylim()[1] * 0.95), xytext=(-5, 0), textcoords='offset points',
                ha='right', fontsize=9, color=INK)
    save(fig, 'rho_hist.png')


def lf_chart(b):
    fig, ax = axes('Load factor of publishable cells (mean load per bus / seats)', 'load factor', 'share of cells %')
    ax.bar(b['lo'], b['pct'], width=b['w'] * 0.9, align='edge', color=DTC['weekday'])
    ax.axvline(1.0, color=INK, lw=1, ls='--')
    ax.annotate('1.0 = all seats taken', (1.0, ax.get_ylim()[1] * 0.95), xytext=(5, 0), textcoords='offset points', fontsize=9, color=INK)
    ax.annotate(f'last bar = {b["lo"].max():.0f} and above', (b['lo'].max(), ax.get_ylim()[1] * 0.3), xytext=(-5, 0),
                textcoords='offset points', ha='right', fontsize=9, color=INK)
    save(fig, 'lf_hist.png')


def lfhist(con, w, top):
    # bins of width w up to `top`; the last bin collects everything above
    b = sql(con, f'''SELECT least(floor(LF / {w}), {int(top / w)}) * {w} lo, count(*) c FROM {CELLS} WHERE flag IS NULL GROUP BY 1 ORDER BY 1''')
    return b.assign(pct=100 * b['c'] / b['c'].sum(), w=w)


def corridors(con, n):
    q = f'''SELECT base || dir route, from_name, to_name, sum(f) flow, sum(n) n FROM {CELLS} WHERE daytype = 'weekday' AND flag IS NULL
        GROUP BY route_id, base, dir, from_stop, to_stop, from_name, to_name ORDER BY flow DESC LIMIT {n}'''
    return table(sql(con, q).to_dict('records'), [('route', 'route'), ('from', 'from_name'), ('to', 'to_name'),
                 ('weekday digital flow/day', 'flow'), ('sampled pax-segments', 'n')], {'flow': ',.0f', 'n': ',.0f'})


def asym(con, am, pm, top):
    # UP share of segment-passenger flow on the busiest routes, in the AM and PM windows
    q = f'''WITH f AS (SELECT base, dir, sum(f) tot, sum(f) FILTER (WHERE slot BETWEEN {am[0] * 2} AND {am[1] * 2 - 1}) a,
          sum(f) FILTER (WHERE slot BETWEEN {pm[0] * 2} AND {pm[1] * 2 - 1}) p FROM {CELLS} WHERE daytype = 'weekday' AND flag IS NULL
          AND dir IN ('UP', 'DOWN') GROUP BY 1, 2),
        b AS (SELECT base, sum(tot) tot, sum(a) FILTER (WHERE dir = 'UP') au, sum(a) FILTER (WHERE dir = 'DOWN') ad,
          sum(p) FILTER (WHERE dir = 'UP') pu, sum(p) FILTER (WHERE dir = 'DOWN') pd FROM f GROUP BY 1 HAVING count(*) = 2
          ORDER BY tot DESC LIMIT {top})
        SELECT base, au / (au + ad) am_up, pu / (pu + pd) pm_up FROM b ORDER BY tot DESC'''
    r = sql(con, q)
    r['peak_am'] = (r['am_up'] >= .5).map({True: 'UP', False: 'DOWN'})
    r['peak_pm'] = (r['pm_up'] >= .5).map({True: 'UP', False: 'DOWN'})
    flip = int((r['peak_am'] != r['peak_pm']).sum())
    t = table(r.to_dict('records'), [('route', 'base'), ('UP share AM', 'am_up'), ('UP share PM', 'pm_up'),
              ('heavier AM', 'peak_am'), ('heavier PM', 'peak_pm')], {'am_up': '.0%', 'pm_up': '.0%'})
    return t, flip, len(r)


def rhos(con):
    return sql(con, f'''SELECT route_id, any_value(base || dir) route, max(rho) rho, sum(n) n FROM {CELLS} WHERE flag IS NULL GROUP BY 1''')


def poor(con, od, k):
    # per base route: share of passengers placed end to end; worst among the top routes by passengers
    q = f'''SELECT base, sum(pc) pax, sum(pc) FILTER (WHERE tid IN (SELECT tid FROM {od})) ok FROM {TIX} WHERE base IS NOT NULL
        GROUP BY 1 ORDER BY pax DESC LIMIT {k}'''
    r = sql(con, q).assign(share=lambda x: x['ok'] / x['pax']).sort_values('share').head(10)
    return table(r.to_dict('records'), [('route', 'base'), ('passengers', 'pax'), ('placed in order', 'share')], {'pax': ',.0f', 'share': '.1%'})


def nights(con):
    return sql(con, f'''SELECT slot // 2 h, count(*) cells, avg((confidence = 'low')::INT) low, avg(n) n FROM {CELLS}
        WHERE flag IS NULL GROUP BY 1 ORDER BY 1''')


def verdict(L):
    c = L['calib_analysis']
    lo, hi = min(c, key=lambda x: x['routes_over_cap_pax_pct']), max(c, key=lambda x: x['routes_over_cap_pax_pct'])
    return (f"Scaling every over-capacity route down to capacity was analysed and not applied (calibration switch: {L['calib']['on']}). "
            f"Even the mildest setting (quantile {lo['quantile']}, crush {lo['crush']}) flags {lo['routes_over_cap']} routes carrying "
            f"{lo['routes_over_cap_pax_pct']}% of riders, and the strictest (quantile {hi['quantile']}, crush {hi['crush']}) flags "
            f"{hi['routes_over_cap']} routes carrying {hi['routes_over_cap_pax_pct']}%, which is too much of the network to treat as noise.")


def build(con, cov, gp, dy):
    L, M, k = cov['load'], cov['match'], cfg()
    am, pm = k['periods']['am'], k['periods']['pm']
    nd = L['n_days']
    wd = int(((dy['daytype'] == 'weekday') & ~dy['flag']).sum())
    h = hourly(con, wd)
    pa, pp = int(h.loc[am[0]:am[1] - 1].idxmax()), int(h.loc[pm[0]:pm[1] - 1].idxmax())
    mid = h.loc[am[1]:pm[0] - 1]
    hourly_chart(h, [pa, pp])
    daily_chart(dy)
    t = sql(con, f'''SELECT count(*) rows, sum(pc) pax, sum(pc) FILTER (WHERE fare_class = 'std') std,
        sum(pc) FILTER (WHERE fare_class = 'ncr') ncr, avg((v IS NULL OR v = 'NULL')::INT) nullv FROM {TIX}''').iloc[0]
    tot = dy.groupby('daytype')['pax'].agg(['mean', 'count']).reindex(list(DTC)).reset_index()
    hi = k['confidence']['high_rho']
    rr = rhos(con).dropna(subset=['rho'])
    rho_chart(rr, hi)
    un = rr[rr['rho'] < hi].sort_values('n', ascending=False)
    lf_chart(lfhist(con, 0.25, 5))
    at, flip, nb = asym(con, am, pm, 20)
    nt = nights(con)
    worst3 = nt.sort_values('low', ascending=False).head(3)
    dev = dy.assign(a=dy['dev'].abs()).sort_values('a', ascending=False).head(5)
    od, g, b = q1(WORK / 'od.parquet'), gp['delivery_all_days'], gp['boarding']
    x = derived(cov, gp)
    dl = [{'t': t_, 'days': g[t_]['days'], 'ratio': g[t_]['total_ratio'], 'q': ' / '.join(f'{v:.2f}' for v in g[t_]['q10_25_50_75_90']),
           'b08': g[t_]['share_below_0.8'], 'veh': gp['vehicles_per_day'][t_]['mean'], 'rpb': gp['vehicles_per_day'][t_]['riders_per_bus_per_day_central']}
          for t_ in ('weekday', 'saturday', 'sunday')]
    ov, rc = gp['overlap'], gp['route_check']
    S = []
    S.append('# CHECKS\n\nGenerated by `python -m seatcast.run checks` from `data/out/` and `data/work/`. Nothing here is typed by hand.\n')
    S.append(f'''## 1. Coverage

| measure | value |
|---|---|
| ticket rows | {int(t['rows']):,} |
| passengers | {int(t['pax']):,} |
| days | {len(dy)} ({nd['weekday']} weekdays, {nd['saturday']} Saturdays, {nd['sunday']} Sundays and holidays) |
| passengers on discounted standard slabs | {100 * t['std'] / t['pax']:.1f}% |
| passengers on NCR fares | {100 * t['ncr'] / t['pax']:.1f}% |
| rows with no vehicle number | {100 * t['nullv']:.1f}% |
| route matched | {M['route_matched_pct']}% of passengers |
| both stops matched | {M['both_stops_pct_of_routed']}% of routed passengers |
| board before alight | {M['in_order_pct_of_both']}% of those |
| usable end to end | {M['usable_pct_of_all']}% of passengers |
| represented in flows (after imputing partial tickets) | {L['represent']['represented_pct']}% |
| agency split of usable passengers | DTC {M['agency_pct_of_usable']['DTC']}%, DIMTS {M['agency_pct_of_usable']['DIMTS']}% |
''')
    S.append(f'''## 2. Expansion

D_daily (mean digital passengers per day) = {L['D_daily']:,.0f}. E low / central / high = {L['E']['low']} / {L['E']['central']} / {L['E']['high']}.
Each ticket passenger stands for about {L['E']['central']:.0f} riders of the {L['ridership_daily']['central']:,} per day in the central estimate (high {L['ridership_daily']['high']:,}); the file is {x['app_share_pct']:.1f}% of that.
''')
    S.append(f'''## 3. Weekday hourly profile

{img('Weekday passengers per hour', 'weekday_hourly.png')}

Morning peak {pa}:00 ({h[pa]:,.0f} passengers per day), evening peak {pp}:00 ({h[pp]:,.0f}). Quietest midday hour {int(mid.idxmin())}:00 ({mid.min():,.0f}). Peak-to-midday ratio: morning {h[pa] / mid.min():.1f}, evening {h[pp] / mid.min():.1f}.
''')
    S.append(f'''## 4. Daily totals by day type

{img('Daily passengers coloured by day type', 'daily_totals.png')}

{table(tot.to_dict('records'), [('day type', 'daytype'), ('days', 'count'), ('mean passengers per day', 'mean')], {'mean': ',.0f', 'count': 'd'})}

Weekday cells carry more flow than Sunday cells in {L['weekday_gt_sunday_pct_of_shared_cells']}% of the cells both day types share. Holidays count as Sundays.
''')
    S.append(f'''## 5. Busiest corridors

Top 15 segments by weekday daily digital flow (before expansion).

{corridors(con, 15)}
''')
    S.append(f'''## 6. Directional asymmetry

UP share of flow on the top {nb} routes by weekday flow, morning window {am[0]}:00-{am[1]}:00 against evening window {pm[0]}:00-{pm[1]}:00. The heavier direction differs between the windows on {flip} of {nb} routes.

{at}
''')
    S.append(f'''## 7. Week-to-week stability

{img('Distribution of week-to-week rho per route', 'rho_hist.png')}

{len(rr)} route-directions have a rho. Median {rr['rho'].median():.2f}; {len(un)} ({100 * len(un) / len(rr):.0f}%) are below the high-confidence threshold of {hi}. The 15 busiest unstable routes:

{table(un.head(15).to_dict('records'), [('route', 'route'), ('rho', 'rho'), ('sampled pax-segments', 'n')], {'rho': '.2f', 'n': ',.0f'})}
''')
    S.append(f'''## 8. Anomalous days

Days flagged (beyond the configured deviation from the same-weekday median): {int(dy['flag'].sum()) or 'none'}. Largest deviations:

{table(dev.to_dict('records'), [('date', 'date'), ('day type', 'daytype'), ('passengers', 'pax'), ('deviation', 'dev')], {'pax': ',.0f', 'dev': '+.1%'})}
''')
    S.append(f'''## 9. Plausibility

{img('Load factor distribution', 'lf_hist.png')}

Publishable cells: {L['cells_publishable']:,} of {L['cells']:,}. Load factor p10 / p50 / p90 / p99 = {L['LF_quantiles_publishable']['p10']} / {L['LF_quantiles_publishable']['p50']} / {L['LF_quantiles_publishable']['p90']} / {L['LF_quantiles_publishable']['p99']}.
Over seats: {L['over_seats_pct']}% of cells. Over total capacity: {L['over_total_pct']}%. Censored at {k['censor_factor']} x total capacity: {L['censored_pct_of_cells']}% of cells (these show as the top load factor, which is the censor cap and explains the repeated top values below).

Routes with most censored cells:

{table(L['censored_routes_top'][:10], [('route', 'base'), ('dir', 'dir'), ('censored cells', 'cells'), ('sampled pax-segments', 'n')], {'n': ',.0f'})}

Ten most crowded route-hours by standee-minutes:

{table(L['top10_route_hours_by_standee_min'], [('route', 'route'), ('day type', 'daytype'), ('hour', 'hour'), ('standee-min', 'standee_min'), ('LF', 'LF'), ('sampled pax', 'n'), ('stretch', 'stretch')], {'standee_min': ',.0f', 'n': ',.0f'})}
''')
    S.append(f'''## 10. Where estimates are weakest

- Low-n cells: {L['cells_by_flag']['low_n']:,} of {L['cells']:,} cells have fewer than {k['min_cell_n']} sampled passengers and are shown as limited data. Of the publishable cells, confidence is high {L['confidence_share_pct']['high']}%, medium {L['confidence_share_pct']['medium']}%, low {L['confidence_share_pct']['low']}%.
- Schedule gaps: {L['schedule_gap_cells']:,} cells carry passengers but no scheduled bus ({L['schedule_gap_pax_pct']}% of passengers).
- Hours with the highest low-confidence share: {', '.join(f"{int(r.h)}:00 ({100 * r.low:.0f}%)" for r in worst3.itertuples())}.

Ten worst-placed routes among the 100 busiest by passengers:

{poor(con, od, 100)}

Per hour of day, publishable cells:

{table(nt.to_dict('records'), [('hour', 'h'), ('cells', 'cells'), ('low confidence', 'low'), ('mean sampled pax-segments', 'n')], {'cells': ',', 'low': '.0%', 'n': '.1f'})}
''')
    S.append(f'''## 11. GPS ground truth

Route check on {rc['n']:,} sampled pings: {rc['within']:.1%} within {k['gps']['route_m']} m of a stop of their own route, against {rc['control_within']:.1%} for another route (median {rc['median_m']:.0f} m against {rc['control_median_m']:,.0f} m).

Vehicle overlap on the {len(gp['detail_days'])} detail days: {ov['share_passengers_in_gps']:.1%} of ticket passengers (with a known vehicle) rode a vehicle that is in the DTC GPS feed.

Where was the bus at purchase? {b['matched']:,} tickets matched to a ping (median lag {b['lag_median_s']:.0f} s). Distance to the matched boarding stop: median {b['board']['median_m']:.0f} m, {b['board']['within_500m']:.0%} within 500 m. Distance to the alighting stop: median {b['alight']['median_m']:,.0f} m, {b['alight']['within_500m']:.1%} within 500 m.

{x['rung_table']}

Delivered service (observed bus-km against scheduled), all days of October:

{table(dl, [('day type', 't'), ('days', 'days'), ('delivered / scheduled', 'ratio'), ('route-band q10/25/50/75/90', 'q'), ('share below 0.8', 'b08'), ('vehicles pinged per day', 'veh'), ('riders per bus per day (central)', 'rpb')], {'b08': '.0%', 'veh': ',', 'rpb': ','})}
''')
    S.append(f'''## 12. The rejected calibration

{x['calib_table']}

{verdict(L)}
''')
    return '\n'.join(S)


def run():
    ensure_gps()
    t0 = time.time()
    con = duckdb.connect()
    con.execute("SET memory_limit='4GB'; SET threads=4")
    cov = json.loads((OUT / 'coverage.json').read_text(encoding='utf-8'))
    gp = json.loads((OUT / 'gps_checks.json').read_text(encoding='utf-8'))
    dy = pd.read_csv(WORK / 'daily.csv')
    md = build(con, cov, gp, dy)
    (ROOT / 'docs' / 'CHECKS.md').write_text(md, encoding='utf-8')
    print('checks: docs/CHECKS.md written', round(time.time() - t0, 1), 's')
