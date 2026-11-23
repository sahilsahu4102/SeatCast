# P0 — Setup and data access

**Goal:** everything needed to build is on disk and the repo exists. **Time box:** 45 min (plus any wait for the GTFS email).
**Lane:** A. **Agents:** `prep-cook` for scaffolding; you for the account, the email and git push. **Depends on:** nothing.

## Inputs
- `data/raw/tickets/October-Delhi.csv` (present: 290 MB, 2,559,899 rows).
- `data/raw/gps/delhi-dtc-bus-gtfs-rt-2026-10.7z`: **complete and verified** (16,077,236,568 bytes; SHA-256 matches `SHA256SUMS`, 23 Nov). Step 2 is done; rerun it only if the file is moved.
- `data/raw/gtfs_sample/`: the official 8-file GTFS sample, for development until the full feed arrives.

## Steps

1. **Get the full GTFS (you, ~15 min).** Do this first; it is the only step that can involve waiting.
   1. Register at https://delhi.transportstack.in (Register), then sign in.
   2. Open *Data & Services* → **Delhi Buses: GTFS Static Data – DTC / DoT** (https://delhi.transportstack.in/data-services/datadetails/1) → **Download**.
   3. Fill the request form. Purpose: *Transport Stack Hackathon 2026, Problem 2 (crowdedness-aware journey planner)*. Type of use: research / non-commercial.
   4. Wait for the confirmation email, sign in again, click **Download Now**.
   5. Unzip so the `.txt` files sit directly in `data/raw/gtfs/`. Expect `agency, calendar, routes, trips, stop_times, stops, shapes, feed_info`, maybe `fare_*`.
   6. Sanity check: ~10,559 stops, 2,403 routes and 89,393 trips (metadata PDF).

2. **Verify the GPS archive.** Expect 16,077,236,568 bytes.
   ```bash
   sha256sum data/raw/gps/delhi-dtc-bus-gtfs-rt-2026-10.7z
   # expect 703bd6ea5237883e1ad8f094a661d365edc74b7555cf83ce4c554408a79c16c9
   ```
   If the file is short or the hash differs, rerun the same command in PowerShell. It resumes where it stopped:
   ```powershell
   curl.exe -C - -L --retry 30 --retry-delay 15 --retry-all-errors -o "F:\PROJECTS\delhiiii\data\raw\gps\delhi-dtc-bus-gtfs-rt-2026-10.7z" "https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/delhi-dtc-bus-gtfs-rt-2026-10.7z"
   ```
   Then list the days: `"C:\Program Files\7-Zip\7z.exe" l data\raw\gps\delhi-dtc-bus-gtfs-rt-2026-10.7z`. P4b extracts three of them.

3. **Python environment** (Python 3.13 is installed):
   ```bash
   python -m venv .venv && .venv/Scripts/activate      # Git Bash; PowerShell: .venv\Scripts\Activate.ps1
   pip install duckdb pandas numpy pyarrow rapidfuzz pyyaml fastapi "uvicorn[standard]" matplotlib pytest httpx
   pip freeze > requirements.txt
   ```
   `gtfs-realtime-bindings` waits for P8.

4. **Scaffold** (CLAUDE.md §5; `prep-cook`): folders, empty modules, `tests/` with one trivial test, `config/route_map.csv`, `config/stop_alias.csv`, `config/series_capacity.csv`.
   - `src/seatcast/run.py` dispatches `all | ingest | match | flows | load | checks | plan | serve`. It is the **primary interface**, because Windows has no `make`.
   - Keep a three-line Makefile wrapper for Unix judges.

5. **`config.yaml`:** CLAUDE.md §6 with these changes (THINKING D-03, D-04, D-05, D-09):
   ```yaml
   holidays: ["2026-10-02", "2026-10-20"]          # Gandhi Jayanti; Dussehra (gazetted)
   ridership_daily: {central: 3960000, high: 4080000}  # DTC 2025-26 [R3] + cluster FY24-25 [R4]; DTC+cluster FY24-25 [R4]
   e_low_factor: 0.7                                # ASSUMPTION
   gps: {days: ["2026-10-14", "2026-10-17", "2026-10-11"], match_window_s: 60}   # Wed, Sat, Sun outside festival week
   planner: {max_transfers: 2, window_min: 120, shift_min: [10, 20, 30], alternatives: 2,
             upstream_walk_min: 10, quiet_hour: "11:00"}
   ```

6. **Git.**
   ```bash
   git init && git add .gitignore CLAUDE.md PRODUCT.md docs/ && git commit -m "Plan and product context"
   git remote add origin https://github.com/sahilsahu4102/SeatCast.git && git push -u origin main
   ```
   - The repo shows 404 to the public today. Create it on github.com if it doesn't exist; keep it private until P7.
   - `.gitignore` already excludes `data/`, `.venv/`, `.playwright-mcp/` and caches.
   - Background lanes B and C need this repo for their worktrees.

7. **Email the organisers (you, 5 min).** To `csm@iiitd.ac.in`, cc `transportstack.hackathon@gmail.com` and `delhitransportstack@gmail.com`:
   > Subject: Problem 2: two data questions (calibration)
   > 1. Does `October-Delhi.csv` cover DTC and cluster (DIMTS) buses, or DTC only?
   > 2. Could you share route-level daily passenger totals from ETM for October 2026 (route, weekday/Saturday/Sunday, passengers)? Aggregates only; we would use them to calibrate the expansion of the e-ticket sample.
   > 3. Is DEVi automatic passenger counter data available for validation?

   A reply after Tuesday still helps Phase 2.

8. **Team check (2 min).** Your Where U Elevate team must list 2–3 members (the form enforces it), and whoever submits must be able to upload all five items.

## Outputs
Venv and `requirements.txt`; scaffold; `config.yaml`; full GTFS in `data/raw/gtfs/`; verified GPS archive; git repo with remote; email sent.

## Done when
- `pytest -q` passes.
- `ls data/raw/gtfs/stops.txt routes.txt trips.txt stop_times.txt calendar.txt` succeeds.
- The GPS SHA-256 matches.
- `git remote -v` shows origin.

## If it goes wrong
- **GTFS not approved by 11:00:** send the email, then build P2 against `data/raw/gtfs_sample/`, which has the same schema. Ask again at 13:00. Last resort is CLAUDE.md §13 degraded mode: stop order inferred from tickets.
- **`pip` fails on a wheel:** use Python 3.12 via `py -3.12 -m venv .venv`.
