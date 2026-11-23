---
version: 1
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: []
---

# Surface brief: SeatCast planner page (web/index.html)

## Scope and mode
One page, three tabs (Planner default, Operators, Data & method). Mode: **Operate**. Built in phases: P6a fixtures, P6b live API, P6c operator + data tabs, P6d finish (docs/phases/P6_frontend.md).

## Audience, job, proof, constraints
- Commuter on a phone at peak: pick between "fast but crowded" and "slower with a seat" in about a second, then act (leave now, leave later, board elsewhere).
- Operator on desktop: which route-hours are overloaded and where one extra bus saves the most standing.
- Judge: the first screen proves the mechanism without a click (Anand Vihar -> Connaught Place, 18:00 weekday).
- Proof on screen: where it gets crowded (real stop names), how sure (confidence, limited data), what to do (leave later / board upstream), what normal looks like (quiet hour). All numbers from data/out/; fixtures only with ?fixture=1, labelled synthetic.
- Constraints: vanilla HTML/CSS/JS, MapLibre + OpenFreeMap, EN/HI toggle, WCAG AA, never colour alone, no vehicle numbers, light mode only.

## Direction contract
- **THESIS:** seat availability in the notation India already reads for trains. Every option ends in an availability line, and operators read a dense chart. Refuses the default of map-first cards with a coloured pill.
- **OWN-WORLD:** chart-paper white, printed ink, hairline ruled rows, tabular bilingual figures; a yellow station-nameboard band for section titles; the blue <-> red crowding scale as the only saturated data colour; one reserved course colour.
- **STORY:** the commuter sees three ranked rows with availability lines, sees the fastest is crowded mid-route, takes "leave 18:20 -> seat likely". The operator ranks route-hours by +1-bus benefit.
- **FIRST VIEWPORT (390 x 844):** (1) yellow band: SeatCast, tabs, EN | हि; (2) enquiry line: ANAND VIHAR -> CONNAUGHT PLACE · WEEKDAY · 18:00 · [Fastest | Comfort]; (3) a three-row options chart (DEP, ARR, MIN, CHG, AVAILABILITY) with row 1 expanded: legs, crowding strip, suggestion; (4) the map below.
- **FORM:** Reservation Chart, grounded candidate 1 of 7 (Impeccable's pick), seed `f55fde5b`.
- **FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Memorable moment
The availability line (`STANDING · seats 3/10`) and the row of chart cells under each bus leg, one per stop-to-stop segment.

## Unresolved
- Hindi strings await a native-speaker check (P6c).
- Live API field shapes (P6b).
