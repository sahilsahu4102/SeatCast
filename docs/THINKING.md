# SeatCast — thinking document

Why each decision was made, what evidence it rests on, and what was rejected. Written 23 Nov 2026 after reading the brief, following every link in it, profiling the full ticket file and inspecting the GTFS sample.

- **How to build it:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) and [phases/](phases/).
- **The method spec:** [../CLAUDE.md](../CLAUDE.md).
- **Product truth for UI work:** [../PRODUCT.md](../PRODUCT.md).

Numbers below come from a one-off standard-library pre-check over the full file (`precheck.py`, 23 Nov). P1 regenerates them reproducibly with DuckDB into `docs/DAY0.md`. Where the two differ, `DAY0.md` wins.

---

## 1. The question behind the brief

The brief asks for crowding by route, direction, stretch and time of day, shown next to journey options. It scores two things: **how well the estimate is grounded in the data** and **how clearly it is shown to commuters**. It also says that a simple planner with a sound model beats a polished planner with a weak one.

The general judging list (Where U Elevate page) adds problem relevance, technical depth and correct use of the data, feasibility, innovation, and usability and impact. Every submission needs a proposal, a working prototype (mock-ups and slides don't qualify), a public repo with a README, a short technical note and a short demo video.

So the winning move is not a cleverer UI. It is an estimator whose every step can be defended from the data, plus a display that communicates risk honestly. The UI then makes that rigour legible in one second.

## 2. What the data really is

| Fact (full file, 2,559,899 rows) | Value | Consequence |
|---|---|---|
| Source | "Ticketing is from ONDC e-ticketing" (organisers' data README) | Digital tickets only. No conductor (ETM) tickets. |
| Fares on a discounted slab (90% of a standard fare) | 99.32% of passengers; NCR series 0.59%; other 0.10%; **full fare 0%** | Independent confirmation that these are app/QR tickets [R1]. |
| Passengers | 2,753,606 (1.0757 per ticket) | Count passengers, never rows. |
| Days | 31 (1–31 Oct), every timestamp `+05:30` | No time-zone surprises. |
| `ticket_type_id` | `1` on every row; 8 zero-fare rows | Pass holders and free (pink-ticket) riders are absent. |
| `passenger_count` | 1, 2 or 3, plus one row with 6 | Flag `pc > 3` as an outlier and keep it. |
| `vehicle_number` NULL | 48.52% of rows | Nothing core may depend on the vehicle. |
| Distinct vehicles | **6,809** (181,620 vehicle-days) | About the whole Delhi city-bus fleet, not DTC alone (see D-03). |
| Identified digital passengers per bus-day | median 6, p90 16, p99 35, max 89 | Against ~756 riders per DTC bus per day [R3]: **per-trip running counts are impossible.** |
| AC share | 80.4% of passengers | E-buses dominate the digital sample. Possible channel bias (D-06). |
| Route codes | 2,259 codes → 1,216 bases; the CLAUDE.md parser fails on 9 named services (877 passengers, 0.03%) | Add those 9 to `config/route_map.csv`. |
| Stop names | 7,552 raw → 6,771 after `norm()`; 0 blank; 114 passengers with start = end | Fuzzy matching is needed, but within each route's own stops. |
| Weekday hour profile | peaks at 09:00 (296,555) and 18:00 (206,202); trough 14:00 (55,927) | Peak-to-midday ratio is about 5.3. The AM peak is ~1.4× the PM peak (see D-06). |
| Daily totals | weekdays ~98–110k; Saturdays 73–91k; Sundays 40–57k; **2 Oct 45,706** and **20 Oct 56,102** | 2 Oct is Gandhi Jayanti. 20 Oct is Dussehra, a gazetted holiday ([timeanddate](https://timeanddate.com/holidays/india/dussehra)). |
| File format | comma-separated, quoted strings, literal `NULL`, `is_ac` = `True`/`False` | The Day-0 SQL in CLAUDE.md compares `ac = 'TRUE'` and would report ~0%. Fixed in P1. |

**What the GTFS looks like** (official sample from the Transport Stack portal; full feed: 10,559 stops, 2,403 routes, 89,393 trips, ~41 stops per trip, last updated 13 Nov 2026):

- `routes.txt`: `route_short_name` uses the **same codes as the tickets, direction included** (`102ADOWN`, `102AUP`, `107STLUP`). Each `route_id` is one direction.
- `agency.txt` lists **DTC** and **DOT** (Transport Department, i.e. cluster buses).
- `calendar.txt` in the sample has **one service running every day, 2025-01-01 to 2040-01-01**. If the full feed matches, the timetable does not distinguish day types.
- `trips.txt`: `trip_id` = `{route_id}_{HH}_{MM}`; `direction_id`, `trip_headsign` and `block_id` are empty; `shape_id` is filled.
- `stop_times.txt` has non-standard `fare_stage` and `stop_dist` columns (empty in the sample). Times look distance-interpolated.
- `stops.txt` names hold HTML entities (`&#34;`), and opposite-side stops share a name with different IDs.
- `shapes.txt` exists with `shape_dist_traveled` in metres, although the metadata PDF does not list it.

## 3. What the organisers' links taught us

| Link | What mattered |
|---|---|
| [Problem 2 brief](https://docs.google.com/document/d/1ocS9rG4_E_Fb9DJcqTG8SClrLJJ_UJqGGAhgPbV8tr4/preview) | Deliverables, the Anand Vihar → CP example, and "things to think about". It suggests per-trip running counts, which the data cannot support (D-01). |
| [Hackathon page](https://delhi.transportstack.in/hackathon/) | Phase 2 (25 Nov–9 Dec) lets shortlisted teams refine or take Problem 5, *Metro and bus crowding*, which "teams moving on from Problem 2 can build on". |
| [Where U Elevate](https://whereuelevate.com/drills/transport-stack-hackathon-2026) | Phase 1 ends **24 Nov 2026, 23:59 IST**. Teams of 2–3. The five submission items. About 10–12 of 200+ teams are shortlisted. AI tools are allowed if credited. |
| [Data README](https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/README.md) | ONDC source. The 16.1 GB DTC GPS archive is **non-solid** (one SQLite file per day, extractable singly) with `vehicle_id`, `route_id`, `trip_id` and timestamps. |
| [Transport Stack catalogue](https://delhi.transportstack.in/data-services) | GTFS static is *Open* and free but needs sign-in plus a request form. No ETM or ticketing dataset is listed. |
| [GTFS-RT reference](https://gtfs.org/documentation/realtime/reference/) | `departure_occupancy_status` with `schedule_relationship = NO_DATA` is valid and still **experimental**, as CLAUDE.md §4.6 assumes. |
| [Problem 5 brief](https://docs.google.com/document/d/1fVuVjfvWTp5NVlcT52liQEipbwBfkQl-k0GnTAd3a0A/preview) | The same segment-load machinery extends to metro and bus AFC taps, which is our Phase 2 path. |

Contact addresses differ by page: `csm@iiitd.ac.in` (README and the brief's actual mailto), `transportstack.hackathon@gmail.com` (brief text), `delhitransportstack@gmail.com` (Where U Elevate). Write to the first and copy the other two.

## 4. Decisions

Each decision gives the question, the evidence, the choice, and what would change it.

### D-01 Pool and expand; never count per trip
- **Question:** the brief suggests grouping tickets by bus trip and keeping a running count. Can we?
- **Evidence:** median 6 identified digital passengers per bus per day, against ~756 riders per DTC bus per day [R3]. About 2% of riders appear (88,826 digital passengers/day against ~40 lakh). Half the rows lack a vehicle anyway.
- **Choice:** CLAUDE.md §4. Pool a month of tickets into mean digital flows per (route, direction, segment, 30-min slot, day type), divide by scheduled buses, and expand to total ridership: **L = E · f / N**.
- **Say it in the tech note** with these numbers, because judges who wrote "keep a running count" need to see why we didn't.

### D-02 Match routes on the full code first
- **Evidence:** GTFS `route_short_name` = ticket `route` format, direction included.
- **Choice:** rung 1 is an exact match on the normalised full code. Rung 2 is (base, direction) ignoring the variant digit. Rung 3 strips leading zeros. Rung 4 is `config/route_map.csv`. CLAUDE.md's OD-vote step becomes a **validation**: board index < alight index for ≥ 95% of passengers. A failing route usually means UP/DOWN are swapped relative to the tickets.

### D-03 Expand to DTC + cluster ridership, not DTC alone (biggest change)
- **Question:** CLAUDE.md §14 leaves open whether the file covers DTC only (E ≈ 28) or DTC + cluster (E ≈ 47).
- **Evidence:**
  - **6,809 distinct vehicles** appear, against DTC's fleet of ~3,800–3,950 and a total city fleet of ~6,800–7,100 in 2026 ([ThePrint](https://theprint.in/india/delhi-gets-500-new-electric-buses-dtc-ev-fleet-crosses-4000/2849506), [India TV](https://www.indiatvnews.com/news/india-dtc-to-get-1-000-new-buses-soon-needs-3-700-more-396238), [NewKerala](https://www.newkerala.com/news/a/dtc-preparing-induct-100-e-buses-delhi-minister-792.htm)).
  - ONDC ticketing covers DTC and DIMTS buses ([CXO Today](https://cxotoday.com/media-coverage/digital-qr-ticketing-for-dtc-buses-now-live-on-the-ondc-network/)).
  - The GTFS carries DTC and DOT agencies.
- **Choice:** `ridership_daily.central = 3,960,000` = DTC 2025-26 (24.3 lakh [R3]) + cluster FY2024-25 (15.3 lakh [R4]). `high = 4,080,000` (DTC + cluster FY2024-25 [R4]). `low = 0.7 × central` (assumption). With D_daily = 88,826 that gives **E ≈ 44.6 central, 45.9 high, 31.2 low**, about 60% above CLAUDE.md's 27.4. P3 recomputes it.
- **Confirm in P2/P4:** the share of passengers on DOT-agency routes, and the share of ticket vehicles that appear in the DTC-only GPS feed. If GPS shows nearly all ticket vehicles are DTC, revert to the DTC denominator.

### D-04 Day types, holidays, anomalies
- **Choice:** weekday / saturday / sunday, where sunday includes **2 Oct and 20 Oct** (both holidays). Their passenger totals (45.7k, 56.1k) sit in the Sunday range (40–57k).
- Anomaly rule unchanged: |deviation| > 30% from the same-day-type median, after reassigning holidays.
- 19 Oct (Mon, Navami; Delhi schools closed 18–20 Oct per [News24](https://news24online.com/india/dussehra-school-holidays-2026-all-cbse-icse-govt-private-schools-to-be-closed-in-delhi-ncr-uttar-pradesh-maharashtra-telangana-check-full-state-wise-list/943700/)) is −19% and stays in. Note it in CHECKS.

### D-05 Service level N: schedule first, observed when we can
- **Evidence:** the timetable may not vary by day type (single all-days service in the sample). The GPS archive gives the trips DTC actually ran.
- **Choice:** N from GTFS by default. In P4b, compute observed trips per route-hour for DTC routes on 3 sample days, and report the delivery ratio (observed / scheduled). If it is materially below 1, offer `service_scale` per route and day type in config. A cancelled trip raises the load on the buses that do run, and that is the kind of grounding judges reward.

### D-06 One E for all cells, with stated biases and a sensitivity test
- **Known biases:**
  - **Bus type.** 80.4% of digital passengers are on AC buses, against roughly 71–76% of the fleet being electric ([NewKerala](https://www.newkerala.com/news/a/dtc-preparing-induct-100-e-buses-delhi-minister-792.htm)). Non-AC crowding may be under-estimated.
  - **Time of day.** The AM-peak hour is ~1.4× the PM-peak hour. App use may differ by trip purpose.
  - **Who is missing.** Women travel free [R5][R6] and are absent.
- **Choice:** keep one E (no data to calibrate strata). Add a CHECKS sensitivity table that stratifies E by `is_ac` using fleet shares, and count how many cells change level. The `route_totals.csv` hook stays the production fix.

### D-07 Capacity by vehicle series
- DEVi 9 m: 23 seats + 13 standing; 12 m e-bus: 39 seated + 24 standing [R14] (confirmed in two more sources). Non-AC CNG remains a placeholder (37/60, VERIFY).
- **Choice:** in P1, cross-tabulate series × route prefix × AC to find which series is the 9 m DEVi. Per-route capacity is the passenger-weighted mix of series seen on that route. Fall back to `is_ac`.

### D-08 Colour-blind-safe crowding colours (replaces red/yellow/green)
- **Evidence (dataviz validator, OKLab ΔE ×100):** the traffic-light status set fails on a map. Red vs green is **4.1 under deuteranopia**, and orange vs yellow is 13.6 for normal vision (floor 15).
- **Choice:** a **diverging blue ↔ red scale split at LF = 1.0 (seats full)**, because crowding has a natural midpoint:

  | Level | Hex | Text on fill |
  |---|---|---|
  | many seats | `#1c5cab` | white |
  | few seats | `#6da7ec` | ink |
  | standing room | `#ef9a72` | ink |
  | very crowded | `#b8322a` | white |
  | limited data | neutral grey + 45° hatch | — |

  In light mode it passes lightness band, chroma floor, CVD separation (all pairs ΔE 17.9) and normal-vision floor (23.2). Contrast against the surface is a WARN, which we cover with labels and outlines.
- Crowding always ships with an icon and a word (PRODUCT.md principle 2). Light mode first; dark-mode steps get selected and validated in Phase 2.

### D-09 Planner: RAPTOR plus diversity, ranked by generalised time
- RAPTOR gives the fastest journeys by (arrival, transfers). The judges' example needs a *slower but less crowded* option, which a pure (arrival, transfers) Pareto set drops.
- **Choice:** candidates = RAPTOR at the requested time, plus two **route-elimination reruns** (ban the winners' bus routes), plus departure shifts of +10/+20/+30 min. Rank them by `pref` using generalised time (CLAUDE.md §4.4). Full multi-criteria McRAPTOR is a Phase 2 upgrade.

### D-10 Bilingual by design
- Full English/Hindi toggle (your call, 23 Nov). One dictionary per language in `web/i18n.js`, `lang` on `<html>`, and a Devanagari-capable typeface.
- Numerals stay in the international form (0–9) in both languages, the official form under Article 343.
- Hindi strings get a native-speaker check before the video.

### D-11 Visual direction through impeccable, not defaults
- impeccable's concept roll (seed `f55fde5b`, Operate mode) assigned **"Stage Ticket"**: the punched-stage paper bus ticket.
  - Its signature move: every bus leg's stops shown as a ticket's stage row, tinted by crowding, with the boarding and alighting stages punched.
- Alternates: Impeccable's pick "Reservation Chart" (railway seat-availability notation); challenger "Gate Board" (rows re-rank in place when Fastest ↔ Comfort flips); the category standard.
- **Chosen (23 Nov): Reservation Chart.**
  - Crowding is set in the availability-line form Indian travellers already read for trains (status word + count, no RAC/WL codes).
  - Section titles sit on a yellow station-nameboard band.
  - The blue ↔ red crowding scale stays the only saturated data colour.
  - Contract draft and risks: [phases/P6_frontend.md](phases/P6_frontend.md) §3.

### D-12 Delivery
- **Hosting:** local run plus video first. Host on a free tier only after submission is safe, and only after reading the GTFS licence.
- **Tooling:** no `make` on the dev machine, so `python -m seatcast.run <step>` is the primary interface and the Makefile is a thin Unix wrapper.

### D-13 Privacy
- Aggregates only. `min_cell_n = 5` suppression. `vehicle_number` and GPS `vehicle_id` never leave `data/work/`.
- A test asserts that no API response contains a vehicle field.
- Raw data and derived parquet stay out of git.

## 5. Assumptions register

| Assumption | Value | Lives in | Test or sensitivity |
|---|---|---|---|
| Boarding time ≈ `created_at` | — | method | P4b: bus GPS position at ticket time vs matched boarding stop |
| Digital riders travel like everyone else | one E | `config.yaml` | D-06 sensitivity; `route_totals.csv` calibration |
| Daily ridership (central / high) | 3.96M / 4.08M | `ridership_daily` | E band shown in UI and tech note |
| Low-E factor | 0.7 | `e_low_factor` | report as the low band |
| Bus-to-bus load spread | run_cv 0.35 | `run_cv` | CHECKS: level changes at 0.25 / 0.45 |
| Capacities | per series | `config/series_capacity.csv` | VERIFY with a DTC fleet list |
| Walk speed and detour | 4.5 km/h × 1.3 | `walk` | none needed |
| Crowding multipliers | Wardman & Whelan [R10] | `multipliers` | cited |
| Desired load factor | 0.8 | `desired_load_factor` | operator table at 0.7 / 0.9 |
| Timetable = what runs | N scheduled | — | P4b delivery ratio |

## 6. Where common entries will go wrong, and what we do instead

| Common approach | Why it fails on this data | SeatCast |
|---|---|---|
| Count tickets per bus trip as the load | ~2% sample: you get 0–3 people per bus | Pool a month, expand with E, show uncertainty |
| Use the raw ticket count as crowding | Ignores how many buses run and how big they are | L = E·f/N against seats and total capacity per series |
| Train a black-box model on ticket counts | No ground-truth load exists to train against | Transparent estimator and checks against known patterns |
| Red/green heatmap | Unreadable for ~1 in 12 men | Validated blue ↔ red scale, icons and words |
| Precise numbers ("43.7 passengers") | False precision | "Seats on 7 of 10 trips" [R16], confidence badge, ranges |
| Google or OSRM routing | Not allowed: must build on static GTFS | Own RAPTOR on the official feed |
| Ignore validation | Judges ask for it explicitly | Peaks, corridors, weekday/weekend, week-to-week ρ, plus GPS ground truth |
| A chatbot | Adds nothing to grounding | None (CLAUDE.md rule) |

## 7. Open questions

| Question | Who answers | What changes |
|---|---|---|
| Does the full GTFS calendar vary by day type? | the feed (P2) | N per day type, D-05 |
| Which series is DEVi 9 m? | P1 crosstab, GPS | capacity on those routes |
| Share of ticket vehicles that are DTC | GPS (P4b) | confirms D-03 |
| Route-level ETM totals by day type | organisers (email in P0) | per-route E calibration |
| Can derived GTFS data be served publicly? | GTFS licence PDF | hosting (P8) |
| Hindi copy correctness | native speaker | UI strings |

## 8. Ideas considered and rejected

- **Per-trip reconstruction for "complete" buses:** no bus is complete. The best bus-day has 89 digital passengers out of hundreds.
- **Downloading all 124 GB of unpacked GPS:** three representative days answer every validation question.
- **Map-matching GPS for run times:** valuable for Problem 1, not needed for crowding in Phase 1.
- **McRAPTOR now:** correct but slower to build and run. Route elimination gives the needed diversity at a tenth of the cost.
- **A framework UI (React/Vite):** CLAUDE.md fixes one page with no build step, and the demo doesn't need more.
- **LLM explanations or chat:** banned by the rules; plain sentences built from numbers do the job.
- **Dark mode on day one:** the commuter scene is outdoors in daylight. Validated dark steps don't exist yet.

## 9. Research log

- Organiser material: links in section 3. GTFS metadata PDF and sample zip from the [GTFS dataset page](https://delhi.transportstack.in/data-services/datadetails/1).
- Fleet and ridership:
  - [NewsBytes / Economic Survey 2025-26](https://www.newsbytesapp.com/news/auto/economic-survey-2025-26-finds-delhi-bus-ridership-down-nearly-20/story): 40.8 lakh/day FY2024-25 (DTC 25.6, cluster 15.3); fleet 6,966.
  - [ackodrive](https://ackodrive.com/news/delhi-s-dtc-bus-fleet-hits-13-year-low-as-daily-ridership-falls-44/): DTC 24.3 lakh/day in 2025-26.
  - [Business Standard](https://www.business-standard.com/india-news/692-cng-buses-to-go-off-road-by-year-end-after-route-rationalisation-dtc-125112200598_1.html): CNG fleet split.
- Holidays: [timeanddate](https://timeanddate.com/holidays/india/dussehra), [officeholidays](https://www.officeholidays.com/holidays/india/delhi/dussehra).
- Capacities: [Mobility Outlook](https://www.mobilityoutlook.com/news/delhi-launches-devi-electric-bus-fleet-with-pmi/), [Tractor Junction](https://trucks.tractorjunction.com/en/news/delhi-electric-devi-buses-public-transport-2026), [electrive](https://www.electrive.com/2026/02/09/india-delhi-flags-off-a-new-batch-of-500-electric-buses/).
- Digital ticketing: [CXO Today](https://cxotoday.com/media-coverage/digital-qr-ticketing-for-dtc-buses-now-live-on-the-ondc-network/), [Inc42](https://inc42.com/buzz/now-dtc-bus-commuters-in-delhi-can-buy-tickets-online-via-ondc). No public figure exists for the digital share of all DTC tickets.
- Download measurements (23 Nov): R2 supports HTTP range requests; ~1.65 MB/s on this connection; the full GPS archive is 16,077,236,568 bytes.
