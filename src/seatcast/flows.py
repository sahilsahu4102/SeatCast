import json
import time

import duckdb

from seatcast import WORK, cfg, service

P3 = service.P3

# empirical other-end distribution of placed tickets, per known end; level 1 = same hour, 2 = day type, 3 = any
DIST = '''
CREATE TABLE dist AS
SELECT pattern_id, 'b' e, b k, a o, hour(ts) hr, daytype, SUM(pc) w FROM od GROUP BY ALL
UNION ALL
SELECT pattern_id, 'a' e, a k, b o, hour(ts) hr, daytype, SUM(pc) w FROM od GROUP BY ALL;
CREATE TABLE l1 AS SELECT pattern_id, e, k, hr, o, SUM(w) w FROM dist GROUP BY ALL;
CREATE TABLE l2 AS SELECT pattern_id, e, k, daytype, o, SUM(w) w FROM dist GROUP BY ALL;
CREATE TABLE l3 AS SELECT pattern_id, e, k, o, SUM(w) w FROM dist GROUP BY ALL;
'''

PICK = '''
CREATE TABLE pick AS
WITH t1 AS (SELECT pattern_id, e, k, hr, SUM(w) tot FROM l1 GROUP BY ALL),
t2 AS (SELECT pattern_id, e, k, daytype, SUM(w) tot FROM l2 GROUP BY ALL),
t3 AS (SELECT pattern_id, e, k, SUM(w) tot FROM l3 GROUP BY ALL)
SELECT p.*, hour(p.ts) hr,
       CASE WHEN t1.tot >= $m THEN 1 WHEN t2.tot >= $m THEN 2 WHEN t3.tot >= $m THEN 3 END lvl,
       CASE WHEN t1.tot >= $m THEN t1.tot WHEN t2.tot >= $m THEN t2.tot ELSE t3.tot END tot
FROM part p
LEFT JOIN t1 ON t1.pattern_id = p.pattern_id AND t1.e = p.e AND t1.k = p.k AND t1.hr = hour(p.ts)
LEFT JOIN t2 ON t2.pattern_id = p.pattern_id AND t2.e = p.e AND t2.k = p.k AND t2.daytype = p.daytype
LEFT JOIN t3 ON t3.pattern_id = p.pattern_id AND t3.e = p.e AND t3.k = p.k
'''

IMP = '''
CREATE TABLE imp AS
SELECT p.tid, p.route_id, p.pattern_id, CASE WHEN p.e = 'b' THEN p.k ELSE l.o END b,
       CASE WHEN p.e = 'b' THEN l.o ELSE p.k END a, p.pc * l.w / p.tot w, p.ts, p.date, p.daytype, p.week
FROM pick p JOIN (
  SELECT 1 lvl, pattern_id, e, k, hr, CAST(NULL AS VARCHAR) daytype, o, w FROM l1
  UNION ALL SELECT 2, pattern_id, e, k, CAST(NULL AS BIGINT), daytype, o, w FROM l2
  UNION ALL SELECT 3, pattern_id, e, k, NULL, NULL, o, w FROM l3) l
ON l.lvl = p.lvl AND l.pattern_id = p.pattern_id AND l.e = p.e AND l.k = p.k
   AND (l.lvl <> 1 OR l.hr = p.hr) AND (l.lvl <> 2 OR l.daytype = p.daytype)
'''

# every digital passenger on a matched route code: placed + imputed, scaled up to the code's total
TK = '''
CREATE TABLE rep AS
SELECT tid, SUM(w) FILTER (WHERE NOT imp) wp, SUM(w) FILTER (WHERE imp) wi FROM (
  SELECT tid, pc w, false imp FROM od UNION ALL SELECT tid, w, true FROM imp) GROUP BY tid;
CREATE TABLE scale AS
SELECT t.route_raw, SUM(t.pc) pax, coalesce(SUM(r.wp), 0) placed, coalesce(SUM(r.wi), 0) imputed,
       SUM(t.pc) / nullif(coalesce(SUM(r.wp), 0) + coalesce(SUM(r.wi), 0), 0) scale
FROM tickets t LEFT JOIN rep r USING (tid) GROUP BY 1;
CREATE TABLE tk AS
SELECT x.*, x.w * s.scale ws FROM (
  SELECT tid, route_id, pattern_id, b, a, CAST(pc AS DOUBLE) w, ts, date, daytype, week FROM od
  UNION ALL SELECT * FROM imp) x
JOIN (SELECT tid, route_raw FROM tickets) t USING (tid) JOIN scale s USING (route_raw);
'''

