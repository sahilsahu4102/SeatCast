# P7 — Submission

**Goal:** all five checklist items submitted on Where U Elevate by **22:00 IST Tue 24 Nov**, two hours before the deadline. **Time box:** 5.5 h (15:00–20:30), with submission at 20:30–22:00.
**Lane:** A, with lane C drafting from Monday. **Agents:** `line-cook` for the templates and README; `head-chef` for the final privacy and security audit. **Depends on:** feature freeze at 15:00 Tue.

## 1. Proposal — `docs/PROPOSAL.md` → PDF (1–2 pages)
Drafted Monday morning in lane C from THINKING; finalised here with real numbers.
1. **Problem chosen:** Problem 2, and why crowding matters to Delhi commuters.
2. **What the data is:** ONDC e-tickets, ~2% of riders, 31 days, 1,216 base routes; static GTFS; October GPS for validation.
3. **Approach:** pooled segment flows → expansion to DTC + cluster ridership → buses per slot → load, P(seat), level, confidence. Then a RAPTOR planner ranking options by time or comfort, an operator "+1 bus" ranking, and a GTFS-RT feed.
4. **Data used:** a table of datasets with source links.
5. **What's different:** the five-point thesis (IMPLEMENTATION_PLAN §1).
6. **Limitations and next steps** (Phase 2).

**Export:** open the rendered markdown in a browser and *Print → Save as PDF*, or use Playwright `page.pdf()`. Check that the fonts embed and the links survive.

## 2. Technical note — `docs/TECH_NOTE.md` (2–4 pages, numbers rendered)
- Write `docs/TECH_NOTE.tmpl.md` with `{placeholders}`. `python -m seatcast.run note` fills them from `data/out/coverage.json`, `gps_checks.json` and the CHECKS outputs.
- No number in the note is typed by hand (CLAUDE.md §2 rule 2).
- **Outline** (CLAUDE.md §11, plus):
  - **Data:** the ONDC evidence; 99.32% discounted slabs, 0 full fare; who is missing.
  - **Why not per-trip counts:** median 6 per bus-day against ~756 riders per bus.
  - **Expansion:** the DTC + cluster evidence (D-03) and the E band.
  - **Uncertainty:** cv terms, P(seat), confidence, the "k of 10" wording.
  - **Validation:** peaks, corridors, weekday/weekend, ρ, **GPS ground truth**.
  - **Display:** GTFS-RT levels; colour-blind-safe scale (D-08).
  - **Operator use:** max-load point, standee-minutes, +1 bus.
  - **Limitations:** digital-rider bias (AC share, AM/PM), timetable vs reality, unverified capacities, declared destinations.
  - **Production path:** ETM route totals, DEVi APC, GTFS-RT publishing, weekly rebuild, $0 / one small VM.
  - **Privacy:** aggregates, `min_cell_n`, no vehicle IDs, DPDP Rules 2025 [R18].
- Cite references by their R-IDs; add R19 for the organisers' data README.

## 3. README.md (judges run from this)
1. One paragraph on what SeatCast is, plus a screenshot.
2. **Quick start:** Python 3.12+; `python -m venv .venv`; `pip install -r requirements.txt`; place the data (ticket zip link; GTFS steps from P0); `python -m seatcast.run all`; `python -m seatcast.run serve` → `http://localhost:8000`. Unix users can run `make all && make serve`.
3. The demo queries to try.
4. An architecture diagram (pipeline → outputs → API → page).
5. Method in five lines, with links to TECH_NOTE, CHECKS and THINKING.
6. Data sources and licences.
7. **Credits:** open-source libraries; *built with help from Claude Code (Anthropic)*. The organisers require AI tools to be credited.
8. Licence (MIT unless the organisers specify otherwise) and privacy notes.

## 4. Demo video (2:30 target, 3:00 max)

| Time | Show | Say |
|---|---|---|
| 0:00–0:15 | page opens on the pre-filled example | Journey planners rank buses by time. SeatCast adds how crowded they usually are, from Delhi's own October tickets. |
| 0:15–0:35 | Data tab: coverage, E band | These are app tickets, about 2% of riders, so we pool the month and scale up to everyone, with the uncertainty shown. |
| 0:35–1:20 | the three options; strip; suggestion; flip to Comfort | Fastest is crowded on the middle stretch; this one is slower with standing room; leave at 18:20 and you'll likely sit. |
| 1:20–1:35 | `EN → हि` | Fully bilingual. |
| 1:35–2:05 | Operator: 18:00 heatmap, top-20, a load profile | Where one more bus saves the most standing. |
| 2:05–2:20 | CHECKS: peaks, weekday/weekend, stability, GPS | Checked against known patterns and against the buses' own GPS. |
| 2:20–2:30 | terminal running `run all`; the `/docs` page | Reproducible, open, and ready to plug into GTFS-Realtime. |

- **Record:** Xbox Game Bar (`Win+Alt+R`, records the active window) or OBS, at 1920×1080, with narration.
- **Compress:** `ffmpeg -i raw.mp4 -vcodec libx264 -crf 26 -preset slow -acodec aac -b:a 128k seatcast_demo.mp4`
- **Upload:** unlisted YouTube or Drive with "anyone with the link". Test the link in a private window.
- Record one backup take on Monday night after G4, in case Tuesday goes wrong.

## 5. Fresh-clone test (19:00)
1. `git clone` into a new folder.
2. New venv, `pip install -r requirements.txt`.
3. Copy the data in, `run all`, `serve`.
4. Run both demo queries; switch the language; open the operator and data tabs.
5. Fix the README for anything you had to do that it doesn't say.

## 6. Privacy and security audit (`head-chef`, 30 min)
- `git ls-files | grep -E '^data/'` is empty.
- No `vehicle_number`, GPS `vehicle_id` or plate pattern in `data/out/`, API responses, `web/` or docs.
- `min_cell_n` suppression is enforced in P3 outputs.
- No secrets, keys or personal data in the repo (including `.playwright-mcp/`, ignored).
- API input validation is in place; no paid API calls.

## 7. Publish and submit (20:30–22:00)
1. Make the GitHub repo **public**.
2. Tag `v1.0-phase1` and push.
3. On the Where U Elevate dashboard, submit: proposal PDF, prototype (repo link plus run instructions; hosted URL only if P8 shipped), repo URL, technical note (PDF or link), video link.
4. Screenshot the confirmation.
5. Don't push to `main` after submitting. Phase 2 work goes on a branch.

## Done when
All five items submitted, the confirmation is captured, and every link opens in a private window.
