import json
import re
import time

import duckdb
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from seatcast import OUT, RAW, ROOT, WORK, cfg, gtfs
from seatcast.clean import norm, parse_route

M = WORK / 'match'
OPP = {'UP': 'DOWN', 'DOWN': 'UP', 'CW': 'CCW', 'CCW': 'CW'}
ODK = ['route_raw', 'ss_n', 'es_n']


def key(s):
    return re.sub(r'\s+', '', str(s)).upper()


def zero(b):
    return re.sub(r'(?<!\d)0+(?=\d)', '', b)


def nums(s):
    return frozenset(re.findall(r'\d+', s))


def strip(s):
    # drop generic descriptors (config match_generic) so they neither create nor block a match
    g = set(cfg().get('match_generic', []))
    w = [x for x in s.split() if x not in g]
    return ' '.join(w) if w else s


def parts(raw):
    p = [norm(x) for x in str(raw).split('/')]
    return p if len(p) > 1 and all(re.search(r'[a-z]{3}', x) for x in p) else []


# ---------- routes ----------

def groutes(g, pat):
    r = g['routes'][['route_id', 'agency_id', 'route_short_name']].copy()
    r['key'] = r['route_short_name'].map(key)
    p = [parse_route(c) or (None, None, None) for c in r['route_short_name']]
    r['base'], r['dir'], r['var'] = zip(*p)
    r['zb'] = [zero(b) if isinstance(b, str) else None for b in r['base']]
    r = r.merge(pat.groupby('route_id')['n_trips'].sum().reset_index(), on='route_id', how='left')
    r['n_trips'] = r['n_trips'].fillna(0).astype(int)
    return r.sort_values(['n_trips', 'route_id'], ascending=[False, True], kind='stable').reset_index(drop=True)


def match_routes(c, r, rmap):
    # c: route_raw, base, dir. Rungs per THINKING D-02; tripless GTFS routes are never targets.
    r = r[r['n_trips'] > 0]
    k1 = dict(zip(r['key'], r['route_id']))
    b = r.dropna(subset=['base'])  # sorted by trips desc: drop_duplicates keeps the busiest route per key
    k2 =b.drop_duplicates(['base', 'dir']).set_index(['base', 'dir'])['route_id'].to_dict()
    k3 = b.drop_duplicates(['zb', 'dir']).set_index(['zb', 'dir'])['route_id'].to_dict()
    out = []
    for raw, base, d in zip(c['route_raw'], c['base'], c['dir']):
        k = key(raw)
        if k in k1:
            out.append((k1[k], 1))
        elif isinstance(base, str) and (base, d) in k2:
            out.append((k2[(base, d)], 2))
        elif isinstance(base, str) and (zero(base), d) in k3:
            out.append((k3[(zero(base), d)], 3))
        elif rmap.get(k) in k1:
            out.append((k1[rmap[k]], 4))
        else:
            out.append((None, 0))
    c = c.copy()
    c['route_id'], c['rung_route'] = zip(*out) if out else ([], [])
    return c


def opposite(r):
    # route_id -> same base, opposite direction; same variant first, then most trips
    b = r[(r['n_trips'] > 0) & r['dir'].isin(list(OPP))]
    same = b.drop_duplicates(['base', 'dir', 'var']).set_index(['base', 'dir', 'var'])['route_id'].to_dict()
    any_ = b.drop_duplicates(['base', 'dir']).set_index(['base', 'dir'])['route_id'].to_dict()
    o = {}
    for rid, base, d, v in zip(b['route_id'], b['base'], b['dir'], b['var']):
        o[rid] = same.get((base, OPP[d], v)) or any_.get((base, OPP[d]))
    return o


# ---------- stops ----------

def rest(q, c):
    # similarity of the tokens the two names do not share, in their original order
    a, b = q.split(), c.split()
    x, y = ''.join(t for t in a if t not in b), ''.join(t for t in b if t not in a)
    if not x or not y:
        return 100.0
    return max(fuzz.ratio(x, y), fuzz.partial_ratio(x, y) if min(len(x), len(y)) >= 3 else 0)


