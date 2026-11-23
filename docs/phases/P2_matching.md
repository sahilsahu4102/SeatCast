# P2 — Matching tickets to the GTFS network

**Goal:** every usable ticket becomes (route_id, pattern, board index, alight index). **Time box:** 4 h, including a 30-min alias review with you at about 18:45 Mon.
**Lane:** A. **Agent:** `sous-chef` (matching quietly corrupts every number if wrong). **Depends on:** P1, GTFS in `data/raw/gtfs/`, or `data/raw/gtfs_sample/` while waiting.

## Inputs
`data/work/tickets.parquet`; GTFS `agency, routes, trips, stop_times, stops, shapes, calendar`.

## Outputs
- `data/work/patterns.parquet`, `data/work/pattern_stops.parquet`
- `data/work/stop_match.csv` (every accepted name → stop decision, reviewable)
- `data/work/unmatched_routes.csv`, `data/work/unmatched_stops.csv`
- `data/work/od.parquet`
- `data/out/coverage.json` (match section)

## Steps

1. **Load GTFS** (`io.py`).
   - Convert `HH:MM:SS` to seconds past midnight; values past 24:00:00 stay > 86,400.
   - `html.unescape` the stop names.
   - Record what the full feed actually holds:
     - Does `calendar.txt` vary by weekday? (The sample has one all-days service: THINKING D-05.)
     - Is `fare_stage` filled?
     - Are shapes present for every trip?

2. **Patterns.** Per `route_id`, group trips by their ordered `stop_id` sequence.
   - Each pattern gets `pattern_id`, `n_trips` and its stop list. The canonical pattern is the one with the most trips.
   - `pattern_stops`: `pattern_id, k, stop_id, name_n, lat, lon, dist_m`. Take `dist_m` from `shape_dist_traveled`; fall back to cumulative haversine × 1.3.

3. **Route match** (THINKING D-02). Key = uppercase with spaces removed.

   | Rung | Rule |
   |---|---|
   | 1 | ticket `route` key = GTFS `route_short_name` key (direction is in both) |
   | 2 | parse both sides; match (base, dir), ignoring the variant digit; take the `route_id` with most trips |
   | 3 | numeric base with leading zeros stripped |
   | 4 | `config/route_map.csv` |

   - Report the share of passengers per rung.
   - **Agency split:** the passenger share on `DTC` vs `DOT` routes goes into `coverage.json`. This is the first evidence for D-03 (DTC + cluster expansion).

4. **Stop match.** Work on **distinct (route_id, name_n) pairs**, not 2.5 M rows. Candidates are the stops of that route's patterns only.

   | Rung | Rule |
   |---|---|
   | a | exact `norm` equality |
   | b | alias table: `config/stop_alias.csv` plus pairs already accepted on other routes |
   | c | rapidfuzz `token_set_ratio`: accept ≥ 88, or 75–88 when the best beats the second by ≥ 5 |
   | d | each part of a `/`-split name (both sides) |

   - **Subset guard:** `token_set_ratio` returns 100 when one name's tokens are a subset of the other's ("nagar" vs "uttam nagar east"). When the shorter side has ≤ 2 tokens, also require `token_sort_ratio ≥ 80`.
   - Use `rapidfuzz.process.cdist` per route for speed.
   - The same stop name twice on one pattern (loops, both road sides) keeps every index; step 5 resolves it.

5. **Board/alight indexes and direction check.**
   - Pick the index pair with board < alight and the smallest span.
   - Per route, compute the in-order share of matched passengers. If it is < 50%, the GTFS UP/DOWN mapping is probably swapped against the ticket codes: retry with the opposite-direction `route_id` of the same base and keep whichever orders more passengers. Log every swap.
   - Drop tickets still out of order, and tickets where board = alight.

6. **`od.parquet`**: `tid, route_id, pattern_id, b, a, pc, ts, slot, date, daytype, week, ac, rung_route, rung_b, rung_a`.

7. **Fare-slab sanity** (CLAUDE.md §4.3 step 6).
   - Compare board→alight distance with the slab implied by `fare_pp` and `ac`. Slab km bounds come from [R7] (`[VERIFY]` before use). Use `fare_stage` differences instead if the full feed fills them.
   - Report the agreement rate. Never drop a ticket on this basis.

8. **Review with you (about 18:45 Mon).**
   - Print the 30 most-travelled unmatched stop names, each with its top routes and best candidate and score.
   - You accept or correct; accepted pairs go to `config/stop_alias.csv`. Rerun. CLAUDE.md §16: no silent guessing.

## Done when
Gate **G2**, by passengers:
- route matched ≥ 90%
- both stops matched ≥ 85%
- in order ≥ 95%

If not met, report the actual rates and the coverage of the top 100 routes, which carry most of the demand.

Also:
- `coverage.json` holds per-rung shares, agency split, swaps and fare-slab agreement.
- `pytest -q` is green.

## Tests (`tests/test_match.py`, toy GTFS in `tests/fixtures/toy_gtfs/`)
The toy feed: two routes (UP and DOWN), six stops, three trips each, hand-written.
- Exact full-code route match; base + direction fallback.
- Exact stop, fuzzy accept, fuzzy reject (margin), and the subset guard.
- A swapped-direction route gets corrected.
- A duplicate stop name resolves to the right index.

## Efficiency
- Develop on the **top 50 routes by passengers** (717A, 729, 511A, 623, 578, 764, …), then run everything.
- Cache GTFS tables as parquet in `data/work/` on first load.

## If it goes wrong
- **Matching stalls below target:** freeze on the top 100 routes, state coverage honestly, and move on at 15:00. P3 does not wait for perfection.
- **No full GTFS yet:** develop against `data/raw/gtfs_sample/` (same schema, 20 routes) and swap in the full feed when it lands. The code doesn't change.
