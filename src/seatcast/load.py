import json
import math
import time

import duckdb
import numpy as np
import pandas as pd

from seatcast import OUT, ROOT, WORK, cfg, gtfs, service
from seatcast.clean import parse_route

P3 = service.P3
NO = 'NO_DATA_AVAILABLE'
LEVELS = ['MANY_SEATS_AVAILABLE', 'FEW_SEATS_AVAILABLE', 'STANDING_ROOM_ONLY', 'CRUSHED_STANDING_ROOM_ONLY']
erf = np.vectorize(math.erf, otypes=[float])

# cell stats pool the slot and its neighbours (slot_window each side): daily flows and scheduled buses alike
STATS = '''
WITH w AS (
  SELECT route_id, s0, s1, slot + j slot, daytype, date, SUM(pax) pax, SUM(n) n
  FROM flows, (SELECT unnest(range(-$w, $w + 1)) j)
  WHERE date NOT IN (SELECT date FROM bad) AND slot + j BETWEEN 0 AND $last
  GROUP BY ALL)
SELECT w.route_id, s0, s1, slot, w.daytype, SUM(pax) / d.nd f, SUM(n) n, COUNT(*) ndata,
       SUM(pax * pax) / d.nd - pow(SUM(pax) / d.nd, 2) var, SUM(pax) / SUM(n) scale
FROM w JOIN nd d USING (daytype)
GROUP BY w.route_id, s0, s1, slot, w.daytype, d.nd
'''

SVW = '''
SELECT route_id, s0, s1, daytype, slot + j slot, SUM(n) N, SUM(n * sec) / SUM(n) / 60 seg_min
FROM sv, (SELECT unnest(range(-$w, $w + 1)) j)
WHERE slot + j BETWEEN 0 AND $last
GROUP BY ALL
'''

HOURLY = '''
SELECT route_id, s0, s1, f.daytype, CAST(slot // $h AS INT) h, SUM(pax) / d.nd f, SUM(n) n
FROM flows f JOIN nd d USING (daytype)
WHERE date NOT IN (SELECT date FROM bad)
GROUP BY route_id, s0, s1, f.daytype, h, d.nd
'''

CAP = '''
WITH m AS (
  SELECT route_id, SUM(pc * c.seats) / SUM(pc) seats, SUM(pc * c.total) / SUM(pc) total
  FROM od JOIN cap c USING (series) GROUP BY 1),
a AS (SELECT route_id, coalesce(SUM(pc) FILTER (WHERE ac), 0) >= coalesce(SUM(pc) FILTER (WHERE NOT ac), 0) ac
      FROM od GROUP BY 1)
SELECT a.route_id, a.ac, m.seats, m.total FROM a LEFT JOIN m USING (route_id)
'''

PAIRS = '''
SELECT p.route_id, s.s0, s.s1, s.pattern_id, s.k FROM seg s JOIN pat p USING (pattern_id)
QUALIFY row_number() OVER (PARTITION BY p.route_id, s.s0, s.s1 ORDER BY p.canonical DESC, p.n_trips DESC,
                           s.pattern_id, s.k) = 1
'''


def p_seat(m, seats, cv):
    # P(load < seats) for a lognormal load with mean m and coefficient of variation cv
    m, seats, cv = (np.asarray(x, float) for x in (m, seats, cv))
    s2 = np.log1p(cv * cv)
    mu = np.log(np.where(m > 0, m, 1)) - s2 / 2
    p = 0.5 * (1 + erf((np.log(seats) - mu) / np.sqrt(2 * s2)))
    p = np.where(m > 0, p, 1.0)
    return float(p) if p.ndim == 0 else p


def level(L, seats, total):
    c = cfg()['levels']
    lf = np.asarray(L, float) / np.asarray(seats, float)
    i = np.select([lf < c['many'], lf < c['few'], lf < np.asarray(total) / np.asarray(seats)], [0, 1, 2], 3)
    return np.where(np.isnan(lf), None, np.array(LEVELS, object)[i])


def expansion(con):
    pax, nd = con.execute('SELECT SUM(pc), COUNT(DISTINCT date) FROM tickets').fetchall()[0]
    c = cfg()
    d = pax / nd
    e = {k: v / d for k, v in c['ridership_daily'].items()}
    e['low'] = e['central'] * c['e_low_factor']
    return d, e


