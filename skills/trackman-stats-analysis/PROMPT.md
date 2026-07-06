# Trackman Stats Analysis

Pull the user's Trackman data via the `golf-coach` MCP tools and produce an
honest, specific **diagnosis** of where they're losing strokes. This is analysis
only — for a drill plan, use the **golf-coaching** prompt.

## Gather

Run `auth(action="status")` first; if it reports expired/not signed in, tell the
user to run `golf-coach login` and stop (don't invent numbers). Then:

- `trackman(action="profile")` → current handicap.
- `trackman(action="handicap")` → handicap trend.
- `trackman(action="sessions")` → recent practice + rounds.
- `trackman(action="rounds")` → scorecards for scoring analysis.
- `trackman(action="clubs")` → per-club gapping and dispersion.
- `trackman(action="session", activity_id=...)` → shot-level detail where you need it.

Then call `synthesize()` — it aligns these Trackman findings against any
GameBook on-course findings by skill area (Trackman is clean-room/flat-lie;
GameBook is on-course, real conditions), so use the aligned view where
available instead of reasoning over `trackman` output alone.

## Analyze (keep only what the data supports)

1. **Club gapping.** From `trackman(action="clubs")`, list avg carry per club. Flag
   overlaps (< ~8–10 m between adjacent clubs) and holes (> ~20 m). Gaps cost
   approach shots.
2. **Dispersion / consistency.** Per club, carry spread and side scatter. Wide
   side dispersion on scoring clubs (wedges, short irons) is high-value to fix.
   Note the tightest and loosest clubs.
3. **Launch quality.** Low smash (poor strike), spin too high/low, launch+spin
   combos that kill carry. Driver especially: launch/spin vs an efficient window.
4. **Scoring trends** (from rounds): fairways hit %, GIR, putts/round, and where
   doubles+ come from (driving / approach / short game).
5. **Handicap movement.** Up, flat, or down over the window — tie it to the above.

## Output: the diagnosis

A short, ranked list — **highest stroke-impact first** — e.g.:

```
1. [Approach] 8-iron side dispersion ±18 m, carry varies 12 m → missing greens.
2. [Gapping] 4-iron and 5-hybrid both carry ~178 m → wasted slot; 188–196 m open.
3. [Driver] launch 9.1° / spin 3400 rpm → ballooning, ~14 m carry left on table.
4. [Short game] 3-putts mostly from >9 m → speed control.
```

For each: the **club/area**, the **specific number** that's off, and **why it
costs strokes** — never vague ("be more consistent"). Cite the metric you read it
from. If data is too thin to judge something, say "not enough data." When the
user wants this turned into practice, hand off to the **golf-coaching** prompt.

## On-course rounds

Trackman covers practice and launch-monitor data. The user's real course rounds
come from Golf GameBook via the `gamebook` tool (screenshot-ingested). When
diagnosing scoring/course trends, include `gamebook(action="compare")` — or
better, `synthesize()`, which already folds GameBook's scoring findings in
alongside Trackman's — but trust only the scoring dimension unless a stat's
`coverage` is not `none`.
