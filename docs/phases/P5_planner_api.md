# P5 — Planner and API

**Goal:** a journey planner on the official static GTFS that returns up to 3 options with crowding per leg, served by FastAPI with the CLAUDE.md §8 contract. **Time box:** 5 h.
**Lane:** split in two to save time.
- **P5a** (steps 1–2, router and network): lane C, background `sous-chef`. Depends only on raw GTFS, so it starts right after P0.
- **P5b** (steps 3–5, crowding, suggestions, API, CLI): lane A. Depends on P3 (`cells.parquet`, operator outputs).

`line-cook` writes `api.py` and the tests, reviewed by `sous-chef`.

## Outputs
- `src/seatcast/raptor.py`, `plan.py`, `operator.py` (serving), `api.py`
- `data/work/network.npz` (cached network)
- CLI `python -m seatcast.run plan "<from>" "<to>" HH:MM <daytype>`
- tests

## Steps

1. **Network build** (once, cached to `data/work/network.npz`, loads in < 1 s)
   - Stops get indexes 0..S-1 with lat/lon arrays.
   - Per routing pattern: a stop-index array and a `times[T, n]` array of departure seconds, with trips sorted by first departure. No overtaking is assumed, so every column is sorted too; assert it.
   - `stop → [(pattern, position)]` index.
   - Footpaths: pairs ≤ 400 m, found with a ~0.004° lat/lon grid and the 3×3 neighbour cells (no SciPy). Walk seconds = distance × 1.3 / 4.5 km/h.

2. **`raptor.py`** (RAPTOR [R9], ~200 lines, NumPy)
   - Sources are stops within 800 m of the origin, with walk times; targets likewise at the destination.
   - Rounds 0..K, where K = `max_transfers` + 1 rides, keep arrival labels τ_k and marked stops.
   - Route scan: from the earliest marked position, `np.searchsorted` on that column for the first catchable trip, then propagate downstream. Improve a label only if it beats both τ_k and the best target arrival (target pruning).
   - Relax footpaths after each round. Keep parent pointers to rebuild legs.
   - Search window: departure to +120 min. Skip patterns with no trip in the window.
   - Output: Pareto journeys by (arrival, number of rides).

3. **`plan.py`: options that show the trade** (THINKING D-09)
   - **Candidates:**
     - RAPTOR at the requested time.
     - Two **route-elimination reruns** (ban the bus routes of the best journey so far), which produce the judges' "slower but less crowded" option.
     - **Departure shifts** of +10/+20/+30 min.
   - **Crowding per bus leg** (pattern, board k1, alight k2, the trip's scheduled time at each k):
     - Look up the cell by (route_id, k, slot of the bus passing k, daytype).
     - P(seat at boarding) = cell(k1).p_seat. Standing minutes = Σ segment minutes × (1 − P(seat)).
     - Worst level. `crowded_between` = the longest contiguous run at ≥ STANDING_ROOM_ONLY.
     - Range from `level_low` to `level_high`. Confidence = the lowest along the leg. `n` = sampled passengers on the most crowded segment.
     - Text: "Seats on k of 10 trips", where k = round(10 × P(seat)) [R16].
   - **Generalised time** (CLAUDE.md §4.4): 1.5·walk + 1.5·wait + 5 min per transfer + Σ segment minutes × m, with m from Wardman & Whelan [R10].
   - **Ranking:** `fastest` by arrival; `comfort` by GT; `balanced` by GT with halved multipliers. Return up to 3 options, deduplicated by their sequence of bus routes.
   - **Suggestions:**
     - *Leave later:* the first shift where P(seat at first boarding) rises by ≥ 0.2 or the level drops a step, for ≤ 30 min extra arrival.
     - *Board upstream:* the 1–2 previous stops on the first leg's pattern within a 10-min walk, when P(seat) rises by ≥ 0.2. First to cut.
   - **Quiet hour:** the same OD at 11:00 on the same day type → total minutes and worst level.
   - `notes`: one line on the data source, plus a link to `/coverage`.

4. **`api.py`** (FastAPI; CLAUDE.md §8 endpoints; serves `web/` at `/`)
   - Startup (lifespan) loads `network.npz`, `cells.parquet` and `operator.parquet` once.
   - **Input validation at the boundary:**
     - `from`/`to` are `lat,lng` inside the GTFS stops' bounding box plus 5 km (the full feed reaches lat 29.69 and lon 76.60 on intercity routes such as Karnal), or a known `stop_id`.
     - `depart` is `YYYY-MM-DDTHH:MM`; `daytype` and `pref` are enums; `q` is ≤ 64 characters; `hour` is 0–23.
     - Anything else gets a 422 with a plain message.
   - `GZipMiddleware` (for `/stops/all`, ~10.5k stops).
   - Pydantic response models with **no vehicle field anywhere**.
   - Cells under `min_cell_n` are already NO_DATA from P3. The API never recomputes or reveals their n.
   - No journey found → 200 with empty `options` and a `reason`.
   - OpenAPI at `/docs`.

5. **CLI** `run.py plan`: fuzzy stop-name search, then the centroid of the matching stop cluster, then a call into `plan.py`. Prints ≤ 3 options with crowding.
   - The demo pre-fill uses GTFS stop IDs looked up by name (Anand Vihar ISBT, the Connaught Place stops). Never hand-typed coordinates.

## Tests
- `test_raptor.py` (toy GTFS): a 1-transfer journey is found; earliest arrival is correct; a footpath transfer works; window pruning.
- `test_plan.py`: crowding per leg from toy cells; GT ranking flips between `fastest` and `comfort`; the leave-later rule.
- `test_api.py` (TestClient): every endpoint, bad inputs return 422, and the **privacy test**: no key or value containing `vehicle` or a `DL\d` plate pattern in any response.

## Done when
**Gate G4:**
- `Anand Vihar → Connaught Place, 18:00 weekday` and `Kashmere Gate ISBT → Nehru Place, 08:30 weekday` each return 3 distinct options with crowding, a suggestion line and a quiet-hour line.
- Median `/journeys` latency < 2 s on this laptop.
- `pytest -q` is green.

## If it goes wrong
- **Too slow:** cache the network in memory (done), drop the +30 shift, run shifts only for the top option, and cache results by (origin stop set, slot, daytype).
- **No sensible alternatives:** widen access to 1,000 m for alternatives only, and allow a third elimination rerun.
- **Strange transfers:** cap footpaths at 400 m and forbid transfers from a route to itself.
