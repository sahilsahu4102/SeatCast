import duckdb
import pandas as pd

from seatcast import WORK, cfg, gtfs

P3 = WORK / 'p3'

SEG = '''
WITH s AS (
  SELECT trip_id, stop_id s0, lead(stop_id) OVER w s1, dep d0, lead(dep) OVER w d1
  FROM st WINDOW w AS (PARTITION BY trip_id ORDER BY stop_sequence))
SELECT tr.route_id, s0, s1, a.daytype, CAST((d0 % 86400) // $q AS INT) slot,
       COUNT(*) n, median(d1 - d0) sec
FROM s JOIN tr USING (trip_id) JOIN a USING (service_id)
WHERE s1 IS NOT NULL
GROUP BY ALL
'''

OFF = '''
WITH s AS (
  SELECT tp.pattern_id, CAST(row_number() OVER w - 1 AS INT) k, dep - first_value(dep) OVER w c,
         CAST((tp.first // 3600) % 24 AS INT) h
  FROM st JOIN tp USING (trip_id) WINDOW w AS (PARTITION BY st.trip_id ORDER BY stop_sequence))
SELECT pattern_id, k, h, median(c) cum FROM s GROUP BY ALL
UNION ALL
SELECT pattern_id, k, -1, median(c) FROM s GROUP BY ALL
'''


def active(g):
    # (service_id, daytype) from calendar weekday flags; date ranges ignored (feed is newer than October)
    r = [(s, t) for t, days in cfg()['daytypes'].items() for s in gtfs.services(g, days)]
    return pd.DataFrame(r, columns=['service_id', 'daytype'])


def segs(st, tr, a):
    # N: trips of a route running stop s0 -> s1 consecutively and leaving s0 in each slot, per day type
    con = duckdb.connect()
    con.register('st', st[['trip_id', 'stop_sequence', 'stop_id', 'dep']])
    con.register('tr', tr[['trip_id', 'route_id', 'service_id']])
    con.register('a', a)
    return con.execute(SEG, {'q': cfg()['slot_min'] * 60}).df()


def offsets(st, tp):
    # cum[k, h]: median seconds from stop 0 to stop k over trips leaving stop 0 in hour h; h = -1 is all day
    con = duckdb.connect()
    con.register('st', st[['trip_id', 'stop_sequence', 'dep']])
    con.register('tp', tp)
    return con.sql(OFF).df()


def fresh(fs):
    src = gtfs.src() / 'stop_times.txt'
    return all(f.exists() and f.stat().st_mtime > src.stat().st_mtime for f in fs)


def run(force=False):
    fs = [WORK / 'service.parquet', WORK / 'offsets.parquet', P3 / 'patterns.parquet', P3 / 'pattern_stops.parquet',
          P3 / 'trip_pattern.parquet']
    if not force and fresh(fs):
        return
    P3.mkdir(parents=True, exist_ok=True)
    g = gtfs.load(w=P3)
    pat, ps, tp = gtfs.patterns(g=g, w=P3)
    tp.merge(g['trips'][['trip_id', 'shape_id']], on='trip_id').to_parquet(P3 / 'trip_pattern.parquet', index=False)
    a = active(g)
    sv = segs(g['stop_times'], g['trips'], a)
    sv.to_parquet(WORK / 'service.parquet', index=False)
    offsets(g['stop_times'], tp).to_parquet(WORK / 'offsets.parquet', index=False)
    one = g['calendar'] is not None and len(g['calendar']) == 1
    print(f'service: {len(sv)} route-segment-slot-daytype rows, {int(sv["n"].sum())} trip-segments, '
          f'{len(pat)} patterns; single all-days service: {one}')
