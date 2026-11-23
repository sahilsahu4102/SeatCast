# SeatCast Delhi — implementation plan

Transport Stack Hackathon 2026 · Problem 2, crowdedness-aware journey planner · **Phase 1 closes Tue 24 Nov 2026, 23:59 IST.**
Plan written Mon 23 Nov, 04:00 IST. One builder plus Claude Code agents.

| Read | For |
|---|---|
| [THINKING.md](THINKING.md) | why: evidence, decisions D-01…D-13, assumptions, rejected ideas |
| [phases/](phases/) | how: one file per phase, each with steps, a "done when" and fallbacks |
| [../CLAUDE.md](../CLAUDE.md) | the method spec (§4), API contract (§8), code rules (§2) |
| [../PRODUCT.md](../PRODUCT.md) | product truth that impeccable reads for every UI decision |

---

## 1. Winning thesis

Judges score **how well crowding is grounded in the data** and **how clearly it is shown**. This file makes both hard:

- It is **ONDC e-tickets only**: 99.3% of passengers pay exactly 90% of a fare slab, and none pay full fare.
- It is about **2% of riders**: a median of 6 identified digital passengers per bus per day, across 6,809 buses.

Common entries will count tickets per bus, train a model with no ground truth, and paint red/green maps. SeatCast stacks five things they won't:

1. **Data forensics first.** Prove what the file is and what it can't do, with numbers ([THINKING §2](THINKING.md#2-what-the-data-really-is)).
2. **A defensible estimator.** Pooled segment flows, expanded to DTC + cluster ridership, divided by the buses that run: L = E·f/N. Uncertainty from sampling, day-to-day and bus-to-bus variation becomes **P(seat)**.
3. **Independent ground truth.** The October DTC GPS feed checks the two weakest assumptions: where the bus was when the ticket was bought, and whether scheduled trips actually ran.
4. **A one-second read for commuters.** "Seats on 7 of 10 trips" [R16], a crowding strip along each bus leg, "leave 20 min later → likely seat", English/Hindi, and colours validated as colour-blind safe.
5. **Decisions for operators, and open standards.** A "+1 bus" ranking by standee-minutes saved, max-load-point frequency gaps [R11], a GTFS-RT occupancy feed, and an OpenAPI.

## 2. Deliverables (the organisers' checklist)

| # | Item | What we ship | Phase |
|---|---|---|---|
| 1 | Proposal: problem, approach, data | `docs/PROPOSAL.md` → PDF, 1–2 pages | drafted P1–P2 (lane C), final P7 |
| 2 | Working prototype | `python -m seatcast.run all` then `python -m seatcast.run serve` → `http://localhost:8000` | P5 + P6 |
| 3 | Source code with README | public GitHub repo `sahilsahu4102/SeatCast` with setup steps that work on a fresh clone | P0, P7 |
| 4 | Short technical note | `docs/TECH_NOTE.md`, 2–4 pages, numbers rendered from `data/out/` | P7 |
| 5 | Short demo video | 2–3 min MP4, unlisted link in the README and the submission | P7 |

The GitHub repo currently returns 404 to anonymous visitors. It must be public before you submit.

## 3. Phases

