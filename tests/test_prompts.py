"""The coaching skills are served as MCP prompts."""

from __future__ import annotations

from fastmcp import FastMCP

from golf_coach import prompts

USER_FACING = {
    "golf-coaching",
    "trackman-stats-analysis",
    "drill-library",
    "trackman-visualizer",
    "trackman-session-analyzer",
    "golf-practice-at-home",
}


def test_load_skills_covers_user_facing_excludes_dev():
    loaded = {s.name for s in prompts.load_skills()}
    assert USER_FACING <= loaded
    assert "trackman-api-discovery" not in loaded  # dev/phase-0 skill is excluded


def test_skill_body_is_stripped_of_front_matter():
    coaching = next(s for s in prompts.load_skills() if s.name == "golf-coaching")
    assert coaching.body
    assert "coach" in coaching.body.lower()
    assert not coaching.body.lstrip().startswith("---")  # no YAML front matter
    assert coaching.description  # carried from front matter


async def test_register_skill_prompts_registers_each():
    m = FastMCP(name="t")
    n = prompts.register_skill_prompts(m)
    assert n == len(prompts.load_skills()) + 1  # skills + the `setup` prompt
    names = {p.name for p in await m.list_prompts()}
    assert USER_FACING <= names
    assert "setup" in names


def test_desktop_prompt_body_is_preferred():
    # The served body is the client-agnostic PROMPT.md, not the Claude Code SKILL.md.
    coaching = next(s for s in prompts.load_skills() if s.name == "golf-coaching")
    assert "call the tools directly" in coaching.body.lower()


def test_served_prompts_have_no_claude_code_only_language():
    # Prompts run in any client (e.g. Claude Desktop) — no subagent/fork/skill-
    # dispatch mechanics should leak into the served text.
    for s in prompts.load_skills():
        low = s.body.lower()
        assert "subagent" not in low, f"{s.name} leaks subagent language"
        assert "forked" not in low, f"{s.name} leaks fork language"


async def test_server_exposes_skill_prompts():
    from golf_coach import server
    names = {p.name for p in await server.mcp.list_prompts()}
    assert USER_FACING <= names
    assert "trackman-api-discovery" not in names


async def test_skill_prompts_take_no_arguments():
    # Skill prompts are static instructions — they must expose NO inputs, or the
    # client (e.g. Claude Desktop) pops up a "fill in the arguments" dialog.
    from golf_coach import server
    for p in await server.mcp.list_prompts():
        args = getattr(p, "arguments", None) or []
        assert args == [], f"{p.name} exposes unexpected arguments: {[a.name for a in args]}"


async def test_skill_prompt_renders_its_body():
    # And invoking it returns the skill text (not empty).
    from golf_coach import server
    result = await (await server.mcp.get_prompt("golf-coaching")).render()
    text = result.messages[0].content.text
    assert len(text) > 500
    assert "coach" in text.lower()
