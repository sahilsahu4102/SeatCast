# Demo video script (target 2:30, max 3:00)

**Before recording:**
- Close other apps.
- Run `python -m seatcast.run serve` and open http://127.0.0.1:8000 in a fresh browser window (the page opens in English).
- Record the browser window at 1920×1080 with narration: Xbox Game Bar (`Win+Alt+R`) or OBS.

The values below are what the page showed on 24 Nov from the committed outputs. If a number differs on screen, say what the screen shows.

| Time | Show | Say |
|---|---|---|
| 0:00–0:15 | Page opens on Anand Vihar ISBT → Connaught Place, 18:00 weekday | "Journey planners rank buses by time. SeatCast adds how crowded each bus usually is, stop by stop, from Delhi's own October tickets." |
| 0:15–0:40 | First option: 943, 18:02–18:45. Open it and point at the strip. | "On the 943, you'll likely get a seat at Anand Vihar, but the strip shows it fills up from Hasanpur Depot all the way into CP. 'Estimate uncertain' means it's so far over capacity that we cap the number; it's certainly very crowded." |
| 0:40–0:55 | Suggestion line: leave at 18:26 on 85EXT | "Leave 26 minutes later on the 85EXT and it's standing room instead of a crush, with a seat at boarding 9 times in 10." |
| 0:55–1:25 | Edit → Kashmere Gate ISBT → Nehru Place, 08:30. Point at 425 vs 425CL. | "Morning peak. The 425 arrives 09:34 and is crushed from Red Fort onwards. The 425CL arrives 09:31 with few seats. And leaving at 09:02 on the 425CL keeps a seat likely. That's the trade, side by side." |
| 1:25–1:35 | Click `हि` | "The whole interface is in Hindi too." Click back to EN. |
| 1:35–2:00 | Operators tab: evening peak, top rows, select one, show the profile | "For operators: where one more bus removes the most standing. These ring-road hours top the list. The profile shows where on the route the load peaks." |
| 2:00–2:20 | Data & method tab: scroll to the GPS checks | "These are app tickets, about 2% of riders, pooled over a month and scaled to everyone. We checked against the buses' own GPS: when a ticket is bought, the bus is a median 218 m from the stop we matched. Only 62% of scheduled bus-kilometres actually ran, so we use the buses that ran, not the timetable." |
| 2:20–2:30 | Terminal: `python -m seatcast.run all`, then `/docs` | "Every number is regenerated from raw data with one command, tested on every push, and served through an open API." |

**After recording:**
- Compress: `ffmpeg -i raw.mp4 -vcodec libx264 -crf 26 -preset slow -acodec aac -b:a 128k seatcast_demo.mp4`
- Upload as unlisted YouTube or as Drive "anyone with the link", and test the link in a private window.
