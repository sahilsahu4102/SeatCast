import time

import numpy as np

from seatcast import WORK, cfg
from seatcast import gtfs

INF = np.iinfo(np.int64).max // 4
BIT = {'weekday': 1, 'saturday': 2, 'sunday': 4}


def walk_s(m):
    w = cfg()['walk']
    return np.round(np.asarray(m) * w['detour'] / (w['speed_kmh'] / 3.6)).astype(np.int64)


def fifo(dep):
    # split trips (sorted by first departure) into groups where no trip overtakes another
    groups = []
    for i in range(len(dep)):
        for g in groups:
            if (dep[i] >= dep[g[-1]]).all():
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def sorted_cols(t):
    return bool((np.diff(t, axis=0) >= 0).all())


def footpaths(lat, lon, r):
    c = r / (111320 * np.cos(np.radians(np.abs(lat).max())))  # cell >= r in both axes, so 3x3 cells cover r
    gy, gx = np.floor(lat / c).astype(int), np.floor(lon / c).astype(int)
    cells = {}
    for i, k in enumerate(zip(gy, gx)):
        cells.setdefault(k, []).append(i)
    cells = {k: np.array(v) for k, v in cells.items()}
    a, b, m = [], [], []
    for (y, x), ii in cells.items():
        jj = [cells[(y + dy, x + dx)] for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (y + dy, x + dx) in cells]
        jj = np.concatenate(jj)
        d = gtfs.hav(lat[ii][:, None], lon[ii][:, None], lat[jj][None], lon[jj][None])
        p, q = np.nonzero((d <= r) & (ii[:, None] != jj[None]))
        a.append(ii[p]), b.append(jj[q]), m.append(d[p, q])
    a, b, m = np.concatenate(a), np.concatenate(b), np.concatenate(m)
    o = np.lexsort((b, a))
    return a[o], b[o], walk_s(m[o])


def csr(keys, n):
    return np.concatenate([[0], np.cumsum(np.bincount(keys, minlength=n))])


def build(d=None, w=WORK):
    t0 = time.time()
    d = gtfs.src(d)
    g = gtfs.load(d, w)
    pat, ps, tp = gtfs.patterns(g=g, w=w)
    s = g['stops']
    sidx = {k: i for i, k in enumerate(s['stop_id'])}
    st = g['stop_times']
    day = np.zeros(len(g['trips']), np.uint8)
    for n, b in BIT.items():
        day |= np.where(g['trips']['service_id'].isin(gtfs.services(g, cfg()['daytypes'][n])), b, 0).astype(np.uint8)
    tday = dict(zip(g['trips']['trip_id'], day))
    tid, off = np.unique(st['trip_id'].to_numpy(str), return_index=True)  # st is sorted by trip, sequence
    off = dict(zip(tid, off))
    sa, sd = st['arr'].to_numpy(np.int64), st['dep'].to_numpy(np.int64)
    pstops = {p: df['stop_id'].map(sidx).to_numpy() for p, df in ps.groupby('pattern_id', sort=False)}
    tp = tp.sort_values(['pattern_id', 'first', 'trip_id'], kind='stable')
    P = dict(pid=[], route=[], stops=[], trip=[], day=[], arr=[], dep=[])
    split = 0
    rid = dict(zip(pat['pattern_id'], pat['route_id']))
    for p, df in tp.groupby('pattern_id', sort=False):
        ids = df['trip_id'].to_numpy(str)
        n = len(pstops[p])
        D = np.array([sd[off[t]:off[t] + n] for t in ids])
        A = np.array([sa[off[t]:off[t] + n] for t in ids])
        gs = fifo(D)
        split += len(gs) - 1
        for gi in gs:
            assert sorted_cols(D[gi]) and sorted_cols(A[gi]), p
            P['pid'].append(p), P['route'].append(rid[p]), P['stops'].append(pstops[p])
            P['trip'].append(ids[gi]), P['day'].append(np.array([tday[t] for t in ids[gi]], np.uint8))
            P['arr'].append(A[gi].ravel()), P['dep'].append(D[gi].ravel())
    ns = np.array([len(x) for x in P['stops']])
    nt = np.array([len(x) for x in P['trip']])
    pat_stop = np.concatenate(P['stops'])
    pat_of = np.repeat(np.arange(len(ns)), ns)
    pos = np.concatenate([np.arange(n) for n in ns])
    o = np.lexsort((pos, pat_of, pat_stop))
    lat, lon = s['stop_lat'].to_numpy(), s['stop_lon'].to_numpy()
    fa, fb, fs = footpaths(lat, lon, cfg()['walk']['transfer_m'])
    mt = max(f.stat().st_mtime for f in d.glob('*.txt'))
    np.savez(w / 'network.npz', src=np.array(f'{d}|{mt}'), stop_id=s['stop_id'].to_numpy(str), stop_name=s['stop_name'].to_numpy(str),
             lat=lat, lon=lon, pid=np.array(P['pid'], str), route=np.array(P['route'], str),
             pat_ptr=np.concatenate([[0], np.cumsum(ns)]), pat_stop=pat_stop,
             trip_ptr=np.concatenate([[0], np.cumsum(nt)]), trip=np.concatenate(P['trip']).astype(str),
             day=np.concatenate(P['day']), time_ptr=np.concatenate([[0], np.cumsum(ns * nt)]),
             arr=np.concatenate(P['arr']).astype(np.int32), dep=np.concatenate(P['dep']).astype(np.int32),
             sp_ptr=csr(pat_stop, len(s)), sp_pat=pat_of[o], sp_pos=pos[o],
             fp_ptr=csr(fa, len(s)), fp_to=fb, fp_sec=fs)
    print(f'network: {len(s)} stops, {len(ns)} routing patterns ({split} from overtaking splits), '
          f'{nt.sum()} trips, {len(fa)} footpaths, {time.time() - t0:.1f}s')


