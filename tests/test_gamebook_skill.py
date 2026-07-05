# tests/test_gamebook_skill.py
from __future__ import annotations

import json
from pathlib import Path

from trackman_mcp import gamebook_analysis as ga
from trackman_mcp import prompts

FIXTURE = Path(__file__).parent / "fixtures" / "gamebook" / "2026-06-09.json"


def _skill_body(name: str) -> str:
    return next(s for s in prompts.load_skills() if s.name == name).body.lower()


def test_skill_is_served_as_prompt():
    names = {s.name for s in prompts.load_skills()}
    assert "gamebook-screenshot-analysis" in names


def test_skill_prompt_has_no_claude_code_only_language():
    body = _skill_body("gamebook-screenshot-analysis")
    assert "subagent" not in body
    assert "forked" not in body


def test_skill_mentions_coverage_and_scoring_truth():
    body = _skill_body("gamebook-screenshot-analysis")
    assert "coverage" in body
    assert "gamebook_round" in body
    assert "self-check" in body or "self check" in body


def test_golden_fixture_matches_analytics():
    record = json.loads(FIXTURE.read_text())
    assert ga.self_check(record) == []
    scoring = ga.scoring_from_holes(record["holes"])
    assert scoring == record["scoring"]
    assert record["coverage"]["scoring"] == "full"
    assert record["coverage"]["gir"] in ("partial", "none")
    assert record["dimensions"]["sand_save"]["coverage"] == "none"
