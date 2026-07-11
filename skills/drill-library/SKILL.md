---
name: drill-library
description: Use when the golf-coaching skill needs a drill or YouTube video for a specific weakness (dispersion, gapping, driver launch, wedge distance control, putting speed/start-line, chipping, course strategy, mental game, etc.). Provides a curated library of drills with metric targets and a seeded set of verified video links, plus a procedure for live web-searching fresh YouTube content when the library lacks a good match.
---

# Drill Library

A maintained library of golf drills mapped to weaknesses, each with **metric
targets** and — where seeded — a **verified YouTube link**, plus a procedure for
finding fresh videos when the library doesn't have a good match. Used by
`golf-coaching` to fill practice blocks.

All distances are **metric (meters)** — the same units the MCP grades against.
Never hand a golfer a yard/foot goal; it will be graded against a metric
measurement.

**Video links degrade gracefully — never fabricate one:**
- **Web-search tool available** → if a drill has no seeded link, run **Live
  search**, verify 1–3 real links, and hand them over. Prefer 2–3 verified links
  per drill; the Fix-it section renders them all.
- **No web-search tool** (e.g. some Claude Desktop setups) → hand the drill with
  its seeded link if it has one, otherwise give the **fully-specified drill with
  no link**. The reps, distances, targets, and feel cue still stand — a drill
  with no video is complete, just link-less. **Never invent a URL** to fill the
  gap.

Every drill also carries a `where` value (`range` needs balls/bay; `home` needs
neither; `course` is played on the course) so the coach can tag its block. The
whole at-home table below is `home`.

## How to use

1. Identify the weakness category from the diagnosis (see categories below).
2. Pick the best-matched drill from the curated library.
3. If nothing fits well, run the **Live search** procedure (when available), use
   the result, and **add the new drill to the library** (see "Maintaining" below)
   so it's there next time.

## Drill categories

`driver-launch` · `dispersion-irons` · `gapping` · `wedge-distance-control` ·
`strike-low-point` · `start-line-face-control` · `putting-speed` ·
`putting-start-line` · `short-game-chipping` · `on-course-strategy` ·
`at-home-no-ball`

## At-home / no-ball drills (no range, no ball — just the club)

Use when the user can't get to a range or asks what they can do at home/in the
yard, or for path/face faults where rehearsal beats ball-striking. Map by the
diagnosed fault. All are `where: "home"`.

| Drill | Fixes | What to do | Video |
|-------|-------|-----------|-------|
| Wall / fence | over-the-top, out-to-in path | Wall a clubhead's length off the trail shoulder along the target line; slow swings that miss it force the club inside. | https://www.youtube.com/watch?v=3f0wlswCZFk |
| Pump-and-drop | the over-the-top transition | At the top, pump hands down twice (trail elbow tucks, club shallows behind), then finish. | https://www.youtube.com/watch?v=3f0wlswCZFk |
| Trail-arm-only throws | inside path + face closing | Trail hand only; slow "skip a stone to right field" swings. | _find via Live search_ |
| Split-hands release | open face at impact | Hands ~10 cm apart; slow half-swings, feel the trail forearm cross over. | _find via Live search_ |
| Step-through | sequencing | Feet together; step toward target with the lead foot as you start down, then swing. | _find via Live search_ |
| Mirror face check | open-face awareness | Rehearse impact in a mirror; learn what square looks like vs your open habit. | _find via Live search_ |
| Towel under trail arm | connection / over-the-top | Trap a towel under the trail armpit through transition to keep the arm connected. | https://www.youtube.com/watch?v=3f0wlswCZFk |

Tell the user: go slow and over-correct (neutral will feel like a hook at
first); daily beats weekly; swing at a dandelion/tee for start-line feedback.
Hand these to the coach as `where: "home"` blocks (with links when available) so
they appear in the Fix-it section of the trajectory page (see
`trackman-visualizer`).

## Curated library

> Seed entries below. Verify a seeded link still works before handing it to the
> user; replace dead links and prune stale ones. Each entry: weakness → drill →
> what to do (metric) → link. Add real, watched-and-verified links as the library
> grows.