# expand each ticket to the segments it rides; slot = time the bus passes stop k (ts + offset b -> k)
DAILY = '''
WITH t0 AS (
  SELECT t.*, hour(ts) * 3600 + minute(ts) * 60 + second(ts) sod, o.cum cb0 FROM tk t
  JOIN off o ON o.pattern_id = t.pattern_id AND o.k = t.b AND o.h = -1),
t1 AS (
  SELECT t0.*, CASE WHEN o.cum IS NULL THEN -1 ELSE o.h END hh, coalesce(o.cum, cb0) cb FROM t0
  LEFT JOIN off o ON o.pattern_id = t0.pattern_id AND o.k = t0.b
   AND o.h = CAST((((sod - cb0) % 86400 + 86400) % 86400) // 3600 AS INT)),
x AS (SELECT *, unnest(range(b, a)) k FROM t1)
SELECT x.route_id, s.s0, s.s1, LEAST($last, GREATEST(0, CAST(floor((sod + o.cum - cb) / $q) AS INT))) slot,
       x.daytype, x.date, x.week, SUM(ws) pax, SUM(w) n
FROM x JOIN off o ON o.pattern_id = x.pattern_id AND o.k = x.k AND o.h = x.hh
JOIN seg s ON s.pattern_id = x.pattern_id AND s.k = x.k
GROUP BY ALL
'''


def daily(con):
    q = cfg()['slot_min'] * 60
    return con.execute(DAILY, {'q': q, 'last': 86400 // q - 1})


def impute(con, m):
    con.execute(DIST)
    con.execute(PICK, {'m': m})
    con.execute(IMP)


def seg(con, ps):
    con.register('ps', ps)
    con.execute('CREATE TABLE seg AS SELECT pattern_id, CAST(k AS INT) k, stop_id s0, '
                'lead(stop_id) OVER (PARTITION BY pattern_id ORDER BY k) s1 FROM ps')
    con.execute('DELETE FROM seg WHERE s1 IS NULL')


def read(con, name, f, tries=5):
    # P2 may be rewriting its outputs; retry a failed read
    for i in range(tries):
        try:
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet('{f.as_posix()}')")
            return
        except duckdb.Error:
            if i == tries - 1:
                raise
            time.sleep(10)


def run():
    t0 = time.time()
    service.run()
    con = duckdb.connect()
    read(con, 'od', WORK / 'od.parquet')
    read(con, 'tickets', WORK / 'tickets.parquet')
    read(con, 'off', WORK / 'offsets.parquet')
    read(con, 'ps', P3 / 'pattern_stops.parquet')
    seg(con, con.table('ps').df())
    f = WORK / 'od_partial.parquet'
    if f.exists():
        read(con, 'part0', f)
        con.execute('CREATE TABLE part AS SELECT tid, route_id, pattern_id, CAST(k AS INT) k, "end" e, pc, ts, '
                    'date, daytype, week FROM part0')
    else:
        con.execute('CREATE TABLE part AS SELECT tid, route_id, pattern_id, b k, \'b\' e, pc, ts, date, daytype, '
                    'week FROM od WHERE false')
    impute(con, cfg()['impute_min_n'])
    con.execute(TK)
    daily(con).df().to_parquet(WORK / 'flows.parquet', index=False)
    con.table('scale').df().to_parquet(WORK / 'scale.parquet', index=False)
    s = summary(con, f.exists())
    (WORK / 'flows_summary.json').write_text(json.dumps(s, indent=2))
    print(json.dumps(s, indent=2))
    print(f'flows: {time.time() - t0:.0f}s')


def summary(con, has_part):
    r = con.sql('''SELECT SUM(pax) pax, SUM(placed) placed, SUM(imputed) imputed,
        SUM(pax) FILTER (WHERE scale IS NULL) lost, SUM(pax) FILTER (WHERE scale IS NOT NULL) kept FROM scale''').df()
    r = r.iloc[0].to_dict()
    p = con.sql('''SELECT lvl, SUM(pc) pax FROM pick GROUP BY 1 ORDER BY 1''').fetchall()
    q = con.execute('''SELECT quantile_cont(scale, [0.1, 0.5, 0.9, 0.99]) q, MAX(scale) mx,
        SUM(pax) FILTER (WHERE scale > 2) / SUM(pax) big FROM scale
        WHERE scale IS NOT NULL''').fetchall()[0]
    w = con.execute('''SELECT quantile_cont(scale, [0.1, 0.5, 0.9, 0.99]) FROM (
        SELECT s.scale FROM tk JOIN (SELECT tid, route_raw FROM tickets) USING (tid) JOIN scale s USING (route_raw))''').fetchall()[0]
    tot = r['pax']
    return {
        'passengers': int(tot),
        'placed_pax': round(r['placed'], 1),
        'imputed_pax': round(r['imputed'], 1),
        'od_partial_used': has_part,
        'impute_level_pax': {str(k): float(v) for k, v in p},
        'represented_pct': round(100 * (r['placed'] + r['imputed']) / tot, 2),
        'scaled_codes_pax_pct': round(100 * r['kept'] / tot, 2),
        'lost_pax_pct': round(100 * r['lost'] / tot, 2),
        'scale_by_code_q10_50_90_99': [round(x, 3) for x in q[0]],
        'scale_max': round(q[1], 2),
        'pax_pct_on_codes_scale_gt_2': round(100 * q[2], 2),
        'scale_ticket_weighted_q10_50_90_99': [round(x, 3) for x in w[0]],
    }