def score(qs, cs, mc):
    # token_set with subset, number and rest guards; token_sort/1e4 breaks ties without moving thresholds.
    # returns (score, rival): rival keeps subset-blocked pairs, which still count against the margin.
    dq, dc = [nums(x) for x in qs], [nums(x) for x in cs]
    tq, tc = [set(x.split()) for x in qs], [set(x.split()) for x in cs]
    qs, cs = [strip(x) for x in qs], [strip(x) for x in cs]
    a = process.cdist(qs, cs, scorer=fuzz.token_set_ratio, dtype=np.float64)
    s = process.cdist(qs, cs, scorer=fuzz.token_sort_ratio, dtype=np.float64)
    u = {k: i for i, k in enumerate(set(dq) | set(dc))}
    iq, ic = np.array([u[x] for x in dq])[:, None], np.array([u[x] for x in dc])[None, :]
    eq = np.array([bool(x) for x in dq])[:, None] & np.array([bool(x) for x in dc])[None, :]
    a[eq & (iq != ic)] = 0
    for i, j in zip(*np.nonzero(a >= mc['maybe'])):
        if rest(qs[i], cs[j]) < mc['rest']:
            a[i, j] = 0
    a = a + s / 1e4
    nq = np.array([len(x.split()) for x in qs])[:, None]
    nc = np.array([len(x.split()) for x in cs])[None, :]
    v = a.copy()
    a[(np.minimum(nq, nc) <= 2) & (s < 80)] = 0
    # sub: one name's full tokens all appear in the other's, sharing a non-generic token (rung e)
    g = set(cfg().get('match_generic', []))
    sub = np.zeros(a.shape)
    for i, j in zip(*np.nonzero(v >= 100)):
        x, y = tq[i], tc[j]
        sub[i, j] = (x <= y or y <= x) and bool((x & y) - g)
    return a, v, sub


def collapse(x, qi, nq, ci, nc):
    # strings -> names: max over each name's strings
    m1 = np.zeros((nq, x.shape[1]))
    np.maximum.at(m1, np.asarray(qi, int), x)
    m = np.zeros((nc, nq))
    np.maximum.at(m, np.asarray(ci, int), m1.T)
    return m.T


def decide(m, v, mc):
    # m: names x candidates; v: rivals. Returns best idx, score, runner idx, runner score, accepted
    n = m.shape[0]
    if m.shape[1] == 0:
        z = np.full(n, -1)
        return z, np.zeros(n), z, np.zeros(n), np.zeros(n, bool)
    r = np.arange(n)
    i1 = np.argmax(m, axis=1)
    s1 = m[r, i1]
    w = v.copy()
    w[r, i1] = -1
    i2 = np.argmax(w, axis=1) if m.shape[1] > 1 else np.full(n, -1)
    s2 = np.maximum(w[r, i2], 0) if m.shape[1] > 1 else np.zeros(n)
    ok = ((s1 >= mc['accept']) | ((s1 >= mc['maybe']) & (s1 - s2 >= mc['margin']))) & (s1 > s2)
    return i1, s1, i2, s2, ok


def strings(names, raws):
    s, i = list(names), list(range(len(names)))
    for k, raw in enumerate(raws):
        for p in parts(raw):
            s.append(p)
            i.append(k)
    return s, i


