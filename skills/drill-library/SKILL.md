---
name: drill-library
description: Use when the golf-coaching skill needs a drill or YouTube video for a specific weakness (dispersion, gapping, driver launch, wedge distance control, putting speed, etc.). Provides a curated library of vetted drills + video links, plus a procedure for live web-searching fresh YouTube content when the library lacks a good match.
---

# Drill Library

A maintained library of golf drills mapped to weaknesses, each with a vetted
YouTube link, **plus** a procedure for finding fresh videos when the library
doesn't have a good match. Used by `golf-coaching` to fill practice blocks.

## How to use

1. Identify the weakness category from the diagnosis (see categories below).
2. Pick the best-matched drill from the curated library.
3. If nothing fits well, run the **Live search** procedure, use the result, and
   **add the new drill to the library** (see "Maintaining" below) so it's there
   next time.

## Drill categories

`driver-launch` · `dispersion-irons` · `gapping` · `wedge-distance-control` ·
`strike-low-point` · `start-line-face-control` · `putting-speed` ·
`putting-start-line` · `short-game-chipping` · `on-course-strategy` ·
`at-home-no-ball`

## At-home / no-ball drills (no range, no ball — just the club)

Use when the user can't get to a range or asks what they can do at home/in the
yard, or for path/face faults where rehearsal beats ball-striking. Map by the
diagnosed fault:

| Drill | Fixes | What to do |
|-------|-------|-----------|
| Wall / fence | over-the-top, out-to-in path | Wall a clubhead's length off the trail shoulder along the target line; slow swings that miss it force the club inside. |
| Pump-and-drop | the over-the-top transition | At the top, pump hands down twice (trail elbow tucks, club shallows behind), then finish. |
| Trail-arm-only throws | inside path + face closing | Trail hand only; slow "skip a stone to right field" swings. |
| Split-hands release | open face at impact | Hands a few inches apart; slow half-swings, feel the trail forearm cross over. |
| Step-through | sequencing | Feet together; step toward target with the lead foot as you start down, then swing. |
| Mirror face check | open-face awareness | Rehearse impact in a mirror; learn what square looks like vs your open habit. |
| Towel under trail arm | connection / over-the-top | Trap a towel under the trail armpit through transition to keep the arm connected. |

Tell the user: go slow and over-correct (neutral will feel like a hook at
first); daily beats weekly; swing at a dandelion/tee for start-line feedback.
Best shown animated one drill at a time (see `trackman-visualizer`).

## Curated library

> Seed entries below. Verify a link still works before handing it to the user;
> replace dead links and prune stale ones. Each entry: weakness → drill → what
> to do → link. Add real, watched-and-verified links as the library grows.

| Category | Drill | What to do | Video |
|----------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | 3 carry numbers (e.g. 50/70/90y), 5 balls each, log carry on Trackman; aim ±5y | _TODO: add vetted link_ |
| `dispersion-irons` | Gate / alignment-stick window | Set sticks as a start-line gate; 7-iron, must start every ball through the gate | _TODO: add vetted link_ |
| `strike-low-point` | Towel / line drill | Strike a line (or just past a towel) so divot starts after the ball; check smash factor | _TODO: add vetted link_ |
| `driver-launch` | Tee height + AoA ladder | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window | _TODO: add vetted link_ |
| `gapping` | Build-your-yardages session | Hit each club 5x, record avg carry, find overlaps/holes; pick one club to re-loft or swap | _TODO: add vetted link_ |
| `putting-speed` | Ladder lag drill | Putt to 20/30/40ft, finish within a 3ft zone past the hole; speed over line | _TODO: add vetted link_ |

These start as `TODO` links on purpose — **do not invent YouTube URLs.** Fill
them via Live search once verified.

## Live search procedure

When the library lacks a good match:

1. Build a query from the weakness + a credible coach/source, e.g.
   `"7 iron dispersion drill alignment stick"` or
   `"driver launch angle low spin drill Trackman"`.
2. Use the web-search tools to find a recent, reputable YouTube video. Prefer
   known instructors / channels with real coaching credibility over random
   uploads. Favor videos that are demonstrable on a launch monitor.
3. **Verify** the link resolves and matches the described drill before giving it
   to the user — never hand over an unchecked or hallucinated URL.
4. Summarize the drill in the user's plan in your own words + the link.

## Maintaining the library

When a Live search turns up a good drill:
- Add a row to the curated table (category, drill, what-to-do, the verified
  link). Keep entries concise and action-oriented.
- Periodically prune dead links and weak drills. Quality over quantity — a small
  set of trusted drills beats a big pile of unchecked links.
