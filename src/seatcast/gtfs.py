import html

import numpy as np
import pandas as pd

from seatcast import RAW, ROOT, WORK, cfg

TABLES = ['stops', 'routes', 'trips', 'stop_times', 'calendar', 'shapes']
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
IDS = ['stop_id', 'route_id', 'trip_id', 'service_id', 'shape_id', 'agency_id']


def src(d=None):
    if d:
        return ROOT / d  # absolute d wins over ROOT
    return RAW / 'gtfs' if (RAW / 'gtfs' / 'stops.txt').exists() else RAW / 'gtfs_sample'


def secs(s):
    p = s.str.strip().str.split(':', expand=True)
    return (p[0].astype(float) * 3600 + p[1].astype(float) * 60 + p[2].astype(float)).astype('Int64')


def hav(lat1, lon1, lat2, lon2):
    a, b, c, d = map(np.radians, (lat1, lon1, lat2, lon2))
    h = np.sin((c - a) / 2) ** 2 + np.cos(a) * np.cos(c) * np.sin((d - b) / 2) ** 2
    return 2 * 6371000 * np.arcsin(np.sqrt(h))


def read(d, n):
    f = d / f'{n}.txt'
    if not f.exists():
        return None
    df = pd.read_csv(f, dtype=str, keep_default_na=False, na_values=[''], encoding='utf-8-sig')
    df.columns = df.columns.str.strip()
    if n == 'stops':
        df['stop_name'] = df['stop_name'].map(html.unescape).str.strip()
        df[['stop_lat', 'stop_lon']] = df[['stop_lat', 'stop_lon']].astype(float)
    if n == 'stop_times':
        df['arr'], df['dep'] = secs(df['arrival_time']), secs(df['departure_time'])
        df['stop_sequence'] = df['stop_sequence'].astype(int)
        for c in ['shape_dist_traveled', 'stop_dist']:
            if c in df:
                df[c] = df[c].astype(float)
        df = df.sort_values(['trip_id', 'stop_sequence'], kind='stable').reset_index(drop=True)
        if df['dep'].isna().any() or df['arr'].isna().any():
            df = fill(df)
    if n == 'shapes':
        df[['shape_pt_lat', 'shape_pt_lon']] = df[['shape_pt_lat', 'shape_pt_lon']].astype(float)
        df['shape_pt_sequence'] = df['shape_pt_sequence'].astype(int)
        if 'shape_dist_traveled' in df:
            df['shape_dist_traveled'] = df['shape_dist_traveled'].astype(float)
        df = df.sort_values(['shape_id', 'shape_pt_sequence'], kind='stable').reset_index(drop=True)
    if n == 'calendar':
        df[DAYS] = df[DAYS].astype(int)
    return df


def fill(st):
    # untimed stops: interpolate linearly by stop_sequence within each trip
    for c in ['arr', 'dep']:
        st[c] = st[c].fillna(st['dep' if c == 'arr' else 'arr'])
        x = st[c].astype(float)
        st[c] = x.groupby(st['trip_id']).transform(lambda v: v.interpolate(limit_area='inside')).round().astype('Int64')
    return st


def orphans(g):
    # the official sample is head-truncated: its stop_times trips are not in trips.txt.
    # trip_id looks like <route_id>_HH_MM (full feed: <route_id>_FULL_HH_MM), so recover route_id and warn.
    t = g['stop_times']['trip_id'].drop_duplicates()
    t = t[~t.isin(g['trips']['trip_id'])]
    if t.empty:
        return g
    sv = g['calendar']['service_id']
    r = t.str.extract(r'^([^_]+)_')[0]
    ok = r.isin(g['routes']['route_id']) & (len(sv) == 1)
    print(f'WARNING gtfs: {len(t)} trips in stop_times are missing from trips.txt; '
          f'recovered {int(ok.sum())} from trip_id, dropped {int((~ok).sum())}')
    add = pd.DataFrame({'route_id': r[ok], 'service_id': sv.iloc[0] if len(sv) == 1 else None, 'trip_id': t[ok]})
    g['trips'] = pd.concat([g['trips'], add], ignore_index=True)
    g['stop_times'] = g['stop_times'][g['stop_times']['trip_id'].isin(g['trips']['trip_id'])].reset_index(drop=True)
    return g


def load(d=None, w=WORK):
    d = src(d)
    c = w / 'gtfs' / d.name
    c.mkdir(parents=True, exist_ok=True)
    g = {}
    for n in TABLES:
        f, p = d / f'{n}.txt', c / f'{n}.parquet'
        if p.exists() and f.exists() and p.stat().st_mtime > f.stat().st_mtime:
            g[n] = pd.read_parquet(p)
            continue
        g[n] = read(d, n)
        if g[n] is not None:
            g[n].to_parquet(p, index=False)
    if (d / 'frequencies.txt').exists():
        print('WARNING gtfs: frequencies.txt present but not expanded; headway-based trips are missing')
    return orphans(g)