def match_route_names(q, c, mc):
    # q: name_n, raw for one route; c: gtfs_n, raw for its stops.
    # full names and '/' parts are scored together; rung c if the full-name pair won, d if a part did.
    qn, cn = q['name_n'].tolist(), c['gtfs_n'].tolist()
    qs, qi = strings(qn, q['raw'])
    cs, ci = strings(cn, c['raw'])
    a, v, sub = score(qs, cs, mc)
    m, w = collapse(a, qi, len(qn), ci, len(cn)), collapse(v, qi, len(qn), ci, len(cn))
    sub = collapse(sub, qi, len(qn), ci, len(cn))
    i1, s1, i2, s2, ok = decide(m, w, mc)
    f = lambda j: cn[j] if j >= 0 else None
    r = np.arange(len(qn))
    if not len(cn):
        return pd.DataFrame({'name_n': qn, 'rung': None, 'gtfs_n': None, 'cand': None, 'score': 0.0,
                             'runner': None, 'runner_score': 0.0})
    rung = np.where(ok, np.where(a[:len(qn), :len(cn)][r, i1] >= s1, 'c', 'd'), None)
    if mc.get('superset'):
        # rung e: the subset guard blocked the route's only token-superset (or subset) candidate; unique, so not ambiguous
        j = np.argmax(sub, axis=1)
        e = ~ok & (sub.sum(axis=1) == 1)
        x = w.copy()
        x[r, j] = -1
        k = np.argmax(x, axis=1)
        i1, s1 = np.where(e, j, i1), np.where(e, w[r, j], s1)
        i2, s2 = np.where(e, k, i2), np.where(e, np.maximum(x[r, k], 0), s2)
        rung, ok = np.where(e, 'e', rung), ok | e
    # unmatched: show the two best candidates before the subset guard, for the alias review
    t = np.argsort(-w, axis=1, kind='stable')
    t2 = t[:, 1] if w.shape[1] > 1 else np.full(len(qn), -1)
    i1, s1 = np.where(ok, i1, t[:, 0]), np.where(ok, s1, w[r, t[:, 0]])
    i2, s2 = np.where(ok, i2, t2), np.where(ok, s2, w[r, t2] if w.shape[1] > 1 else 0)
    return pd.DataFrame({
        'name_n': qn, 'rung': rung,
        'gtfs_n': [f(j) if k else None for j, k in zip(i1, ok)],
        'cand': [f(j) for j in i1], 'score': np.round(s1, 1),
        'runner': [f(j) for j in i2], 'runner_score': np.round(s2, 1),
    })


def match_names(q, cand, alias, mc):
    # q: route_id, name_n, raw, p. cand: route_id, gtfs_n, raw. alias: route_id ('' = any), name_n, gtfs_n.
    cs = {r: d.drop_duplicates('gtfs_n').reset_index(drop=True) for r, d in cand.groupby('route_id')}
    al = {(r, n): t for r, n, t in zip(alias['route_id'], alias['name_n'], alias['gtfs_n'])}
    out = []
    for r, d in q.groupby('route_id'):
        c = cs.get(r, pd.DataFrame({'gtfs_n': [], 'raw': []}))
        have = set(c['gtfs_n'])
        d = d.reset_index(drop=True)
        a = d['name_n'].isin(have)
        t = [al.get((r, n)) or al.get(('', n)) for n in d['name_n']]
        b = pd.Series([x in have for x in t]) & ~a
        todo = d[~a & ~b]
        x = match_route_names(todo, c, mc) if len(todo) else pd.DataFrame(columns=['name_n'])
        y = pd.DataFrame({'name_n': d['name_n'], 'rung': np.where(a, 'a', np.where(b, 'b', None)),
                          'gtfs_n': np.where(a, d['name_n'], np.where(b, t, None)),
                          'score': np.where(a | b, 100.0, np.nan)})
        y = y[a | b]
        out.append(pd.concat([y, x], ignore_index=True).assign(route_id=r))
    nm = pd.concat(out, ignore_index=True).merge(q[['route_id', 'name_n', 'p']], on=['route_id', 'name_n'])
    # pairs accepted on other routes are not reused: a fuzzy score depends only on the two strings,
    # so reuse would only ever override a local ambiguity (P2 review, 23 Nov)
    return nm


# ---------- order ----------

