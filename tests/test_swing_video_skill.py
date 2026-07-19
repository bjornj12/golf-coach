"""Guards on the swing-video-check skill (single-angle, grounded, honest)."""

from __future__ import annotations

from golf_coach import prompts


def _body(name: str) -> str:
    return next(s for s in prompts.load_skills() if s.name == name).body.lower()


def test_skill_is_served_as_prompt():
    assert "swing-video-check" in {s.name for s in prompts.load_skills()}


def test_skill_prompt_has_no_claude_code_only_language():
    body = _body("swing-video-check")
    assert "subagent" not in body
    assert "forked" not in body


def test_skill_extracts_frames_rather_than_pretending_to_watch():
    body = _body("swing-video-check")
    assert "ffmpeg" in body
    assert "frame" in body
    assert "never pretend" in body or "never fake" in body


def test_skill_grounds_in_the_live_practice_card_not_hardcoded_faults():
    body = _body("swing-video-check")
    assert "practice-card.md" in body
    assert "driver-rebuild-tracker.md" in body
    assert "never hardcode" in body
    # A rebuild that deliberately overshoots must be graded as progress.
    assert "progress" in body


def test_skill_is_honest_about_what_a_single_angle_shows():
    body = _body("swing-video-check")
    assert "one camera angle" in body
    assert "not visible from this angle" in body
    assert "does not measure" in body or "measures nothing" in body


def test_skill_output_is_one_swing_thought():
    body = _body("swing-video-check")
    assert "one swing thought" in body or "one-swing-thought" in body
    assert "verdict" in body


def test_frame_extraction_helper_ships_with_the_skill():
    d = prompts.skills_dir()
    assert d is not None
    script = d / "swing-video-check" / "scripts" / "extract_frames.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111  # executable