| Phase | CLAUDE.md tasks | Main outputs | Time box | Gate: done when |
|---|---|---|---|---|
| [P0 Setup & data access](phases/P0_setup.md) | T0 | venv, scaffold, GTFS in `data/raw/gtfs/`, GPS verified, git remote | 0.75 h | `pytest -q` green; GTFS files present; GPS SHA-256 matches |
| [P1 Ingest & clean](phases/P1_ingest_clean.md) | T1, T2 | `tickets.parquet`, `docs/DAY0.md` | 1.25 h | DAY0 matches the pre-check; ≥ 99.9% of passengers parse |
| [P2 Matching](phases/P2_matching.md) | T3 | `od.parquet`, `coverage.json`, alias tables | 4 h | ≥ 90% passengers route-matched; ≥ 85% both stops; ≥ 95% in order |
| [P3 Crowding model](phases/P3_crowding_model.md) | T4, T5, T10 (calc) | `cells.parquet`, `segments.geojson`, `operator.parquet` | 3.5 h | P(seat) tests pass; < 1% of cells absurd; peaks visible |
| [P4 Validation & checks](phases/P4_validation_checks.md) | T6 + GPS | `docs/CHECKS.md`, `docs/img/*.png` | 3 h | all checks regenerate from outputs; GPS section present |
| [P5 Planner & API](phases/P5_planner_api.md) | T7, T8, T10 (API) | `raptor.py`, `plan.py`, `api.py` | 5 h | both demo queries return 3 options in < 2 s; TestClient green |
| [P6 Frontend](phases/P6_frontend.md) | T9, T10 (UI) | `web/` | 6 h | demo flows work in EN and HI; impeccable finish review passes |
| [P7 Submission](phases/P7_submission.md) | T11 | proposal, tech note, README, video, public repo, submission | 5 h | submitted by 22:00 IST Tue |
| [P8 Stretch](phases/P8_stretch.md) | T12 + extras | GTFS-RT feed, hosted URL | gaps only | only after P7's submission is in |

## 4. Timeline and lanes

Three lanes run at once. Lane A is the critical path you drive with `sous-chef`. Lanes B and C are background agents in their own git worktrees, each started with a phase file as its brief. Every merge from B or C is reviewed by `sous-chef` (CLAUDE.md §17).

```
            Mon 23 Nov (from 14:00)                                        Tue 24 Nov
Lane A  P0─P1─P2 matching──────P3 model────P5b crowding+API─┐ G4─P6d finish─│FREEZE│─P7 docs─video─clone─SUBMIT
                                                             │              │15:00 │                    22:00
Lane B     P6a UI shell on fixtures (Reservation Chart)──────┴─P6b wire─P6c operator/data/Hindi
Lane C     P5a RAPTOR on raw GTFS (no crowding needed)───P4b GPS truth─P4 checks─tech-note template─README
GPS archive: complete 13:45 (16,077,236,568 bytes); SHA-256 checked in P0
```

**Re-baselined Mon 14:00** (about 4 h behind the first draft). The time comes back by splitting P5:
- **P5a**, the RAPTOR router and network, needs only GTFS. It starts in lane C as soon as GTFS lands.
- **P5b** adds crowding to legs and the API after P3.
- The UI never waits for the model: it builds on fixtures.

| When (IST) | Lane A: critical path (you + `sous-chef`) | Lane B: UI (background `sous-chef`) | Lane C: router, checks, docs (background) |
|---|---|---|---|
| **Mon 14:00–14:45** | P0: GTFS request + download, venv, scaffold, git | — | — |
| 14:45–15:45 | P1 ingest + DAY0 | P6a: contract, shell, form, option rows on fixtures | P5a: network build + RAPTOR + toy tests (`sous-chef`) |
| 15:45–19:45 | P2 matching; **18:45 alias review with you (30 min)** | P6a: crowding strip, map, all states | P5a cont.; proposal draft |
| 19:45–23:00 | P3 model → `cells.parquet` | P6a polish on fixtures | P4b: extract 3 GPS days, vehicle overlap, observed trips (`line-cook`) |
| 23:00–00:30 | P5b: crowding per leg, suggestions, API | — | — |
| 00:30–07:30 | sleep (laptop may sleep; nothing long-running left) | | |
| **Tue 07:30–10:00** | **Gate G4**: demo queries pass; operator endpoints | P6b: wire to the live API | P4 checks on real outputs |
| 10:00–15:00 | P6d finish: impeccable detect → finish review → fixes; accessibility pass | P6c: operator + data tabs, all Hindi strings | tech-note template, README |
| **15:00** | **Feature freeze.** After this, only fixes and docs | | |
| 15:00–18:00 | P7: render the tech note, finalise README and proposal, privacy audit (`head-chef`) | | |
| 18:00–19:30 | Record and trim the demo video | | |
| 19:30–20:30 | Fresh-clone test, make the repo public, tag `v1.0-phase1` | | |
| **20:30–22:00** | **Submit all five items on Where U Elevate** | | |
| 22:00–23:59 | Buffer. P8 only if already submitted | | |