def order(od, nm, pos):
    # od: OD rows with route_id. Pick b < a, canonical-most pattern first, then smallest span.
    n = nm[['route_id', 'name_n', 'gtfs_n', 'rung']]
    x = od.merge(n.rename(columns={'name_n': 'ss_n', 'gtfs_n': 'gb', 'rung': 'rung_b'}), on=['route_id', 'ss_n'], how='left')
    x = x.merge(n.rename(columns={'name_n': 'es_n', 'gtfs_n': 'ga', 'rung': 'rung_a'}), on=['route_id', 'es_n'], how='left')
    both = x['gb'].notna() & x['ga'].notna()
    y = x[both & (x['gb'] != x['ga'])][ODK + ['route_id', 'gb', 'ga']]
    pb = pos.rename(columns={'gtfs_n': 'gb', 'k': 'b'})
    pa = pos.rename(columns={'gtfs_n': 'ga', 'k': 'a'})[['route_id', 'pattern_id', 'ga', 'a']]
    y = y.merge(pb, on=['route_id', 'gb']).merge(pa, on=['route_id', 'pattern_id', 'ga'])
    y = y[y['b'] < y['a']]
    y = y.assign(span=y['a'] - y['b']).sort_values(['n_trips', 'span', 'pattern_id', 'b'],
                                                    ascending=[False, True, True, True], kind='stable')
    y = y.drop_duplicates(ODK)[ODK + ['pattern_id', 'b', 'a']]
    x = x.merge(y, on=ODK, how='left')
    x['status'] = np.select([x['route_id'].isna(), ~both, x['gb'] == x['ga'], x['pattern_id'].isna()],
                            ['route', 'stops', 'same', 'order'], 'ok')
    return x


def build(od, g, pat, ps, alias=None, rmap=None, mc=None):
    # od: route_raw, base, dir, ss, es, ss_n, es_n, p (passengers), one row per distinct OD
    mc = {**cfg()['match'], 'rest': cfg()['match_rest'], 'superset': cfg()['match_superset'], **(mc or {})}
    rmap = rmap or {}
    r = groutes(g, pat)
    c = od[['route_raw', 'base', 'dir']].drop_duplicates('route_raw')
    rm = match_routes(c, r, rmap)
    opp = opposite(r)
    rm['opp_id'] = rm['route_id'].map(opp)
    od = od.merge(rm[['route_raw', 'route_id', 'rung_route', 'opp_id']], on='route_raw')

    s = g['stops'][['stop_id', 'stop_name']].assign(gtfs_n=lambda d: d['stop_name'].map(norm))
    pos = ps[['pattern_id', 'k', 'stop_id']].merge(s, on='stop_id').merge(pat[['pattern_id', 'route_id', 'n_trips']], on='pattern_id')
    pos = pos[['route_id', 'pattern_id', 'n_trips', 'k', 'gtfs_n']]
    cand = ps[['pattern_id', 'stop_id']].merge(pat[['pattern_id', 'route_id']], on='pattern_id').merge(s, on='stop_id')
    cand = cand.rename(columns={'stop_name': 'raw'})[['route_id', 'gtfs_n', 'raw']].drop_duplicates(['route_id', 'gtfs_n'])

    q = pd.concat([od[['route_id', 'ss_n', 'ss', 'p']].set_axis(['route_id', 'name_n', 'raw', 'p'], axis=1),
                   od[['opp_id', 'ss_n', 'ss', 'p']].set_axis(['route_id', 'name_n', 'raw', 'p'], axis=1).assign(p=0),
                   od[['route_id', 'es_n', 'es', 'p']].set_axis(['route_id', 'name_n', 'raw', 'p'], axis=1),
                   od[['opp_id', 'es_n', 'es', 'p']].set_axis(['route_id', 'name_n', 'raw', 'p'], axis=1).assign(p=0)])
    q = q.dropna(subset=['route_id', 'name_n'])
    q = q.assign(sl=q['raw'].str.contains('/', na=False)).sort_values('sl', ascending=False, kind='stable')
    q = q.groupby(['route_id', 'name_n'], sort=False).agg(raw=('raw', 'first'), p=('p', 'sum')).reset_index()
    al = alias if alias is not None else pd.DataFrame(columns=['route_id', 'name_n', 'gtfs_n'])
    nm = match_names(q, cand, al, mc)

    x0 = order(od, nm, pos)
    x1 = order(od.drop(columns='route_id').rename(columns={'opp_id': 'route_id'}).assign(opp_id=od['route_id']), nm, pos)
    sw = swaps(x0, x1)
    x = pd.concat([x0[~x0['route_raw'].isin(sw['route_raw'])],
                   x1[x1['route_raw'].isin(sw['route_raw'])].assign(swapped=True)], ignore_index=True)
    x['swapped'] = x['swapped'].fillna(False).astype(bool) if 'swapped' in x else False
    # what a per-ticket retry on the opposite direction would add (reported, not applied)
    y = x[x['status'] == 'order'][ODK].merge(x1[x1['status'] == 'ok'][ODK + ['p']], on=ODK)
    return {'od': x, 'routes': rm, 'names': nm, 'swaps': sw, 'flip_p': float(y['p'].sum()), 'r': r}


