# Testing notes

By Sucharita Chattopadhyay. Manual testing of the SeatCast app before submission.

## What I tested

- **The two demo routes:**
  - Anand Vihar → Connaught Place, 18:00 on a weekday.
  - ISBT Kashmere Gate → Nehru Place, 08:30 on a weekday.
- **The planner:**
  - the Fastest and Most comfortable switch;
  - each option's details;
  - the stop-by-stop crowding strip;
  - the suggestions to leave later or board upstream.
- **The Hindi page** (the हि button), and switching back to English.
- **The Operators tab:**
  - the day type and hour slider;
  - the top-20 table;
  - a route's load profile.
- **The Data & method tab.**
- **The page on a phone.**

## Bugs I found, and how they were fixed

| # | What I saw | Fix |
|---|---|---|
| 1 | Every journey option showed "LOW CONFIDENCE". | Confidence now reflects sampling only. Loads capped as implausible are marked "estimate uncertain" separately. |
| 2 | The Operators tab said "76 buses needed" for one route-hour, which is impossible. | The peak load is capped. The table ranks route-hours by the shortfall against the buses that actually ran. |
| 3 | The "·" between words was invisible, because it has zero width in the Anek font. | It was replaced with "∙" (U+2219). |
| 4 | "Leave later" sometimes suggested a trip with a *lower* chance of a seat. | A later trip is suggested only if its seat chance is at least as high. |
| 5 | The third option was sometimes the same bus a bit later, even when it was no better. | A later bus on the same route is added only if its seat chance is at least 0.2 higher. |
| 6 | The demo started at the Anand Vihar ISBT terminus, where every bus starts empty, so the brief's example didn't show. | The default start is now the Anand Vihar main-road stop. |
| 7 | The technical note had leftover template text at the top. | The note generator now removes it. |

## Phone testing

Playwright checks at 390×844 and 360×780 covered the planner, both languages, the Operators tab and the Data tab.

| What I found | Fix |
|---|---|
| Operator ranking and stop-profile tables extended beyond the phone width and required sideways scrolling. | The mobile layout stacks each row into a labelled card and keeps the sortable ranking controls visible. Labels follow the selected language. |
| Language buttons, the planner preference control, operator route buttons, and MapLibre zoom and attribution controls were smaller than 44px. | Their interactive targets now meet the 44px minimum. |
