# P8 — Stretch (only after P7's submission is in)

**Rule:** nothing here touches the submitted tag. Work on a branch; merge only if the result is tested and the demo still runs.
**Order:** by value per hour.

## 1. Apply observed service levels (1 h; needs P4b)
- If the GPS delivery ratio is materially below 1 on busy routes, set `service_scale[route, daytype]` from `data/work/service_scale.csv` and rebuild P3.
- Report "loads with scheduled N" against "loads with observed N" in CHECKS §11. This directly answers "timetable ≠ reality".

## 2. GTFS-RT occupancy feed — T12 (1.5 h)
- `pip install gtfs-realtime-bindings`.
- `feed.py` builds a `FeedMessage` with a `TripUpdate` for each trip running in the next hour. Each `StopTimeUpdate` sets `stop_sequence`, `schedule_relationship = NO_DATA` and `departure_occupancy_status` = the predicted level. The spec allows this, but the field is experimental; say so [R13].
- Serve it at `/gtfs-rt/occupancy.pb`.
- **Test:** decode with the bindings; check the entity count and that every status is a valid enum.
- Describe it as **ready to plug in** to Google Maps (via the agency's Transit Partner account [R12]), One Delhi or Chartr. Not live.

## 3. Public demo URL (1–1.5 h; only if the GTFS licence allows)
- Read `LicenceAgreement1.0.pdf` from the GTFS dataset page first.
- If serving derived stop and route data is allowed: deploy the FastAPI app with `data/out/` and `network.npz` only (never raw tickets or GPS) to a free tier: Hugging Face Spaces (Docker) or Render.
- Add the URL to the README and the submission, if the form still accepts edits.

## 4. Smaller items
- The "board upstream" suggestion, if it was cut.
- The operator heatmap map, if it was cut.
- Dark mode, with crowding steps re-selected and validated against a dark surface (D-08).
- Route load-profile charts on the operator tab.

## Done when
Each shipped item has its own test, the demo queries still pass, and CHECKS/TECH_NOTE are regenerated if model outputs changed.
