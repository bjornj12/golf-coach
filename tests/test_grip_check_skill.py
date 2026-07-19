"""Guards on the grip-check skill and the coach's grip-first gate."""

from __future__ import annotations

from golf_coach import prompts


def _body(name: str) -> str:
    return next(s for s in prompts.load_skills() if s.name == name).body.lower()


def test_skill_is_served_as_prompt():
    assert "grip-check" in {s.name for s in prompts.load_skills()}


def test_skill_prompt_has_no_claude_code_only_language():
    body = _body("grip-check")
    assert "subagent" not in body
    assert "forked" not in body


def test_skill_requires_both_face_forward_views():
    body = _body("grip-check")
    assert "club up" in body
    assert "club down" in body
    assert "face-forward" in body
    assert "ask" in body  # missing view → ask for it, don't guess


def test_skill_classifies_weak_vs_strong():
    body = _body("grip-check")
    assert "too weak" in body
    assert "too strong" in body
    assert "knuckle" in body
    assert "fingers" in body and "palm" in body


def test_skill_grades_against_the_live_practice_card():
    body = _body("grip-check")
    assert "practice-card.md" in body
    assert "never hardcode" in body


def test_golf_coaching_gates_prescriptions_on_a_grip_check():
    body = _body("golf-coaching")
    assert "grip-check" in body
    assert "club up" in body and "club down" in body
    assert "never prescribe blind" in body
