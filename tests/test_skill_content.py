"""Guards on the coaching-skill content (proactive, visual, no-ball at-home)."""

from __future__ import annotations

from trackman_mcp import prompts


def _body(name: str) -> str:
    return next(s for s in prompts.load_skills() if s.name == name).body.lower()


def test_drill_library_has_at_home_no_ball_drills():
    b = _body("drill-library")
    assert "no-ball" in b or "no ball" in b
    assert "at-home" in b or "at home" in b
    for drill in ("wall", "pump-and-drop", "trail-arm", "split-hands", "step-through"):
        assert drill in b, f"drill-library missing the {drill!r} no-ball drill"


def test_golf_coaching_is_visual_first_and_proactive():
    b = _body("golf-coaching")
    assert "build_visualization" in b          # visualize by default
    assert "verify" in b                       # auto-grade against the plan
    assert "no-ball" in b or "no range" in b or "at-home" in b


def test_practice_at_home_skill_exists():
    b = _body("golf-practice-at-home")
    assert b
    assert "no ball" in b or "no-ball" in b
    assert "training_plan" in b                # saves the routine
