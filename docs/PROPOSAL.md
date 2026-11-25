# SeatCast Delhi — Proposal

**Delhi Transport Stack Hackathon 2026, Phase 1 · Problem 2: crowdedness-aware journey planner**

## 1. The problem

Journey planners rank Delhi buses by time. For a commuter at Anand Vihar at 18:00, the difference between a 45-minute ride standing in a crush and a 50-minute ride with a seat matters as much as the minutes. SeatCast estimates **how crowded each bus usually is, stretch by stretch and half-hour by half-hour**, and shows that next to every journey option. The same estimates show operators where one more bus would remove the most standing.

## 2. What the data really is

We tested the ticket file before modelling it:

- **2,559,899 tickets, 2,753,606 passengers, 1–31 October 2026.**
- **99.32% of passengers paid exactly 90% of a standard fare slab, and none paid full fare.** That is Delhi's 10% discount on app tickets, so the file holds **ONDC app e-tickets only**, not conductor tickets, free Pink-pass riders or pass holders.
- That is **88,826 digital passengers a day**, about **2.2%** of the 3.96 million daily DTC and cluster riders. There is a median of 6 identified digital passengers per bus per day.

**Consequence: we keep the brief's running count at the only level the data supports.** Expanding each ticket over the segments it rides and summing *is* the running count (boardings minus alightings, accumulated along the route). We accumulate it over every bus in a 30-minute slot across the month, then divide by the buses that GPS shows actually ran. Per individual bus the app sample is a median of 6 ticketed riders a day ([DAY0](DAY0.md)), so a per-trip count would be noise. GPS puts the bus a median 218 m from our matched boarding stop at ticket time, so the tickets are where we place them. The result is expanded to all riders, with the uncertainty carried through to what the user sees.

## 3. Approach

1. **Match tickets to the network.** Route codes and messy stop names are matched to the official static GTFS: 6,862 stops, 2,574 routes, 80,357 trips. The matcher works through exact names, guarded fuzzy matching, and finally the same name found anywhere in the city and snapped to the route's nearest stop within 300 m.
   - Results by passengers: **98.35% route matched, 93.89% both stops, 99.78% in travel order.**
   - Distances travelled rise monotonically with the fare slab paid, an independent check of the stop matching (the official slab km bounds could not be verified).
2. **Pooled segment flows.** Each ticket rides the segments between its stops, timed by the schedule.
   - Half-matched tickets get their missing end from riders who boarded at the same stop and hour.
   - In total **97.6%** of digital passengers are represented.
3. **Load per bus**, L = E · f / N.
   - f is the mean daily digital flow on a stretch in a 30-minute slot.
   - N is the number of buses that actually run through it, from GPS (§4), not the timetable.
   - E scales digital riders to all riders: **44.6, with a range of 31.2–45.9**.
4. **From load to a seat.** Sampling, day-to-day and bus-to-bus variation (measured from GPS headways, §4) combine into a probability of getting a seat. Commuters see it as **"seats on 7 of 10 trips"**, plus a GTFS-Realtime crowding level and a confidence badge. Stretches with fewer than 5 sampled riders say "limited data" and never show a number.
5. **Planner.** A RAPTOR router on the static GTFS returns up to 3 options, ranked by time or by a crowding-weighted time. It also gives "leave 20 minutes later → likely seat" and "board one stop earlier" suggestions, and a quiet-hour comparison.
6. **Operators.** For each route-hour: the busiest stretch, the frequency it needs (maximum-load-point method), standee-minutes, and a ranking of where **one more bus** saves the most standing.

## 4. Ground truth, not just a model

The October bus GPS feed lets us check our two weakest assumptions independently:

- **Ticket time is boarding time, and the stop matching is right.** When a ticket was bought, the bus was a median of **218 m** from the boarding stop we matched, against **4.3 km** from the alighting stop.
- **The ticket file covers DTC and cluster buses.** 99.3% of ticket passengers' buses appear in the GPS feed, which covers cluster routes too, so we expand to DTC plus cluster ridership. The organisers confirmed this on 23 Nov.
- **Far fewer buses run than the timetable says.** GPS bus-km over all 31 days is **62%** of timetable bus-km on weekdays (63% Saturday, 66% Sunday), and a count of buses passing a stop agrees.
  - Counting GPS trip ids would have shown the opposite, because the feed splits journeys into fragments; we test for this.
  - N uses the observed service.