def services(g, days):
    # service_ids running on most of the given weekday numbers (Mon = 0); date ranges ignored
    c = g['calendar']
    return set(c.loc[c[[DAYS[i] for i in days]].sum(axis=1) * 2 > len(days), 'service_id'])


def snap(lat, lon, sh):
    # along-shape distance per stop: first close shape point at or after the previous one, then its local minimum
    if sh is None or 'shape_dist_traveled' not in sh or sh['shape_dist_traveled'].isna().any():
        return None
    y, x, s = sh['shape_pt_lat'].to_numpy(), sh['shape_pt_lon'].to_numpy(), sh['shape_dist_traveled'].to_numpy()
    out, j = [], 0
    for a, b in zip(lat, lon):
        dd = hav(a, b, y[j:], x[j:])
        near = np.flatnonzero(dd < 100)
        if near.size == 0:
            return None
        i = near[0]
        while i + 1 < dd.size and dd[i + 1] <= dd[i]:
            i += 1
        j += i
        out.append(s[j])
    return np.array(out)


def dist(ps, st, sh):
    # dist_m per pattern stop: stop_times shape_dist_traveled, else shape projection, else haversine x detour
    for c in ['shape_dist_traveled', 'stop_dist']:
        if c in st and st[c].notna().all():
            return st[c].to_numpy(float) - st[c].iloc[0], c
    s = snap(ps['lat'].to_numpy(), ps['lon'].to_numpy(), sh)
    if s is not None:
        return s - s[0], 'shape'
    h = hav(ps['lat'].to_numpy()[:-1], ps['lon'].to_numpy()[:-1], ps['lat'].to_numpy()[1:], ps['lon'].to_numpy()[1:])
    return np.concatenate([[0], np.cumsum(h)]) * cfg()['walk']['detour'], 'haversine'


def patterns(d=None, g=None, w=WORK):
    g = g or load(d, w)
    st, tr = g['stop_times'], g['trips']
    seq = st.groupby('trip_id', sort=False)['stop_id'].agg('|'.join).rename('seq').reset_index()
    seq = seq.merge(tr[['trip_id', 'route_id'] + (['shape_id'] if 'shape_id' in tr else [])], on='trip_id')
    seq['first'] = st.groupby('trip_id', sort=False)['dep'].first().reindex(seq['trip_id']).to_numpy()
    n = seq.groupby(['route_id', 'seq']).size().rename('n_trips').reset_index()
    n = n.sort_values(['route_id', 'n_trips', 'seq'], ascending=[True, False, True], kind='stable')
    n['i'] = n.groupby('route_id').cumcount()
    n['pattern_id'] = n['route_id'] + ':' + n['i'].astype(str)
    n['canonical'] = n['i'] == 0
    n['n_stops'] = n['seq'].str.count(r'\|') + 1
    tp = seq.merge(n[['route_id', 'seq', 'pattern_id']], on=['route_id', 'seq'])[['trip_id', 'pattern_id', 'first']]
    ps, how = stops_of(n, tp, g)
    pat = n[['pattern_id', 'route_id', 'n_trips', 'n_stops', 'canonical']].reset_index(drop=True)
    pat['dist_src'] = pat['pattern_id'].map(how)
    pat.to_parquet(w / 'patterns.parquet', index=False)
    ps.to_parquet(w / 'pattern_stops.parquet', index=False)
    return pat, ps, tp


def stops_of(n, tp, g):
    st, tr, s = g['stop_times'], g['trips'], g['stops'].set_index('stop_id')
    sh = dict(tuple(g['shapes'].groupby('shape_id'))) if g['shapes'] is not None else {}
    rep = tp.groupby('pattern_id')['trip_id'].first()
    shp = tr.set_index('trip_id')['shape_id'] if 'shape_id' in tr else pd.Series(dtype=str)
    byt = dict(tuple(st[st['trip_id'].isin(rep.values)].groupby('trip_id')))
    out, how = [], {}
    for p, seq in zip(n['pattern_id'], n['seq']):
        ids = seq.split('|')
        df = pd.DataFrame({'pattern_id': p, 'k': range(len(ids)), 'stop_id': ids})
        df['lat'], df['lon'] = s.loc[ids, 'stop_lat'].to_numpy(), s.loc[ids, 'stop_lon'].to_numpy()
        t = rep[p]
        df['dist_m'], how[p] = dist(df, byt[t].reset_index(drop=True), sh.get(shp.get(t)))
        out.append(df)
    return pd.concat(out, ignore_index=True), how


if __name__ == '__main__':
    pat, ps, tp = patterns()
    print(pat.to_string())
    print(ps.groupby('pattern_id')['dist_m'].max())
