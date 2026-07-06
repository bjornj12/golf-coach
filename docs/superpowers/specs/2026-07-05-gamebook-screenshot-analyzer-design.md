# GameBook Screenshot Analyzer — Design

*2026-07-05*

## Problem

Trackman covers the user's **practice and launch-monitor** data, but not their
**real on-course rounds**. That on-course record lives in Golf GameBook, which
has no public API, no export, and a mobile-only client — every programmatic route
into it is a ToS-violating reverse-engineering effort (see
`docs/golfgamebook-api.md` for why that road was abandoned).

But the data the user cares about is already on their phone as **screenshots** of
GameBook's Round Summary and Statistics screens. Claude can read those directly.
So instead of fetching GameBook data, we **ingest screenshots the user pastes**,
extract a structured round, and feed it to the existing coach — giving the
golf trainer the missing on-course dimension without touching GameBook's servers.

The critical constraint, learned from a real sample round (9 June 2026, 8
screenshots): **GameBook only reliably records score-per-hole.** Everything
else — putts, fairways, GIR, chips, bunkers, scrambling, up-and-down, sand
saves, putting distances — is only as complete as what the user tapped in during
the round. In that sample, putts were logged on ~12 of 18 holes, only 6 of ~12
driving holes had a fairway result, and Scrambling / Up-and-Down / Sand-save all
read "0.0%" purely because nothing was entered. **The analyzer must know what it
doesn't know** and refuse to analyze dimensions that weren't really tracked.

## Goals

- A **skill** (`gamebook-screenshot-analysis`) that takes N screenshots of one
  GameBook round, extracts a **coverage-aware** round record, self-checks the
  read arithmetically, and returns a normalized summary.
- A small **MCP tool** (`gamebook_round`) backing a local JSON store
  (`~/.trackman-mcp/gamebook-rounds.json`), a **rolling window of the last 5
  rounds**, newest first.
- **Coverage as a first-class field**: every non-scoring dimension carries a
  `full | partial | none` flag plus a holes-tracked count. The extractor's job
  includes *measuring what's missing*, not just reading what's there.
- **Scoring-led progress**: `gamebook_round(action="compare")` computes
  deterministic deltas of the newest round vs the up-to-4 before it, stated
  confidently on scoring and only-where-both-rounds-tracked-it on everything
  else. The coach turns those deltas into the "you're progressing / backsliding /
  plateaued — go practice X" narrative.
- Respect the repo's hard boundary: the **skill** does vision extraction, the
  **server** stores and computes deterministic deltas, the **coaching skills** do
  all judgment. No coaching verdict in the server; no hardcoded data in the skill.

## Non-goals

- **No GameBook API / scraping / interception.** Screenshots are the only input.
- **No handicap or all-time-aggregate screens in v1** — scope is single-round
  scorecards + that round's Statistics pages. (Easy to add later.)
- **No fabricated data.** A dimension that wasn't tracked is reported as `none`,
  never estimated. "0.0% sand save" with no bunker-hole detail is `none`, not a 0.
- **No coaching output from the skill or server** — direction/deltas only; the
  prescription is `golf-coaching`'s.
- Not capped at 30 like the Trackman session store — **5**, per the user's ask
  (a short "are you trending up or down" window, not a full history).

## Architecture

Three pieces, matching existing patterns in the repo:

```
User pastes N screenshots of one round (main thread)
        │
        ▼
skill: gamebook-screenshot-analysis         (mirrors trackman-session-analyzer)
  • dispatched as a SUBAGENT given the image file paths (keeps image tokens
    off the main thread); runs inline in non-Claude-Code clients
  • vision-extracts each image → merges into one coverage-aware round record
  • arithmetic self-check (Out+In == gross; distribution & par-type avgs
    reconcile) — on mismatch, flags the specific holes instead of saving
  • echoes the scorecard for a one-line user confirm
        │ calls
        ▼
MCP tool: gamebook_round(action, …)         (mirrors training_plan / session_analysis)
  • save   → persist record, evict oldest beyond 5
  • list   → index (date, course, gross/net/to_par, coverage), newest first
  • get    → one full record
  • compare→ deterministic newest-vs-prior-4 deltas (analysis.py-style)
  • store: ~/.trackman-mcp/gamebook-rounds.json  (JSON, cap 5, newest first)
        │ deltas
        ▼
skills: golf-coaching / trackman-stats-analysis
  • read compare() output, respect coverage flags, produce the progress
    narrative + practice prescription (the "kick in the nuts")
```

### The coverage-aware round record

Source of truth is the **two scorecard halves**; the Statistics pages are used to
**validate and enrich**, never as the primary number.

