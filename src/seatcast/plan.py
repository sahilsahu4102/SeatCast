import datetime as dtm
import functools
import hashlib
import json
import sys
import time
from functools import lru_cache

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from rapidfuzz import fuzz

from seatcast import OUT, cfg, gtfs, raptor
from seatcast.clean import daytype, norm, parse_route
from seatcast.load import LEVELS, NO

LV = LEVELS + [NO]  # level codes 0..3; 4 = no data
DT = ['weekday', 'saturday', 'sunday']
CONF = ['low', 'medium', 'high']
WHY = [None, 'schedule_gap', 'implausible', 'low_n']  # 0 ok, 1 gap, 2 absurd, 3 no published cell (n < min_cell_n)
COLS = ['route_id', 'from_stop', 'to_stop', 'slot', 'daytype', 'n', 'N_sched', 'L_low', 'L', 'L_high', 'LF', 'p_seat',
        'level_low', 'level', 'level_high', 'flag', 'confidence', 'seats', 'total', 'censored', 'N_obs']
NOTE = 'Estimates from Oct 2026 app e-tickets expanded to total ridership; see /coverage'
DAY = 86400


def enc(s, m, miss=-1):
    s = s.astype('category')
    lut = np.array([m.get(x, miss) for x in s.cat.categories] + [miss], np.int64)
    return lut[s.cat.codes.to_numpy()]  # code -1 (null) takes the last entry


def codes(v):
    return {x: i for i, x in enumerate(v)}


class Cells:
    # published cells in sorted integer keys: (route, from stop, to stop, day type, slot) -> row
    def __init__(self, c, net):
        self.S, self.B = len(net.stop_id), 1440 // cfg()['slot_min']
        self.rid = codes(pd.unique(np.concatenate([net.route.astype(str), c['route_id'].astype(str).unique()])))
        sid = codes(net.stop_id.tolist())
        r, a, b = enc(c['route_id'], self.rid), enc(c['from_stop'], sid), enc(c['to_stop'], sid)
        d, s = enc(c['daytype'], codes(DT)), c['slot'].to_numpy(np.int64)
        ok = (r >= 0) & (a >= 0) & (b >= 0) & (d >= 0)
        k = self.key(r, a, b, d, s)[ok]
        o = np.argsort(k, kind='stable')
        self.k = k[o]
        x = {'r': r, 'a': a, 'b': b, 'd': d, 's': s,
             'lv': enc(c['level'], codes(LV), 4), 'lo': enc(c['level_low'], codes(LV), 4),
             'hi': enc(c['level_high'], codes(LV), 4), 'why': enc(c['flag'], {'gap': 1, 'absurd': 2}, 0),
             'conf': enc(c['confidence'], codes(CONF))}
        c = c if 'N_obs' in c else c.assign(N_obs=c['N_sched'])  # outputs without GPS service: timetable buses
        for n in ['n', 'N_sched', 'N_obs', 'L_low', 'L', 'L_high', 'LF', 'p_seat', 'seats', 'total']:
            x[n] = c[n].to_numpy(np.float64)
        x['cen'] = c['censored'].fillna(False).to_numpy(bool) if 'censored' in c else np.zeros(len(c), bool)
        self.__dict__.update({n: v[ok][o] for n, v in x.items()})

    def key(self, r, a, b, d, s):
        return (((np.int64(r) * self.S + a) * self.S + b) * 3 + d) * self.B + s

    def find(self, route_id, a, b, dt, slot):
        a = np.asarray(a, np.int64)
        r = self.rid.get(route_id)
        if r is None or not len(self.k):
            return np.full(len(a), -1)
        k = self.key(r, a, b, DT.index(dt), np.asarray(slot, np.int64))
        i = np.minimum(np.searchsorted(self.k, k), len(self.k) - 1)
        return np.where(self.k[i] == k, i, -1)

    def get(self, col, i, fill=np.nan):
        v = getattr(self, col)
        out = np.full(len(i), fill, v.dtype if fill is not np.nan else np.float64)
        out[i >= 0] = v[i[i >= 0]]
        return out


