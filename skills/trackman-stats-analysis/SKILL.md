---
name: trackman-stats-analysis
description: Use when the user wants to understand their golf game, find weaknesses, or before building a practice plan. Pulls stats through the Trackman MCP tools and diagnoses weak areas — dispersion, club gapping, scoring trends, handicap movement. Analysis only; the golf-coaching skill turns the diagnosis into drills.
---

# Trackman Stats Analysis

Pull the user's Trackman data via the MCP and produce an honest, specific
**diagnosis** of where they're losing strokes. This skill does NOT prescribe
drills — it hands a prioritized weakness list to the `golf-coaching` skill.

## Inputs

Call the MCP tools (run `auth` first if needed):
- `get_profile` → current handicap.
- `list_sessions` → recent practice + rounds (default: last 60–90 days).
- `get_course_rounds` → scorecards for scoring analysis.
- `get_club_stats` → per-club gapping and dispersion.
- `get_session` / `get_session` → shot-level detail where you need it.

If a tool errors with auth expired, re-run `auth`. If the MCP isn't
built yet (Phase 0/1 incomplete), say so and stop — don't invent numbers.

## What to analyze

Work through these lenses and keep only what the data supports:

1. **Club gapping.** From `get_club_stats`, list avg carry per club. Flag
   overlapping clubs (gaps < ~8–10y between adjacent clubs) and big holes in
   the set (gaps > ~20y). Gaps cost approach shots.
2. **Dispersion / consistency.** Per club, look at carry spread and
   side/left-right scatter. Wide side dispersion on scoring clubs (wedges,
   short irons) is high-value to fix. Note the tightest and loosest clubs.
3. **Launch quality.** Spot inefficiencies: low smash factor (poor strike),
   spin too high/low for the club, launch + spin combos that kill carry. Driver
   especially: launch/spin vs an efficient window.
4. **Scoring trends** (from rounds): fairways hit %, greens in regulation,
   putts/round, and where doubles+ come from (driving? approach? short game?).
   This anchors practice to what actually costs scores.
5. **Handicap movement.** Is it trending up, flat, or down over the window?
   Tie it to the above.

## Output: the diagnosis

Produce a short, ranked list — **highest stroke-impact first** — e.g.:

```
1. [Approach] 8-iron side dispersion ±18y, carry varies 12y → missing greens long/short.
2. [Gapping] 4-iron and 5-hybrid both carry ~195y → a wasted slot; 205–215y gap is open.
3. [Driver] launch 9.1° / spin 3400rpm → ballooning, ~15y carry left on the table.
4. [Short game] 78 putts trend, 3-putts mostly from >30ft → speed control.
```

For each item give: the **club/area**, the **specific number** that's off, and
**why it costs strokes** — never vague ("be more consistent"). Cite the metric
you read it from. If the data is too thin to judge something, say "not enough
data" rather than padding the list.

Hand this ranked list to `golf-coaching`.

## On-course rounds

Trackman covers practice and launch-monitor data. The user's real course rounds
come from Golf GameBook via the `gamebook_round` tool (screenshot-ingested). When
diagnosing scoring/course trends, include `gamebook_round(action="compare")`, but
trust only the scoring dimension unless a stat's `coverage` is not `none`.
