# Multi-Angle Drill Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the illegible single-line top-down drill diagram with a deterministic, animated down-the-line + face-on stick-figure comparison (current fault vs target move), driven by a small hand-authored fault-archetype library, wired into both Claude Code and Claude Desktop.

**Architecture:** A new `swing_archetypes.py` module holds 5 named fault archetypes (pose keyframes + projection math) as pure, unit-tested Python — no HTML in it. `visualize.py` gains a sibling function, `build_drill_fragment`, that renders those archetypes as an inline SVG+CSS fragment (nested-group CSS `transform` animations, no JS animation loop — only a tiny inline `onclick` for Replay) instead of the existing top-down canvas panel. The MCP tool `build_visualization` (`server.py`) branches on a new optional `drill` key: present → fragment + `render_as: "text/html fragment"`; absent → today's full page, unchanged. Skill prompts (`trackman-visualizer`, `golf-practice-at-home`, `drill-library` — both `SKILL.md` and `PROMPT.md` each) are updated to call this instead of freehand-authoring the diagram.

**Tech Stack:** Python 3.11+, inline SVG + CSS animations, pytest, Playwright (existing `[login]` extra) for the manual visual spot-check.

## Global Constraints

- Zero new runtime dependencies — stdlib only in `swing_archetypes.py` and the new code in `visualize.py` (matches the rest of the file).
- `requires-python = ">=3.11"`; `uv run ruff check` (rules `E,F,I,UP,B`, line length 100, `E501` ignored) and `uv run mypy` (`files = ["src"]`, `check_untyped_defs = true`) must both pass after every task.
- `build_html`'s existing behavior and the existing 5 tests in `tests/test_visualize.py` are untouched — the new rendering is a separate function, never a branch inside `build_html`.
- The string returned by `build_drill_fragment` must never start with `<!doctype html>` (it's embedded into a caller's own card markup, not a standalone document) and must contain no `http://`/`https://` substring (no external resources) — same self-containment guarantee `test_visualize.py` already enforces for the full page.
- `ARCHETYPE_IDS` is exactly `{"over_the_top", "early_transition", "disconnected_sequencing", "open_face", "inside_closing"}` — these 5 ids and no others, per the design doc's drill→archetype mapping table.
- Any skill content change is made in **both** `SKILL.md` and `PROMPT.md` for that skill — Claude Desktop only ever reads `PROMPT.md` (via `src/trackman_mcp/prompts.py`'s `load_skills()`), never `SKILL.md`.
- Unknown `archetype` id is a raised `ValueError` with a message listing valid ids — never a silent/blank render (repo's fail-loud convention, see `CLAUDE.md`).
- Design doc: `docs/superpowers/specs/2026-06-30-multi-angle-drill-visualization-design.md` — read it first if anything below is ambiguous.

---

### Task 1: Fault archetype data + projection geometry (`swing_archetypes.py`)

**Files:**
- Create: `src/trackman_mcp/swing_archetypes.py`
- Test: `tests/test_swing_archetypes.py`

**Interfaces:**
- Consumes: nothing (pure stdlib).
- Produces (used by Task 2):
  - `PHASES: tuple[str, ...]` — `("address", "top", "transition", "impact", "finish")`
  - `ARCHETYPE_IDS: frozenset[str]` — the 5 valid archetype ids
  - `class Keyframe` (frozen dataclass): fields `shoulder_turn, hip_turn, arm_plane, club_plane, wrist_hinge, trail_elbow` (all `float` except `trail_elbow: str`)
  - `keyframes_for(archetype_id: str, track: str) -> list[Keyframe]` — `track` is `"current"` or `"target"`; raises `ValueError` for an unknown archetype or track
  - `apply_club_path_override(keyframes: list[Keyframe], club_path_deg: float) -> list[Keyframe]`
  - `view_params(view: str, kf: Keyframe) -> dict[str, float]` — `view` is `"down_the_line"` or `"face_on"`; returns keys `hip_translate_x, spine_rotate, arm_rotate, club_rotate, elbow_offset_x`; raises `ValueError` for an unknown view

- [ ] **Step 1: Write the failing test file**

Create `tests/test_swing_archetypes.py`:

```python
"""Tests for the fault-archetype pose library and its projection math.

Pure-Python — no HTML/SVG/DOM involved. The actual visual rendering is tested
separately in tests/test_visualize.py via build_drill_fragment.
"""

from __future__ import annotations

import pytest

from trackman_mcp.swing_archetypes import (
    ARCHETYPE_IDS,
    PHASES,
    Keyframe,
    apply_club_path_override,
    keyframes_for,
    view_params,
)


def test_archetype_ids_match_the_drill_library_mapping():
    assert ARCHETYPE_IDS == {
        "over_the_top",
        "early_transition",
        "disconnected_sequencing",
        "open_face",
        "inside_closing",
    }


@pytest.mark.parametrize("archetype_id", sorted(ARCHETYPE_IDS))
@pytest.mark.parametrize("track", ["current", "target"])
def test_every_archetype_track_has_five_keyframes_in_phase_order(archetype_id, track):
    kfs = keyframes_for(archetype_id, track)
    assert len(kfs) == len(PHASES) == 5
    assert all(isinstance(kf, Keyframe) for kf in kfs)


def test_keyframes_for_unknown_archetype_raises():
    with pytest.raises(ValueError, match="unknown archetype"):
        keyframes_for("does_not_exist", "current")


def test_keyframes_for_unknown_track_raises():
    with pytest.raises(ValueError, match="unknown track"):
        keyframes_for("over_the_top", "sideways")


def test_keyframes_for_returns_independent_copies():
    a = keyframes_for("over_the_top", "current")
    b = keyframes_for("over_the_top", "current")
    assert a == b
    assert a is not b


def test_view_params_down_the_line_uses_arm_and_club_plane_directly():
    kf = Keyframe(
        shoulder_turn=0.0, hip_turn=0.0, arm_plane=20.0, club_plane=5.0,
        wrist_hinge=0.5, trail_elbow="connected",
    )
    params = view_params("down_the_line", kf)
    assert params["arm_rotate"] == 20.0
    assert params["club_rotate"] == 5.0


def test_view_params_face_on_damps_arm_and_club_plane():
    kf = Keyframe(
        shoulder_turn=0.0, hip_turn=0.0, arm_plane=20.0, club_plane=5.0,
        wrist_hinge=0.5, trail_elbow="connected",
    )
    params = view_params("face_on", kf)
    assert params["arm_rotate"] == pytest.approx(8.0)   # 20 * 0.4
    assert params["club_rotate"] == pytest.approx(2.0)  # 5 * 0.4


def test_view_params_unknown_view_raises():
    kf = Keyframe(0.0, 0.0, 0.0, 0.0, 0.0, "connected")
    with pytest.raises(ValueError, match="unknown view"):
        view_params("overhead", kf)


def test_view_params_elbow_offset_bigger_when_disconnected():
    connected = Keyframe(0.0, 0.0, 0.0, 0.0, 1.0, "connected")
    disconnected = Keyframe(0.0, 0.0, 0.0, 0.0, 1.0, "disconnected")
    assert (
        view_params("down_the_line", disconnected)["elbow_offset_x"]
        > view_params("down_the_line", connected)["elbow_offset_x"]
    )


def test_apply_club_path_override_replaces_only_impact_club_plane():
    kfs = keyframes_for("over_the_top", "current")
    overridden = apply_club_path_override(kfs, -5.0)
    impact_idx = PHASES.index("impact")
    assert overridden[impact_idx].club_plane == pytest.approx(-30.0)  # -5.0 * 6.0
    for i, (orig, new) in enumerate(zip(kfs, overridden)):
        if i == impact_idx:
            assert orig.club_plane != new.club_plane
        else:
            assert orig == new


def test_apply_club_path_override_clamps_extreme_values():
    kfs = keyframes_for("over_the_top", "current")
    overridden = apply_club_path_override(kfs, 50.0)  # would be 300deg unclamped
    impact_idx = PHASES.index("impact")
    assert overridden[impact_idx].club_plane == 45.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_swing_archetypes.py -v`
Expected: `ModuleNotFoundError: No module named 'trackman_mcp.swing_archetypes'` (or `ImportError`) — the module doesn't exist yet.

- [ ] **Step 3: Write the implementation**

Create `src/trackman_mcp/swing_archetypes.py`:

```python
"""Fault-archetype pose library for the per-drill comparison visualization.

A small, hand-authored set of named swing-fault "shapes" — not per-conversation
improvised body kinematics. Each archetype is a pair of 5-keyframe pose tracks
(`current`, the fault; `target`, the fix) covering the swing's five phases.
`visualize.py` renders these as an animated stick-figure SVG; this module only
holds the pose data and the projection math from pose parameters to per-view
animated CSS transform values — no HTML/SVG/CSS here.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

PHASES: tuple[str, ...] = ("address", "top", "transition", "impact", "finish")

CLUB_PLANE_VISUAL_SCALE = 6.0
CLUB_PLANE_VISUAL_CLAMP = 45.0


@dataclass(frozen=True)
class Keyframe:
    shoulder_turn: float       # 0..1, rotation progress through the swing
    hip_turn: float            # 0..1
    arm_plane: float           # degrees, arm angle off the spine (down-the-line view)
    club_plane: float          # degrees, club angle relative to the arm (the hinge)
    wrist_hinge: float         # 0..1, scales the visible elbow-connection gap
    trail_elbow: str           # "connected" | "disconnected"


_K = Keyframe

# Archetypes share the same address/top/finish shape (the backswing top
# position doesn't depend on the downswing fault) and diverge specifically at
# transition/impact — where each named fault actually lives.
ARCHETYPES: dict[str, dict[str, tuple[Keyframe, ...]]] = {
    "over_the_top": {
        "current": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.7, 0.5, -60.0, -70.0, 0.9, "disconnected"),
            _K(0.2, 0.8, 20.0, 35.0, 0.5, "disconnected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
        "target": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.6, 0.5, -75.0, -35.0, 0.7, "connected"),
            _K(0.2, 0.8, 15.0, 5.0, 0.5, "connected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
    },
    "early_transition": {
        "current": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.5, 0.2, -50.0, -65.0, 0.9, "disconnected"),
            _K(0.2, 0.7, 18.0, 10.0, 0.5, "disconnected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
        "target": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.7, 0.6, -80.0, -40.0, 0.7, "connected"),
            _K(0.2, 0.85, 15.0, 5.0, 0.5, "connected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
    },
    "disconnected_sequencing": {
        "current": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.85, 0.25, -90.0, -45.0, 0.75, "connected"),
            _K(0.55, 0.15, -55.0, -60.0, 0.85, "disconnected"),
            _K(0.2, 0.6, 20.0, 15.0, 0.5, "disconnected"),
            _K(0.0, 0.9, 105.0, 55.0, 0.3, "connected"),
        ),
        "target": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.85, 0.25, -90.0, -45.0, 0.75, "connected"),
            _K(0.65, 0.55, -78.0, -38.0, 0.7, "connected"),
            _K(0.2, 0.85, 15.0, 5.0, 0.5, "connected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
    },
    "open_face": {
        "current": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.65, 0.55, -78.0, -38.0, 0.7, "connected"),
            _K(0.2, 0.8, 15.0, 40.0, 0.5, "connected"),
            _K(0.0, 1.0, 108.0, 70.0, 0.3, "connected"),
        ),
        "target": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.65, 0.55, -78.0, -38.0, 0.7, "connected"),
            _K(0.2, 0.8, 15.0, 5.0, 0.5, "connected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
    },
    "inside_closing": {
        "current": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.6, 0.6, -85.0, -30.0, 0.6, "connected"),
            _K(0.2, 0.85, 10.0, -30.0, 0.5, "connected"),
            _K(0.0, 1.0, 112.0, 50.0, 0.3, "connected"),
        ),
        "target": (
            _K(0.0, 0.0, 0.0, 0.0, 0.1, "connected"),
            _K(0.9, 0.3, -95.0, -50.0, 0.8, "connected"),
            _K(0.65, 0.55, -78.0, -38.0, 0.7, "connected"),
            _K(0.2, 0.8, 15.0, 5.0, 0.5, "connected"),
            _K(0.0, 1.0, 110.0, 60.0, 0.3, "connected"),
        ),
    },
}

ARCHETYPE_IDS: frozenset[str] = frozenset(ARCHETYPES)


def keyframes_for(archetype_id: str, track: str) -> list[Keyframe]:
    """Return a fresh copy of the 5 keyframes for one archetype's current/target track."""
    if archetype_id not in ARCHETYPES:
        valid = ", ".join(sorted(ARCHETYPE_IDS))
        raise ValueError(f"unknown archetype {archetype_id!r}, expected one of: {valid}")
    if track not in ("current", "target"):
        raise ValueError(f"unknown track {track!r}, expected 'current' or 'target'")
    return list(ARCHETYPES[archetype_id][track])


def apply_club_path_override(keyframes: list[Keyframe], club_path_deg: float) -> list[Keyframe]:
    """Return a copy of `keyframes` with the impact club_plane replaced by a
    visually-scaled, clamped version of a real measured clubPath value.

    The archetype's own impact angle is illustrative; a real clubPath (typically
    a few degrees) is too small to read on a simplified stick figure, so it's
    scaled up for legibility and clamped to a sane visual range.
    """
    scaled = club_path_deg * CLUB_PLANE_VISUAL_SCALE
    scaled = max(-CLUB_PLANE_VISUAL_CLAMP, min(CLUB_PLANE_VISUAL_CLAMP, scaled))
    out = list(keyframes)
    impact_idx = PHASES.index("impact")
    out[impact_idx] = dataclasses.replace(out[impact_idx], club_plane=scaled)
    return out


def view_params(view: str, kf: Keyframe) -> dict[str, float]:
    """Project one keyframe's pose parameters into animated CSS transform values
    for one camera angle.

    Both views read the same keyframe parameters — only the projection differs:
    down-the-line uses the angles directly (this view is the swing plane seen
    edge-on); face-on damps them (rotation toward/away from the camera
    foreshortens into lateral motion).
    """
    spine_lean = 35.0 - 8.0 * kf.shoulder_turn
    elbow_offset = (8.0 if kf.trail_elbow == "disconnected" else 2.0) * (0.4 + 0.6 * kf.wrist_hinge)
    if view == "down_the_line":
        return {
            "hip_translate_x": 2.0 * kf.hip_turn,
            "spine_rotate": -spine_lean,
            "arm_rotate": kf.arm_plane,
            "club_rotate": kf.club_plane,
            "elbow_offset_x": elbow_offset,
        }
    if view == "face_on":
        return {
            "hip_translate_x": 6.0 * kf.hip_turn,
            "spine_rotate": -spine_lean * 0.25,
            "arm_rotate": kf.arm_plane * 0.4,
            "club_rotate": kf.club_plane * 0.4,
            "elbow_offset_x": elbow_offset,
        }
    raise ValueError(f"unknown view {view!r}, expected 'down_the_line' or 'face_on'")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_swing_archetypes.py -v`
Expected: all tests `PASS`.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check src/trackman_mcp/swing_archetypes.py tests/test_swing_archetypes.py && uv run mypy src/trackman_mcp/swing_archetypes.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/trackman_mcp/swing_archetypes.py tests/test_swing_archetypes.py
git commit -m "$(cat <<'EOF'
Add fault-archetype pose library for drill visualizations

Pure data + projection geometry for 5 hand-authored swing-fault
archetypes, covering the at-home-no-ball drill set. No HTML yet —
visualize.py consumes this in the next task.
EOF
)"
```

---

### Task 2: Drill comparison fragment renderer (`visualize.py`)

**Files:**
- Modify: `src/trackman_mcp/visualize.py`
- Test: `tests/test_visualize.py`

**Interfaces:**
- Consumes: `trackman_mcp.swing_archetypes` (`ARCHETYPE_IDS`, `PHASES`, `keyframes_for`, `apply_club_path_override`, `view_params`) from Task 1.
- Produces (used by Task 3): `build_drill_fragment(data: dict) -> str` in `trackman_mcp.visualize` — raises `ValueError` for an unknown/missing `data["drill"]["archetype"]`; returns a self-contained HTML fragment (not a full document).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_visualize.py` (after the existing 5 tests, same file):

```python
from trackman_mcp.swing_archetypes import ARCHETYPE_IDS
from trackman_mcp.visualize import build_drill_fragment


def test_build_drill_fragment_unknown_archetype_raises():
    with pytest.raises(ValueError, match="unknown archetype"):
        build_drill_fragment({"drill": {"archetype": "nonsense"}})


def test_build_drill_fragment_missing_archetype_raises():
    with pytest.raises(ValueError, match="unknown archetype"):
        build_drill_fragment({"drill": {}})


@pytest.mark.parametrize("archetype_id", sorted(ARCHETYPE_IDS))
def test_build_drill_fragment_renders_all_four_stick_figures(archetype_id):
    html = build_drill_fragment({"drill": {"archetype": archetype_id, "name": "Test drill"}})
    assert html.count("<svg") == 4
    assert "dtl-current" in html and "dtl-target" in html
    assert "fo-current" in html and "fo-target" in html
    assert "Test drill" in html


def test_build_drill_fragment_is_a_fragment_not_a_full_document():
    html = build_drill_fragment({"drill": {"archetype": "over_the_top"}})
    assert not html.lstrip().lower().startswith("<!doctype html>")
    assert html.lstrip().startswith('<div class="drill-compare')


def test_build_drill_fragment_is_self_contained():
    html = build_drill_fragment({"drill": {"archetype": "over_the_top"}})
    assert re.search(r'<script[^>]+src=', html) is None
    assert "http://" not in html and "https://" not in html


def test_build_drill_fragment_name_is_html_escaped():
    html = build_drill_fragment({"drill": {
        "archetype": "over_the_top",
        "name": "<img src=x onerror=alert(1)>",
    }})
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_build_drill_fragment_no_name_omits_title():
    html = build_drill_fragment({"drill": {"archetype": "over_the_top"}})
    assert "drill-title" not in html


def test_build_drill_fragment_handedness_mirrors_via_css_class():
    rh = build_drill_fragment({"drill": {"archetype": "over_the_top"}, "handedness": "RH"})
    lh = build_drill_fragment({"drill": {"archetype": "over_the_top"}, "handedness": "LH"})
    assert "drill-compare lh" not in rh
    assert "drill-compare lh" in lh


def test_build_drill_fragment_applies_real_club_path_override():
    with_real = build_drill_fragment({
        "drill": {"archetype": "over_the_top"},
        "swing": {"clubPath": -5.0},
    })
    without = build_drill_fragment({"drill": {"archetype": "over_the_top"}})
    assert with_real != without


def test_build_html_unaffected_by_drill_feature():
    # Regression guard: build_html's own code path is untouched by this feature.
    html = build_html({"title": "Coach", "shots": [{"carry": 200}]})
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert "drill-compare" not in html
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: the new tests `FAIL` with `ImportError: cannot import name 'build_drill_fragment'`; the 5 pre-existing tests still `PASS`.

- [ ] **Step 3: Write the implementation**

In `src/trackman_mcp/visualize.py`, add this import near the top (after the existing `import sys`):

```python
from .swing_archetypes import (
    ARCHETYPE_IDS,
    apply_club_path_override,
    keyframes_for,
    view_params,
)
```

Then append the following to the end of the file (after `_DEMO`, before `def main`) — this does not modify `build_html`, `_json_for_script`, `_TEMPLATE`, or `_DEMO` in any way:

```python
# --------------------------------------------------------------------------- #
# Single-drill comparison fragment (current fault vs target move, two angles)
# --------------------------------------------------------------------------- #

_PHASE_PERCENTS: tuple[int, ...] = (0, 25, 45, 70, 100)
_ROTATE_PROPS = ("spine_rotate", "arm_rotate", "club_rotate")
_TRANSLATE_PROPS = ("hip_translate_x", "elbow_offset_x")
_PROP_CLASS = {
    "spine_rotate": "spine-anim",
    "arm_rotate": "arm-anim",
    "club_rotate": "club-anim",
    "hip_translate_x": "hip-anim",
    "elbow_offset_x": "elbow-anim",
}

_DRILL_CSS_BASE = """
.drill-compare{font:13px/1.4 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#e7eef7}
.drill-compare .drill-title{font-size:15px;margin:0 0 10px;color:#bcd2f0}
.drill-compare .row{margin-bottom:14px}
.drill-compare .row-label{font-size:11px;letter-spacing:.3px;text-transform:uppercase;color:#8aa0bd;margin-bottom:4px}
.drill-compare .pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.drill-compare .cell{background:#0e1626;border-radius:8px;padding:8px}
.drill-compare .cell-label{font-size:11px;margin-bottom:4px}
.drill-compare .cell-label.red{color:#ff6b6b}
.drill-compare .cell-label.green{color:#27c08a}
.drill-compare svg.stick{width:100%;height:auto;display:block}
.drill-compare .stick .ground{stroke:#1b2740;stroke-width:1}
.drill-compare .stick .target-tick{stroke:#3a4a66;stroke-width:1;stroke-dasharray:3,3}
.drill-compare .stick .head{fill:#9fb4d4}
.drill-compare .stick .elbow-flag{fill:#ffd166}
.drill-compare .stick.red line,.drill-compare .stick.red circle.joint{stroke:#ff6b6b;fill:#ff6b6b}
.drill-compare .stick.green line,.drill-compare .stick.green circle.joint{stroke:#27c08a;fill:#27c08a}
.drill-compare .stick line{stroke-width:2.4;fill:none}
.drill-compare.lh svg.stick{transform:scaleX(-1)}
.drill-compare .legend{display:flex;gap:14px;color:#8aa0bd;font-size:12px;margin:8px 0}
.drill-compare .legend .dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:middle}
.drill-compare .legend .dot.red{background:#ff6b6b}
.drill-compare .legend .dot.green{background:#27c08a}
.drill-compare .replay-btn{background:#1c2c47;color:#e7eef7;border:1px solid #2b4068;border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px}
.drill-compare .replay-btn:hover{background:#22365a}
.drill-compare .anim{animation-duration:4.5s;animation-timing-function:ease-in-out;animation-fill-mode:forwards}
""".strip()

_REPLAY_JS = (
    "this.closest('.drill-compare').querySelectorAll('.anim').forEach("
    "function(el){el.style.animation='none';void el.offsetWidth;el.style.animation='';})"
)


def _keyframes_css(name: str, prop: str, values: list[float]) -> str:
    """One @keyframes rule plus the matching {.name{animation-name:name}} binding."""
    is_rotate = prop in _ROTATE_PROPS
    stops = []
    for pct, v in zip(_PHASE_PERCENTS, values):
        t = f"rotate({v:.1f}deg)" if is_rotate else f"translate({v:.1f}px,0)"
        stops.append(f"{pct}%{{transform:{t}}}")
    keyframes_rule = f"@keyframes {name}{{{''.join(stops)}}}"
    binding_rule = f".{name}{{animation-name:{name}}}"
    return keyframes_rule + binding_rule


def _stick_svg(names: dict[str, str], color: str) -> str:
    """A single stick-figure SVG. `names` maps each animated prop to its unique
    CSS class/animation name (see _keyframes_css) for this (view, track) pair.

    Joint chain: hip -> spine -> shoulder/head -> arm -> elbow flag -> club.
    Each "-anim" group carries ONLY a CSS-animated transform (rotate or
    translate); static positioning uses separate nested groups with a plain
    SVG `transform` attribute, so the two never collide on the same element.
    """
    return (
        f'<svg viewBox="0 0 100 110" class="stick {color}">'
        '<line class="ground" x1="5" y1="100" x2="95" y2="100"/>'
        '<line class="target-tick" x1="50" y1="100" x2="50" y2="92"/>'
        '<g transform="translate(50,90)">'
        f'<g class="anim {names["hip_translate_x"]}">'
        '<circle class="joint" r="2"/>'
        f'<g class="anim {names["spine_rotate"]}">'
        '<line x1="0" y1="0" x2="0" y2="-24"/>'
        '<circle class="head" cx="0" cy="-28" r="4"/>'
        '<g transform="translate(0,-24)">'
        f'<g class="anim {names["arm_rotate"]}">'
        '<line x1="0" y1="0" x2="0" y2="22"/>'
        f'<g class="anim {names["elbow_offset_x"]}">'
        '<circle class="elbow-flag" cx="0" cy="12" r="1.6"/>'
        '</g>'
        '<g transform="translate(0,22)">'
        f'<g class="anim {names["club_rotate"]}">'
        '<line x1="0" y1="0" x2="0" y2="30"/>'
        '</g></g></g></g></g></g></g></svg>'
    )


def build_drill_fragment(data: dict) -> str:
    """Render a single-drill current-vs-target comparison as an embeddable
    HTML fragment (not a full document): an animated down-the-line + face-on
    stick-figure pair, current move (red) vs target move (green).

    `data["drill"]["archetype"]` selects the fault-pose library entry (see
    `trackman_mcp.swing_archetypes.ARCHETYPE_IDS`); `data["drill"]["name"]` is
    an optional label. `data["swing"]["clubPath"]`, if present, overrides the
    archetype's illustrative impact angle with the real measured value.
    `data["handedness"]` ("RH"|"LH", default "RH") mirrors the figures.
    """
    drill = data.get("drill") or {}
    archetype = drill.get("archetype")
    if archetype not in ARCHETYPE_IDS:
        valid = ", ".join(sorted(ARCHETYPE_IDS))
        raise ValueError(f"unknown archetype {archetype!r}, expected one of: {valid}")
    name = _html.escape(str(drill.get("name", "")))
    lh_class = " lh" if data.get("handedness", "RH") == "LH" else ""
    swing = data.get("swing") or {}
    club_path = swing.get("clubPath")

    css_parts: list[str] = []
    rows: list[str] = []
    for view_id, view_param_key, view_label in (
        ("dtl", "down_the_line", "Down-the-line"),
        ("fo", "face_on", "Face-on"),
    ):
        cells: list[str] = []
        for track, color, label in (
            ("current", "red", "your current move"),
            ("target", "green", "target move"),
        ):
            kfs = keyframes_for(archetype, track)
            if track == "current" and club_path is not None:
                kfs = apply_club_path_override(kfs, float(club_path))
            prefix = f"{view_id}-{track}"
            params = [view_params(view_param_key, kf) for kf in kfs]
            names: dict[str, str] = {}
            for prop in (*_ROTATE_PROPS, *_TRANSLATE_PROPS):
                anim_name = f"{prefix}-{_PROP_CLASS[prop]}"
                names[prop] = anim_name
                css_parts.append(_keyframes_css(anim_name, prop, [p[prop] for p in params]))
            cells.append(
                f'<div class="cell"><div class="cell-label {color}">{label}</div>'
                f'{_stick_svg(names, color)}</div>'
            )
        rows.append(
            f'<div class="row"><div class="row-label">{view_label}</div>'
            f'<div class="pair">{"".join(cells)}</div></div>'
        )

    style = _DRILL_CSS_BASE + "\n" + "\n".join(css_parts)
    title_html = f'<h3 class="drill-title">{name}</h3>' if name else ""
    return (
        f'<div class="drill-compare{lh_class}"><style>{style}</style>'
        f'{title_html}{"".join(rows)}'
        '<div class="legend"><span class="dot red"></span>your current move '
        '<span class="dot green"></span>target move</div>'
        f'<button class="replay-btn" onclick="{_REPLAY_JS}">↻ Replay</button>'
        '</div>'
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_visualize.py -v`
Expected: all tests (the original 5 plus the new ones) `PASS`.

- [ ] **Step 5: Lint and type-check**

Run: `uv run ruff check src/trackman_mcp/visualize.py tests/test_visualize.py && uv run mypy src/trackman_mcp/visualize.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/trackman_mcp/visualize.py tests/test_visualize.py
git commit -m "$(cat <<'EOF'
Add build_drill_fragment: animated multi-angle drill comparison

Renders the swing_archetypes pose library as an inline SVG + CSS
fragment (down-the-line + face-on, current vs target, nested-group
transform animations). build_html and its existing behavior are
untouched.
EOF
)"
```

---

### Task 3: Wire `build_visualization` to the new `drill` mode

**Files:**
- Modify: `src/trackman_mcp/server.py:513-529`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `build_drill_fragment`, `build_html` from `trackman_mcp.visualize` (Task 2).
- Produces: no new public interface — this is the tool's external contract (`build_visualization(data) -> {html, bytes, render_as}`), consumed by skills (Task 4) and by Claude Desktop/Code directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server.py` (it already has `import pytest` and `from trackman_mcp import server` at the top):

```python
async def test_build_visualization_without_drill_returns_full_artifact():
    result = await server.build_visualization({"title": "Coach"})
    assert result["render_as"] == "text/html artifact"
    assert result["html"].lstrip().lower().startswith("<!doctype html>")


async def test_build_visualization_with_drill_returns_fragment():
    result = await server.build_visualization({"drill": {"archetype": "over_the_top"}})
    assert result["render_as"] == "text/html fragment"
    assert result["html"].lstrip().startswith('<div class="drill-compare')


async def test_build_visualization_with_unknown_archetype_raises():
    with pytest.raises(ValueError, match="unknown archetype"):
        await server.build_visualization({"drill": {"archetype": "nonsense"}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_server.py -v -k build_visualization`
Expected: `test_build_visualization_with_drill_returns_fragment` and `test_build_visualization_with_unknown_archetype_raises` `FAIL` (today's tool always returns `render_as: "text/html artifact"` and never raises on a `drill` key, since it's ignored); `test_build_visualization_without_drill_returns_full_artifact` already `PASS`es (today's only path).

- [ ] **Step 3: Write the implementation**

In `src/trackman_mcp/server.py`, replace the `build_visualization` function (lines 513-529):

```python
@mcp.tool(annotations=_RO_LOCAL)
async def build_visualization(data: dict[str, Any]) -> dict[str, Any]:
    """Render a coaching diagnosis into a self-contained animated HTML page.

    Returns `{html}` — one standalone document (inline canvas/JS, no network, no
    external resources) ready to drop straight into a Claude **HTML artifact**.

    `data` shape (all optional; the viz adapts): {title, subtitle, diagnosis,
    handedness "RH"|"LH", shots:[{launchDirection,carry,totalSide,curve}],
    swing:{clubPath,faceAngle,faceToPath}, targets:[{label,value,target,low,high,
    met}], blocks:[{name,detail,goal,link}]}. See the trackman-visualizer prompt.
    """
    from .visualize import build_html

    html = build_html(data)
    return {"html": html, "bytes": len(html.encode()),
            "render_as": "text/html artifact"}
```

with:

```python
@mcp.tool(annotations=_RO_LOCAL)
async def build_visualization(data: dict[str, Any]) -> dict[str, Any]:
    """Render a coaching diagnosis into a self-contained animated HTML page, or
    (when `data.drill` is present) a single-drill comparison fragment.

    Without `drill`: returns `{html}` — one standalone document (inline canvas/
    JS, no network, no external resources) ready to drop straight into a Claude
    **HTML artifact**. `data` shape (all optional; the viz adapts): {title,
    subtitle, diagnosis, handedness "RH"|"LH",
    shots:[{launchDirection,carry,totalSide,curve}],
    swing:{clubPath,faceAngle,faceToPath}, targets:[{label,value,target,low,high,
    met}], blocks:[{name,detail,goal,link}]}.

    With `drill: {archetype, name}`: returns `{html}` as an **embeddable
    fragment** (not a full document — embed it inside your own per-drill card,
    don't wrap it in another `<html>`) showing an animated down-the-line +
    face-on stick-figure comparison of the current fault (red) vs the target
    move (green), for one of the known archetypes — see
    `trackman_mcp.swing_archetypes.ARCHETYPE_IDS` and the `drill-library`
    prompt's at-home-no-ball table for the archetype each drill maps to.
    `swing.clubPath`, if present, overrides the archetype's illustrative
    impact angle with the real measured value. `handedness` mirrors the
    figures. See the trackman-visualizer prompt.
    """
    from .visualize import build_drill_fragment, build_html

    if "drill" in data:
        html = build_drill_fragment(data)
        return {"html": html, "bytes": len(html.encode()),
                "render_as": "text/html fragment"}
    html = build_html(data)
    return {"html": html, "bytes": len(html.encode()),
            "render_as": "text/html artifact"}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_server.py -v -k build_visualization`
Expected: all three tests `PASS`.

- [ ] **Step 5: Run the full test suite, lint, and type-check**

Run: `uv run pytest && uv run ruff check && uv run mypy`
Expected: all tests pass (including `tests/test_setup.py`, which already asserts `build_visualization` is among the tool list — unaffected by this change), no lint/type errors.

- [ ] **Step 6: Commit**

```bash
git add src/trackman_mcp/server.py tests/test_server.py
git commit -m "$(cat <<'EOF'
Wire build_visualization to the new drill comparison fragment mode

data.drill present -> build_drill_fragment + render_as "text/html
fragment"; absent -> today's full-page behavior, unchanged.
EOF
)"
```

---

### Task 4: Update skill content (Claude Code + Claude Desktop)

**Files:**
- Modify: `skills/trackman-visualizer/SKILL.md`
- Modify: `skills/trackman-visualizer/PROMPT.md`
- Modify: `skills/golf-practice-at-home/SKILL.md`
- Modify: `skills/golf-practice-at-home/PROMPT.md`
- Modify: `skills/drill-library/SKILL.md`
- Modify: `skills/drill-library/PROMPT.md`
- Test: `tests/test_skill_content.py`

**Interfaces:**
- Consumes: the `drill: {archetype, name}` contract from Task 3 (no code interface — this task is markdown only).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_skill_content.py`:

```python
def test_trackman_visualizer_uses_drill_archetype_fragment():
    b = _body("trackman-visualizer")
    assert "archetype" in b
    assert "drill-library" in b
    assert "render_as" in b or "fragment" in b


def test_golf_practice_at_home_uses_drill_archetype():
    b = _body("golf-practice-at-home")
    assert "archetype" in b


def test_drill_library_at_home_drills_carry_an_archetype_id():
    b = _body("drill-library")
    for archetype in (
        "over_the_top", "early_transition", "disconnected_sequencing",
        "open_face", "inside_closing",
    ):
        assert archetype in b, f"drill-library missing the {archetype!r} archetype mapping"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_skill_content.py -v`
Expected: the 3 new tests `FAIL` (none of the words appear yet); the existing tests in this file still `PASS`.

- [ ] **Step 3: Edit `skills/drill-library/SKILL.md`**

Replace the at-home-no-ball table (and its lead-in sentence):

```markdown
| Drill | Fixes | What to do |
|-------|-------|-----------|
| Wall / fence | over-the-top, out-to-in path | Wall a clubhead's length off the trail shoulder along the target line; slow swings that miss it force the club inside. |
| Pump-and-drop | the over-the-top transition | At the top, pump hands down twice (trail elbow tucks, club shallows behind), then finish. |
| Trail-arm-only throws | inside path + face closing | Trail hand only; slow "skip a stone to right field" swings. |
| Split-hands release | open face at impact | Hands a few inches apart; slow half-swings, feel the trail forearm cross over. |
| Step-through | sequencing | Feet together; step toward target with the lead foot as you start down, then swing. |
| Mirror face check | open-face awareness | Rehearse impact in a mirror; learn what square looks like vs your open habit. |
| Towel under trail arm | connection / over-the-top | Trap a towel under the trail armpit through transition to keep the arm connected. |
```

with:

```markdown
`Archetype` is the id to pass as `build_visualization`'s `drill.archetype` (see
the `trackman-visualizer` prompt) — it selects the matching animated
current-vs-target comparison.

| Drill | Fixes | What to do | Archetype |
|-------|-------|-----------|-----------|
| Wall / fence | over-the-top, out-to-in path | Wall a clubhead's length off the trail shoulder along the target line; slow swings that miss it force the club inside. | `over_the_top` |
| Pump-and-drop | the over-the-top transition | At the top, pump hands down twice (trail elbow tucks, club shallows behind), then finish. | `early_transition` |
| Trail-arm-only throws | inside path + face closing | Trail hand only; slow "skip a stone to right field" swings. | `inside_closing` |
| Split-hands release | open face at impact | Hands a few inches apart; slow half-swings, feel the trail forearm cross over. | `open_face` |
| Step-through | sequencing | Feet together; step toward target with the lead foot as you start down, then swing. | `disconnected_sequencing` |
| Mirror face check | open-face awareness | Rehearse impact in a mirror; learn what square looks like vs your open habit. | `open_face` |
| Towel under trail arm | connection / over-the-top | Trap a towel under the trail armpit through transition to keep the arm connected. | `early_transition` |
```

- [ ] **Step 4: Edit `skills/drill-library/PROMPT.md`**

Replace the matching at-home-no-ball table with the same content + lead-in sentence as Step 3 (the table rows are identical between `SKILL.md` and `PROMPT.md` in this file today).

- [ ] **Step 5: Edit `skills/trackman-visualizer/SKILL.md`**

Replace:

```markdown
**Be proactive and per-exercise.** Don't wait to be asked — visualize whenever
you diagnose a fault, show a shot pattern, or hand over drills. For a visual
learner or a "I still don't get it," animate **one drill at a time** (red current
move → green target move), not all at once, and offer to slow it down or switch
camera (top-down / face-on / side). Use `build_visualization` for the shot
pattern + swing path + targets, and per-drill animations for the mechanics.
```

with:

```markdown
**Be proactive and per-exercise.** Don't wait to be asked — visualize whenever
you diagnose a fault, show a shot pattern, or hand over drills. For a visual
learner or a "I still don't get it," animate **one drill at a time**: call
`build_visualization` with `{drill: {archetype, name}, swing?, handedness?}` —
`archetype` comes from the drill's row in `drill-library`'s at-home-no-ball
table. This returns an embeddable fragment (`render_as: "text/html fragment"`)
with an animated down-the-line + face-on comparison already built in — your
current move in red, the target move in green — so there's no "switch camera"
to offer; both angles are always shown together. Use `build_visualization` with
no `drill` key for the shot pattern + swing path + targets page, and the
`drill` form for per-drill mechanics.
```

Then replace the data dict shape block:

```markdown
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
```

with:

```markdown
For the shot pattern + swing path + targets page, the data dict shape:
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

For a single drill's mechanics (one card, one exercise), the data dict shape:
```
{
  "handedness": "RH" | "LH",
  "drill": {"archetype": "<id from drill-library's at-home-no-ball table>", "name": "Pump-and-drop"},
  "swing": {"clubPath": deg}   // optional — overrides the impact angle with a real number
}
```
This returns a fragment, not a full page — embed it inside your own per-drill
card (title, progress, feel cue, reps/club/order, video link, prev/next); don't
wrap it in another `<html>` document.
```

- [ ] **Step 6: Edit `skills/trackman-visualizer/PROMPT.md`**

Replace:

```markdown
- **One drill at a time** — if a drill isn't clicking, animate that single
  drill's intended motion: the red current move (e.g. out-to-in, face open) vs
  the green target move. Show them **one per exercise**, not all at once — that's
  what makes mechanics land. Use `build_visualization` with the drill's target
  `swing` + a one-line `diagnosis`, or the client's own HTML/SVG artifact
  capability for a richer per-drill animation. Offer to slow it down or change
  the camera (top-down vs face-on vs side) if it still isn't clear.
```

with:

```markdown
- **One drill at a time** — if a drill isn't clicking, animate that single
  drill's intended motion. Call `build_visualization({handedness, drill:
  {archetype, name}, swing?})` — `archetype` is the id from the drill's row in
  `drill-library`'s at-home-no-ball table, and `swing.clubPath` (if you have a
  real measured value) overrides the illustrative impact angle. This returns an
  embeddable fragment (not a full page) with an animated down-the-line +
  face-on comparison already built in — current move in red, target in green —
  so there's no "switch camera" to offer; both angles are always shown
  together. Show them **one per exercise**, not all at once — that's what makes
  mechanics land.
```

