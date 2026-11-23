# P6 — Frontend (impeccable brief)

**Goal:** one bilingual page where a commuter reads each option's crowding in about a second, and an operator sees where one more bus helps most. **Time box:** 6 h, split P6a 2.5 h / P6b 1 h / P6c 1.5 h / P6d 1 h.
**Lane:** B (background `sous-chef` in a worktree) for P6a–P6c; you plus impeccable for P6d. **Depends on:** this brief, plus fixtures (P6a) or the live API (P6b+).

**Skills:**
- **impeccable** owns the visual world and finish: direction contract, build, `detect`, finish review, `DESIGN.md`.
- **dataviz** owns the crowding scale and charts.
- **fixing-accessibility** runs the last pass.
- `PRODUCT.md` is the product truth impeccable reads.
- Image generation isn't available here, so this is a **code-led** build: the ambition lives in the direction contract's first viewport and signature move.

---

## 1. Job and audience (impeccable mode: **Operate**)
- **Commuter on a phone:** choosing between buses, often at peak hours. Must understand "fast but crowded" vs "slower with a seat" at a glance, then act: leave now, leave later, or board elsewhere.
- **Operator or planner on a desktop:** which route-hours are overloaded, and where one extra bus saves the most standing.
- **Judge:** watches the 2–3 minute video and may run it locally. The first screen must prove the mechanism without a click.

## 2. Outcome and proof
- **Success:** the first screen opens on the judges' own example (Anand Vihar → Connaught Place, 18:00 weekday) with three options already showing. Each has time, crowding word and icon, "Seats on k of 10 trips", and the crowding strip along its bus legs.
- **Proof on screen, all from `data/out/`:**
  - where it gets crowded ("crowded from Laxmi Nagar to ITO"-style, real stop names);
  - how sure we are (confidence badge, "limited data");
  - what to do ("Leave at 18:20 → likely seat");
  - what normal looks like ("at 11:00 this trip usually has many seats").
- **Product truth no competitor can copy:** crowding derived from Delhi's own October tickets, with the uncertainty shown.

## 3. Direction — **Reservation Chart** (chosen 23 Nov; impeccable roll `f55fde5b`, Operate mode)

The world may lend only **type, palette, density and one signature move**. Layout, navigation and controls stay standard web.

### Chosen: Reservation Chart
- **World:** India's railway seat-availability notation, plus the yellow station nameboard with bilingual black lettering. Both are read by almost every Indian traveller.
- **What we borrow:** the *form* of the availability line (status word + count). Never the codes: no RAC or WL.
- **Palette:**
  - Chart-paper white ground with printed-ink text and hairline ruled rows.
  - **One yellow nameboard band** carries section titles in black, English and Hindi, as on station boards.
  - The validated blue ↔ red crowding scale (§4) is the only saturated data colour.
  - One reserved course colour marks the selected journey on the map.
  - Keep the shell free of saturated blue and red, so neither competes with crowding meaning.
  - Run the validator on yellow + course colour + the four crowding steps together.
