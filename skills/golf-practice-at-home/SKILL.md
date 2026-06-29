---
name: golf-practice-at-home
description: Use when the user wants to practice at home / in the yard / without a ball or range, or can't get to a range. Builds a short daily no-ball routine targeting their diagnosed swing fault, shows each drill animated one at a time, and saves it as a training plan to recall and grade later. Triggers on "practice at home", "no range", "without a ball", "in the yard", "drills I can do at home".
---

# Practice at Home (no ball, no range)

Build the user a short **daily no-ball routine** for the yard or living room with
just a club, targeting their actual swing fault — and **show each drill
animated**, since this is usually asked by someone who learns by seeing. The MCP
tools supply the data; this skill turns it into a home routine.

## Steps

1. **Know the fault.** Reuse the diagnosis — pull the saved plan with
   `training_plan(action="next")` (it carries diagnosis + target_specs), or run a
   quick read via the `trackman-stats-analysis` skill. Don't guess; tie the
   routine to a specific fault (e.g. slice = out-to-in path + open face).

2. **Pick 3–5 no-ball drills for that fault** from the `at-home-no-ball` set in
   the `drill-library` skill, by mechanism:
   - over-the-top / out-to-in path → wall, pump-and-drop, step-through
   - open face → split-hands release, mirror face check
   - both → trail-arm-only throws

3. **Make it a routine, not a list.** A 5–10 min daily block: ordered
   (transition → path → face), reps each, one *feel* per drill, what it fixes.
   Daily beats weekly; go slow and over-correct (neutral feels like a hook first).

4. **Show it — one drill at a time, with a video.** Animate each drill (red
   current → green target) via the `trackman-visualizer` skill, one per exercise,
   **and give each a verified YouTube link** (from `drill-library`, or
   live-search + verify — never invent URLs). Animation + video for every drill.

5. **Save it.** Persist with `training_plan(action="save")` (title, drills as
   blocks, fault in `diagnosis`, `target_specs` from the swing plan if
   measurable) so "what's today's training?" recalls it and you can grade it
   once they're back on a launch monitor.

Close by telling them to do it daily, and that you'll check it against their
numbers next range session.