Then replace the data dict shape block (the one under "## Build it") with the same two-shape version from Step 5 (shot-pattern shape unchanged, plus the new drill shape and embedding note).

- [ ] **Step 7: Edit `skills/golf-practice-at-home/SKILL.md`**

Replace:

```markdown
4. **Show it — one drill at a time, with a video.** Animate each drill (red
   current → green target) via the `trackman-visualizer` skill, one per exercise,
   **and give each a verified YouTube link** (from `drill-library`, or
   live-search + verify — never invent URLs). Animation + video for every drill.
```

with:

```markdown
4. **Show it — one drill at a time, with a video.** For each drill, call
   `build_visualization({handedness, drill: {archetype, name}, swing?})` (the
   `archetype` comes from the drill's row in `drill-library`'s at-home-no-ball
   table) and embed the returned fragment in your own per-drill card alongside
   **a verified YouTube link** (from `drill-library`, or live-search + verify —
   never invent URLs). Animation + video for every drill.
```

- [ ] **Step 8: Edit `skills/golf-practice-at-home/PROMPT.md`**

Replace the equivalent step 4:

```markdown
4. **Show it — one drill at a time, with a video.** Animate each drill's intended
   motion (red current move → green target move) via the `trackman-visualizer`
   prompt, one per exercise, **and give each drill a verified YouTube link** (from
   the `drill-library` prompt, or live-search + verify one — never invent URLs).
   Animation + video for every drill; lead with the visual, don't make them ask.
```

