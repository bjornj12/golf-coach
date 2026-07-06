---
name: trackman-visualizer
description: Use when the user wants to SEE a golf diagnosis — animate their real measured ball flight (side view + top-down), show why it curves, and link the drills that fix it. Turns golf-coaching output + real shot metrics into a self-contained animated HTML artifact. Triggers on "visualize", "show me the curve", "show my ball flight", "draw my slice", or after a coaching diagnosis.
---

# Trackman Visualizer

Turn a coaching diagnosis into a **self-contained animated HTML artifact** that
animates the golfer's **real measured flight**: a side-view height profile
(launch → apex → landing → roll), a top-down shape view with every shot's
tracer, the swing path that explains *why* it curves, progress vs targets, and
a **Fix it** section linking drills for both the range and home. Uses real shot
data — no invented shapes, no freehand diagrams.

## When to use

After `golf-coaching` produces a diagnosis (or when the user asks to "see" /
"draw" / "animate" their slice, flight, dispersion, or progress). It's a
presentation layer on top of the coach — it adds no new diagnosis.

**Be proactive.** Don't wait to be asked — build this page whenever you
diagnose a fault, show a shot pattern, or hand over drills. One page carries
the whole story: what the ball is doing, why, and the exercises that fix it.

## Inputs to gather

Reuse what the coach already pulled, or fetch via the MCP:

1. **Shots** — per-shot measurements for the club under discussion, from
   `get_session`: `launchDirection`, `launchAngle`, `carry`, `total`,
   `totalSide`, `curve`, `maxHeight`, `landingAngle`, `hangTime`. Pass every
   shot (that's what makes the dispersion visible); the page animates the
   average and draws the rest faint. Missing fields are fine — the page only
   labels what was measured.
2. **Swing** — `clubPath`, `faceAngle`, `faceToPath` (mean over those shots),
   where the session kind captures them.
3. **Targets** — from the saved plan (`training_plan(action="next")` /
   `training_plan(action="list")`) and/or `training_plan(action="verify")`:
   each as `{label, value, target, low, high, met}`.
4. **Blocks** — the prescribed drills, each tagged `where: "range"` or
   `where: "home"`, each with 1–3 **verified** links
   (`links: [{label, url}]`) from `drill-library` or live search. Never
   invent URLs.

Also note **handedness** (`profile.dexterity`) — it sets which way "right" is.

## Build the artifact

Assemble the data dict (schema below) and render it. Two ways:

- **MCP tool (preferred):** call `build_visualization(data)` → returns `{html}`.
- **Direct:** `uv run python scripts/visualize.py <data.json> <out.html>` or
  `from golf_coach.visualize import build_html`.

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

### Present per environment

- **Claude Desktop / claude.ai (artifacts):** emit the returned `html` as a
  **`text/html` artifact** — fully self-contained, renders in the sandbox.
- **Claude Code (terminal):** write the html OUTSIDE the repo (it contains the
  user's data), e.g. `~/.golf-coach/viz/<name>.html`, and offer to `open` it.
  Optionally `scripts/check-visualization.py <file>` headless-renders it for a
  sanity check.

## Present it

- Briefly narrate what the visual shows (e.g. "side view: you launch at 9° and
  peak at 18 m — low for driver; top-down: every shot bends right").
- Point at the Fix it section: range drills for the next session, home drills
  for today.

## What it renders

- **Flight — side view** (hero): every shot's measured arc faint, the average
  animated with the ball, apex label (only when `maxHeight` was measured),
  dotted roll after carry, launch/peak/landing/hang caption.
- **Ball flight — top-down**: per-shot curved tracers + landing spots, the
  average animated, target line, plain-language caption.
- **Swing path**: animated clubhead along the actual path (red) vs ideal
  (green), face at impact (yellow), caption tying path + face-to-path to curve.
- **Targets**: bars with the good zone shaded, met/not-yet pills, replay button.
- **Fix it — drills**: "At the range" and "At home — no ball" groups, each
  drill with its links.

Keep it honest: only plot metrics that exist in the data. If a field is
missing, the viz adapts (panel hides, label drops) rather than faking it.
