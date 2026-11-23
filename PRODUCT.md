# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static HTML/CSS/JS on one page, no framework, no build step (CLAUDE.md §9). MapLibre GL JS with OpenFreeMap tiles. Served from `web/` by the project's FastAPI app (`src/seatcast/api.py`).

## Users

- **Delhi bus commuters**, mostly on phones, choosing between bus options before or during a trip, often at peak hours. Job: pick a trip they can bear, trading minutes for a seat or standing room.
- **Bus operators and planners** (DTC, Transport Department / cluster operators): see which routes, stretches and hours are overloaded and where one extra bus helps most.
- **Hackathon judges** (Transport Stack Hackathon 2026, Problem 2): judge how well the crowding estimate is grounded in data and how clearly it is shown. They watch a short demo video and may run the prototype.

## Product Purpose

SeatCast estimates how crowded Delhi buses usually are, by route, direction, stretch between stops, 30-minute slot and day type, from one month of ONDC e-tickets. It shows that crowding next to every journey option with its travel time. Success: a commuter reads each option's crowding in about a second and can choose a faster or a more comfortable trip; an operator sees where extra buses would help most.

## Positioning

Crowding comes from Delhi's own October 2026 ticket records, pooled and expanded to total ridership with the uncertainty stated. It is not guessed, crowd-sourced, or counted per trip from a ~2–3% sample. Every option says how often there is a seat ("seats on 7 of 10 trips"), where on the ride it gets crowded, and how sure the estimate is.

## Operating Context

- First screen: the planner opens pre-filled with the judges' example (Anand Vihar → Connaught Place, 18:00 weekday) with results showing (confirmed 23 Nov 2026).
- Commuters: phone in hand, at a stop or before leaving (inferred, not user-tested).
- Operators: desktop, planning sessions; ranked lists and a map.
- Judges: a 2–3 minute demo video plus a local run from the README.

## Capabilities and Constraints

- Planner: From/To via in-browser stop search or map click; day type; time; Fastest ↔ Comfort preference; up to 3 options; "leave later" and "board upstream" suggestions; a quiet-hour reference line.
- Crowding levels use the GTFS-Realtime `OccupancyStatus` names: MANY_SEATS_AVAILABLE, FEW_SEATS_AVAILABLE, STANDING_ROOM_ONLY, CRUSHED_STANDING_ROOM_ONLY, plus NO_DATA_AVAILABLE shown as "limited data".
- Operator tab: hour and day-type controls, segment heatmap, top-20 route-hours ranked by "+1 bus" benefit.
- Data tab: coverage numbers and method caveats from `GET /coverage`.
- Full English/Hindi toggle for every UI string (confirmed 23 Nov 2026). Hindi strings need a native-speaker check.
- $0 to run: no paid APIs, no geocoding API, no LLM or chatbot features.
- Privacy: no personal data; `vehicle_number` is never shown; any cell built from fewer than `min_cell_n` sampled passengers shows "limited data".
- Open decision: a public hosted URL. Local run plus video first; host only if time allows and the GTFS licence permits serving derived data.

## Brand Commitments

Name: SeatCast (SeatCast Delhi). No logo, palette or typeface exists yet.

## Evidence on Hand

- `data/raw/tickets/October-Delhi.csv`: 2,559,899 ONDC e-tickets, 2,753,606 passengers, 1–31 Oct 2026.
- Static GTFS from Transport Stack (about 10,559 stops, 2,403 routes, 89,393 trips): not yet downloaded.
- October 2026 DTC bus GPS archive: downloaded to `data/raw/gps/` (16.1 GB, 31 daily SQLite files), used to validate service levels and boarding positions.
- No users, testimonials, partner endorsements or usage metrics exist. Never invent them.

## Product Principles

1. Honest numbers: every figure on screen comes from computed outputs, and uncertainty is shown, not hidden.
2. One-second read: crowding is a word plus a colour plus its place on the trip, never colour alone.
3. Show the trade, let people choose: minutes against a seat, side by side.
4. One model, two readings: commuters and operators see the same estimates.
5. Light enough for a mid-range phone on mobile data.

## Accessibility & Inclusion

- Bilingual English/Hindi interface.
- Crowding is never encoded by colour alone; text meets WCAG AA contrast.
- Single column below 700 px, with comfortable touch targets.
