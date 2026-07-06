# GameBook Screenshot Analysis

Turn the user's Golf GameBook screenshots into a structured on-course round the
coach can use. GameBook has no export/API — read the screenshots directly.

## The one rule that governs everything

GameBook reliably records only **score-per-hole**. Putts, fairways, GIR, chips,
bunkers, scrambling, up-and-down and sand saves are only as complete as what the
golfer tapped in. **Never analyze a dimension that wasn't really tracked.** A
"0.0%" sand-save/up-and-down/scrambling with no supporting hole data means "not
entered," not a genuine zero. Flag coverage; do not invent.

## Reading the screens (legend)

- **Header:** the big number is **gross** (it may sit partly behind the "Net
  score" label — it's still the round total; confirm it equals Out+In). "Net
  score" + a coloured +/- chip = net and net-to-par. "Position x/y" = group finish.
- **Scorecard rows:** HCP, Par, Score, Net, then Putts, Fairways, GIR, Bunkers,
  Chips, Penalties, with an Out/In total column. A **blank cell means not entered
  → `null`, never 0.**
- **Fairway icons:** ✓ = hit, → = missed right, ← = missed left; blank on a par 3
  = `na`. The Out/In fairway total counts only *tracked* driving holes.
- **GIR icons:** ✓ = green hit; an arrow (↑ ↓ ← →) = missed that way (still a
  miss). If the per-hole card and the Statistics dial disagree, **trust the card**.
- **Statistics → Scores** gives bogey/double/worse counts and par-type averages —
  use them to **cross-check** the per-hole read, not as the source.
- **The 0.0% trap:** Scrambling / Up-and-Down / Sand save at 0.0% with no
  hole-level data means *not tracked* → coverage `none`, not a real 0.

## Workflow

1. **Group the images into one round** — usually 2 scorecard halves plus optional
   Statistics pages. The **scorecard is the source of truth**; Statistics pages
   only validate and give miss-direction splits. Scorecard-only is fine.

2. **Extract per hole** from the scorecard: `par`, `score`, and when shown
   `putts`, `fairway` (`hit`/`miss_left`/`miss_right`/`na`), `gir`, `bunkers`,
   `chips`, `penalties` — `null` where absent. Read course `par`/`CR`/`slope` and
   the header `gross`/`net`/`position`.

3. **Assign coverage per dimension** (`full`/`partial`/`none`): full at ~90%+ of
   eligible holes (fairways exclude par 3s), partial if some, none if zero. Any
   Statistics rate with no hole-level backing is `none`. Scorecard wins ties;
   record contradictions in `notes`.

4. **Self-check before saving:** hole scores sum to gross, hole pars sum to
   course par, 9 or 18 holes. If anything fails, confirm the shaky holes with the
   user and fix the read first.

5. **Save** with `gamebook(action="save", round=<record>)` (the tool computes
   the scoring block and keeps the last 5). If it returns `saved: false`, fix the
   `problems` and retry.

6. **Report progress** with `gamebook(action="compare")` — confidently on
   scoring, and on other dimensions only where `comparable` is true — then use the
   `golf-coaching` prompt for the practice prescription.

Keep the summary factual and lead with the reliable scoring story. No drills
here — `golf-coaching` prescribes from this.
