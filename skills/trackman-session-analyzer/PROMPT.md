# Trackman Session Analyzer

Ingest the user's recent Trackman sessions, store a deterministic analysis of
each (the MCP keeps the last 30, newest first), and report the **most recent
session with its stats normalized against prior sessions**. The heavy
computation (classify, metrics, course difficulty, normalization,
used-vs-available clubs) happens inside the MCP — your job is orchestration and
narration, not recomputing numbers. Keep it tight; don't paste raw shot payloads
into the conversation.

## Workflow

1. **Auth.** `auth(action="status")`. If not authenticated, tell the user to run
   `golf-coach login` and stop — don't fabricate data.
2. **Recent sessions.** `trackman(action="sessions", take=30)` (newest first) —
   practice and rounds.
3. **What's already stored.** `session_analysis(action="list")` for stored ids.
4. **Analyze new sessions, OLDEST first.** Walk the fetched list oldest → newest;
   for each id not already stored, call
   `session_analysis(action="analyze", activity_id=<id>)`. Oldest-first matters:
   each session is normalized against the ones chronologically before it, so the
   history must be stored before the newest is analyzed. If a call errors, note
   it and continue.
5. **Read back the latest.** `session_analysis(action="list")` again → take
   `latest_id` → `session_analysis(action="get", activity_id=latest_id)` for the
   full record.
6. **Summarize the latest** using that record's fields (`category`,
   `seriousness`, `is_improvement_attempt`, `reasons`, `metrics`, `normalized`,
   `clubs_used`, `clubs_unused`, `summary`).

## What the classification means (already computed)

- **game** — a played round; reported with score-to-par, GIR, putts, driving, and
  a 0–1 course-difficulty score.
- **practice** — a genuine improvement attempt (enough volume/duration/club
  variety, or a focused kind: shot analysis, find-my-distance, performance
  center, map-my-bag, putting, combine). `is_improvement_attempt` true.
- **warmup** — too short/few strokes to count (e.g. 8 balls over 5 min, one
  club). `is_improvement_attempt` false. Don't credit these as training.

## Output

```
## Latest Trackman session — <date> (<category>)

<one-line headline from the record's summary>

**Type:** <game | serious practice | warm-up>  ·  seriousness <0–1, if practice>
**Why:** <reasons>

**Key stats** (metric units — m/s, meters):
<game: to_par, GIR, putts, drive avg, course difficulty>
<practice: stroke count, duration, clubs used, avg carry, notable per-club>

**Normalized vs prior sessions** (n = <history size>):
<each normalized metric: value, mean, delta, better/worse>

**Clubs:** used <clubs_used>  ·  available-but-unused <clubs_unused>

**Habit check:** of the last <N> stored sessions, <X> serious practice,
<Y> warm-ups, <Z> games.
```

Keep it factual. This prompt doesn't give drills — for a plan, use the
**golf-coaching** prompt.
