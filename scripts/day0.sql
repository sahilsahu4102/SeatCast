-- # setup
CREATE OR REPLACE TABLE x AS
SELECT CAST(passenger_count AS INT) pc, CAST(amount AS DOUBLE) amt, vehicle_number v,
       ticket_type_id tt, start_stop_name ss, end_stop_name es, route r,
       CAST(regexp_replace(created_at, '\+05:30$', '') AS TIMESTAMP) ts,
       lower(is_ac) = 'true' ac,
       created_at LIKE '%+05:30' tz_ok
FROM read_csv('{csv}', header = true, nullstr = ['NULL', ''], all_varchar = true);
CREATE OR REPLACE TABLE y AS
SELECT *, ROUND(amt / pc, 2) fpp, nullif(regexp_extract(v, '^DL[0-9]+[A-Z]+', 0), '') series,
       CASE WHEN (ac AND ROUND(amt / pc, 2) IN (9, 13.5, 18, 22.5)) OR (NOT ac AND ROUND(amt / pc, 2) IN (4.5, 9, 13.5)) THEN 'std'
            WHEN ROUND(amt / pc, 2) >= 22 AND abs((ROUND(amt / pc, 2) - 22) / 4.5 - round((ROUND(amt / pc, 2) - 22) / 4.5)) < 1e-6 THEN 'ncr'
            WHEN (ac AND ROUND(amt / pc, 2) IN (10, 15, 20, 25)) OR (NOT ac AND ROUND(amt / pc, 2) IN (5, 10, 15)) THEN 'full'
            ELSE 'other' END fc
FROM x WHERE pc > 0;
-- # Rows, passengers, days, timezone check
SELECT COUNT(*) rows_n, SUM(pc) pax, COUNT(DISTINCT CAST(ts AS DATE)) n_days,
       ROUND(SUM(pc) * 1.0 / COUNT(*), 4) pax_per_ticket, COUNT(*) FILTER (WHERE NOT tz_ok) bad_tz,
       (SELECT COUNT(*) FROM x WHERE pc IS NULL OR pc <= 0) bad_pc FROM x;
-- # Fare class share (by passengers and by rows)
SELECT fc, SUM(pc) pax, ROUND(100.0 * SUM(pc) / SUM(SUM(pc)) OVER (), 2) pct_pax,
       COUNT(*) rows_n, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) pct_rows FROM y GROUP BY 1 ORDER BY 2 DESC;
-- # Ticket types and zero fares
SELECT tt, COUNT(*) rows_n, COUNT(*) FILTER (WHERE amt = 0) zero_fare_rows FROM x GROUP BY 1;
-- # Passenger count distribution
SELECT pc, COUNT(*) rows_n, ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 3) pct_rows FROM x GROUP BY 1 ORDER BY 1;
-- # NULL vehicle share
SELECT ROUND(100.0 * AVG(CASE WHEN v IS NULL THEN 1 ELSE 0 END), 2) pct_null_rows,
       ROUND(100.0 * SUM(CASE WHEN v IS NULL THEN pc ELSE 0 END) / SUM(pc), 2) pct_null_pax FROM x;
-- # Passengers per vehicle-day
SELECT quantile_cont(n, 0.5) q50, quantile_cont(n, 0.9) q90, quantile_cont(n, 0.99) q99, MAX(n) mx, COUNT(*) vehicle_days FROM (
  SELECT v, CAST(ts AS DATE) d, SUM(pc) n FROM x WHERE v IS NOT NULL GROUP BY 1, 2);
-- # Daily totals
SELECT CAST(ts AS DATE) d, dayname(ts) dow, SUM(pc) pax FROM x GROUP BY 1, 2 ORDER BY 1;
-- # Weekday hourly profile (Mon-Fri)
SELECT hour(ts) h, SUM(pc) pax FROM x WHERE isodow(ts) BETWEEN 1 AND 5 GROUP BY 1 ORDER BY 1;
-- # Saturday hourly profile
SELECT hour(ts) h, SUM(pc) pax FROM x WHERE isodow(ts) = 6 GROUP BY 1 ORDER BY 1;
-- # Sunday hourly profile
SELECT hour(ts) h, SUM(pc) pax FROM x WHERE isodow(ts) = 7 GROUP BY 1 ORDER BY 1;
-- # Series by AC: passengers and distinct vehicles
SELECT series, ac, SUM(pc) pax, COUNT(DISTINCT v) vehicles FROM y WHERE v IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 30;
-- # Series by route prefix (D- routes vs others)
SELECT series, CASE WHEN r LIKE 'D-%' THEN 'D-' ELSE 'other' END prefix, SUM(pc) pax, COUNT(DISTINCT r) route_codes
FROM y WHERE v IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 30;
-- # Top 20 route codes
SELECT r, SUM(pc) pax, COUNT(*) rows_n FROM x GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
