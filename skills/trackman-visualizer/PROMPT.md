# Trackman Visualizer

Turn a coaching diagnosis into a **self-contained animated HTML artifact**: the
ball-flight curve, an animated swing path showing *why* the ball curves, and
progress bars vs the plan's targets. Use real shot data — never invent shapes.
This is a presentation layer; it adds no new diagnosis.

**Lead with it — don't wait to be asked.** Any time you diagnose a fault, show a
shot pattern, or prescribe drills, produce a visual. Many golfers (especially
self-described visual learners, or anyone who says "I don't get it") only grasp
the fault when they *see it move*. Two modes:

- **Shot pattern + swing path + targets** — the standard `build_visualization`
  artifact below. Great for "here's your slice and why."
- **One drill at a time** — if a drill isn't clicking, animate that single
  drill's intended motion: the red current move (e.g. out-to-in, face open) vs
  the green target move. Show them **one per exercise**, not all at once — that's
  what makes mechanics land. Use `build_visualization` with the drill's target
  `swing` + a one-line `diagnosis`, or the client's own HTML/SVG artifact
  capability for a richer per-drill animation. Offer to slow it down or change
  the camera (top-down vs face-on vs side) if it still isn't clear.

## Gather the inputs (reuse what the coach already pulled, or fetch via the MCP)

1. **Shot shape** — driver (or target club) measurements from the relevant
   session: `launchDirection`, `carry` (or `total`), `totalSide`, `curve`. Get
   them from `get_session`, filtered to the club. Several shots → a dispersion
   cloud; one → a single tracer.
2. **Swing** — `clubPath`, `faceAngle`, `faceToPath` (mean over those shots).
3. **Targets** — from the saved plan
   (`training_plan(action="next")` / `training_plan(action="list")`) and/or
   `training_plan(action="verify", plan_id=<id>)`: each as
   `{label, value, target, low, high, met}`.
4. **Handedness** — from `get_profile` (`profile.dexterity`); it sets which way
   "right" is.

## Build it

Assemble the data dict (shape below) and call `build_visualization(data)` → it
returns `{html}`, one standalone document (inline canvas/JS, no network).

```
{
  "title": "...", "subtitle": "...", "diagnosis": "<one line>",
  "handedness": "RH" | "LH",
  "shots": [{"launchDirection": deg, "carry": m, "totalSide": m, "curve": m}],
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label","value","target","low","high","met"}],
  "blocks": [{"name","detail","goal","link"}]
}
```

## Present it

Emit the returned `html` as a **`text/html` artifact** — it's fully
self-contained, so it renders directly in the artifact panel. Then narrate in one
or two lines what the visual shows (e.g. "red line = your out-to-in path; green =
ideal — the ball starts left and curves right").

## What it renders

- **Ball flight** (top-down): animated tracer of the average shot, all landing
  spots as a dispersion cloud, target line, and a plain-language caption.
- **Swing path**: animated clubhead along your actual path (red) vs ideal
  (green), the face at impact (yellow), and a caption tying path + face-to-path
  to the curve.
- **Targets**: bars with the good zone shaded and your value marked, met/not-yet
  pills, plus the plan's drills with links, and a replay button.

Only plot metrics that exist in the data — if a field is missing, the viz adapts
(single straight shot, no swing panel, etc.) rather than faking it.