def swaps(x0, x1):
    # per ticket route code: in-order share < 50% and the opposite route orders more passengers
    f = lambda x: x.groupby('route_raw').apply(
        lambda d: pd.Series({'both': d.loc[d['status'].isin(['ok', 'order']), 'p'].sum(),
                             'ok': d.loc[d['status'] == 'ok', 'p'].sum(),
                             'route_id': d['route_id'].iloc[0]}), include_groups=False)
    a, b = f(x0), f(x1[x1['route_id'].notna()])
    t = a.reset_index().merge(b.reset_index(), on='route_raw', suffixes=('', '_opp'))
    t = t[(t['ok'] < 0.5 * t['both']) & (t['ok_opp'] > t['ok'])]
    return t[['route_raw', 'route_id', 'route_id_opp', 'both', 'ok', 'ok_opp']]


# ---------- run ----------

def feed():
    g = gtfs.load(RAW / 'gtfs', w=M)
    f, src = M / 'patterns.parquet', RAW / 'gtfs' / 'stop_times.txt'
    if f.exists() and f.stat().st_mtime > src.stat().st_mtime and (M / 'pattern_stops.parquet').exists():
        return g, pd.read_parquet(f), pd.read_parquet(M / 'pattern_stops.parquet')
    pat, ps, _ = gtfs.patterns(g=g, w=M)
    return g, pat, ps


def configs(r):
    rm = pd.read_csv(ROOT / 'config' / 'route_map.csv', dtype=str).fillna('')
    rmap = {key(a): key(b) for a, b in zip(rm['ticket_route'], rm['route_short_name'])}
    al = pd.read_csv(ROOT / 'config' / 'stop_alias.csv', dtype=str).fillna('')
    ids = dict(zip(r['key'], r['route_id']))
    al = pd.DataFrame({'route_id': [ids.get(key(x), '') if x else '' for x in al['route']],
                       'name_n': al['ticket_name'].map(norm), 'gtfs_n': al['gtfs_name'].map(norm)})
    return rmap, al