class World:
    def __init__(self, net, cells, routes, heads=None, shapes=None):
        self.net, self.cells, self.routes = net, cells, routes
        self.heads, self.shapes = heads or {}, shapes or {}
        self.names = [str(x) for x in net.stop_name]
        self.keys = [norm(x) for x in self.names]
        self.sid = codes(net.stop_id.tolist())


def read_cells(f=None):
    f = f or OUT / 'cells.parquet'
    s = ['route_id', 'from_stop', 'to_stop', 'daytype', 'level_low', 'level', 'level_high', 'flag', 'confidence']
    have = set(pq.read_schema(f).names)  # older outputs may lack N_obs or censored
    return pq.read_table(f, columns=[c for c in COLS if c in have], read_dictionary=s).to_pandas()


def route_meta(d=None):
    r = gtfs.read(gtfs.src(d), 'routes')
    p = [parse_route(x) or (x, '', '') for x in r['route_short_name']]
    return {k: (s, b[0], b[1]) for k, s, b in zip(r['route_id'], r['route_short_name'], p)}


def headsigns(d=None):
    f = gtfs.src(d) / 'trips.txt'
    t = pd.read_csv(f, dtype=str, usecols=lambda c: c.strip() in ('trip_id', 'trip_headsign'), encoding='utf-8-sig')
    t.columns = t.columns.str.strip()
    return dict(zip(t['trip_id'], t['trip_headsign'])) if 'trip_headsign' in t else {}


def read_shapes(f=None):
    f = f or OUT / 'segments.geojson'
    if not f.exists():
        return {}
    g = json.loads(f.read_text(encoding='utf-8'))
    return {(p['properties']['route_id'], p['properties']['from_stop'], p['properties']['to_stop']):
            p['geometry']['coordinates'] for p in g['features']}


def world(d=None):
    net = raptor.load(d)
    for t in DT:
        net.view(t)
    return World(net, Cells(read_cells(), net), route_meta(d), headsigns(d), read_shapes())


# ---------- crowding per bus leg ----------

def hm(t):
    return raptor.hm(int(t) % DAY)


def rnd(x, k=2):
    return None if x is None or x != x else round(float(x), k)


def pstops(net, rp, k1, k2):
    a = net.pat_ptr[rp]
    return net.pat_stop[a + k1:a + k2 + 1]


def run_of(m):
    # longest run of True as (start, end) inclusive, or None
    best, a = None, None
    for i, x in enumerate(list(m) + [False]):
        if x and a is None:
            a = i
        if not x and a is not None:
            if best is None or i - a > best[1] - best[0] + 1:
                best = (a, i - 1)
            a = None
    return best


