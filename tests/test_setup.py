"""The one-call `setup` onboarding tool + prompt."""

from __future__ import annotations

from golf_coach import onboarding, server


def test_setup_kit_shape():
    kit = onboarding.build_setup_kit()
    assert set(kit) >= {"summary", "system_prompt", "skills", "instructions"}
    # System prompt is the always-on coach and references the real tools.
    sp = kit["system_prompt"].lower()
    assert "coach" in sp
    for tool in ("auth", "training_plan", "build_visualization", "session_analysis",
                 "gamebook_round"):
        assert tool in sp
    # Per-client steps are all present.
    assert set(kit["instructions"]) >= {
        "claude_project", "claude_desktop_skills", "claude_code", "chatgpt"
    }


def test_setup_kit_skills_are_upload_ready():
    kit = onboarding.build_setup_kit()
    names = {s["name"] for s in kit["skills"]}
    assert {"golf-coaching", "drill-library", "trackman-stats-analysis",
            "gamebook-screenshot-analysis"} <= names  # incl. on-course GameBook skill
    assert "trackman-api-discovery" not in names  # dev skill excluded
    for s in kit["skills"]:
        assert s["filename"] == f"{s['name']}/SKILL.md"
        assert s["content"].startswith("---\n")          # front matter
        assert f"name: {s['name']}" in s["content"]


async def test_setup_tool_returns_kit():
    kit = await server.setup()
    assert kit["system_prompt"]
    assert len(kit["skills"]) == len(onboarding.build_setup_kit()["skills"])


async def test_setup_tool_and_prompt_registered():
    tools = {t.name for t in await server.mcp.list_tools()}
    assert "setup" in tools
    prompts = {p.name for p in await server.mcp.list_prompts()}
    assert "setup" in prompts