def run():
    t0 = time.time()
    M.mkdir(parents=True, exist_ok=True)
    g, pat, ps = feed()
    rmap, al = configs(groutes(g, pat))
    c = duckdb.connect()
    c.execute(f"create view t as select * from '{(WORK / 'tickets.parquet').as_posix()}'")
    od = c.sql("""select route_raw, any_value(base) base, any_value(dir) dir, ss_n, es_n,
        coalesce(max(ss) filter (where ss like '%/%'), max(ss)) ss,
        coalesce(max(es) filter (where es like '%/%'), max(es)) es, sum(pc) p, count(*) n
        from t group by route_raw, ss_n, es_n""").df()
    res = build(od, g, pat, ps, al, rmap)
    x = res['od']
    c.register('x', x[ODK + ['route_id', 'pattern_id', 'b', 'a', 'rung_route', 'rung_b', 'rung_a', 'status']])
    c.execute(f"""copy (select t.tid, x.route_id, x.pattern_id, x.b::int b, x.a::int a, t.pc, t.ts, t.slot, t.date,
        t.daytype, t.week, t.ac, t.series, t.fare_pp, t.fare_class, x.rung_route::int rung_route, x.rung_b, x.rung_a
        from t join x using (route_raw, ss_n, es_n) where x.status = 'ok' order by t.tid)
        to '{(WORK / 'od.parquet').as_posix()}' (format parquet)""")
    write(res, c, ps)
    print(f'match: {time.time() - t0:.0f}s')


def write(res, c, ps):
    x, nm, r = res['od'], res['names'], res['r']
    sn = dict(zip(r['route_id'], r['route_short_name']))
    ok = nm[nm['rung'].notna()].assign(route=lambda d: d['route_id'].map(sn))
    ok = ok[ok['p'] > 0]
    ok[['route', 'route_id', 'name_n', 'gtfs_n', 'rung', 'score', 'runner', 'runner_score', 'p']].sort_values(
        'p', ascending=False).to_csv(WORK / 'stop_match.csv', index=False)
    ur = x[x['status'] == 'route'].groupby('route_raw').agg(base=('base', 'first'), dir=('dir', 'first'),
                                                            p=('p', 'sum'), n=('n', 'sum')).reset_index()
    ur.sort_values('p', ascending=False).to_csv(WORK / 'unmatched_routes.csv', index=False)
    um = unmatched(x, nm, sn)
    um.to_csv(WORK / 'unmatched_stops.csv', index=False)
    proposals(um).to_csv(WORK / 'alias_proposals.csv', index=False)
    cov(res, c, ps)


def unmatched(x, nm, sn):
    # passengers lost per (route, name) because that end did not match
    d = x[x['route_id'].notna()]
    u = pd.concat([d[d['rung_b'].isna()][['route_id', 'ss_n', 'p']].set_axis(['route_id', 'name_n', 'p'], axis=1),
                   d[d['rung_a'].isna()][['route_id', 'es_n', 'p']].set_axis(['route_id', 'name_n', 'p'], axis=1)])
    u = u.groupby(['route_id', 'name_n'])['p'].sum().reset_index()
    u = u.merge(nm[['route_id', 'name_n', 'cand', 'score', 'runner', 'runner_score']], on=['route_id', 'name_n'], how='left')
    u['route'] = u['route_id'].map(sn)
    return u[['name_n', 'route', 'route_id', 'p', 'cand', 'score', 'runner', 'runner_score']].sort_values('p', ascending=False)


def proposals(um, n=30):
    out = []
    for name, d in um.groupby('name_n'):
        d = d.sort_values('p', ascending=False)
        top = d.sort_values('score', ascending=False).iloc[0]
        out.append({'name': name, 'passengers': int(d['p'].sum()),
                    'top_routes': ' '.join(f'{r}({int(p)})' for r, p in zip(d['route'].head(3), d['p'].head(3))),
                    'best_candidate': top['cand'], 'score': top['score'], 'best_route': top['route'],
                    'runner_up': top['runner'], 'runner_score': top['runner_score']})
    return pd.DataFrame(out).sort_values('passengers', ascending=False).head(n)


def share(a, b):
    return round(100 * float(a) / float(b), 2) if b else None