with:

```markdown
4. **Show it — one drill at a time, with a video.** For each drill, call
   `build_visualization({handedness, drill: {archetype, name}, swing?})` (the
   `archetype` comes from the drill's row in `drill-library`'s at-home-no-ball
   table) and embed the returned fragment in your own per-drill card, **and
   give each drill a verified YouTube link** (from the `drill-library` prompt,
   or live-search + verify one — never invent URLs). Animation + video for
   every drill; lead with the visual, don't make them ask.
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `uv run pytest tests/test_skill_content.py -v`
Expected: all tests `PASS`, including the 3 new ones and the original ones (the original tests check substrings like `"no exceptions"`, `"never invent"`, `"build_visualization"`, `"verify"` — none of which were removed by the edits above).

- [ ] **Step 10: Run the full test suite**

Run: `uv run pytest`
Expected: all tests pass (this also re-validates `tests/test_prompts.py` and `tests/test_setup.py`, which load skill content indirectly).

- [ ] **Step 11: Commit**

```bash
git add skills/trackman-visualizer/SKILL.md skills/trackman-visualizer/PROMPT.md \
        skills/golf-practice-at-home/SKILL.md skills/golf-practice-at-home/PROMPT.md \
        skills/drill-library/SKILL.md skills/drill-library/PROMPT.md \
        tests/test_skill_content.py
