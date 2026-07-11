# Practice at Home (no ball, no range)

**This is a thin pointer — the logic lives elsewhere.** An at-home / no-ball
routine is already first-class in the coach, so don't re-implement it here:

- **`golf-coaching`** rule 4 already mandates at least one at-home / no-ball
  block in every plan (and its at-home flavor builds a full home routine).
- **`drill-library`** holds the `at-home-no-ball` drill set — the **single source
  of truth** for those drills, their feel cues, and their videos.
- **`training_plan(action="save")`** persists the routine and later grades it.

When the user asks for a home / no-ball routine ("what can I do at home / without
a ball / no range"):

1. Run the **`golf-coaching`** prompt in its at-home flavor — reuse the existing
   diagnosis (`training_plan(action="next")`, or a quick `trackman-stats-analysis`
   read), then build the plan.
2. Pull drills from the **`drill-library`** prompt's `at-home-no-ball` set,
   matched to the diagnosed fault (over-the-top / out-to-in → wall, pump-and-drop,
   step-through; open face → split-hands release, mirror face check; both →
   trail-arm-only throws).
3. Present it home-first: a 5–10 min ordered daily block (transition → path →
   face), reps + one *feel* per drill, videos where available (from
   `drill-library` or a verified live search — never invented), rendered via the
   **`trackman-visualizer`** prompt as `where: "home"` Fix-it blocks.
4. Save it with `training_plan(action="save")` so "what's today's training?"
   recalls and grades it next range session.

Everything above is `golf-coaching` + `drill-library` behavior — this prompt only
routes there so the at-home path isn't a second full copy that drifts. Close by
telling the user to do it daily and that you'll check it against their numbers
next range session.
