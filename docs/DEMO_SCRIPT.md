# Demo video script (2:56)

The video is narrated in the author's own voice, synthesised with Chatterbox TTS (open source), and the end card says so. It is screen-recorded from the live app (`python -m seatcast.run serve`) at 1920×1080, with captions burned in. Two waits for the planner and profile to load are cut; nothing else is edited.

Every number spoken or shown comes from the app on screen or from the generated reports (`docs/CHECKS.md`, `docs/TECH_NOTE.md`). If a number on screen differs after a rerun, the narration must follow the screen.

| # | Show | Say |
|---|---|---|
| 1 | Title card: *How crowded is my bus, really?* | "Every journey planner tells you the fastest bus. None of them tells you whether you'll get a seat." |
| 2 | The planner opens on Anand Vihar → Connaught Place, 18:00 weekday; the crowded route is red on the map | "SeatCast does, for Delhi's buses, stretch by stretch." |
| 3 | Ring the query, then the three option rows | "This is the brief's own example. From Anand Vihar, to Connaught Place, at six in the evening, on a weekday. Every option shows its travel time, and how crowded it usually is." |
| 4 | Open the fastest (473 + 85, 18:00–18:45): seats 1/10; ring each leg's strip | "The fastest takes 45 minutes, but you'd get a seat on only one trip in ten. The strip shows exactly where: packed from Anand Vihar to Laxmi Nagar, and again on the second bus." |
| 5 | Scroll to its suggestion: board upstream at Yamuna Sport Complex | "SeatCast also hunts for a seat. Walk ten minutes back to Yamuna Sport Complex, board there, and you'll almost surely sit." |
| 6 | Switch to *Most comfortable*; open 39A + 317A (18:10–18:51, seats 10/10) | "Or switch to most comfortable. Leave ten minutes later on the 39A, and you arrive just six minutes later, with a seat on nearly every trip." |
| 7 | Ring the confidence line, then the 317A leg (limited data) | "Every estimate shows how many sampled riders it rests on. Where there are too few, like the second bus here, it simply says limited data." |
| 8 | Edit: ISBT Kashmere Gate → Nehru Place, 08:30 | "Now the morning rush: Kashmere Gate to Nehru Place, at eight thirty." |
| 9 | Open the 425 (packed from Red Fort), then the 425CL (few seats, arrives 09:31 vs 09:34) | "Two direct buses leave together. On the 425, you'd probably sit at the terminal, but from Red Fort onwards it's packed. The 425CL keeps seats wherever we have data, and arrives three minutes earlier." |
| 10 | Switch to हि and back | "And the whole page works in Hindi too." |
| 11 | Operators tab; sweep the hour slider from 18:00 to 09:00; ring the table | "For operators, the same estimates show where buses are overloaded. Every stretch is coloured by its usual load, hour by hour, and the route-hours most short of buses are ranked." |
| 12 | Pick the top route-hour; show its load profile | "Pick one, and its profile shows where along the route the load is highest. That's where one more bus helps most." |
| 13 | Data & method tab: 2.2% of riders; how it works | "So why trust it? The ticket file is app tickets only, about two in every hundred riders. Far too few to count any one bus. So we pool a whole month of tickets on every stretch, scale up to all riders, and divide by the buses that actually ran." |
| 14 | GPS checks: 218 m; 62% of timetabled service | "We checked this against the buses' own GPS. When a ticket is bought, the bus is a median of 218 metres from the stop we matched. And on weekdays, only 62% of the timetabled service actually ran. So we divide by real buses, not the timetable." |
| 15 | Card: hold-out test (95.0%, ceiling 97.0%, high-confidence 97.9%; `CHECKS.md` §15) | "We also tested it as a forecast. Built from the first three weeks, it predicts the fourth week's crowding within one level on 95% of stretch-slots. That's close to the 97% that sampling noise alone allows." |
| 16 | End card: repo link, data and map credits, AI-voice disclosure | "Every number is rebuilt from the raw data with one command, and tested on every push. SeatCast. Pick the bus you can actually sit in." |

**Upload:**
- Upload the video as unlisted on YouTube, or to Drive with "anyone with the link" access.
- On YouTube, add `SeatCast_Demo.srt` as captions. The MP4 already has the captions burned in.
- Test the link in a private window before submitting.