git commit -m "$(cat <<'EOF'
Wire skills to the new drill archetype visualization

trackman-visualizer and golf-practice-at-home now call
build_visualization's drill mode instead of freehand-authoring a
per-drill diagram; drill-library's at-home-no-ball table gains an
Archetype column as the explicit drill->archetype mapping. Edited in
both SKILL.md (Claude Code) and PROMPT.md (every other client,
including Claude Desktop) for each skill.
EOF
)"
```

---

### Task 5: Visual spot-check via the Playwright render-check script

**Files:**
- Modify: `scripts/check-visualization.py`

**Interfaces:**
- Consumes: `build_drill_fragment` (Task 2), `ARCHETYPE_IDS` (Task 1).
- Produces: nothing consumed by later tasks — this is a manual visual verification gate, not pytest-discovered.

- [ ] **Step 1: Add `--demo-drill` to the script**

In `scripts/check-visualization.py`, update the module docstring's usage block:

```python
"""Headless render-check for a visualization HTML — proves it works like an artifact.

Loads the HTML via page.set_content (the same way a Claude artifact sandboxes it
through an iframe srcdoc), captures console errors / page errors, lets the
animation run, and saves a screenshot. Exit 0 if no errors.

    uv run python scripts/check-visualization.py <file.html> [screenshot.png]
    uv run python scripts/check-visualization.py --demo [screenshot.png]
    uv run python scripts/check-visualization.py --demo-drill <archetype> [screenshot.png]

Needs the [login] extra (Playwright) + a browser.
"""
```

Replace `main`:

```python
def main(argv: list[str]) -> int:
    from trackman_mcp.visualize import _DEMO, build_html

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--demo":
        html = build_html(_DEMO)
        shot = argv[1] if len(argv) > 1 else "viz-check.png"
    else:
        html = open(argv[0]).read()
        shot = argv[1] if len(argv) > 1 else "viz-check.png"
    return asyncio.run(check(html, shot))
