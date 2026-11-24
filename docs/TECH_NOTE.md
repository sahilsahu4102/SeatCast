# SeatCast Delhi: technical note

*Delhi Transport Stack Hackathon 2026, Problem 2. Every number in this note is generated from the pipeline outputs (`data/out/coverage.json`, `data/out/gps_checks.json`, `config.yaml`) by `python -m seatcast.run note`.*

## 1. Problem and approach

Commuters choose buses by time, but in Delhi whether you get a seat matters as much. SeatCast estimates the **usual load of each bus** on every stretch between stops, per 30-minute slot and day type, from one month of e-tickets, and shows it next to every journey option. The estimate is pooled over the month, expanded to all riders, divided by the buses that actually ran (from GPS), and turned into a probability of getting a seat. The same estimates rank route-hours for operators by how much standing one extra bus would remove.

## 2. Data

- **What the ticket file is.** It holds 2,559,899 tickets and 2,753,606 passengers, 1–31 October 2026.
  - 99.32% of passengers paid exactly 90% of a standard fare slab, Delhi's 10% discount for app tickets [R1][R7]. Only 8 tickets have zero fare.
  - So the file is **ONDC app e-tickets only**. Conductor tickets, free Pink-pass riders [R5] (women are 33–42% of bus riders [R6]) and pass holders are absent.
- **Coverage.** The file averages 88,826 digital passengers a day, **2.2%** of the 3,960,000 daily DTC and cluster riders [R3][R4]. Counting passengers per individual trip is therefore impossible, so we pool.
- **Network.** We use the official static GTFS from the Delhi Transport Stack. Its route short names carry the direction (e.g. 102ADOWN), so the full ticket route code matches it exactly first.
- **Ground truth.** The October 2026 bus GPS feed (31 days) [R19] is used only for validation and for counting delivered service.

## 3. Method

1. **Matching.**
   - **Routes.** 98.35% of passengers match a GTFS route.
   - **Stops.** Stop names are cleaned, then matched in this order: exact; reviewed or GPS-evidenced aliases; guarded fuzzy matching (generic words ignored, numbers must agree, subset names checked); and finally the same name found anywhere in the city and snapped to the route's own stop within 300 m.
   - **Result.** Both stops match for **93.89%** of route-matched passengers, and **99.78%** of those are in travel order.
   - **Operators.** Usable passengers split DTC 77.97% / cluster 22.03%, so cluster buses are in the file.
2. **Pooled segment flows.** Each ticket rides the segments from its boarding stop to its alighting stop. Each segment is timed by the scheduled offset from the boarding stop.
   - Tickets with only one stop matched get the other end imputed from riders who boarded or alighted at the same stop and hour: 151,951 passengers.
   - A per-route scale covers the remainder. In all, **97.61%** of digital passengers are represented; 1.66% are on route codes absent from GTFS.
   - For each cell (route, direction, stretch, 30-minute slot, day type), the mean daily flow f is taken over all days of that type.
   - **This is the brief's running count (§5), kept at the only level the data supports.** Expanding each ticket over the segments it rides and summing *is* the running count (boardings minus alightings, accumulated along the route). We accumulate it over every bus in a 30-minute slot across the month, then divide by the buses that GPS shows actually ran. Per individual bus the app sample is a median of 6 ticketed riders a day, so a per-trip count would be noise. GPS puts the bus a median 218 m from our matched boarding stop at ticket time, so the tickets are where we place them. The unit test `tests/test_flows.py::test_two_tickets_segment_flows` checks the count on a toy route.
3. **Buses that actually ran (N).** The timetable overstates service.
   - GPS bus-km against timetable bus-km gives a delivery ratio of **62%** on weekdays, 63% on Saturdays and 66% on Sundays. The daily coefficient of variation is 0.05.
   - A count of buses passing a stop agrees closely on the busiest routes.
   - Counting GPS trip ids would have doubled service, because the feed splits journeys into fragments. We test for this and avoid it.
   - Scheduled buses per slot are scaled by the ratio for each route, day type and hour band, clamped to [0.25, 1.5].
4. **Load per bus.** **L = E · f / N**, with E = R / D = 44.58 (range 31.21–45.93).
   - This gives 31.6 passenger-km per observed bus-km, on 6,197 buses seen in GPS per weekday.
   - Seats and total capacity come from the bus types seen on each route [R14]. Every capacity value is marked VERIFY.

## 4. Uncertainty

