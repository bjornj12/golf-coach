---
name: trackman-visualizer
description: Use when the user wants to SEE a golf diagnosis — visualize the ball-flight curve (slice/hook), animate the swing path and why it's wrong, or show progress vs targets. Turns the golf-coaching output + real shot metrics into a self-contained animated HTML artifact. Triggers on "visualize", "show me the curve", "animate my swing", "draw my slice", or after a coaching diagnosis.
---

# Trackman Visualizer

Turn a coaching diagnosis into a **self-contained animated HTML artifact**: the
ball-flight curve, an animated swing path that shows *why* the ball curves, and
progress bars vs the plan's targets. Uses real shot data — no invented shapes.

## When to use

After `golf-coaching` produces a diagnosis (or when the user asks to "see"/"draw"/
"animate" their slice, swing, dispersion, or progress). It's a presentation
layer on top of the coach — it adds no new diagnosis.

## Inputs to gather

You need three things; reuse what the coach already gathered, or pull via the MCP:

1. **Shot shape** — driver (or target club) measurements from the relevant
   session(s): `launchDirection`, `carry` (or `total`), `totalSide`, `curve`.
   Several shots → dispersion; one → a single tracer. Get them from
   `get_session` / the `SESSION_MEASUREMENTS` query, filtered to the club.
2. **Swing** — `clubPath`, `faceAngle`, `faceToPath` (mean over those shots).
3. **Targets** — from the saved plan (`get_next_training` /
   `list_training_plans`) and/or `verify_training_progress`: each as
   `{label, value, target, low, high, met}`.

Also note **handedness** (`profile.dexterity`) — it sets which way "right" is.

## Build the artifact

Assemble a data dict (schema in `scripts/visualize.py`) and generate the HTML:

```bash
# write the data dict to a temp json, then:
uv run python scripts/visualize.py <data.json> <out.html>
```

Or import `build_html(data)` directly. The output is **one self-contained HTML
file** (pure canvas/JS, no network) — write it OUTSIDE the repo (it contains the
user's data), e.g. `~/.trackman-mcp/viz/<name>.html`.

Data dict shape:
```
{
  "title": "...", "subtitle": "...", "diagnosis": "<one line>",
  "handedness": "RH" | "LH",
  "shots": [{"launchDirection": deg, "carry": m, "totalSide": m, "curve": m}],
  "swing": {"clubPath": deg, "faceAngle": deg, "faceToPath": deg},
  "targets": [{"label","value","target","low","high","met"}],
  "blocks": [{"name","detail","goal","link"}]   // the plan, optional
}
```

## Present it

- Tell the user the file path and offer to open it (`open <file>` on macOS).
- If running on claude.ai with artifacts, you may instead inline the generated
  HTML as an HTML artifact (same markup `build_html` produces).
- Briefly narrate what the visual shows (e.g. "red line = your out-to-in path;
  green = ideal — the ball starts left and curves right").

## What it renders

- **Ball flight** (top-down): animated tracer of the average shot, all landing
  spots as a dispersion cloud, target line, and a plain-language "starts X,
  finishes Y" caption.
- **Swing path**: animated clubhead along your actual path (red) vs ideal
  (green), the club face at impact (yellow), and a caption tying path + face-to-
  path to the curve ("why it's wrong").
- **Targets**: bars with the good zone shaded and your value marked, met/not-yet
  pills, plus the plan's drills with links. A replay button re-runs the animation.

Keep it honest: only plot metrics that exist in the data. If a field is missing,
the viz adapts (single straight shot, no swing panel, etc.) rather than faking it.