class Net:
    def __init__(self, z):
        self.__dict__.update({k: z[k] for k in z.files})
        self.views = {}

    def view(self, dt):
        # per routing pattern: (stops, dep[T, n], arr[T, n], trip rows) for trips running on day type dt
        if dt not in self.views:
            v = []
            for p in range(len(self.pid)):
                a, b = self.pat_ptr[p], self.pat_ptr[p + 1]
                t0, t1 = self.trip_ptr[p], self.trip_ptr[p + 1]
                n = b - a
                m = (self.day[t0:t1] & BIT[dt]) > 0
                T = slice(self.time_ptr[p], self.time_ptr[p + 1])
                v.append((self.pat_stop[a:b], self.dep[T].reshape(-1, n)[m].astype(np.int64),
                          self.arr[T].reshape(-1, n)[m].astype(np.int64), np.flatnonzero(m) + t0))
            self.views[dt] = v
        return self.views[dt]


def load(d=None, rebuild=False, w=WORK):
    d, f = gtfs.src(d), w / 'network.npz'
    mt = max(x.stat().st_mtime for x in d.glob('*.txt'))
    if not rebuild and f.exists():
        z = np.load(f)
        if str(z['src']) == f'{d}|{mt}':
            return Net(z)
    build(d, w)
    return Net(np.load(f))


def near(net, lat, lon, r=None):
    r = r or cfg()['walk']['access_m']
    m = gtfs.hav(lat, lon, net.lat, net.lon)
    i = np.flatnonzero(m <= r)
    return list(zip(i.tolist(), walk_s(m[i]).tolist()))