def crowd(W, leg, dt):
    # per segment cells for the trip's scheduled times; summary for the leg; per-segment multipliers for GT
    C, nm, k = W.cells, W.names, cfg()
    st = pstops(W.net, leg['rp'], leg['k1'], leg['k2'])
    t = np.array(leg['times'][:-1] + [leg['arr']], np.int64)
    mins = np.diff(t) / 60
    sl = t[:-1] // (60 * k['slot_min']) % C.B
    i = C.find(leg['route_id'], st[:-1], st[1:], dt, sl)
    why = C.get('why', i, 3)
    ok = why == 0
    p = np.where(ok, C.get('p_seat', i), np.nan)
    lf = np.where(ok, C.get('LF', i), np.nan)
    lv = np.where(ok, C.get('lv', i, 4), 4)
    n = C.get('n', i)
    pb = p[ok][0] if ok.any() else 1.0
    q = np.fmax.accumulate(p)  # a seat once found is kept; standing riders sit when the load drops
    q = np.where(np.isnan(q), pb, q)
    m = k['multipliers']
    ms = np.where(lf < m['seat_lf'], m['seat_low'], m['seat_high'])  # ponytail: no-data stretches count as seated in a busy bus
    mult = q * ms + (1 - q) * m['stand']
    segs = []
    for x in range(len(mins)):
        g = {'from': nm[st[x]], 'to': nm[st[x + 1]], 'min': rnd(mins[x], 1), 'level': LV[lv[x]],
             'p_seat': rnd(p[x]), 'n': None if i[x] < 0 else int(n[x]),
             'censored': bool(i[x] >= 0 and C.cen[i[x]])}  # very crowded, magnitude capped
        sh = W.shapes.get((leg['route_id'], str(W.net.stop_id[st[x]]), str(W.net.stop_id[st[x + 1]])))
        if sh:
            g['shape'] = sh
        segs.append(g)
    w = mins + 0.01
    if w[ok].sum() < 0.5 * w.sum():
        bad = pd.Series(w[~ok]).groupby(why[~ok]).sum().idxmax()
        c = {'level': NO, 'p_seat': None, 'stand_min': None, 'crowded_between': None, 'text': 'Limited data',
             'confidence': 'low', 'n': None, 'range': None, 'reason': WHY[bad]}
    else:
        j = np.flatnonzero(ok)
        top = j[np.argmax(lf[j])]
        cb = run_of(ok & (lv >= 2))
        cb = [nm[st[cb[0]]], nm[st[cb[1] + 1]]] if cb else None
        kk = round(10 * pb)
        odds = 'likely' if pb > .5 else 'unlikely' if pb < .5 else 'possible'
        c = {'level': LV[lv[j].max()], 'p_seat': rnd(pb), 'stand_min': rnd((mins * (1 - q)).sum(), 1),
             'crowded_between': cb,
             'text': f'Seat {odds} at boarding ({kk} of 10 trips) · crowded {cb[0]} to {cb[1]}' if cb
             else f'Seats on {kk} of 10 trips',
             'confidence': CONF[C.get('conf', i, 9)[j].min()], 'n': int(n[top]),
             'range': [LV[C.lo[i[top]]], LV[C.hi[i[top]]]],
             'censored': bool(C.cen[i[j]].any())}  # some stretch's load is capped: level sure, size uncertain
    return c, segs, mins, mult


# ---------- options ----------

def bus_leg(W, l, dt, off):
    c, segs, mins, mult = crowd(W, l, dt)
    r = W.routes.get(l['route_id'], (l['route_id'], l['route_id'], ''))
    net = W.net
    st = pstops(net, l['rp'], l['k1'], l['k2'])
    last = net.pat_stop[net.pat_ptr[l['rp'] + 1] - 1]
    out = {'mode': 'bus', 'route': r[1], 'dir': r[2], 'route_name': r[0],
           'headsign': W.heads.get(l['trip_id']) or W.names[last],
           'board': W.names[l['board']], 'alight': W.names[l['alight']],
           'depart': hm(l['dep'] + off), 'arrive': hm(l['arr'] + off), 'ride_min': round((l['arr'] - l['dep']) / 60),
           'crowding': c, 'segments': segs,
           'stops': [{'name': W.names[s], 'lat': round(float(net.lat[s]), 5), 'lon': round(float(net.lon[s]), 5)} for s in st]}
    return out, mins, mult