- **Variation.** cv² = 1/n (sampling) + cv_day² (day-to-day) + run_cv² (bus-to-bus variation, measured from GPS headways: median 0.62, see `docs/CHECKS.md` §17). This full cv sets the range and the confidence badge.
- **Seat probability.** The load on a given bus is treated as lognormal with mean L and the **trip-to-trip** variation only: cv_trip² = max(cv_day² − sampling part, 0) + run_cv². Sampling noise says how sure we are of the average, not how much one bus differs from the next, so it is left out (median cv 1.06 → cv_trip 0.75). **P(seat) = P(load < seats)**; once a rider gets a seat, they keep it for the rest of the leg.
- **Levels.** Load factor maps to GTFS-Realtime occupancy levels [R13]: many seats < 0.5 of seats, few seats < 1.0, standing < total capacity, crushed above that.
- **Confidence.**
  - High needs n ≥ 30 and week-to-week Spearman ρ ≥ 0.7; medium needs n ≥ 10.
  - Cells with fewer than 5 sampled riders are never published. The page says "limited data" instead.
  - Shares of published cells: high 26.34%, medium 43.62%, low 30.04%.
- **Censoring.** 12.3% of cells imply more than 1.5× a bus's total capacity, most of them on 717A UP, 717A DOWN, 717 UP, 717 DOWN, 717B DOWN.
  - These cells are well sampled and certainly crushed, but the magnitude is implausible. We show them as crushed, capped at 1.5× capacity and marked "estimate uncertain"; their confidence badge still reflects how well they are sampled, because the level is sure and only the size is not.
- **Expansion scenarios.** E low / central / high are carried through as a load range on every cell.

## 5. Validation

- **Bus position when the ticket was bought** (3 GPS days; 87% of tickets with a known vehicle found a ping within 60 s; median lag 8 s).
  - The bus was a median **218 m** from the matched boarding stop, against **4,308 m** from the matched alighting stop. 81% of tickets were within 500 m of the boarding stop.
  - This confirms both that ticket time ≈ boarding time and that the stop matching is right. By matching rule:

| stop-match rule | tickets | median m | within 500 m |
|---|---|---|---|
| a | 65,948 | 209 | 82% |
| b | 1,091 | 186 | 88% |
| c | 11,351 | 219 | 80% |
| d | 9,809 | 247 | 77% |
| e | 4,197 | 268 | 74% |
| f | 2,762 | 294 | 73% |

The rules are: a exact name, b reviewed or GPS-evidenced alias, c guarded fuzzy match, d one part of a "/" name, e the only stop containing all the words, f the same name elsewhere in the city snapped to the route.

- **The GPS route id is the GTFS route id.** The median distance from a ping to its own route's stops is 137 m, against 10,650 m for a shuffled route.
- **Who is in the file.** 99.3% of ticket passengers with a vehicle ride a bus that appears in the GPS feed, which covers DTC and cluster routes.
- **Fares agree with distances.** Distances along the route rise monotonically with the fare slab paid, an independent check of the stop matching (the official slab km bounds could not be verified):

| AC | fare per passenger (Rs) | passengers | km p10 | km p50 | km p90 |
|---|---|---|---|---|---|
| False | 4.5 | 190,578 | 1.5 | 3.0 | 4.7 |
| False | 9.0 | 190,509 | 4.7 | 7.4 | 10.4 |
| False | 13.5 | 125,248 | 10.8 | 17.3 | 30.2 |
| True | 9.0 | 832,540 | 1.6 | 3.1 | 4.7 |
| True | 13.5 | 679,369 | 4.3 | 6.4 | 8.6 |
| True | 18.0 | 268,902 | 7.7 | 10.0 | 12.7 |
| True | 22.5 | 231,879 | 12.5 | 17.8 | 29.3 |

- **Hold-out forecast.** Levels built from weeks 1–3 alone predict week 4 within one level on **95.0%** of 858,886 cells (same level 64.9%), against 97.0% / 67.0% for two halves of the same weeks; high-confidence cells reach 97.9%, at the noise ceiling (`docs/CHECKS.md` §15). A GPS dwell-time check (stop dwell against predicted activity per bus) was too weak to use: pings every ~11 s are too coarse.
- **Known patterns** (details in `docs/CHECKS.md`).
  - On-board load (segment flows) peaks on weekdays at 9:00 and 19:00, with the low at 14:00. Boardings by hour are in `docs/CHECKS.md` §3.
  - Weekday loads exceed Sunday loads on 75.6% of shared cells.
  - Of the 10 most crowded route-hours, 9 fall in peak windows.
- **Distribution.** Published cells have a median load factor of 0.785 and a 90th percentile of 2.427.
  - Level shares: many seats 31.51%, few seats 28.3%, standing 17.24%, crushed 22.94%.

### A calibration we rejected, and why

We tried a route-level plausibility calibration: lower E on any route whose 95th-percentile load exceeds a crush limit, and raise E on the others so the city total stays fixed. With the observed bus counts it has no solution at realistic crush limits:

| quantile | crush x total | routes over cap | their riders % | carried if cut % | max carried at cap % |
|---|---|---|---|---|---|
| 0.9 | 1.5 | 569 | 55.2 | 82.6 | 111.1 |
| 0.9 | 2.0 | 298 | 31.5 | 91.5 | 148.1 |
| 0.9 | 2.5 | 164 | 17.2 | 95.3 | 185.2 |
| 0.9 | 3.0 | 91 | 10.7 | 97.0 | 222.2 |
| 0.95 | 1.5 | 837 | 76.0 | 69.5 | 83.3 |
| 0.95 | 2.0 | 552 | 56.5 | 81.8 | 111.0 |
| 0.95 | 2.5 | 355 | 38.0 | 89.1 | 138.8 |
| 0.95 | 3.0 | 230 | 26.2 | 93.4 | 166.5 |

