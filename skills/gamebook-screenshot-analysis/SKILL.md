---
name: gamebook-screenshot-analysis
description: Use to ingest Golf GameBook round screenshots (Round Summary + Statistics) into the coach. Extracts a coverage-aware round from the images, self-checks the read, stores it via the gamebook_round MCP tool (rolling last 5), and returns a normalized summary plus scoring-led progress vs prior rounds. Only score-per-hole is trusted; every other stat is flagged by how completely it was tracked.
---

# GameBook Screenshot Analysis

Turn the user's Golf GameBook screenshots into a structured on-course round the
coach can use. GameBook has no export/API, but the data is on the user's phone as
screenshots — read them directly.

## The one rule that governs everything

GameBook reliably records only **score-per-hole**. Putts, fairways, GIR, chips,
bunkers, scrambling, up-and-down and sand saves are only as complete as what the
golfer tapped in during the round. **Never analyze a dimension that wasn't really
tracked.** A "0.0%" sand-save/up-and-down/scrambling with no supporting hole data
means "not entered," not a genuine zero. Flag coverage; do not invent.

## Run this off the main thread

This reads several images (large tokens). In Claude Code, the main agent should
dispatch ONE fresh subagent (Task/Agent tool, `general-purpose`) whose prompt is:
"Follow the gamebook-screenshot-analysis skill end to end on these image paths:
<paths> and return only the final summary." The subagent does the work and
returns just the summary. If you are that dispatched worker, proceed.

## Reading the screens (legend)

- **Header:** the big number is **gross** (it may sit partly behind the "Net
  score" label — it's still the round total; confirm it equals Out+In). "Net
  score" + a coloured +/- chip = net and net-to-par. "Position x/y" = group finish.
- **Scorecard rows:** HCP, Par, Score, Net, then Putts, Fairways, GIR, Bunkers,
  Chips, Penalties, with an Out/In total column. A **blank cell means not entered
  → `null`, never 0.**
- **Fairway icons:** ✓ = hit, → = missed right, ← = missed left; blank on a par 3
  = `na`. The Out/In fairway total (e.g. 3/5) counts only *tracked* driving holes.
- **GIR icons:** ✓ = green hit; an arrow (↑ ↓ ← →) = missed that way (still a
  miss). If the per-hole card and the Statistics dial disagree, **trust the card**
  (this round: card 1/18 vs dial 8%).
- **Statistics → Scores** gives bogey/double/worse counts and par-type averages —
  use them to **cross-check** the per-hole read, not as the source.
- **The 0.0% trap:** Scrambling / Up-and-Down / Sand save at 0.0% with no
  hole-level chip/bunker data means *not tracked* → coverage `none`, not a real 0.

## Workflow

1. **Group the images into one round.** A round is usually 2 scorecard halves
   (front/back) plus optional Statistics pages. The **scorecard is the source of
   truth**; Statistics pages are used only to validate and to read miss-direction
   splits. If only the scorecard is provided, that's fine — you still get the
   reliable scoring dimension.

2. **Extract per hole** from the scorecard: `par`, `score`, and when present
   `putts`, `fairway` (`hit`/`miss_left`/`miss_right`/`na` on par 3s),
   `gir` (bool), `bunkers`, `chips`, `penalties`. Use `null` for any hole where a
   value isn't shown. Read the course `par`, `CR`, `slope`, and the header
   `gross`/`net`/`position`.

3. **Assign coverage per dimension** (`full`/`partial`/`none`): full if tracked on
   ~90%+ of eligible holes (fairways exclude par 3s), partial if some, none if
   zero. Any Statistics-page rate (sand save, up-and-down, scrambling) with no
   hole-level backing is `none`. If a Statistics number contradicts the
   scorecard, keep the scorecard and add a `notes` entry.

4. **Self-check before saving.** Confirm hole scores sum to gross, hole pars sum
   to course par, and there are 9 or 18 holes. If anything fails, show the user
   the holes you're unsure about and fix the read — do not save a wrong round.

5. **Save** by calling `gamebook_round(action="save", round=<record>)`. The record
   shape is in the tool docs; the tool computes the `scoring` block and stores it
   (rolling last 5). If it returns `saved: false`, resolve the `problems` and retry.

6. **Report progress.** Call `gamebook_round(action="compare")`. Summarize the
   latest round and its direction of travel vs prior rounds — **confidently on
   scoring, and on any other dimension only where `comparable` is true** — then
   hand off to `golf-coaching` for the practice prescription.

## Output format (this skill's return value)

```
## GameBook round — <date> (<course par>, gross <gross> / net <net>)

<one-line headline: to-par and the scoring shape>

**Scoring (reliable):** +<to_par>; <bogey>/<double>/<triple_plus> spread;
par-3 <+x.xx>, par-4 <+x.xx>, par-5 <+x.xx>.

**Tracked this round:** putts <coverage>, fairways <coverage>, GIR <coverage>,
short game <coverage>. <one line naming what's too sparse to judge>

**Progress vs last <n> rounds:** <to-par direction + par-type direction; putts
direction only if comparable; "accuracy not comparable — not tracked in enough
rounds" otherwise>

<Notes: any scorecard-vs-stats discrepancies>
```

Keep it factual. No drills here — `golf-coaching` prescribes from this.