```

with:

```python
def main(argv: list[str]) -> int:
    from trackman_mcp.visualize import _DEMO, build_drill_fragment, build_html

    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--demo":
        html = build_html(_DEMO)
        shot = argv[1] if len(argv) > 1 else "viz-check.png"
    elif argv[0] == "--demo-drill":
        from trackman_mcp.swing_archetypes import ARCHETYPE_IDS
        archetype = argv[1] if len(argv) > 1 else "over_the_top"
        if archetype not in ARCHETYPE_IDS:
            print(f"unknown archetype {archetype!r}, expected one of: "
                  f"{', '.join(sorted(ARCHETYPE_IDS))}")
            return 1
        html = build_drill_fragment({
            "drill": {"archetype": archetype, "name": archetype.replace("_", " ").title()},
        })
        shot = argv[2] if len(argv) > 2 else f"viz-check-{archetype}.png"
    else:
        html = open(argv[0]).read()
        shot = argv[1] if len(argv) > 1 else "viz-check.png"
    return asyncio.run(check(html, shot))
```

- [ ] **Step 2: Lint**

Run: `uv run ruff check scripts/check-visualization.py`
Expected: no errors.

- [ ] **Step 3: Run the spot-check for all 5 archetypes**

Run, for each archetype:

```bash
uv run python scripts/check-visualization.py --demo-drill over_the_top /tmp/viz-over_the_top.png
uv run python scripts/check-visualization.py --demo-drill early_transition /tmp/viz-early_transition.png
uv run python scripts/check-visualization.py --demo-drill disconnected_sequencing /tmp/viz-disconnected_sequencing.png
uv run python scripts/check-visualization.py --demo-drill open_face /tmp/viz-open_face.png
uv run python scripts/check-visualization.py --demo-drill inside_closing /tmp/viz-inside_closing.png
```

Expected for each: exits 0, prints `RENDER OK — no console errors or page errors.` (no JS errors means the CSS keyframe names and SVG nesting are well-formed). Then view each PNG: it should show 4 small line-drawn golfer figures in a 2×2 grid (down-the-line row, face-on row; current/red column, target/green column) — a head, a spine, an arm, and a club line, recognizably mid-swing, not garbled or overlapping into a meaningless tangle. If a figure looks broken (e.g. limbs pointing the wrong way, or the two columns look identical), the bug is in `swing_archetypes.py`'s keyframe data or `view_params` projection (Task 1) — fix the specific numbers there, not the rendering code, and re-run this step.

- [ ] **Step 4: Commit**

```bash
git add scripts/check-visualization.py
git commit -m "$(cat <<'EOF'
Add --demo-drill mode to the visualization render-check script

