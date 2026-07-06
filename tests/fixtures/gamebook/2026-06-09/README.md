# GameBook extraction eval set — 9 June 2026 round

The user's own Golf GameBook round, used as the ground-truth eval for the
`gamebook-screenshot-analysis` skill and the extraction grader.

**Raw screenshots are gitignored** (personal data — see `.gitignore`). They live
locally alongside this README for running live vision evals; only the
hand-verified golden record (`../2026-06-09.json`) and this manifest are
committed. To re-run the eval you supply your own screenshots matching the layout
below.

## The 8 screens (one round)

| File | Screen | What it grounds |
|------|--------|-----------------|
| `01-scorecard-front9.png` | Round Summary — front 9 | Per-hole par/score/putts/fairway/GIR/bunkers/chips/penalties, holes 1–9; header gross 109 / net 62 / position 1/4; course par 70, CR 68.1, slope 119 |
| `02-scorecard-back9.png` | Round Summary — back 9 | Per-hole, holes 10–18 (In totals) |
| `03-stats-scores.png` | Statistics → Scores | Distribution cross-check (7 bogey / 5 double / 6 worse), avg-to-par +39, par-type avgs (+2.83 / +1.88 / +1.75) |
| `04-stats-fairways.png` | Statistics → Fairways | Fairway hit% and miss-left/right split (0% / 67% / 33%) |
| `05-stats-greens.png` | Statistics → Greens | GIR dial (8% hit) — note the scorecard-vs-dial discrepancy |
| `06-stats-putting.png` | Statistics → Putting | Putts/hole 2.3, 2-putt/3-putt/3+ split |
| `07-stats-putting-distances.png` | Statistics → Putting distances | One-putt %, distance buckets (mostly empty this round) |
| `08-stats-chips-bunkers.png` | Statistics → Chips, Bunkers & Penalties | Scrambling 0.0%, up&down 0.0%, sand save 0.0% (all untracked → coverage `none`) |

## Ground-truth reconciliation (why the golden record is trusted)

The golden `holes` array cross-checks three independent ways:
- front 49 + back 60 = gross **109**;
- reconstructing hole results gives **7 bogey / 5 double / 6 triple-plus**, matching screen 03;
- per-hole scores reproduce par-3 **+2.83**, par-4 **+1.88**, par-5 **+1.75**, matching screen 03.

## Coverage this round (the point of the eval)

`scoring` = full; `putts`/`fairways`/`gir` = partial; `sand_save`/`up_and_down`/`scrambling` = none
(shown as 0.0% but nothing was entered). A correct extraction must reproduce
these coverage flags, not just the numbers.