def cov(res, c, ps):
    x, r = res['od'], res['r']
    P = x['p'].sum()
    st = x.groupby('status')['p'].sum()
    routed = P - st.get('route', 0)
    both = st.get('ok', 0) + st.get('order', 0) + st.get('same', 0)
    inord = both - st.get('same', 0)  # board = alight after matching is neither order; reported in status_pax
    ok = st.get('ok', 0)
    m = x[x['status'] == 'ok']
    rung_s = lambda col: {str(k): share(v, ok) for k, v in m.groupby(col)['p'].sum().items()}
    ends = pd.concat([x.loc[x['route_id'].notna(), ['rung_b', 'p']].set_axis(['r', 'p'], axis=1),
                      x.loc[x['route_id'].notna(), ['rung_a', 'p']].set_axis(['r', 'p'], axis=1)])
    ag = m.merge(r[['route_id', 'agency_id']], on='route_id').groupby('agency_id')['p'].sum()
    top = x.groupby('route_raw')['p'].sum().nlargest(100).index
    tx = x[x['route_raw'].isin(top)]
    sw = res['swaps']
    mt = {
        'passengers': int(P),
        'route_matched_pct': share(routed, P),
        'both_stops_pct_of_routed': share(both, routed),
        'in_order_pct_of_both': share(ok, inord),
        'usable_pct_of_all': share(ok, P),
        'gate_g2': bool(routed >= 0.9 * P and both >= 0.85 * routed and ok >= 0.95 * inord),
        'status_pax': {k: int(v) for k, v in st.items()},
        'route_rung_pct_of_all': {(str(k) if k else 'unmatched'): share(v, P) for k, v in x.groupby('rung_route')['p'].sum().items()},
        'stop_end_rung_pct_of_routed_ends': {str(k): share(v, 2 * routed) for k, v in
                                             ends.fillna({'r': 'none'}).groupby('r')['p'].sum().items()},
        'usable_route_rung_pct': rung_s('rung_route'),
        'agency_pct_of_usable': {k: share(v, ok) for k, v in ag.items()},
        'gtfs_trips_by_agency': {k: int(v) for k, v in r.groupby('agency_id')['n_trips'].sum().items()},
        'direction_swaps': sw[['route_raw', 'route_id', 'route_id_opp', 'ok', 'ok_opp']].astype(
            {'ok': int, 'ok_opp': int}).to_dict('records'),
        'out_of_order_in_order_on_opposite_pax': int(res['flip_p']),
        'top100_routes': {'pax_share_pct': share(tx['p'].sum(), P),
                          'usable_pct': share(tx.loc[tx['status'] == 'ok', 'p'].sum(), tx['p'].sum())},
        'fare_slab': fare(c, ps),
    }
    f = OUT / 'coverage.json'
    OUT.mkdir(parents=True, exist_ok=True)
    d = json.loads(f.read_text(encoding='utf-8')) if f.exists() else {}
    d['match'] = mt
    f.write_text(json.dumps(d, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in mt.items() if k not in ('direction_swaps', 'fare_slab')}, indent=1))


def fare(c, ps):
    # R7 km bounds unverified (page 404) and fare_stage is a 0/1 flag, so no agreement rate yet;
    # report along-route km per standard slab instead, to show the slabs order by distance.
    c.register('ps', ps[['pattern_id', 'k', 'dist_m']])
    q = c.sql(f"""select o.ac, o.fare_pp, sum(o.pc)::int pax,
        round(quantile_cont((pa.dist_m - pb.dist_m) / 1000, 0.1), 1) km_p10,
        round(quantile_cont((pa.dist_m - pb.dist_m) / 1000, 0.5), 1) km_p50,
        round(quantile_cont((pa.dist_m - pb.dist_m) / 1000, 0.9), 1) km_p90
        from '{(WORK / 'od.parquet').as_posix()}' o
        join ps pb on pb.pattern_id = o.pattern_id and pb.k = o.b
        join ps pa on pa.pattern_id = o.pattern_id and pa.k = o.a
        where o.fare_class = 'std' group by all order by all""").df()
    return {'agreement_pct': None,
            'why': 'slab km bounds from [R7] not verified (source page 404); GTFS fare_stage is a 0/1 flag, not stage numbers',
            'km_by_slab': q.to_dict('records')}