- **Type and density:** chart-dense rows; uppercase column heads (DEP · ARR · MIN · CHG · AVAILABILITY); tabular bilingual figures. The printed feel comes from figures and rules, never a fake dot-matrix font (that's costume).
- **Signature move: the availability line.** Every option ends in a line set like a train availability result, e.g. `STANDING · seats 3/10`. Expanded, it reads "Seats on 3 of 10 trips · crowded Laxmi Nagar → ITO". The crowding strip under each bus leg is a row of chart cells, one per stop-to-stop segment.
- **Kept from the round** (disciplines, not clothes):
  - reserved course colour (orienteering);
  - operator tab as a strict hairline module grid (Japanese high-density);
  - section titles on the yellow band (manual tab board);
  - focused option expands, others compress to one row (streaming wall);
  - the Data tab's only texture is real data (Ikeda).
- **Honest risk:** it can read as a dated government portal. Counter it with modern spacing, a strict grid, crisp type and fast interaction. Familiar is the point; dated is the failure.

**Direction contract draft.** Write it at P6a start with `impeccable surface-brief write web/index.html <file>`; never copy it into `web/`.
- **THESIS:** seat availability in the notation India already reads for trains. Every option ends in an availability line, and operators read a dense chart. Refuses the default of map-first cards with a coloured pill.
- **OWN-WORLD:** chart-paper white, printed ink, hairline ruled rows, tabular bilingual figures; a yellow station-nameboard band for section titles; the blue ↔ red crowding scale as the only saturated data colour; one reserved course colour.
- **STORY:** the commuter sees three ranked rows with availability lines, sees the fastest is crowded mid-route, takes "leave 18:20 → seat likely". The operator ranks route-hours by +1-bus benefit.
- **FIRST VIEWPORT (390 × 844):**
  1. Yellow band: SeatCast, tabs, EN | हि.
  2. Enquiry line: ANAND VIHAR → CONNAUGHT PLACE · WEEKDAY · 18:00 · [Fastest | Comfort].
  3. A three-row options chart (DEP, ARR, MIN, CHG, AVAILABILITY), with row 1 expanded: legs, crowding strip, suggestion.
  4. The map below.
- **FORM:** Reservation Chart, grounded candidate 1 of 7 (Impeccable's pick), seed `f55fde5b`.
- **FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

### All cards shown in the round (for the record)

**A. Stage Ticket** (assigned by the roll; my grounded candidate 5 of 7)
- **Thesis:** every bus leg reads like the stage row printed along a city-bus ticket. The stages you ride are punched, and each stage is tinted by how crowded it usually is.
- **Palette:**
  - Ticket-stock tints: one full-strength hue owns each tab's header ground.
  - Printing-ink near-black for text.
  - The validated crowding scale (§4) is the only saturated data colour.
- **Type and density:** condensed bilingual type for times and numbers (tabular figures); ticket-compact density. Perforation hairlines are the only ornament.
- **Signature move:** the **stage strip**. Under each bus leg sits a row of stage cells, punched at boarding and alighting, each tinted by its crowding level. "Crowded in the middle stretch" is visible without reading.
- **Raises carried over from declined challengers:**
  - *Orienteering map:* one reserved "course" colour, used only for the selected journey on the map.
  - *Japanese high-density web:* the operator tab packs 20 route-hours into a strict hairline module grid with no SaaS whitespace.
  - *Manual tab board:* each section (Planner / Operator / Data) owns one ticket-stock hue.
  - *Streaming wall:* focusing an option expands it (legs and strip) while the others compress to one line.
  - *Ikeda datamatics:* the Data tab's only texture is real data, a 31-day × 24-hour field of ticket counts.
- **Honest risk:** ticket ornament can tip into costume (serial numbers, fake tears). Younger riders know QR tickets better than punched paper.

**B. Reservation Chart** — *Impeccable's pick* (my top-ranked grounded candidate)
- **Thesis:** seat availability in the notation India already reads for trains. Each option carries an availability line like a railway enquiry; the operator view is a dense chart.
- **Signature:** the availability line, "SEAT 7/10 · STANDING from Laxmi Nagar".
- **Risk:** familiar, and close to a dated government portal. RAC/WL codes don't map to buses, so only the line's form is borrowed.

**C. Gate Board** (catalog challenger, verdict *competitive*)
- **Thesis:** options are segmented passes on a live departures board. Flipping Fastest ↔ Comfort re-ranks the rows in place, and a moved row stays lit until noticed.
- **Strengths:** best at dramatising the time-vs-comfort trade.
- **Weakness:** airport idiom, less familiar to Delhi bus riders than a bus ticket.

**D. Category standard** (always available)
- A Citymapper / Google Maps-style planner: white cards over a full-bleed map, route badges, a crowding pill. Executed straight at their craft level.

**Declined** (their raises are already in A): orienteering map, Japanese high-density web, manual acetate tab board, streaming title wall, Ikeda datamatics.

**Done 23 Nov:** you chose B; the telemetry ping (`--kind pick`) has been sent. Writing the contract above is the first step of P6a.

## 4. Tokens fixed regardless of direction

**Crowding scale** (THINKING D-08). Validated by the dataviz script: all-pairs CVD ΔE 17.9, normal-vision 23.2, light mode.

| GTFS-RT level | Token | Fill | Text on fill | EN | HI (draft, check) | Icon |
|---|---|---|---|---|---|---|
| MANY_SEATS_AVAILABLE | `--crowd-1` | `#1c5cab` | white | Many seats | कई सीटें खाली | two seats |
| FEW_SEATS_AVAILABLE | `--crowd-2` | `#6da7ec` | ink | Few seats | कुछ सीटें खाली | one seat |
| STANDING_ROOM_ONLY | `--crowd-3` | `#ef9a72` | ink | Standing room | खड़े होने की जगह | standing person |
| CRUSHED_STANDING_ROOM_ONLY | `--crowd-4` | `#b8322a` | white | Very crowded | बहुत भीड़ | crowd |
| NO_DATA_AVAILABLE | `--crowd-0` | neutral grey + 45° hatch | ink | Limited data | डेटा कम है | dotted outline |

- **Never colour alone:** every chip carries icon plus word. Strip cells have 2 px gaps and a text summary. Map segments carry the legend and a tooltip.
- **Map lines** get a 2 px light casing for contrast relief (the validator's WARN on the two light steps).
- **The reserved course colour** for the selected journey must differ from all five levels. Pick it with the world, and run the validator with it added.
- **After the world sets the surface colour**, re-run:
  ```
  node <dataviz>/scripts/validate_palette.js "#1c5cab,#6da7ec,#ef9a72,#b8322a" --mode light --pairs all --surface <surface>
  ```
- Light mode only for Phase 1. Dark steps are a Phase 2 task.

**Type:**
- At most two families, covering **Devanagari + Latin** with matched x-heights, from Google Fonts with `display=swap`.
- Tabular figures for times.
- Numerals stay international (0–9) in Hindi too (THINKING D-10).

## 5. Scope, layout and interaction

**Tabs:** Planner (default) · Operator · Data. The header holds SeatCast, the tabs and an `EN | हि` toggle.

**Planner layout:**
- **≥ 1024 px:** left panel (~440 px) with the form and the option cards; MapLibre map fills the right.
- **< 700 px:** single column. After a search, the form collapses to one summary line ("Anand Vihar → CP · Weekday 18:00 · Edit"), then the cards, then a 40vh map that expands on tap.
- **First viewport on a 390 × 844 phone:** header, summary line, option 1 fully (chip, k-of-10 line, stage strip), and option 2's chip.

**Form:**
- From/To comboboxes with in-browser search over `/stops/all` (normalised prefix plus token match, no library), plus "pick on map".
- Swap button; day-type select; time input; a **Fastest ↔ Comfort** segmented control.

**Option card:**
- Depart → arrive, total minutes, changes.
- Crowding chip (icon, word, range on hover), "Seats on k of 10 trips", confidence badge.
- Legs: walk / bus with route badge, board and alight stops; the stage strip under each bus leg.
- Suggestion line and quiet-hour line.

**Interaction:**
- Changing the preference **re-sorts the cards with a 200 ms move**, no fade, keeping keyboard focus on the same card.
- Selecting a card draws its legs on the map in the course colour, with segments tinted by level.
- Respect `prefers-reduced-motion`.

**Operator tab:**
- Day-type select and hour slider (05–23) drive a segment heatmap.
- Top-20 table, sortable: route, direction, hour, peak load per bus, buses/hour scheduled vs needed, gap, standee-minutes, **+1-bus benefit**.
- Row click highlights the route and shows its load profile for that hour (segments × load against seats and total lines).

**Data tab:** `/coverage` numbers; E low/central/high; who is missing (pass holders, free pink-ticket riders); a three-line method; limitations; links to TECH_NOTE and CHECKS on GitHub; the 31 × 24 real-data field.

## 6. States and ranges
- **Options:** 0–3. Legs: 1–5. Strip cells: 2–60 per leg (cells shrink, then a horizontal scroll inside the strip above ~40).
- **States:**
  - loading: 3 skeleton cards, no spinner;
  - no route within 2 h: explain and offer +1 h or nearest stops;
  - origin = destination; outside the Delhi box;
  - limited data: hatched chip plus a one-line why;
  - schedule gap: treated as limited data, with a note;
  - API error: message plus retry;
  - slow network: skeleton persists, the map loads independently.
- **Language:** Hindi strings run ~10–30% longer. Design for the Hindi lengths.

## 7. Bilingual implementation (THINKING D-10)
- `web/i18n.js` holds `{en: {...}, hi: {...}}` keyed strings with `{k}`-style placeholders and one `t(key, vars)` function.
- `<html lang>` switches. The choice persists in `localStorage` wrapped in try/catch, so the page still works with storage blocked.
- Stop names stay as in GTFS (English), since Hindi stop names aren't in the feed.
- **Draft Hindi for review** (a native speaker checks before the video; unreviewed keys fall back to English):

| Key | EN | HI (draft) |
|---|---|---|
| tab.planner / operator / data | Plan a trip / Operators / Data & method | यात्रा खोजें / ऑपरेटर / डेटा और तरीका |
| from / to / swap | From / To / Swap | कहाँ से / कहाँ तक / बदलें |
| daytype.weekday / saturday / sunday | Weekday / Saturday / Sunday or holiday | कार्यदिवस / शनिवार / रविवार या छुट्टी |
| leave_at / search | Leave at / Search | निकलने का समय / खोजें |
| pref.fastest / pref.comfort | Fastest / Most comfortable | सबसे तेज़ / सबसे आरामदायक |
| seats_k_of_10 | Seats on {k} of 10 trips | 10 में से {k} यात्राओं में सीट मिलती है |
| crowded_between | Crowded from {a} to {b} | {a} से {b} तक भीड़ |
| leave_later | Leave at {t} → likely seat | {t} बजे निकलें → सीट मिलने की संभावना |
| board_upstream | Walk {m} min to {stop} and board there → seat more likely | {m} मिनट चलकर {stop} से चढ़ें → सीट मिलने की संभावना ज़्यादा |
| quiet_hour | At 11:00 this trip is usually: {level} | सुबह 11 बजे यह यात्रा आमतौर पर: {level} |
| changes | {n} change(s) | {n} बार बस बदलें |
| walk_min | Walk {m} min | पैदल {m} मिनट |
| confidence.high / medium / low | High / Medium / Low confidence | भरोसा: ज़्यादा / मध्यम / कम |
| no_route | No bus route found within 2 hours | 2 घंटे में कोई बस रूट नहीं मिला |
| data_note | Estimated from October 2026 app tickets, scaled to all riders | अक्टूबर 2026 के ऐप टिकटों से अनुमान, सभी यात्रियों के हिसाब से |

## 8. Constraints
- **Stack:** vanilla HTML/CSS/JS, no build step.
- **Map:** MapLibre GL JS pinned to an exact version from unpkg or jsdelivr, with OpenFreeMap `https://tiles.openfreemap.org/styles/liberty` [R15]. No other JS libraries. Fonts from Google Fonts only.
- **Budget:** first load < 1.5 MB before tiles; `/stops/all` ≈ 150 KB gzipped; `/journeys` < 30 KB.
- **Privacy:** nothing vehicle-related anywhere in the DOM or network.
- **Accessibility:**
  - WCAG AA text contrast; visible focus; touch targets ≥ 44 px.
  - The combobox follows the ARIA 1.2 pattern.
  - Each strip is `role="img"` with an `aria-label` summary such as "Seats likely until Laxmi Nagar, crowded Laxmi Nagar to ITO".
  - Hindi blocks carry `lang="hi"`.
- **Fixtures:** `tests/fixtures/journeys.sample.json` follows the CLAUDE.md §8 shape and is labelled synthetic. The page loads it only with `?fixture=1`, never by default.

## 9. Build sequence
1. **P6a (fixtures, lane B):** contract written; shell, tabs and language toggle; form; option cards; stage strip; map with course colour; all states. Start with Hindi keys present (English values allowed).
2. **P6b:** swap fixtures for the live API; fix every shape mismatch in the API, not the UI.
3. **P6c:** operator tab (heatmap, table, profile); data tab; all Hindi strings filled; native check requested.
4. **P6d finish:**
   1. Capture `.impeccable/review/desktop.png` (1440) and `mobile.png` (390) with Playwright.
   2. Run `impeccable detect --json web/` once and fix the mechanical findings.
   3. Spawn the fresh `impeccable-finish-reviewer` with the brief, contract and screenshots. At most 2 fix rounds.
   4. `impeccable-documenter` writes `DESIGN.md` and `.impeccable/design.json`.
   5. Run the `fixing-accessibility` pass.

## Done when
- Both demo queries work end to end in **English and Hindi**, at 1440 px and 390 px.
- Preference re-sort, map highlight, operator table and data tab all work against the live API.
- impeccable `detect` is clean or its findings are resolved; the finish review returns **ship**; `DESIGN.md` exists.
- Zero colour-only encodings; the crowding palette validator passes against the final surface.