Lets each fault archetype's fragment be headlessly rendered and
screenshotted for a visual sanity check, same as --demo already does
for the full page.
EOF
)"
```

---

### Task 6: Full-suite gate + Claude Desktop verification

**Files:** none (verification only).

**Interfaces:** none.

- [ ] **Step 1: Run the full automated gate**

Run: `uv run pytest && uv run ruff check && uv run mypy`
Expected: all pass, zero errors. This is the same gate `scripts/release.sh` runs before a release.

- [ ] **Step 2: Confirm the local package still builds clean for the Desktop dev server**

Run: `uv run python -c "import trackman_mcp.server; print('import ok')"`
Expected: prints `import ok` (this is the same check already run when the `trackman-golf-dev` entry was added to the Desktop config — confirms the new module imports cleanly through the same path Desktop uses).

- [ ] **Step 3: Restart Claude Desktop**

The `trackman-golf-dev` MCP server entry already exists in
`~/Library/Application Support/Claude/claude_desktop_config.json`, pointing at
this checkout. Quit and reopen Claude Desktop (or use its "reload extensions" /
"restart MCP servers" control if available) so it picks up the new code.

- [ ] **Step 4: Manually verify the tool in a Desktop chat**

In a new Claude Desktop conversation, ask it to call the `build_visualization`
tool with a `drill` payload, e.g.: *"Call build_visualization on the
trackman-golf-dev server with `{\"drill\": {\"archetype\": \"early_transition\",
\"name\": \"Pump-and-drop\"}}` and show me the result as an HTML artifact."*

Expected: the tool returns `render_as: "text/html fragment"`, and the rendered
artifact shows the 2×2 down-the-line/face-on, current/target stick-figure grid
with a Replay button that visibly restarts the animation when clicked.

- [ ] **Step 5: Manually verify the skill prompts in Desktop's prompt picker**

Open Desktop's prompt picker (the `/` or attachment menu, depending on Desktop
version) and confirm `trackman-visualizer` and `golf-practice-at-home` are
listed (served via `prompts.py` from the `trackman-golf-dev` server). Invoke
`golf-practice-at-home` and confirm the resulting conversation calls
`build_visualization` with a `drill` key for at least one drill, rather than
freehand-authoring a diagram.

- [ ] **Step 6: Record the outcome**

If everything in Steps 4-5 works: no further action — the feature is done. If
something doesn't render or the prompt doesn't pick up the new wording, that's
a real bug to fix (most likely in Task 2's SVG/CSS or Task 4's prompt text) —
fix it in the relevant task's files, re-run that task's tests, and repeat
Task 6 from Step 1.
