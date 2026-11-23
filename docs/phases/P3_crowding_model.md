# P3 — Crowding model

**Goal:** a cell table with load, uncertainty, seat probability, level and confidence for every (route, direction, segment, 30-min slot, day type), plus operator metrics. **Time box:** 3.5 h.
**Lane:** A. **Agent:** `sous-chef` for `flows.py` and `load.py`; `line-cook` for `service.py` scaffolding. **Depends on:** P2 (`od.parquet`, patterns).

Method: CLAUDE.md §4.3 steps 8–17 and §4.5. Decisions: THINKING D-01, D-03, D-05, D-06, D-07.

## Outputs
- `data/work/service.parquet` (N and run times)
- `data/work/flows.parquet` (daily and weekly flows)
- `data/out/cells.parquet`, `data/out/segments.geojson`, `data/out/route_profiles.json`
- `data/out/operator.parquet`
- `coverage.json` (E section, anomaly days)

## Steps

1. **`service.py`: buses and run times**
   - **Cumulative scheduled minutes** per pattern and hour: `cum[k, h]` = median over trips leaving stop 0 in hour h of `(dep_k − dep_0)`. Then offset Δ(b→k) = `cum[k,h] − cum[b,h]` and segment minutes = `cum[k+1,h] − cum[k,h]`. This is O(stops) per pattern, not O(stops²).
   - **N(cell)** = trips of the `route_id` (any pattern) that run stop k → stop k+1 consecutively and depart stop k in slot b, on day type t.
     - Use `calendar.txt` weekday flags and ignore its date ranges (the feed is newer than October).
     - If the feed has one all-days service, N is the same for every day type. Say so in CHECKS.
   - Optional `service_scale[route, daytype]` from the P4b GPS delivery ratio; default 1.0.

2. **`flows.py`: pooled digital flows** (DuckDB)
   ```sql
   SELECT o.route_id, k, o.date, o.daytype, o.week,
          CAST(floor((minute_of_day(o.ts) + d.delta_min) / 30) AS INT) AS slot,
          SUM(o.pc) AS pax
   FROM od o, UNNEST(range(o.b, o.a)) AS u(k)
   JOIN offsets d USING (pattern_id, b, k, hour)
   GROUP BY ALL;
   ```
   About 20 M ticket-segment rows, fine in DuckDB.
   - Clip slots past 47 (after midnight, rare).
   - **Mean daily flow** f = Σ_dates pax / n_days(t). n_days(t) counts **all** non-anomalous dates of day type t, including dates with zero flow on that cell. Dividing by "dates with data" would bias every estimate upward.
   - Also keep n_cell (total sampled passengers), cv_day (std/mean of daily flows over the same n_days; 0.5 if fewer than 3 dates have data), and weekly flows per (route, segment, hour) for ρ.

3. **`load.py`: expansion, load, uncertainty**
   - D_daily = total passengers / 31 (expect 88,826 from DAY0).
   - E_central = 3,960,000 / D_daily, E_high = 4,080,000 / D_daily, E_low = 0.7 × E_central. Expect about 44.6 / 45.9 / 31.2. All three come from `config.yaml`; none is typed into code.
   - Optional `data/calib/route_totals.csv` overrides E per route and day type.
   - **L = E · f / N**, with L_low and L_high.
   - **Capacity per route:** the passenger-weighted mix of vehicle series seen on it (`config/series_capacity.csv`), falling back to its majority `is_ac`. The DEVi series found in P1 gets 23 seats / 36 total.
   - cv² = 1/max(n_cell, 1) + cv_day² + run_cv²; then `p_seat(L, seats, cv)` (CLAUDE.md §4.3 step 14); then LF = L / seats.
   - **Level:** CLAUDE.md §4.3 step 15 thresholds. Compute it for L_low and L_high too, so the UI can show a range.
   - **NO_DATA** when n_cell < `min_cell_n` (5), or when N = 0 but f > 0 (schedule gap; flag it).
   - **Confidence:** ρ per route is the mean pairwise Spearman across the 4 weeks over segment × hour flows (pandas `corr('spearman')`, no SciPy). High = n ≥ 30 and ρ ≥ 0.7; medium = n ≥ 10; otherwise low.

4. **Geometry and profiles**
   - `segments.geojson`: one LineString per (route_id, k), cut from `shapes.txt` by `shape_dist_traveled` between the two stops' projected positions. Fall back to a straight stop-to-stop line. Properties: route, direction, k, from_stop, to_stop. Levels are joined at query time by the API.
   - `route_profiles.json`: per route, direction and day type, the load by segment for each hour. This drives the operator's load-profile chart.

5. **Operator metrics** (CLAUDE.md §4.5, computed here and served in P5)
   - Peak hourly flow at the max-load segment, F_req = ⌈peak ÷ (0.8 × total)⌉, F_sched, gap.
   - Standee-minutes = Σ_k N × max(0, L − seats) × segment minutes.
   - **+1 bus benefit** = standee-minutes now − standee-minutes with L' = L·N/(N+1).
   - Write `operator.parquet`, top 20 per day type and period (am / pm / all).

## Done when
- `tests/test_pseat.py` passes. With seats = 39 and cv = 0.45, P(seat) = 0.96 / 0.68 / 0.45 / 0.22 at L = 20 / 35 / 45 / 60 (±0.01).
- `tests/test_flows.py` passes: two tickets on a 4-stop toy route give the expected per-segment flows, and a zero-flow date lowers f.
- **Gate G3:**
  - LF distribution is sane, and < 1% of cells have L > 3 × total capacity.
  - The 10 most crowded route-hours fall in 07:00–10:00 or 17:00–20:00 on weekdays.
  - Weekday loads exceed Sunday loads on the same cells.
  - Failures get listed, flagged as schedule or match errors and set to NO_DATA, never silently clipped.

## Gotchas
- Never use `vehicle_number` beyond the capacity mix; `cells.parquet` must not carry it.
- Slot on the time the bus passes stop k (`ts + Δ`), not the boarding time.
- Keep E, run_cv, the thresholds and the capacities in `config.yaml` / `config/` only.

## If it goes wrong
- **N looks too small on busy corridors:** check that variant patterns are counted (any pattern traversing k → k+1).
- **Absurd loads cluster on a few routes:** usually a wrong route match (P2) or a timetable gap. Mark NO_DATA and list them in CHECKS §9.
