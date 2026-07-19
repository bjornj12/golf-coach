"""Guards on the coaching-skill content (proactive, visual, no-ball at-home)."""

from __future__ import annotations

from golf_coach import prompts


def _body(name: str) -> str:
    return next(s for s in prompts.load_skills() if s.name == name).body.lower()


def test_drill_library_has_at_home_no_ball_drills():
    b = _body("drill-library")
    assert "no-ball" in b or "no ball" in b
    assert "at-home" in b or "at home" in b
    for drill in ("wall", "pump-and-drop", "trail-arm", "split-hands", "step-through"):
        assert drill in b, f"drill-library missing the {drill!r} no-ball drill"


def test_drill_library_video_link_rule_degrades_gracefully():
    b = _body("drill-library")
    assert "degrade gracefully" in b            # links preferred, not mandatory when no web search
    assert "youtube link" in b or "video link" in b
    assert "never invent" in b or "never fabricate" in b   # but no hallucinated URLs


def test_golf_coaching_is_visual_first_and_proactive():
    b = _body("golf-coaching")
    assert "build_visualization" in b          # visualize by default
    assert "verify" in b                       # auto-grade against the plan
    assert "no-ball" in b or "no range" in b or "at-home" in b


def test_golf_coaching_mandates_visual_and_video_every_time():
    b = _body("golf-coaching")
    # Visuals are required, not optional.
    assert "every time" in b or "never give text-only" in b
    assert "animat" in b                        # animate the mechanics
    # Every drill carries a verified video link when web search is available; never fabricated.
    assert "video link" in b
    assert "never fabricate" in b or "invented" in b


def test_practice_at_home_skill_exists():
    b = _body("golf-practice-at-home")
    assert b
    assert "no ball" in b or "no-ball" in b
    assert "training_plan" in b                # saves the routine


def test_at_home_practice_feedback_card_shape():
    b = _body("at-home-practice-feedback")
    # The mobile-first drill card carries every section of the output structure.
    for section in ("fault", "root cause", "drill", "feedback method",
                    "equipment needed", "validation checkpoint", "youtube"):
        assert section in b, f"at-home-practice-feedback missing {section!r} section"
    assert "mobile" in b
    assert "drill-library" in b                # drills/videos come from the library
    assert "never invent" in b or "never fabricate" in b  # no hallucinated URLs
    assert "training_plan" in b                # offers to save for later grading
