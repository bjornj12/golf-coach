"""The coaching skills are served as MCP prompts."""

from __future__ import annotations

from fastmcp import FastMCP

from trackman_mcp import prompts

USER_FACING = {
    "golf-coaching",
    "trackman-stats-analysis",
    "drill-library",
    "trackman-visualizer",
    "trackman-session-analyzer",
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
    assert n == len(prompts.load_skills())
    names = {p.name for p in await m.list_prompts()}
    assert USER_FACING <= names


async def test_server_exposes_skill_prompts():
    from trackman_mcp import server
    names = {p.name for p in await server.mcp.list_prompts()}
    assert USER_FACING <= names
    assert "trackman-api-discovery" not in names