```jsonc
{
  "id": "2026-06-09",                       // date; suffix -2 etc. if same-day dupe
  "date": "2026-06-09",
  "source": "golf-gamebook",
  "course": { "par": 70, "cr": 68.1, "slope": 119, "name": null },
  "result": { "gross": 109, "net": 62, "to_par": 39, "position": "1/4" },

  "holes": [                                // 18 entries; score+par always present
    { "hole": 1, "par": 4, "score": 7, "putts": 2,
      "fairway": "hit",                     // hit | miss_left | miss_right | na | null
      "gir": false, "bunkers": 0, "chips": 0, "penalties": 0 }
    // …
  ],

  "scoring": {                              // ALWAYS full — derived from holes
    "to_par": 39,
    "distribution": { "eagle_or_better": 0, "birdie": 0, "par": 0,
                      "bogey": 7, "double": 5, "triple_plus": 6 },
    "by_par_type": { "par3": 2.83, "par4": 1.88, "par5": 1.75 }
  },

  "dimensions": {                           // value + how complete it is
    "putts":       { "total": 27, "holes_tracked": 12, "coverage": "partial" },
    "fairways":    { "hit": 4, "tracked": 6, "eligible": 12, "coverage": "partial" },
    "gir":         { "hit": 1, "tracked": 12, "coverage": "partial" },
    "bunkers":     { "total": 3, "coverage": "partial" },
    "chips":       { "total": 12, "coverage": "partial" },
    "penalties":   { "total": 1, "coverage": "partial" },
    "sand_save":   { "value": null, "coverage": "none" },   // app showed 0.0%, untracked
    "up_and_down": { "value": null, "coverage": "none" },
    "scrambling":  { "value": null, "coverage": "none" }
  },

  "coverage": { "scoring": "full", "putts": "partial", "fairways": "partial",
                "gir": "partial", "short_game": "none" },

  "notes": [ "GIR: scorecard 1/18 but Stats dial read ~8% — treated as low-confidence",
             "Sand save / up&down / scrambling shown as 0.0% with no hole data → none" ]
}
```

**Coverage rules (deterministic, applied by the extractor):**

- `scoring` → always `full` (score + par exist on every hole).
- Per-hole dimension (putts, fairways, gir, bunkers, chips, penalties):
  `full` if tracked on ≥ ~90% of *eligible* holes (fairways exclude par-3s),
  `partial` if some, `none` if zero.
- A Statistics-page summary rate (sand save, up-and-down, scrambling) that has
  **no corroborating hole-level data** is `none` regardless of the % shown —
  "0.0%" almost always means "not entered," and we must not read it as a real 0.
- Any Stats-page number that **contradicts** the scorecard is kept as a `note`
  and the scorecard wins.

### Arithmetic self-check (before save)

The extractor validates its own read using GameBook's internal redundancy:

- `Out + In == gross` (49 + 60 == 109 ✓)
- score distribution reconstructed from holes matches the Stats "Scores" bars
  (7 bogey / 5 double / 6 worse ✓)
- per-hole scores reproduce the "Average Per Hole" par-type figures
  (par-3 +2.83, par-4 +1.88, par-5 +1.75 ✓)

If any check fails, the skill reports the specific holes it's unsure about and
asks the user, rather than saving a wrong record. (On the sample round all three
checks pass, which is why its scorecard read is high-confidence.)

### `gamebook_round` actions

| action | args | does |
|--------|------|------|
| `save` | `round` | Persist a coverage-aware record; evict oldest beyond 5. Returns the stored record + current count. |
| `list` | — | Index (id, date, course par, gross, net, to_par, coverage map), newest first. |
| `get` | `round_id` | One full record. |
| `compare` | `round_id?` (default latest) | Deterministic deltas of this round vs the up-to-4 chronologically before it: to-par, scoring distribution shift, and score-by-par-type — plus any dimension where **both** rounds are `full`/`partial`. Each delta tagged `better|worse|same` and carries the min coverage of the pair. No narrative. |

`compare` lives in analysis code (new `gamebook_analysis.py` or an addition to
`analysis.py`), same "measurement not coaching" stance as
`analysis.verify_targets`.

### Coaching integration

`golf-coaching` (and `trackman-stats-analysis`) get a short section: on-course
rounds are available via `gamebook_round`; call `compare` for progress; **lead
with scoring, and speak to any other dimension only where its coverage is not
`none` and both compared rounds tracked it.** The motivational "go practice X"
line keys off the reliable signals (e.g. this round: par-3 scoring +2.83, 6
triple-plus holes) — never off an untracked 0.0%.

## Data flow (the sample round)

1. User pastes 8 images for one round → main agent dispatches the
   `gamebook-screenshot-analysis` subagent with the 8 file paths.
2. Subagent reads all 8, builds the record above, runs the 3 self-checks (pass),
   echoes the scorecard, and on confirm calls `gamebook_round(action="save")`.
3. Later rounds accumulate (cap 5). When round #2+ arrives, the coach calls
   `gamebook_round(action="compare")` and tells the user the direction of travel
   on scoring, honestly caveating the sparse dimensions.

## Testing

- **Fixture**: the 9 June round — the 8 PNGs (or a hand-verified transcription)
  under `tests/fixtures/gamebook/2026-06-09/`, plus the expected normalized
  record. It's the user's own round; no secrets to scrub beyond leaving the
  course name null (never shown).
- **Extraction contract test**: expected record's `scoring` block and coverage
  flags (scoring `full`, putts/fairways/gir `partial`, short-game `none`).
- **Self-check test**: a deliberately corrupted hole makes `Out+In != gross` and
  is rejected/flagged.
- **Store test**: cap-at-5 rolling eviction; `list` ordering newest-first.
- **compare test**: two fixtures → correct `better/worse/same` on to-par and
  par-type scoring, and correct suppression of a dimension that's `none` in one.

## Boundary compliance

- Skill = vision extraction (reads the user's screenshot live; no hardcoded data).
- Server = storage + deterministic deltas (no verdicts).
- Coaching skills = all judgment, constrained by coverage flags.
- Served as an MCP prompt like the other skills (Desktop can attach images),
  except the run-in-a-subagent detail is Claude-Code-specific.

## Open decisions (confirm in review)

1. **Round id**: date string, `-2` suffix on same-day duplicates. OK?
2. **Store path**: `~/.trackman-mcp/gamebook-rounds.json`, consistent with
   `training-plans.json` / `session-analyses.json`. OK?
3. **Subagent extraction** in Claude Code (vs inline): proposed **subagent** to
   keep 8-image token loads off the main thread, matching
   `trackman-session-analyzer`. OK?