- **Bus bunching is measured, not assumed.** The gaps between consecutive buses at two reference stops per route, net of the timetable's own irregularity, give a bus-to-bus variation of **0.62** (median), not the 0.35 we first assumed. It changes seat chances, never crowding levels.
- **Tested as a forecast.** Crowding levels built from weeks 1–3 predict week 4 within one level on **95.0%** of 858,888 stretch-slots; two halves of the same weeks agree on 97.0%, the most that sampling noise allows.
- **Robust to unverified inputs.** Changing bus capacity by ±15% or the expansion factor to its low or high value moves levels by at most one step; using the timetable instead of GPS-observed buses would change 40% of levels.
- **Stop names the matcher can't settle.** Where a name fits two stops, the bus's position at purchase picks the right one.

## 5. Data used

| Dataset | Source | Use |
|---|---|---|
| October 2026 app e-tickets (ONDC) | Hackathon organisers ([data README](https://pub-091bd9e794bb4877b10b29e6df80f065.r2.dev/2026-10/README.md)) | Demand: flows by stretch and slot |
| Delhi bus static GTFS (DTC / DoT) | [Delhi Transport Stack](https://delhi.transportstack.in/data-services/datadetails/1) | Network, stop order, schedules, buses per slot, routing |
| October 2026 bus GPS (31 days) | Hackathon organisers (data README) | Validation; observed service |
| DTC and cluster daily ridership | DTC 2025-26 ([AckoDrive](https://ackodrive.com/news/delhi-s-dtc-bus-fleet-hits-13-year-low-as-daily-ridership-falls-44/)); Delhi Economic Survey 2025-26 ([NewsBytes](https://www.newsbytesapp.com/news/auto/economic-survey-2025-26-finds-delhi-bus-ridership-down-nearly-20/story)) | Expansion factor E |
| Bus capacities | [electrive](https://www.electrive.com/2026/02/09/india-delhi-flags-off-a-new-batch-of-500-electric-buses/), [Autocar Pro](https://www.autocarpro.in/news/delhi-government-introduces-devi-electric-bus-fleet-for-improved-connectivity-126223) | Seats and total capacity |
| Map tiles | [OpenFreeMap](https://openfreemap.org) | Free basemap, no keys |

## 6. What is different

1. **Data forensics first.** We prove what the file is (app tickets, about 2% of riders) and design around what it cannot do.
2. **A defensible estimator.** Pooled flows divided by the buses that run, expanded to all riders, with uncertainty turned into a seat probability.
3. **Independent ground truth from GPS** for boarding position, fleet coverage and delivered service.
4. **A one-second read.** Natural-frequency wording, a crowding strip along every bus leg, seat-finding suggestions, a full English/Hindi interface, and a colour-blind-safe scale where crowding is never shown by colour alone.
5. **Operator decisions and open standards.** A "+1 bus" ranking, GTFS-Realtime occupancy levels, an OpenAPI, $0 to run, and one command to rebuild everything.

## 7. Limitations and next steps

- **Digital riders may not travel like everyone else.** App use is likely higher on some corridors, so one city-wide E over-states them. Route-level ticketing-machine (ETM) totals would calibrate this; we have asked the organisers for them.
- **Missing riders.** Free (Pink pass) and pass riders are missing from the file. Expanding to total ridership assumes they travel in the same pattern.
- **Capacities are estimates.** They are taken from fleet announcements until a fleet register is available.
- **Destinations are as declared** on the ticket.
- **Phase 2:** calibrate E with ETM route totals, validate with DEVi automatic passenger counters, publish a GTFS-Realtime occupancy feed, rebuild weekly, and extend the same segment-load model to metro and bus smart-card taps (Problem 5).
