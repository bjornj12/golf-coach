# Practice at Home (no ball, no range)

Build the user a short **daily no-ball routine** they can do in the yard or living
room with just a club, targeting their actual swing fault — and **show each drill
animated**, because this is usually asked by someone who learns by seeing, not
reading. Use when they say "what can I do at home / without a ball / no range,"
or can't get to a range.

## Steps

1. **Know the fault.** Reuse the existing diagnosis: pull the saved plan with
   `training_plan(action="next")` (it carries the diagnosis + target_specs), or
   if there's none, do a quick read via the `trackman-stats-analysis` prompt
   (e.g. a slice = out-to-in path + open face → spin axis tilted). Don't guess —
   tie the routine to a specific fault.

2. **Pick 3–5 no-ball drills that hit that fault.** Use the `at-home-no-ball`
   set in the `drill-library` prompt and choose by mechanism:
   - over-the-top / out-to-in path → **wall**, **pump-and-drop**, **step-through**
   - open face → **split-hands release**, **mirror face check**
   - both path + face → **trail-arm-only throws**
   Don't pile on — 3–5 that cover the fault beats ten.

3. **Make it a routine, not a list.** A 5–10 minute daily block: order the
   drills (transition fix → path → face), reps each, the one *feel* per drill,
   and what it fixes. Daily beats weekly; go slow and over-correct (neutral will
   feel like a hook at first).

4. **Show it — one drill at a time, with a video.** Animate each drill's intended
   motion (red current move → green target move) via the `trackman-visualizer`
   prompt, one per exercise, **and give each drill a verified YouTube link** (from
   the `drill-library` prompt, or live-search + verify one — never invent URLs).
   Animation + video for every drill; lead with the visual, don't make them ask.

5. **Save it so it sticks.** Persist the routine with `training_plan(action="save")`
   (title like "At-home no-ball slice routine", the drills as blocks, the fault
   in `diagnosis`, and `target_specs` copied from the swing plan if measurable),
   so "what's today's training?" recalls it and you can grade it later once they
   get back on a launch monitor.

Close by telling them to do it daily and that you'll check it against their
numbers next range session.
