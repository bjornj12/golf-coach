---
name: trackman-session-analyzer
description: Use to ingest and analyze the user's recent Trackman sessions and report on the most recent one. Pulls activities via the MCP, classifies each as warm-up vs serious practice vs game, stores a per-session analysis locally (last 30, latest first), and returns a normalized performance summary of the LATEST session vs prior sessions. This is a data-collection skill — it MUST run in a forked subagent, never on the main thread.
---

# Trackman Session Analyzer

Ingests the user's recent Trackman sessions, stores a deterministic analysis of
each in the MCP's local store (capped at the last 30, newest first), and returns
a **summary of the most recent session with its stats normalized against prior
sessions**.

<HARD-RULE: RUN IN A FORK, NEVER ON THE MAIN THREAD>
This is a **data-collection** skill. It makes many MCP calls and pulls large
shot-level payloads that would bloat the main conversation. The main agent must
**NOT** execute the steps below inline.

Instead, the main agent's ONLY job is to **dispatch a single subagent** (the
Agent/Task tool, `general-purpose` type) whose prompt is "Follow the
trackman-session-analyzer skill end to end and return only the final summary."
The subagent does all the work in its own context and returns just the summary
section. If you are the dispatched subagent, proceed with the workflow.
</HARD-RULE>

## Inputs / tools used (all from the `trackman-golf` MCP)

`auth`, `list_sessions`, `session_analysis(action="analyze")`,
`session_analysis(action="list")`, `session_analysis(action="get")`. The heavy lifting (classify,
metrics, course difficulty, normalization, used-vs-available clubs) is done
deterministically inside `session_analysis(action="analyze")` — your job is orchestration
and narration, not recomputing numbers.

## Workflow (subagent)

1. **Auth check.** Call `auth`. If not authenticated, stop and report
   that the user needs to run `trackman-mcp login` — do not fabricate data.

2. **Pull recent sessions.** Call `list_sessions` with `take: 30` (newest
   first). This includes both practice activities and course rounds.

3. **Find what's new.** Call `session_analysis(action="list")` to get already-stored ids.

4. **Analyze + store new sessions, OLDEST first.** Reverse the fetched list and
   walk it oldest → newest. For each session whose id is not already stored, call
   `session_analysis(action="analyze", activity_id)`. Oldest-first matters: each session is
   normalized against the sessions chronologically before it, so the history must
   already be stored when the newest session is analyzed. The store keeps only the
   last 30. Skip nothing silently — if a call errors, note it and continue.

5. **Read back the latest.** Call `session_analysis(action="list")` again, take
   `latest_id`, then `session_analysis(action="get", activity_id=latest_id)` for the full record.

6. **Summarize the latest session** using that record (see format below). Use
   the record's own fields — `category`, `seriousness`, `is_improvement_attempt`,
   `reasons`, `metrics`, `normalized`, `clubs_used`, `clubs_unused`, `summary`.
   For "normalized vs previous," report the `normalized` deltas/z-scores.

## What the classification means (already computed for you)

- **game** — a played round (COURSE_PLAY / ON_COURSE / virtual). Reported with
  score-to-par, GIR, putts, driving, and a 0–1 **course difficulty** score.
- **practice** — a genuine attempt to improve: enough volume/duration/club
  variety, or an inherently focused kind (shot analysis, find-my-distance,
  performance center, map-my-bag, putting, combine). `is_improvement_attempt`
  is true.
- **warmup** — too short/few strokes to count as improvement (e.g. 8 balls over
  5 minutes with one club). `is_improvement_attempt` is false. **Do not** credit
  these as training.

## Output format (this is the skill's return value)

Return ONLY this summary — not the raw session payloads.

```
## Latest Trackman session — <date> (<category>)

<one-line headline from record.analysis.summary>

**Type:** <game | serious practice | warm-up>  ·  seriousness <0–1, if practice>
**Why classified this way:** <record.analysis.reasons>

**Key stats** (metric units — m/s, meters):
<for a game: to_par, GIR, putts, drive avg, course difficulty>
<for practice: stroke count, duration, clubs used, avg carry, notable per-club>

**Normalized vs your prior sessions** (n = <history size>):
<for each normalized metric: value, mean, delta, and whether better/worse>

**Clubs:** used <clubs_used>  ·  available-but-unused <clubs_unused>

**Recent habit check:** of the last <N> stored sessions, <X> were serious
practice, <Y> warm-ups, <Z> games.
```

Keep it tight and factual. This skill **does not** give coaching drills — hand
the summary to the `golf-coaching` skill for that.