Over-capacity loads are concentrated in the peaks across many routes. App users appear to be more peak-concentrated than riders overall, so a route-level correction is the wrong tool. We keep the city-wide E, preserve total ridership, and censor the extreme cells. The fix is a time-of-day calibration from route-level ticketing-machine totals (§8).

## 6. Display

- **Option rows.** Each journey option is a row in a "reservation chart": departure, arrival, minutes, changes, and an availability line such as **"seats 7/10"** [R16].
  - The crowding chip shows the worst level on the ride, as a word, an icon and a colour, never colour alone. The colour scale is blue to red, chosen because it stays distinguishable under colour blindness.
- **Per leg.** A stop-by-stop strip shows where the bus fills. The sentence reads "Seat likely at boarding (k of 10 trips) · crowded A to B".
- **Suggestions.** "Leave 20 minutes later → many seats" (any route arriving ≤ 30 min later whose seat chance rises by ≥ 0.2 or whose worst level drops a step). "Board one stop earlier". A quiet-hour comparison at 11:00.
- **Uncertainty is visible.** Every number carries a confidence badge, and the page and API never show a cell built from fewer than 5 riders. Everything is in English and Hindi.

## 7. Operator use

For each route-hour:
- the maximum-load segment;
- the frequency needed at a 0.8 design load factor (maximum-load-point method [R11]), against the observed frequency;
- standee-minutes;
- the **"+1 bus" benefit**: the standee-minutes removed by one more bus, assuming the load spreads evenly.

The operator tab ranks the top 20 route-hours and maps load factor by segment and hour.

## 8. Limitations

- **Peak magnitudes are inflated.** Before capping, the mean load per observed bus on weekdays is 82 at 09:00 and 70 at 18:00, against a typical total capacity of 60; 7.3% of cells exceed twice the capacity. App users are more peak-concentrated than riders overall (§5), so one city-wide E overstates peaks. Levels (crushed or not) are robust; sizes at the peak are not. The fix is hourly route totals from the conductors' machines (ETM), which would set E by time of day.
- **Stability.** Week 1 and week 2 give the same published level on 58.8% of cells and within one level on 89.1%, against 62.5% and 92.4% for two interleaved halves of the same days. Most week-to-week difference is sampling noise, not drift (`docs/CHECKS.md` §14).
- **Fractional buses.** 11.6% of cells see fewer than one observed bus per slot window on average; their loads are averages over days with and without a bus.
- **Missing riders.** Free (Pink pass) and pass riders are missing; expansion assumes they travel like app riders.
- **Service.** Delivery ratios are by route, day type and hour band, not per trip; bunching is modelled only as variance. 2.62% of passengers fall in cells where the timetable has no bus (flagged as gaps).
- **Capacities** come from fleet announcements and stay marked VERIFY until a fleet register is available. The DL51GD series is treated as a 12 m bus; if it is the 9 m DEVi, its routes are more crowded than shown.
- **GPS coverage.** 87% of tickets with a known bus find a ping within 60 s. If missing pings also hide some service, true delivery is higher and loads lower. This is reported as a sensitivity, not applied.
- **Night hours** (00:00–05:00) have few tickets and mostly low-confidence cells.
- **Alighting stops are as declared on the ticket.** The single all-days GTFS calendar means day-type differences come only from demand and GPS service.

## 9. Production path

- **Route-level ETM totals** by route and hour, to calibrate E in time and space (requested from the organisers).
- **DEVi automatic passenger counters** for direct validation [R17].
- **A GTFS-Realtime occupancy feed** from the same levels [R12][R13], and a weekly rebuild.
- **Cost:** $0 on free tiers today; one small VM at city scale.

## 10. Privacy

- Tickets carry no personal identifiers.
- Vehicle numbers are used only internally (capacity mix and GPS matching) and never leave `data/work`.
- Published outputs are aggregates with at least 5 sampled riders per cell. Tests scan every API response and output for plate patterns.
- This is consistent with the DPDP Rules 2025 [R18].

## References

[R1] One Delhi app 10% fare discount · [R3] DTC daily ridership 2025-26 · [R4] DTC + cluster ridership FY2024-25 · [R5] Pink Saheli card · [R6] women's share of bus riders (WRI India) · [R7] DTC fare slabs · [R11] Ceder, max-load-point frequency · [R12] Google Maps transit occupancy · [R13] GTFS-Realtime OccupancyStatus · [R14] bus capacities · [R16] natural frequencies (Hoffrage et al.) · [R17] DEVi passenger counters (ICCT) · [R18] DPDP Rules 2025 · [R19] organisers' October 2026 data README. Links in `CLAUDE.md` §15.