def days():
    d = pd.read_csv(WORK / 'daily.csv', parse_dates=['date'])
    ok = d[~d['flag']]
    return ok.groupby('daytype').size().rename('nd').reset_index(), d.loc[d['flag'], ['date']]


def win():
    q = cfg()['slot_min']
    return {'w': cfg()['slot_window'], 'last': 24 * 60 // q - 1}


def stats(con):
    s = con.execute(STATS, win()).df()
    s['cv_day'] = np.where(s['ndata'] < 3, 0.5, np.sqrt(s['var'].clip(lower=0)) / s['f'])
    return s.drop(columns='var')


def rho(con):
    # mean pairwise Spearman between weeks of weekday flows over segment x hour, per route
    h = cfg()['slot_min'] / 60
    w = con.execute(f'''SELECT route_id, s0, s1, CAST(floor(slot * {h}) AS INT) h, week, SUM(pax) x FROM flows
        WHERE daytype = 'weekday' AND week IS NOT NULL AND date NOT IN (SELECT date FROM bad)
        GROUP BY ALL''').df()
    p = w.pivot_table(index=['route_id', 's0', 's1', 'h'], columns='week', values='x', fill_value=0)

    def r(d):
        if len(d) < 3:
            return np.nan
        c = d.corr('spearman').to_numpy()
        c = c[np.triu_indices(len(c), 1)]
        c = c[~np.isnan(c)]
        return c.mean() if c.size else np.nan
    return p.groupby(level=0).apply(r).rename('rho').reset_index()


def capacity(con):
    c = cfg()['capacity_default']
    con.register('cap', pd.read_csv(ROOT / 'config' / 'series_capacity.csv'))
    k = con.sql(CAP).df()
    for x in ['seats', 'total']:
        k[x] = k[x].fillna(k['ac'].map({True: c['ac'][x], False: c['nonac'][x]})).astype(float)
    return k[['route_id', 'seats', 'total']]


def meta(g):
    r = g['routes'][['route_id', 'route_short_name', 'agency_id']].copy()
    p = r['route_short_name'].map(lambda x: parse_route(x) or (x, '', ''))
    r['base'], r['dir'] = p.str[0], p.str[1]
    return r.rename(columns={'route_short_name': 'route', 'agency_id': 'agency'})


def model(c, E):
    k = cfg()
    c['N'] = c['N'].fillna(0).astype(float)
    run2, n = k['run_cv'] ** 2, k['min_cell_n']
    N = c['N_obs'].where(c['N'] > 0)
    top = k['censor_factor'] * c['total']
    c['censored'] = (c['N'] > 0) & (c['n'] >= n) & (E['central'] * c['calib'] * c['f'] / N > top)
    for x, e in [('L_low', E['low']), ('L', E['central']), ('L_high', E['high'])]:
        c[x] = np.minimum(e * c['calib'] * c['f'] / N, top)  # censored: well sampled, magnitude uncertain
    c['LF'] = c['L'] / c['seats']
    c['cv'] = np.sqrt(1 / c['n'].clip(lower=1) + c['cv_day'] ** 2 + run2)
    c['p_seat'] = p_seat(c['L'].fillna(0), c['seats'], c['cv'])
    for x in ['low', '', 'high']:
        c['level' + (x and '_' + x)] = level(c['L' + (x and '_' + x)], c['seats'], c['total'])
    c['flag'] = np.select([c['N'] == 0, c['n'] < n], ['gap', 'low_n'], None)
    q = k['confidence']
    c['confidence'] = np.select([c['censored'], (c['n'] >= q['high_n']) & (c['rho'] >= q['high_rho']),
                                 c['n'] >= q['med_n']], ['low', 'high', 'medium'], 'low')
    bad = c['flag'].notna()
    c.loc[bad, ['L_low', 'L', 'L_high', 'LF', 'p_seat']] = np.nan
    c.loc[bad, ['level_low', 'level_high', 'confidence']] = None
    c.loc[bad, 'level'] = NO
    return c


def ratios(use):
    # GPS delivery ratio (observed / scheduled) per route, day type and hour band; None = timetable as is
    # fresh from `run gps` if it ran, else the shipped aggregate (built from the Oct 2026 GPS; no vehicle data)
    f = next((x for x in (WORK / 'service_scale.csv', ROOT / 'config' / 'service_scale.csv') if x.exists()), None)
    if not use or f is None:
        return None
    r = pd.read_csv(f, dtype={'route_id': str})[['route_id', 'daytype', 'band', 'ratio']]
    return r.assign(ratio=r['ratio'].clip(*cfg()['gps']['ratio_clamp']))


def observe(c, r, h):
    # N_obs = N x ratio of the route, day type and band of hour column h; no row means ratio 1
    if r is None:
        return c.assign(N_obs=c['N'], ratio=np.nan)
    b = np.array(cfg()['gps']['bands'][:-1])
    c = c.assign(band=b[np.searchsorted(b, c[h].to_numpy(), 'right') - 1])
    c = c.merge(r, on=['route_id', 'daytype', 'band'], how='left').drop(columns='band')
    return c.assign(N_obs=c['N'] * c['ratio'].fillna(1))


def calibrate(c, D, E, k):
    # per-route E multiplier m = min(u, h). h caps the route's q-quantile load at crush x total; the common u >= 1
    # lifts the rest so riders on judged routes stay sum(D). If even every route at its cap can't carry them, u = 1
    # (cap only) and the shortfall is reported. Routes with no cells to judge keep m = 1. c: route_id, f, N_obs, total
    lim = c.groupby('route_id')['total'].first() * k['crush_factor']
    q = (E * c['f'] / c['N_obs']).groupby(c['route_id']).quantile(k['quantile'])
    h = (lim / q).reindex(D.index)
    ok = h.notna()

    def carried(u):
        return (np.minimum(u, h[ok]) * D[ok]).sum()
    u, need = 1.0, D[ok].sum()
    if carried(1.0) < need <= carried(h.max()):
        lo, hi = 1.0, h.max()
        for _ in range(60):
            u = (lo + hi) / 2
            lo, hi = (u, hi) if carried(u) < need else (lo, u)
        u = hi
    return np.minimum(u, h).fillna(1.0), (h < u).fillna(False)


def hourly(con, E, r, m):
    # route x segment x hour x day type: all sampled flow against all observed buses in the hour
    h = 60 // cfg()['slot_min']
    x = con.execute(HOURLY, {'h': h}).df()
    s = con.execute('SELECT route_id, s0, s1, daytype, CAST(slot // $h AS INT) h, SUM(n) N, '
                    'SUM(n * sec) / SUM(n) / 60 seg_min FROM sv GROUP BY ALL', {'h': h}).df()
    x = observe(x.merge(s, on=['route_id', 's0', 's1', 'daytype', 'h']), r, 'h')
    x['E'] = E * m.reindex(x['route_id']).fillna(1).to_numpy()
    x['L'] = x['E'] * x['f'] / x['N_obs']
    return x


def censor(x):
    return x.assign(L=np.minimum(x['L'], cfg()['censor_factor'] * x['total']))


def operator(x, cap, names):
    k = cfg()
    x = x.merge(cap, on='route_id')
    x = censor(x[x['n'] >= k['min_cell_n']])
    N = x['N_obs']
    x['st'] = N * (x['L'] - x['seats']).clip(lower=0) * x['seg_min']
    x['st1'] = (N + 1) * (x['L'] * N / (N + 1) - x['seats']).clip(lower=0) * x['seg_min']
    g = ['route_id', 'daytype', 'h']
    m = x.loc[x.groupby(g)['f'].idxmax()].set_index(g)
    o = x.groupby(g)[['st', 'st1']].sum()
    o['P_max'] = m['E'] * m['f']
    o['F_sched'], o['F_obs'] = m['N'], m['N_obs']
    o['F_req'] = np.ceil(o['P_max'] / (k['desired_load_factor'] * m['total'])).astype(int)
    o['gap'] = (o['F_req'] - o['F_sched']).clip(lower=0)
    o['gap_obs'] = (o['F_req'] - o['F_obs']).clip(lower=0)
    o['standee_min'] = o['st']
    o['plus1_benefit'] = o['st'] - o['st1']
    o['L_max'], o['LF_max'], o['n_max'] = m['L'], m['L'] / m['seats'], m['n']
    o['max_from'], o['max_to'] = m['s0'].map(names), m['s1'].map(names)
    return o.drop(columns=['st', 'st1']).reset_index().rename(columns={'h': 'hour'})


def profiles(x, pairs, cap, rm, names):
    x = x[x['n'] >= cfg()['min_cell_n']].merge(pairs[pairs['pattern_id'].str.endswith(':0')], on=['route_id', 's0', 's1'])
    by = dict(tuple(x.groupby('route_id')))
    out = {}
    for r, ps in pairs[pairs['pattern_id'].str.endswith(':0')].sort_values('k').groupby('route_id'):
        if r not in by:
            continue
        m = rm.loc[r]
        d = {'route': m['route'], 'base': m['base'], 'dir': m['dir'],
             'stops': [names[s] for s in ps['s0']] + [names[ps['s1'].iloc[-1]]],
             'seats': round(float(cap.loc[r, 'seats']), 1), 'total': round(float(cap.loc[r, 'total']), 1), 'L': {}}
        v = by[r].pivot_table(index=['daytype', 'h'], columns='k', values='L', aggfunc='first')
        for (t, h), row in v.reindex(columns=ps['k']).round(1).iterrows():
            d['L'].setdefault(t, {})[str(h)] = [None if math.isnan(q) else q for q in row.to_numpy()]
        out[r] = d
    return out


def geometry(pairs, ps, pat, tp, g):
    # one LineString per (route, s0, s1), cut from the shape between the two stops' along-shape positions
    sh = dict(tuple(g['shapes'].groupby('shape_id'))) if g['shapes'] is not None else {}
    shp = tp.groupby('pattern_id')['shape_id'].first()
    src = pat.set_index('pattern_id')['dist_src']
    feats, byp = [], dict(tuple(ps.groupby('pattern_id')))
    for p, z in pairs.groupby('pattern_id'):
        s = byp[p].set_index('k')
        cut = cutter(s, sh.get(shp.get(p)) if src.get(p) == 'shape' else None)
        for r in z.itertuples():
            a, b = s.loc[r.k], s.loc[r.k + 1]
            line = cut(r.k) if cut else None
            line = [[round(a['lon'], 5), round(a['lat'], 5)]] + (line or []) + [[round(b['lon'], 5), round(b['lat'], 5)]]
            feats.append({'type': 'Feature', 'geometry': {'type': 'LineString', 'coordinates': line},
                          'properties': {'route_id': r.route_id, 'k': int(r.k), 'from_stop': r.s0, 'to_stop': r.s1}})
    return {'type': 'FeatureCollection', 'features': feats}


def cutter(s, sh, step=25):
    if sh is None:
        return None
    d0 = gtfs.snap(s['lat'].to_numpy()[:1], s['lon'].to_numpy()[:1], sh)
    if d0 is None:
        return None
    d = s['dist_m'].to_numpy() + d0[0]
    x, y, t = sh['shape_pt_lon'].to_numpy(), sh['shape_pt_lat'].to_numpy(), sh['shape_dist_traveled'].to_numpy()

    def cut(k):
        i, j = np.searchsorted(t, d[k], 'right'), np.searchsorted(t, d[k + 1], 'left')
        if j <= i:
            return []
        keep = np.flatnonzero(np.diff(np.floor(t[i:j] / step), prepend=-1) > 0) + i
        return [[round(float(x[q]), 5), round(float(y[q]), 5)] for q in keep]
    return cut


def read(con, name, f, cols='*', tries=5):
    for i in range(tries):
        try:
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT {cols} FROM read_parquet('{f.as_posix()}')")
            return
        except duckdb.Error:
            if i == tries - 1:
                raise
            time.sleep(10)


def run(gps=None, cal=None, write=True):
    t0 = time.time()
    k = cfg()
    gps = k.get('service_from_gps', False) if gps is None else gps
    cal = k['calib'].get('enabled', False) if cal is None else cal
    con = duckdb.connect(config={'memory_limit': '4GB', 'threads': 4})
    for n, f, cols in [('flows', WORK / 'flows.parquet', '*'), ('od', WORK / 'od.parquet', 'route_id, series, ac, pc'),
                       ('tickets', WORK / 'tickets.parquet', 'pc, date'),
                       ('seg0', P3 / 'pattern_stops.parquet', 'pattern_id, k, stop_id, lat, lon, dist_m'),
                       ('pat', P3 / 'patterns.parquet', '*'), ('sv', WORK / 'service.parquet', '*'),
                       ('scale', WORK / 'scale.parquet', '*')]:
        read(con, n, f, cols)
    con.execute('CREATE TABLE seg AS SELECT pattern_id, CAST(k AS INT) k, stop_id s0, '
                'lead(stop_id) OVER (PARTITION BY pattern_id ORDER BY k) s1 FROM seg0')
    con.execute('DELETE FROM seg WHERE s1 IS NULL')
    nd, bad = days()
    con.register('nd', nd)
    con.register('bad', bad)
    D, E = expansion(con)
    g = gtfs.load(w=P3)
    names = g['stops'].set_index('stop_id')['stop_name']
    rm = meta(g).set_index('route_id')
    cap = capacity(con)
    pairs = con.sql(PAIRS).df()
    con.register('pairs', pairs)
    r = ratios(gps)
    c = stats(con)
    c = c.merge(con.execute(SVW, win()).df(), on=['route_id', 's0', 's1', 'slot', 'daytype'], how='left')
    c['N'] = c['N'].fillna(0).astype(float)
    c = observe(c.assign(hr=c['slot'] * k['slot_min'] // 60), r, 'hr').drop(columns='hr')
    c = c.merge(cap, on='route_id', how='left').merge(rho(con), on='route_id', how='left')
    Dr = con.sql(f"SELECT route_id, SUM(pax) / {nd['nd'].sum()} d FROM scale WHERE route_id IS NOT NULL "
                 'GROUP BY 1').df().set_index('route_id')['d']
    m, fixed = pd.Series(1.0, index=Dr.index), pd.Series(False, index=Dr.index)
    if cal:
        m, fixed = calibrate(c[(c['n'] >= k['min_cell_n']) & (c['N'] > 0)], Dr, E['central'], k['calib'])
    c['calib'] = m.reindex(c['route_id']).fillna(1).to_numpy()
    c = model(c, E)
    c = c.merge(pairs, on=['route_id', 's0', 's1'], how='left').merge(rm[['base', 'dir']], left_on='route_id',
                                                                      right_index=True, how='left')
    c['from_name'], c['to_name'] = c['s0'].map(names), c['s1'].map(names)
    c = c.rename(columns={'s0': 'from_stop', 's1': 'to_stop'})
    x = hourly(con, E['central'], r, m)
    op = operator(x, cap, names).merge(rm[['route', 'base', 'dir']], left_on='route_id', right_index=True, how='left')
    cov = report(c, op, x, D, E, nd, bad, g)
    cov['service'] = service_note(c, r, con, x)
    cov['calib'] = calib_note(m, fixed, Dr, E['central'], rm, cal)
    cov['calib_analysis'] = feasibility(c[(c['n'] >= k['min_cell_n']) & (c['N'] > 0)], Dr, E['central'])
    if not write:
        return c, op, cov
    OUT.mkdir(parents=True, exist_ok=True)
    public(c).to_parquet(OUT / 'cells.parquet', index=False, compression='zstd')
    op.to_parquet(OUT / 'operator.parquet', index=False)
    prof = profiles(x, pairs, cap.set_index('route_id'), rm, names)
    (OUT / 'route_profiles.json').write_text(json.dumps(prof, separators=(',', ':')), encoding='utf-8')
    used = pairs.merge(c[['route_id', 'from_stop', 'to_stop']].drop_duplicates()
                       .rename(columns={'from_stop': 's0', 'to_stop': 's1'}), on=['route_id', 's0', 's1'])
    ps, pat = con.table('seg0').df(), con.table('pat').df()
    tp = pd.read_parquet(P3 / 'trip_pattern.parquet')
    gj = geometry(used, ps, pat, tp, g)
    (OUT / 'segments.geojson').write_text(json.dumps(gj, separators=(',', ':')), encoding='utf-8')
    merge_cov(cov)
    print(json.dumps(cov, indent=2, default=str))
    print(f'load: {time.time() - t0:.0f}s')


KM = '''
SELECT p.route_id, p.s0, p.s1, (b.dist_m - a.dist_m) / 1000 km FROM pairs p
JOIN seg0 a ON a.pattern_id = p.pattern_id AND a.k = p.k
JOIN seg0 b ON b.pattern_id = p.pattern_id AND b.k = p.k + 1
'''


def service_note(c, r, con, x):
    # share of cells / passengers without a GPS ratio; weekday passenger-km per bus-km as a sanity check
    s = c[c['N'] > 0]
    d = con.sql(KM).df()
    h = 60 // cfg()['slot_min']
    w = x[x['daytype'] == 'weekday'].merge(d, on=['route_id', 's0', 's1'])
    sv = con.sql(f"SELECT route_id, s0, s1, daytype, CAST(slot // {h} AS INT) h, SUM(n) N FROM sv "
                 "WHERE daytype = 'weekday' GROUP BY ALL").df()
    sv = observe(sv, r, 'h').merge(d, on=['route_id', 's0', 's1'])
    pk, bk = (w['E'] * w['f'] * w['km']).sum(), (sv['N_obs'] * sv['km']).sum()
    miss = s['ratio'].isna()
    return {
        'from_gps': r is not None,
        'no_ratio_cells_pct': round(100 * miss.mean(), 2) if r is not None else None,
        'no_ratio_pax_pct': round(100 * s.loc[miss, 'n'].sum() / s['n'].sum(), 2) if r is not None else None,
        'weekday_bus_km': round(bk),
        'weekday_bus_km_sched': round((sv['N'] * sv['km']).sum()),
        'weekday_pax_km': round(pk),
        'avg_load_per_bus_km': round(pk / bk, 1),
    }


def feasibility(c, D, E):
    # route-level E cut needed to keep each route's q-quantile load under crush x total (not applied; tech note)
    out = []
    for qq in [0.9, 0.95]:
        q = (E * c['f'] / c['N_obs']).groupby(c['route_id']).quantile(qq)
        for cr in [1.5, 2.0, 2.5, 3.0]:
            h = (cr * c.groupby('route_id')['total'].first() / q).reindex(D.index).dropna()
            d = D[h.index]
            out.append({'quantile': qq, 'crush': cr, 'routes_over_cap': int((h < 1).sum()),
                        'routes_over_cap_pax_pct': round(100 * d[h < 1].sum() / D.sum(), 1),
                        'carried_cut_only_pct': round(100 * (np.minimum(1, h) * d).sum() / d.sum(), 1),
                        'max_carried_pct': round(100 * (h * d).sum() / d.sum(), 1)})
    return out


def calib_note(m, fixed, D, E, rm, on):
    if not on:
        return {'on': False}
    a = 1 / m[fixed]
    return {
        'on': True,
        'routes_capped': int(fixed.sum()),
        'capped_digital_pax_pct': round(100 * D[fixed].sum() / D.sum(), 2),
        'app_share_multiple_q10_50_90_max': [round(v, 2) for v in a.quantile([.1, .5, .9, 1])] if len(a) else [],
        'E_uncapped': round(E * m[~fixed].max(), 2) if (~fixed).any() else None,
        'riders_carried_pct': round(100 * (m * D).sum() / D.sum(), 2),
        'feasible': bool(round((m * D).sum() / D.sum(), 6) >= 1),
        'top10_multiple': [dict(route_id=i, route=rm['route'].get(i), multiple=round(v, 2), E=round(E * m[i], 2),
                                digital_pax_day=round(D[i], 1)) for i, v in a.nlargest(10).items()],
    }


def public(c):
    # cells under min_cell_n leave the public table: an absent cell means limited data
    c = c[c['n'] >= cfg()['min_cell_n']].sort_values(['route_id', 'daytype', 'k', 'slot'])
    c = c.drop(columns='ratio')
    c = c.astype(dict.fromkeys(c.select_dtypes('float64').columns, 'float32'))
    return c.rename(columns={'N': 'N_sched'})  # DuckDB folds N into n


def merge_cov(load):
    f = OUT / 'coverage.json'
    d = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    d['load'] = load
    f.write_text(json.dumps(d, indent=2, default=str), encoding='utf-8')


def report(c, op, x, D, E, nd, bad, g):
    k = cfg()
    fl = json.loads((WORK / 'flows_summary.json').read_text())
    ok = c[c['flag'].isna()]
    pos = c[(c['N'] > 0) & (c['n'] >= k['min_cell_n'])]
    lf = ok['LF']
    wk = ok[ok['daytype'] == 'weekday']
    hr = wk.assign(h=wk['slot'] // (60 // k['slot_min'])).groupby('h')['f'].sum()
    both = ok.pivot_table(index=['route_id', 'from_stop', 'to_stop', 'slot'], columns='daytype', values='L')
    both = both.dropna(subset=['weekday', 'sunday']) if {'weekday', 'sunday'} <= set(both) else both.iloc[:0]
    am, pm = k['periods']['am'], k['periods']['pm']
    top = op[op['n_max'] >= k['confidence']['med_n']].nlargest(10, 'standee_min')
    peak = top['hour'].between(am[0], am[1] - 1) | top['hour'].between(pm[0], pm[1] - 1)
    ab = c[c['censored']].groupby(['route_id', 'base', 'dir'])['n'].agg(['size', 'sum']).nlargest(10, 'size')
    one = g['calendar'] is not None and len(g['calendar']) == 1
    return {
        'D_daily': round(D, 1),
        'E': {x: round(v, 2) for x, v in E.items()},
        'ridership_daily': k['ridership_daily'],
        'n_days': dict(zip(nd['daytype'], nd['nd'].astype(int))),
        'anomaly_days_excluded': [str(d.date()) for d in bad['date']],
        'service_note': ('GTFS has one calendar service running every day, so N is the same for every day type (D-05)'
                         if one else 'N per day type from calendar.txt weekday flags'),
        'represent': fl,
        'cells': int(len(c)),
        'cells_by_flag': {str(a): int(b) for a, b in c['flag'].fillna('ok').value_counts().items()},
        'cells_publishable': int(len(ok)),
        'schedule_gap_cells': int((c['flag'] == 'gap').sum()),
        'schedule_gap_pax_pct': round(100 * c.loc[c['flag'] == 'gap', 'n'].sum() / c['n'].sum(), 2),
        'censored_pct_of_cells': round(100 * pos['censored'].mean(), 3),
        'absurd_pct_of_cells_with_service_and_n': round(100 * pos['censored'].mean(), 3),  # same as censored_pct
        'censored_routes_top': [dict(route_id=a, base=b, dir=d, cells=int(r['size']), n=round(r['sum'], 1))
                              for (a, b, d), r in ab.iterrows()],
        'LF_quantiles_publishable': dict(zip(['p10', 'p25', 'p50', 'p75', 'p90', 'p99'],
                                             [round(v, 3) for v in lf.quantile([.1, .25, .5, .75, .9, .99])])),
        'level_share_pct': {a: round(100 * b, 2) for a, b in ok['level'].value_counts(normalize=True).items()},
        'confidence_share_pct': {a: round(100 * b, 2) for a, b in ok['confidence'].value_counts(normalize=True).items()},
        'over_seats_pct': round(100 * (ok['LF'] > 1).mean(), 2),
        'over_total_pct': round(100 * (ok['L'] > ok['total']).mean(), 2),
        'weekday_flow_by_hour_peak': {'am': int(hr.loc[:11].idxmax()), 'pm': int(hr.loc[12:].idxmax()),
                                      'midday_min': int(hr.loc[10:16].idxmin())},
        'weekday_gt_sunday_pct_of_shared_cells': round(100 * (both['weekday'] > both['sunday']).mean(), 1)
        if len(both) else None,
        'top10_route_hours_by_standee_min': [dict(route=r.route, daytype=r.daytype, hour=int(r.hour),
                                   standee_min=round(r.standee_min), LF=round(r.LF_max, 2),
                                   L=round(r.L_max, 1), n=round(r.n_max, 1), stretch=f'{r.max_from} -> {r.max_to}')
                              for r in top.itertuples()],
        'top10_in_peak_windows': int(peak.sum()),
        'top10_weekday': int((top['daytype'] == 'weekday').sum()),
        'cells_public': int((c['n'] >= k['min_cell_n']).sum()),
    }