def option(W, j, t0):
    # one RAPTOR journey -> response option (private fields start with _)
    k, dt, off = cfg(), j.get('dt', 'weekday'), j.get('off', 0)
    legs, walk, wait, ride, ready = [], 0, 0, [], t0
    for i, l in enumerate(j['legs']):
        if l['mode'] == 'walk':
            walk += l['sec']
            ready += l['sec']
            if l['sec'] > 0:
                to = 'destination' if l['to'] is None else W.names[l['to']]
                legs.append({'mode': 'walk', 'to': to, 'min': max(1, round(l['sec'] / 60))})
            continue
        b, mins, mult = bus_leg(W, l, dt, off)
        wait += max(0, l['dep'] + off - ready)
        ready = l['arr'] + off
        ride.append((mins, mult))
        legs.append(b)
    buses = [l for l in j['legs'] if l['mode'] == 'bus']
    dep = buses[0]['dep'] + off - j['legs'][0]['sec'] if buses else t0
    arr = j['arrive'] + off
    w = k['weights']
    tr = max(len(buses) - 1, 0)

    def gt(h):
        f = (lambda x: 1 + (x - 1) / 2) if h else (lambda x: x)
        return (f(w['walk']) * walk + f(w['wait']) * wait) / 60 + w['transfer_min'] * tr + \
            sum(float((a * f(b)).sum()) for a, b in ride)
    ids = '|'.join(l['trip_id'] for l in buses) or 'walk'
    return {'id': 'o' + hashlib.md5(ids.encode()).hexdigest()[:8], 'label': None,
            'depart': hm(dep), 'arrive': hm(arr), 'total_min': round((arr - dep) / 60), 'transfers': tr,
            'generalised_min': None, 'crowding': summary(legs), 'legs': legs,
            '_dep': dep, '_arr': arr, '_gt': gt(False), '_gth': gt(True), '_seq': tuple(l['route_id'] for l in buses),
            '_j': j}


def summary(legs):
    c = [l['crowding'] for l in legs if l['mode'] == 'bus']
    if not c:
        return None
    known = [x for x in c if x['level'] != NO]
    if not known:  # no bus on the trip has data
        return {'level': NO, 'p_seat': None, 'confidence': 'low', 'n': None, 'range': None, 'reason': c[0]['reason']}
    # level from the buses we can estimate; a trip with an unknown bus is 'partial' and low confidence (the leg says which)
    w, part = max(known, key=lambda x: LV.index(x['level'])), len(known) < len(c)
    return {'level': w['level'], 'p_seat': min(x['p_seat'] for x in known),
            'confidence': 'low' if part else min((x['confidence'] for x in known), key=CONF.index),
            'n': min(x['n'] for x in known), 'range': w['range'], 'partial': part,
            'censored': any(x.get('censored') for x in known)}


def walk_only(W, a, b, t0):
    s = int(raptor.walk_s(gtfs.hav(a[0], a[1], b[0], b[1])))
    j = {'legs': [{'mode': 'walk', 'from': None, 'to': None, 'sec': s}], 'arrive': t0 + s, 'rides': 0}
    o = option(W, j, t0)
    o['legs'] = [{'mode': 'walk', 'to': 'destination', 'min': max(1, round(s / 60))}]
    return o


KEYS = {'fastest': lambda o: (o['_arr'], o['transfers'], o['_gt']),
        'comfort': lambda o: (o['_gt'], o['_arr']),
        'balanced': lambda o: (o['_gth'], o['_arr'])}


def trust(o):
    c = o['crowding'] or {}
    return CONF.index(c.get('confidence') or 'low'), c.get('n') or 0


def rank(opts, pref):
    # GT within 3 min counts as a tie: the better-evidenced option goes first (ponytail: pairwise rule, not a strict order)
    if pref == 'fastest':
        return sorted(opts, key=KEYS[pref])
    g = '_gth' if pref == 'balanced' else '_gt'

    def cmp(a, b):
        if abs(a[g] - b[g]) <= 3 and trust(a) != trust(b):
            return -1 if trust(a) > trust(b) else 1
        return -1 if KEYS[pref](a) < KEYS[pref](b) else 1 if KEYS[pref](a) > KEYS[pref](b) else 0
    return sorted(sorted(opts, key=KEYS[pref]), key=functools.cmp_to_key(cmp))