**Checkpoint rule:** if lane A is more than 1.5 h behind this table at 19:45 or at Tue 10:00, apply the cut list (§6) at once.

**Do first, right now:** register on Transport Stack and request the GTFS ([P0 step 1](phases/P0_setup.md)). It is the only blocker that might need a wait for email. Also keep the laptop awake while the GPS download runs: *Settings → System → Power → Screen and sleep → Never* while plugged in.

## 5. Gates and quality bars

| Gate | Check | If it fails |
|---|---|---|
| G1 after P1 | DAY0 confirms facts 1–3 (pre-check already says yes) | stop and ask (CLAUDE.md §13) |
| G2 after P2 | route ≥ 90%, both stops ≥ 85%, order ≥ 95% (by passengers) | prioritise the top 100 routes by passengers; hand-alias their top misses; report honestly |
| G3 after P3 | LF distribution sane; < 1% of cells with L > 3 × total capacity; AM/PM peaks on radial corridors | flag the cell as a schedule gap (NO_DATA); inspect N and the matching for that route |
| G4 after P5 | Anand Vihar → CP 18:00 weekday and Kashmere Gate → Nehru Place 08:30 weekday each return 3 options with crowding in < 2 s | cache the network; reduce shifts; widen access radius |
| G5 Tue 15:00 | feature freeze | cut from the list below |
| G6 before submit | the checklist in §8 | — |

**Every step is tested before it is committed** (agreed 23 Nov):
1. **Unit tests** on hand-made fixtures (`tests/test_*.py`, toy feeds in `tests/fixtures/`). They need no data, so CI runs them.
2. **Data checks** on the real outputs of each step (`tests/test_data.py`): completeness against the raw file, invariants such as contiguous stop indexes and distances that never run backwards, the CLAUDE.md §3 facts, the demo query, and privacy of everything in `data/out/`. Each check skips when its input isn't built, so CI skips them and a local `pytest -q` runs them.
3. **CI** (`.github/workflows/ci.yml`) on every push and pull request: install from `requirements.txt`, `ruff check` (bug rules only), `pytest -q`, and guards that fail if any `data/` file is committed or a vehicle plate appears in a tracked file. A `v*` tag runs the same job and then publishes a GitHub release.
4. **Review:** code written by `line-cook` is reviewed by `sous-chef` (CLAUDE.md §17); every phase commits only on a green suite, one commit per logical step.

## 6. Cut list (cut in this order)

1. P8 entirely: GTFS-RT feed, hosting.
2. The "board upstream" suggestion (keep "leave later").
3. The operator heatmap map (keep the top-20 table).
4. The quiet-hour reference line.
5. P4b reduced to observed-vs-scheduled trips only (drop the ticket-position check).
6. Hindi on the operator and data tabs (keep Hindi on everything a commuter sees).

Never cut: crowding next to every option, the uncertainty wording, CHECKS.md, the tech note, the video, privacy suppression.

## 7. Risk register

| Risk | Signal | Response |
|---|---|---|
| GTFS approval delayed | no "Download Now" by Mon 11:00 | email `csm@iiitd.ac.in`; build P2/P3 against the GTFS sample in `data/raw/gtfs_sample/`; CLAUDE.md §13 degraded mode as last resort |
| Low stop-match rate | G2 misses | top-100 routes first; review `unmatched_stops.csv` with you; manual aliases |
| Full calendar has a single all-days service | P2 inspection | N identical across day types; say so; use the GPS delivery ratio per day type if available |
| RAPTOR too slow in Python | > 2 s per query | NumPy arrays per pattern, prune patterns with no trips in the window, cache by (origin stops, slot) |
| GPS archive corrupt or late | SHA-256 mismatch | rerun the same curl command (it resumes); P4b is optional, so the core plan is unaffected |
| Time overrun | behind the timeline by > 1.5 h at any checkpoint | apply the cut list immediately; don't negotiate with it |
| Wrong Hindi | review | ship only checked strings; unreviewed strings fall back to English |
| Repo not public / video link private | G6 | fix in the 20:30 slot; test the links from a private browser window |