def query(net, src, dst, t0, dt='weekday', ban=(), K=None, window=None):
    # src, dst: [(stop index, walk seconds)]; t0: seconds past midnight. Pareto journeys by (arrival, rides).
    pl = cfg()['planner']
    K = K or pl['max_transfers'] + 1
    end = t0 + 60 * (window or pl['window_min'])
    chg = pl.get('change_s', 0)
    V, S = net.view(dt), len(net.stop_id)
    ban = set(ban)
    tau = np.full((K + 1, S), INF, np.int64)
    ride = np.full((K + 1, S), INF, np.int64)
    best = np.full(S, INF, np.int64)
    par = np.full((K + 1, S, 4), -1, np.int64)  # ride: pattern, trip row in view, board pos, alight pos
    wfrom = np.full((K + 1, S), -1, np.int64)
    egress = dict(dst)
    for s, w in src:
        if t0 + w < tau[0, s]:
            tau[0, s] = best[s] = t0 + w
    marked = {s for s, _ in src}
    tbest = min((tau[0, s] + w for s, w in dst if tau[0, s] < INF), default=INF)
    for k in range(1, K + 1):
        Q = {}
        for s in marked:
            for j in range(net.sp_ptr[s], net.sp_ptr[s + 1]):
                p, i = net.sp_pat[j], net.sp_pos[j]
                if len(V[p][1]) and net.route[p] not in ban and i < len(V[p][0]) - 1:
                    Q[p] = min(Q.get(p, i), i)
        imp = []
        for p, i0 in Q.items():
            stops, D, A, _ = V[p]
            r, b = -1, -1
            for i in range(i0, len(stops)):
                s = stops[i]
                if r >= 0 and A[r, i] < min(best[s], tbest):
                    ride[k, s] = tau[k, s] = best[s] = A[r, i]
                    par[k, s] = (p, r, b, i)
                    imp.append(s)
                    if s in egress:
                        tbest = min(tbest, A[r, i] + egress[s])
                tp = tau[k - 1, s]
                if tp < INF and (r < 0 or tp + (chg if k > 1 else 0) <= D[r, i]):
                    x = np.searchsorted(D[:, i], tp + (chg if k > 1 else 0))
                    if x < len(D) and D[x, i] <= end and (r < 0 or x < r):
                        r, b = x, i
        marked = set(imp)
        for s in imp:
            for j in range(net.fp_ptr[s], net.fp_ptr[s + 1]):
                q, w = net.fp_to[j], net.fp_sec[j]
                a = ride[k, s] + w
                if a < min(best[q], tbest) and a < tau[k, q]:
                    tau[k, q] = best[q] = a
                    wfrom[k, q] = s
                    marked.add(q)
                    if q in egress:
                        tbest = min(tbest, a + egress[q])
        if not marked:
            break
    return pareto(net, V, tau, ride, par, wfrom, src, dst, K)


def pareto(net, V, tau, ride, par, wfrom, src, dst, K):
    out, last = [], INF
    acc = dict(src)
    for k in range(1, K + 1):
        c = [(tau[k, s] + w, s, w) for s, w in dst if tau[k, s] < INF]
        if not c:
            continue
        a, s, w = min(c)
        if a >= last:
            continue
        last = a
        legs = trace(net, V, ride, par, wfrom, k, s, tau)
        legs.insert(0, {'mode': 'walk', 'from': None, 'to': legs[0]['board'], 'sec': acc[legs[0]['board']]})
        legs.append({'mode': 'walk', 'from': s, 'to': None, 'sec': w})
        out.append({'arrive': int(a), 'rides': k, 'legs': legs})
    return out


def trace(net, V, ride, par, wfrom, k, s, tau):
    legs = []
    while k > 0:
        if tau[k, s] < ride[k, s]:
            f = int(wfrom[k, s])
            legs.append({'mode': 'walk', 'from': f, 'to': s, 'sec': int(tau[k, s] - ride[k, f])})
            s = f
        p, r, b, i = (int(x) for x in par[k, s])
        stops, D, A, rows = V[p]
        legs.append({'mode': 'bus', 'pattern': str(net.pid[p]), 'route_id': str(net.route[p]), 'rp': p,
                     'trip_id': str(net.trip[rows[r]]), 'k1': b, 'k2': i,
                     'board': int(stops[b]), 'alight': int(stops[i]),
                     'dep': int(D[r, b]), 'arr': int(A[r, i]), 'times': D[r, b:i + 1].tolist()})
        s, k = int(stops[b]), k - 1
    return legs[::-1]


def names(net, j):
    n = net.stop_name
    out = []
    for l in j['legs']:
        if l['mode'] == 'bus':
            out.append(f"{l['route_id']} {n[l['board']]} {hm(l['dep'])} -> {n[l['alight']]} {hm(l['arr'])}")
        else:
            out.append(f"walk {l['sec'] // 60} min")
    return f"arrive {hm(j['arrive'])}, {j['rides']} ride(s): " + ' | '.join(out)


def hm(t):
    return f'{t // 3600:02d}:{t // 60 % 60:02d}'


if __name__ == '__main__':
    import sys
    t = time.time()
    net = load(rebuild='--rebuild' in sys.argv)
    print(f'load {time.time() - t:.2f}s')
    a, b = net.stop_id.tolist().index('2'), net.stop_id.tolist().index('7587')
    t = time.time()
    js = query(net, near(net, net.lat[a], net.lon[a]), near(net, net.lat[b], net.lon[b]), 6 * 3600, 'weekday')
    print(f'query {time.time() - t:.3f}s')
    for j in js:
        print(names(net, j))