def pick(opts, pref, n=3):
    s = rank(opts, pref)
    out = s[:1]
    for o in [rank(opts, 'fastest')[0], rank(opts, 'comfort')[0]] + s:
        if len(out) < n and o['_seq'] not in {x['_seq'] for x in out}:
            out.append(o)
    for o in s:  # fill with the same routes at another departure, only if it really is calmer (seat chance +0.2)
        same = [x for x in out if x['_seq'] == o['_seq']]
        p = first_p(o)
        if len(out) < n and same and p is not None and all(
                abs(o['_dep'] - x['_dep']) >= 600 and first_p(x) is not None and p >= first_p(x) + 0.2 for x in same):
            out.append(o)
    out = rank(out, pref)
    f = rank(out, 'fastest')[0]
    rest = [o for o in out if o is not f]
    c = rank(rest, 'comfort')[0] if rest else None
    for o in out:
        o['label'] = 'fastest' if o is f else 'comfort' if o is c and rank([f, c], 'comfort')[0] is c else 'balanced'
        o['generalised_min'] = round(o['_gth'] if pref == 'balanced' else o['_gt'], 1)
    return out


# ---------- candidates ----------

def search(W, src, dst, t0, dt, prev, ban=(), K=None):
    js = [dict(j, dt=dt, off=0) for j in raptor.query(W.net, src, dst, t0, dt, ban=ban, K=K)]
    if t0 < int(W.net.dep.max()) - DAY:  # just after midnight: yesterday's service still runs (times past 24:00)
        js += [dict(j, dt=prev, off=-DAY) for j in raptor.query(W.net, src, dst, t0 + DAY, prev, ban=ban, K=K)]
    return js


def row(W, l, dt):
    V = W.net.view(dt)[l['rp']]
    return int(np.flatnonzero(W.net.trip[V[3]] == l['trip_id'])[0])


def bump(W, j, dt):
    # the same itinerary on the next trips: first bus strictly later, each change at least change_s
    net, chg = W.net, cfg()['planner'].get('change_s', 0)
    legs, ready, first = [], None, True
    for l in j['legs']:
        if l['mode'] == 'walk':
            legs.append(l)
            ready = None if ready is None else ready + l['sec']
            continue
        stops, D, A, rows = net.view(dt)[l['rp']]
        col = D[:, l['k1']]
        x = np.searchsorted(col, l['dep'], 'right') if first else np.searchsorted(col, ready + chg)
        if x >= len(D):
            return None
        legs.append(dict(l, trip_id=str(net.trip[rows[x]]), dep=int(D[x, l['k1']]), arr=int(A[x, l['k2']]),
                         times=D[x, l['k1']:l['k2'] + 1].tolist()))
        ready, first = int(A[x, l['k2']]), False
    return dict(j, legs=legs, arrive=ready + (legs[-1]['sec'] if legs[-1]['mode'] == 'walk' else 0))


def later(W, j, span):
    out, cur = [], j
    dep = next(l['dep'] for l in j['legs'] if l['mode'] == 'bus')
    while True:
        cur = bump(W, cur, j['dt'])
        if cur is None or max(next(l['dep'] for l in cur['legs'] if l['mode'] == 'bus') - dep,
                              cur['arrive'] - j['arrive']) > span:
            return out
        out.append(cur)


def leave_later(o, pool):
    # any candidate leaving at least one shift step later, any route, arriving at most 30 min later: seat chance at first
    # boarding up 0.2, or the worst level on the ride (seated or not: a seat in a crushed bus is still crushed) down a
    # step. Best = calmest, then seat.
    sh = cfg()['planner']['shift_min']
    span, step = 60 * max(sh), 60 * min(sh)
    p0, l0 = first_p(o), (o['crowding'] or {}).get('level', NO)
    ok = []
    for v in pool:
        if v['_dep'] < o['_dep'] + step or v['_arr'] - o['_arr'] > span or not v['crowding']:
            continue
        p, lv = first_p(v), v['crowding']['level']
        if p is None or lv == NO:
            continue
        if p0 is not None and p < p0:  # never suggest a lower seat chance than the option itself
            continue
        if (p0 is not None and p >= p0 + 0.2) or (l0 != NO and LV.index(lv) < LV.index(l0)):
            ok.append((LV.index(lv), -p, v['_arr'], v['_dep'], v))
    if not ok:
        return None
    v = min(ok, key=lambda x: x[:4])[4]
    return {'type': 'leave_later', 'for': o['id'], 'depart': v['depart'], 'p_seat': rnd(first_p(v)),
            'extra_min': max(0, round((v['_arr'] - o['_arr']) / 60)), 'level': v['crowding']['level'],
            'route': ' + '.join(l['route'] for l in v['legs'] if l['mode'] == 'bus')}