| Category | Drill | Where | What to do | Video |
|----------|-------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | range | 3 carry numbers (e.g. 50/70/90 m), 5 balls each, log carry on Trackman; aim ±5 m | https://www.youtube.com/watch?v=ABeuttW6nyA |
| `dispersion-irons` | Gate / alignment-stick window | range | Set sticks as a start-line gate ~30 cm ahead of the ball; 7-iron, must start every ball through the gate | https://www.youtube.com/watch?v=bTeL3PsGr7o |
| `start-line-face-control` | Alignment-stick face-control gate | range | Sticks form a gate ~a clubhead wide; square the face so every ball starts through it (contact left = closed, right = open) | https://www.youtube.com/watch?v=bTeL3PsGr7o |
| `strike-low-point` | Towel / line drill | range | Strike a line (or just past a towel) so the divot starts after the ball; check smash factor | https://www.youtube.com/watch?v=yaOakJPu1rI |
| `driver-launch` | Tee height + AoA ladder | range | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window and a positive attack angle | https://www.youtube.com/watch?v=iMK7tGhL68o · https://www.youtube.com/watch?v=ngNZOmYHIgE |
| `gapping` | Build-your-carries session | range | Hit each club 5×, record avg carry (m), find overlaps (< ~8–10 m) / holes (> ~18–20 m); pick one club to re-loft or swap | _find via Live search_ |
| `putting-speed` | Ladder lag drill | range | Putt to 6/9/12 m, finish within a 1 m zone past the hole; speed over line | https://www.youtube.com/watch?v=COJRUps4g1o |
| `putting-start-line` | Tee gate drill | range | Two tees a ball-width apart ~50 cm ahead of the ball; roll 10 putts, miss both tees (contact = face open/closed at impact) | https://www.youtube.com/watch?v=MY7O8zX597Q |
| `short-game-chipping` | Landing-spot ladder chips | range | Chip to landing spots at 3/6/9 m, each within a 1.5 m circle; ball-first contact, low point after the ball | https://www.youtube.com/watch?v=8Bp0V7btnos |

## Course management & mental game (`on-course-strategy`)

Strokes leak on the course from *decisions*, not just swings — especially when a
gap shows up on-course but not on the range. These are `where: "course"` blocks:
narrate them, don't animate them (there's no ball-flight to plot). Keep them
measurable — track a number over a few rounds, not a vague "think better."

| Focus | The rule | Measure it |
|-------|----------|-----------|
| Tee-club selection | On any hole with trouble in driver range, drop to the club whose dispersion keeps you in play; driver only where a miss is survivable. | Log tee shots for 3 rounds; pick the club that finds fairway/playable ≥ 80% of the time. |
| Aim to the fat side | Aim at center-of-green (or the safe half away from a tucked pin), never straight at a short-side pin. | Count short-sided approaches per round; target < 2. |
| Lay-up logic | On par-5s / long par-4s you can't reach, lay back to your **best** wedge number (e.g. a full 90 m) instead of a scrappy in-between. | Track how often the approach is a stock number vs an awkward partial; grow the stock share. |
| Avoid the big number | After a bad tee shot, take the punch-out that guarantees bogey-or-better rather than the hero shot. | Count doubles+ caused by a *second* mistake after the first; drive toward 0. |
| Pre-shot routine | Same routine every shot: pick a specific target, one rehearsal, commit, go — no swing thoughts over the ball. | Rate commitment 1–5 per hole; average ≥ 4. |
| Pressure / first tee | Take a club you can swing at 80% and start it at the safe side; breathe out before the trigger. | Track first-tee and closing-hole scores vs your round average; close the gap. |

## Live search procedure

When the library lacks a good match **and a web-search tool is available**:

1. Build a query from the weakness + a credible coach/source, e.g.
   `"7 iron dispersion drill alignment stick"` or
   `"driver launch angle low spin drill Trackman"`.
2. Use the web-search tools to find a recent, reputable YouTube video. Prefer
   known instructors / channels with real coaching credibility over random
   uploads. Favor videos that are demonstrable on a launch monitor.
3. **Verify** the link resolves and matches the described drill before giving it
   to the user — never hand over an unchecked or hallucinated URL.
4. Summarize the drill in the user's plan in your own words + the link(s).

If **no web-search tool is available**, skip live search: give the
fully-specified drill (reps, distances, targets, feel) without a link rather than
inventing one.

## Maintaining the library

When a Live search turns up a good drill:
- Add a row to the curated table (category, drill, `where`, metric what-to-do,
  and the verified link). Keep entries concise and action-oriented.
- Periodically prune dead links and weak drills. Quality over quantity — a small
  set of trusted drills beats a big pile of unchecked links.
