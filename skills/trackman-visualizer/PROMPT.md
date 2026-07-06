# Trackman Visualizer

Turn a coaching diagnosis into a **self-contained animated HTML artifact** that
animates the golfer's **real measured flight**: side-view height profile
(launch → apex → landing → roll), top-down shape with every shot's tracer, the
swing path explaining *why* it curves, progress vs targets, and a **Fix it**
section linking drills for range and home. Real shot data only — never invent
shapes or URLs. This is a presentation layer; it adds no new diagnosis.

**Lead with it — don't wait to be asked.** Any time you diagnose a fault, show
a shot pattern, or prescribe drills, build this page. One artifact carries the
whole story: what the ball is actually doing, why, and the exercises that fix
it.

## Gather the inputs (reuse what the coach already pulled, or fetch via the MCP)

1. **Shots** — per-shot measurements for the club under discussion, from
   `trackman(action="session", activity_id=...)`: `launchDirection`, `launchAngle`, `carry`, `total`,
   `totalSide`, `curve`, `maxHeight`, `landingAngle`, `hangTime`. Pass every
   shot — the page animates the average and draws the rest faint. Missing
   fields are fine; the page only labels what was measured.
2. **Swing** — `clubPath`, `faceAngle`, `faceToPath` (mean over those shots),
   where the session kind captures them.
3. **Targets** — from the saved plan (`training_plan(action="next")` /
   `training_plan(action="list")`) and/or
   `training_plan(action="verify", plan_id=<id>)`: each as
   `{label, value, target, low, high, met}`.
4. **Blocks** — the prescribed drills, each tagged `where: "range"` or
   `where: "home"`, each with 1–3 **verified** links
   (`links: [{label, url}]`) from the `drill-library` prompt or live search.
5. **Handedness** — from `trackman(action="profile")` (`profile.dexterity`).

## Build it

Assemble the data dict and call `build_visualization(data)` → returns `{html}`,
one standalone document (inline canvas/JS, no network).

```
{
  "title": "...", "subtitle": "...", "diagnosis": "<one line>",
  "handedness": "RH" | "LH",
  "shots": [{"launchDirection": deg, "launchAngle": deg, "carry": m,
             "total": m, "totalSide": m, "curve": m, "maxHeight": m,
             "landingAngle": deg, "hangTime": s}],
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label","value","target","low","high","met"}],
  "blocks": [{"name","detail","goal","where":"range"|"home",
              "links":[{"label","url"}]}]
}
```

## Present it

Emit the returned `html` as a **`text/html` artifact** — it renders directly in
the artifact panel. Narrate in one or two lines what the visual shows (e.g.
"side view: you launch at 9° and peak at 18 m — low for driver; top-down: every
shot bends right"), then point at the Fix it section: range drills for the next
session, home drills for today.

## What it renders

- **Flight — side view** (hero): every measured arc faint, the average animated,
  apex label only when `maxHeight` was measured, dotted roll after carry, and a
  launch/peak/landing/hang caption.
- **Ball flight — top-down**: per-shot curved tracers + landing spots, the
  average animated, target line, caption.
- **Swing path**: animated clubhead on the actual path (red) vs ideal (green),
  face at impact (yellow), caption tying path + face-to-path to the curve.
- **Targets**: bars with the good zone shaded, met/not-yet pills, replay.
- **Fix it — drills**: "At the range" and "At home — no ball" groups, each
  drill with its links.

Only plot metrics that exist in the data — if a field is missing, the viz
adapts (panel hides, label drops) rather than faking it.