## 8. Submission checklist

- [ ] Proposal PDF (1–2 pages): problem chosen, approach, data used.
- [ ] Prototype runs from a fresh clone with `python -m seatcast.run all` and `serve`. README steps tested on a clean venv.
- [ ] Repo public; README has setup, data download steps, the demo queries, credits for libraries and AI tools, and a licence.
- [ ] `docs/TECH_NOTE.md`: method, assumptions, limitations, where estimates are weakest. Every number rendered from outputs.
- [ ] Demo video 2–3 min, end to end: planner → Hindi toggle → operator → data → checks. Link opens in a private window.
- [ ] `docs/CHECKS.md` regenerated on the final build.
- [ ] Privacy audit: no `vehicle_number` anywhere public, `min_cell_n` enforced, `data/` not in git.
- [ ] Submitted on Where U Elevate before 22:00 IST, 24 Nov.

## 9. Errata to CLAUDE.md (verified 23 Nov; these win where they conflict)

| CLAUDE.md says | Verified fact | Source |
|---|---|---|
| Day-0 SQL `ac = 'TRUE'`; sample was tab-separated | file is comma-separated, quoted; `is_ac` is `True`/`False` → use `lower(is_ac) = 'true'` | full file |
| median 1 / p90 3 / max 9 passengers per bus-day; 1.062 per ticket | **6 / 16 / 89**, p99 35; **1.0757** per ticket; 88,826 passengers/day | pre-check |
| no zero-fare rows; `passenger_count` 1–3 | 8 zero-fare rows; one row with 6 | pre-check |
| NULL vehicle 56.5% | **48.52%** | pre-check |
| 1,133 codes → 701 bases, parser 100% | **2,259 → 1,216**; 9 named-service codes need `route_map.csv` (0.03% of passengers) | pre-check |
| 2,944 → 2,770 stop names | **7,552 → 6,771** | pre-check |
| match the parsed base to `route_short_name` | GTFS short names carry direction (`102ADOWN`): match the **full code** first | GTFS sample |
| E central from DTC 2.43M (E ≈ 28) | file covers DTC + cluster → central **3.96M**, high 4.08M (E ≈ 45) | D-03 |
| holidays: 2 Oct | add **20 Oct (Dussehra)** | timeanddate |
| green / yellow / orange / red chips | red/green fails colour-blind checks → validated **blue ↔ red** scale (D-08) | dataviz validator |
| `[SUBMISSION_TIME]` | **23:59 IST, 24 Nov 2026** | Where U Elevate |
| deliverables 1–5 (no proposal or video) | add **proposal** and **demo video**; repo must be **public** | organisers' checklist |
| "Solo developer" | rules require teams of 2–3; you're the only builder | Where U Elevate |
| `make all && make serve` | no `make` on Windows → `python -m seatcast.run all` / `serve` is primary | dev machine |
| `norm()` | also `html.unescape` (GTFS names contain `&#34;`) | GTFS sample |
| shapes may be missing | the sample has `shapes.txt` with `shape_dist_traveled` (m) | GTFS sample |

## 10. If shortlisted: Phase 2 (25 Nov – 9 Dec)

- **Calibrate:** ask for route-level ETM totals by day type and plug in `route_totals.csv`; validate against DEVi passenger counters [R17].
- **Reality-based service:** observed trips and run times from the full GPS month, per route and day type.
- **Problem 5:** extend the same segment-load machinery to metro and bus AFC taps, the explicit follow-on to Problem 2.
- **Planner:** McRAPTOR with a comfort criterion; live GTFS-RT positions ("your bus is 6 min away").
- **Product:** native-speaker Hindi review, dark mode, offline-capable page, user tests with commuters at Anand Vihar ISBT.