def first_p(o):
    b = [l for l in o['legs'] if l['mode'] == 'bus']
    return b[0]['crowding']['p_seat'] if b else None


def upstream(W, o, a):
    # board the same bus 1-2 stops earlier, within a short walk of the origin, if it is clearly emptier there
    l = next((x for x in o['_j']['legs'] if x['mode'] == 'bus'), None)
    p0 = first_p(o)
    if l is None or p0 is None:
        return None
    k, net, C = cfg(), W.net, W.cells
    stops, D, A, rows = net.view(o['_j']['dt'])[l['rp']]
    r, best = row(W, l, o['_j']['dt']), None
    for kk in range(l['k1'] - 1, max(l['k1'] - 3, -1), -1):
        s, t = stops[kk], int(D[r, kk])
        wm = int(raptor.walk_s(gtfs.hav(a[0], a[1], net.lat[s], net.lon[s]))) / 60
        if wm > k['planner']['upstream_walk_min']:
            continue
        i = C.find(l['route_id'], [s], [stops[kk + 1]], o['_j']['dt'], [t // (60 * k['slot_min']) % C.B])
        if C.get('why', i, 3)[0] != 0:
            continue
        p = float(C.p_seat[i[0]])
        if p >= p0 + 0.2 and (best is None or p > best['p_seat']):
            best = {'type': 'board_upstream', 'for': o['id'], 'stop': W.names[s], 'walk_min': max(1, round(wm)),
                    'p_seat': rnd(p), 'depart': hm(t + o['_j'].get('off', 0) - 60 * wm)}
    return best


@lru_cache(maxsize=512)
def quiet(W, src, dst, dt):
    t = cfg()['planner']['quiet_hour']
    t0 = int(t[:2]) * 3600 + int(t[3:5]) * 60
    js = search(W, list(src), list(dst), t0, dt, dt)
    if not js:
        return None
    o = min((option(W, j, t0) for j in js), key=KEYS['fastest'])
    return {'time': t, 'total_min': o['total_min'], 'level': o['crowding']['level'] if o['crowding'] else NO}


def plan(W, a, b, depart, dt=None, pref='balanced'):
    # a, b: {name, lat, lon}; depart: datetime. Response per CLAUDE.md section 8, plus the P6a fields.
    k = cfg()
    pl = k['planner']
    day = depart.date()
    prev = dt or daytype(day - dtm.timedelta(days=1))
    dt = dt or daytype(day)
    t0 = depart.hour * 3600 + depart.minute * 60
    q = {'from': a['name'], 'to': b['name'], 'depart': depart.strftime('%Y-%m-%dT%H:%M'), 'daytype': dt, 'pref': pref,
         'from_point': a, 'to_point': b}
    pa, pb = (a['lat'], a['lon']), (b['lat'], b['lon'])
    src, dst = raptor.near(W.net, *pa), raptor.near(W.net, *pb)
    close = gtfs.hav(*pa, *pb) <= k['walk']['access_m']
    pool, seen, last, ban = [], set(), [], set()

    def add(js):
        for j in js:
            key = tuple(l.get('trip_id') for l in j['legs'])
            if key not in seen:
                seen.add(key)
                pool.append(j)
    if src and dst:
        last = search(W, src, dst, t0, dt, prev)
        add(last)
        for _ in range(pl.get('alternatives', 2)):  # route elimination: the slower option that may have room
            ban |= {l['route_id'] for j in last for l in j['legs'] if l['mode'] == 'bus'}
            last = search(W, src, dst, t0, dt, prev, ban)
            add(last)
        for m in pl['shift_min']:
            add(search(W, src, dst, t0 + 60 * m, dt, prev, K=pl.get('shift_rides')))  # leave-later alternatives: fewer changes, faster
        for j in list(pool):
            add(later(W, j, 60 * max(pl['shift_min'])))
    opts = [option(W, j, t0) for j in pool]
    if close:
        opts.append(walk_only(W, pa, pb, t0))
    out = pick(opts, pref) if opts else []
    sug = []
    for o in out:
        if o['_seq']:
            sug += [x for x in (leave_later(o, opts), upstream(W, o, pa)) if x]
    qh = quiet(W, tuple(src), tuple(dst), dt) if out and src and dst else None
    res = {'query': q, 'options': [{x: v for x, v in o.items() if not x.startswith('_')} for o in out],
           'suggestions': sug, 'quiet_hour': qh, 'notes': [NOTE]}
    if not out:
        res['reason'] = 'no_route' if src and dst else 'no_stop_nearby'
    return res


# ---------- stop search and CLI ----------

def find(W, q, n=10):
    # fuzzy stop search: whole-query containment first, then closeness of the full name
    s = norm(q)
    if not s:
        return []
    sc = [(fuzz.token_set_ratio(s, x), fuzz.ratio(s, x), -i) for i, x in enumerate(W.keys)]
    o = sorted(range(len(sc)), key=lambda i: sc[i], reverse=True)
    return [i for i in o[:n] if sc[i][0] >= 60]


def point(W, q):
    # best match, then the centroid of equally good stops within 1 km of it
    f = find(W, q, 50)
    if not f:
        return None
    net, top = W.net, f[0]
    best = fuzz.token_set_ratio(norm(q), W.keys[top])
    c = [i for i in f if fuzz.token_set_ratio(norm(q), W.keys[i]) == best
         and gtfs.hav(net.lat[top], net.lon[top], net.lat[i], net.lon[i]) <= 1000]
    return {'name': W.names[top], 'lat': round(float(np.mean(net.lat[c])), 6), 'lon': round(float(np.mean(net.lon[c])), 6)}


def show(r):
    q = r['query']
    print(f"{q['from_point']['name']} -> {q['to_point']['name']}, {q['depart'][11:]} {q['daytype']} ({q['pref']})")
    if not r['options']:
        print('no journey found:', r.get('reason'))
    for o in r['options']:
        print(f"\n[{o['label']}] {o['depart']} -> {o['arrive']}, {o['total_min']} min, {o['transfers']} change(s), "
              f"generalised {o['generalised_min']} min")
        for l in o['legs']:
            if l['mode'] == 'walk':
                print(f"  walk {l['min']} min to {l['to']}")
                continue
            c = l['crowding']
            print(f"  bus {l['route']} {l['dir']} towards {l['headsign']}: {l['board']} {l['depart']} -> {l['alight']} {l['arrive']}")
            print(f"    {c['level']} · {c['text']} · confidence {c['confidence']}, n={c['n']}, range {c['range']}")
        for s in r['suggestions']:
            if s['for'] != o['id']:
                continue
            if s['type'] == 'leave_later':
                print(f"  -> leave at {s['depart']} on {s['route']}: {s['level']}, seat chance {s['p_seat']}, "
                      f"{s['extra_min']} min later arrival")
            else:
                print(f"  -> walk {s['walk_min']} min to {s['stop']} and board there: seat chance {s['p_seat']}")
    if r['quiet_hour']:
        h = r['quiet_hour']
        print(f"\nat {h['time']} this is usually {h['total_min']} min, {h['level']}")


def cli(frm, to, hhmm='18:00', dt='weekday'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    W = world()
    a, b = point(W, frm), point(W, to)
    if a is None or b is None:
        raise SystemExit(f'no stop matches {frm if a is None else to!r}')
    t = time.time()
    h, m = (int(x) for x in hhmm.split(':'))
    r = plan(W, a, b, dtm.datetime(2026, 10, 28, h, m), dt)
    show(r)
    print(f'\n({time.time() - t:.2f}s)')
    return r
