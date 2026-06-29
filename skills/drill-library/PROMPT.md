# Drill Library

A library of golf drills mapped to weaknesses, each with a vetted YouTube link,
**plus** a procedure for finding fresh videos when nothing fits. Use it to fill
the practice blocks in a coaching plan.

**Every drill you hand the user ships with a video link — no exceptions.** If the
table has no link for it, run Live search and verify one before giving it. Never
hand over a drill without a video, and never invent a URL.

## How to use

1. Identify the weakness category from the diagnosis (below).
2. Pick the best-matched drill from the curated table.
3. If nothing fits, run **Live search**, use the result, and tell the user it's a
   freshly-found video (verified, not from the seed table).

## Categories

`driver-launch` · `dispersion-irons` · `gapping` · `wedge-distance-control` ·
`strike-low-point` · `start-line-face-control` · `putting-speed` ·
`putting-start-line` · `short-game-chipping` · `on-course-strategy` ·
`at-home-no-ball`

## At-home / no-ball drills (no range, no ball, just the club)

Reach for these whenever the user can't get to a range, asks "what can I do at
home / in the yard / without a ball," or has a path/face fault where rehearsal
beats ball-striking (there's no result to chase, so the new motion grooves
faster). Each maps to a specific fault — pick by the diagnosis.

| Drill | Fixes | What to do |
|-------|-------|-----------|
| **Wall / fence** | over-the-top, out-to-in path | Set a wall a clubhead's length off the trail shoulder along the target line; slow swings that *miss* it force the club to drop inside. Instant feedback. |
| **Pump-and-drop** | the over-the-top *transition* | At the top, pump the hands down twice feeling the trail elbow tuck and the club shallow behind you, then finish. Grooves the slot. |
| **Trail-arm-only throws** | inside path **+** face closing | Club in the trail hand only; slow "skip a stone to right field" swings. Brings it from inside and rotates the forearm to square the face. |
| **Split-hands release** | open face at impact | Hands a few inches apart; slow half-swings through impact so the trail forearm crosses over — exaggerates squaring the face. |
| **Step-through** | sequencing (arms over-the-top) | Feet together; step toward the target with the lead foot as you start down, then swing — lower body leads instead of the arms heaving over. |
| **Mirror face check** | open clubface awareness | In a mirror, rehearse impact and check the leading edge; learn what square *looks* like vs your habitual open. |
| **Towel/headcover under trail arm** | connection / over-the-top | Trap a towel under the trail armpit through the backswing/transition; keeps the arm connected so the club doesn't fly out and over. |

**Ground rules to tell the user (these make it transfer):**
- **Go slow and over-correct.** For an ingrained out-to-in/open-face habit, a
  genuinely neutral move will *feel* like a wild hook for a while — it isn't.
- **Daily beats weekly.** 5 minutes/day rewires the pattern faster than one long
  session.
- **Want start-line feedback without a ball?** Swing at a dandelion head or a tee
  in the grass — direction feedback, zero pressure.

These are **best shown animated, one drill at a time** (red current move → green
target move) — see the `trackman-visualizer` prompt.

## Curated library

> Verify a link still resolves before handing it over. Each entry:
> weakness → drill → what to do → link.

| Category | Drill | What to do | Video |
|----------|-------|-----------|-------|
| `wedge-distance-control` | Clock / ladder wedges | 3 carry numbers (e.g. 50/70/90 m), 5 balls each, log carry on Trackman; aim ±5 m | _find via Live search_ |
| `dispersion-irons` | Gate / alignment-stick window | Sticks as a start-line gate; 7-iron must start every ball through the gate | _find via Live search_ |
| `strike-low-point` | Towel / line drill | Strike a line so the divot starts after the ball; check smash factor | _find via Live search_ |
| `driver-launch` | Tee height + AoA ladder | Adjust tee height/ball position to raise launch & cut spin; target an efficient launch/spin window | _find via Live search_ |
| `gapping` | Build-your-yardages session | Hit each club 5×, record avg carry, find overlaps/holes; pick one club to re-loft or swap | _find via Live search_ |
| `putting-speed` | Ladder lag drill | Putt to 6/9/12 m, finish within a 1 m zone past the hole; speed over line | _find via Live search_ |

**Never invent YouTube URLs.** If you don't have a verified link, use Live search.

## Live search procedure

1. Build a query from the weakness + a credible coach/source, e.g.
   `"7 iron dispersion drill alignment stick"` or
   `"driver launch angle low spin drill Trackman"`.
2. Use web search to find a recent, reputable YouTube video — prefer known
   instructors with real coaching credibility; favor drills demonstrable on a
   launch monitor.
3. **Verify** the link resolves and matches the described drill before giving it
   to the user — never hand over an unchecked or hallucinated URL.
4. Summarize the drill in your own words + the link.
