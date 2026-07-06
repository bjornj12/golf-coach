"""Serve the bundled coaching skills as MCP prompts.

Each user-facing skill in `skills/` becomes an invocable MCP prompt, so the
coaching brain is available in any MCP client (Claude Desktop included), not
only the Claude Code plugin. The skill markdown is the single source of truth;
it is bundled into the wheel (see pyproject `force-include`) and loaded here at
import time. The server still computes no coaching verdicts — these prompts just
deliver the same skill instructions Claude would get from the plugin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Skills that are not end-user coaching skills (project/dev tooling).
EXCLUDE = {"trackman-api-discovery"}


@dataclass(frozen=True)
class SkillPrompt:
    name: str
    description: str
    body: str


def skills_dir() -> Path | None:
    """Locate the bundled skills directory, in both installed and dev layouts."""
    here = Path(__file__).resolve().parent
    candidates = [
        here / "skills",            # installed wheel (force-included as package data)
        here.parent.parent / "skills",  # editable/dev: repo-root skills/
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _parse_front_matter(md: str) -> tuple[dict[str, str], str]:
    """Split a SKILL.md into its YAML front matter (name/description) and body."""
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, re.S)
    if not m:
        return {}, md.strip()
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fm[key.strip()] = value.strip()
    return fm, m.group(2).strip()


def load_skills() -> list[SkillPrompt]:
    """Load user-facing skills (excluding dev tooling), name-sorted.

    Metadata (name/description) comes from each skill's SKILL.md front matter.
    The prompt *body* comes from a client-agnostic PROMPT.md when present (the
    version tuned for being invoked as an MCP prompt, e.g. in Claude Desktop —
    no subagents/skill-dispatch); otherwise it falls back to the SKILL.md body.
    """
    d = skills_dir()
    if not d:
        return []
    out: list[SkillPrompt] = []
    for sub in sorted(d.iterdir()):
        if not sub.is_dir() or sub.name in EXCLUDE:
            continue
        skill_md = sub / "SKILL.md"
        if not skill_md.is_file():
            continue
        fm, skill_body = _parse_front_matter(skill_md.read_text(encoding="utf-8"))
        name = fm.get("name") or sub.name
        description = fm.get("description") or f"The {name} skill."
        prompt_md = sub / "PROMPT.md"
        body = prompt_md.read_text(encoding="utf-8").strip() if prompt_md.is_file() else skill_body
        out.append(SkillPrompt(name=name, description=description, body=body))
    return out


def _make_render(body: str):
    """Build a zero-argument render function that returns `body`.

    The body is captured in the closure — NOT as a function parameter — so the
    prompt exposes no arguments. (A parameter, even with a default, would surface
    as a required/optional input in the client UI.)
    """
    def render() -> str:
        return body

    return render


_SETUP_PROMPT_BODY = """\
Set up the Trackman golf coach for this user. Call the `setup` tool to get the kit
(an always-on coach `system_prompt`, the `skills`, and per-client `instructions`),
then:

- If you can write files here (e.g. Claude Code): create each skill at
  `.claude/skills/<name>/SKILL.md` from `skills`, write `system_prompt` into
  `CLAUDE.md`, and confirm what you created.
- Otherwise (Claude Desktop / claude.ai / ChatGPT): show the `system_prompt` for
  the user to paste into a new Project's custom instructions, and walk them
  through the matching entry in `instructions` (plus the `skills` they can
  optionally upload for auto-activation).

Keep it to a short, actionable walkthrough — no raw JSON dumps.
"""

SETUP_PROMPT_NAME = "setup"
SETUP_PROMPT_DESCRIPTION = (
    "Set up the Trackman golf coach: get an always-on coach system prompt for a "
    "Project, plus the installable skills and per-client steps (Claude Desktop, "
    "claude.ai, ChatGPT, Claude Code)."
)


def register_skill_prompts(mcp) -> int:
    """Register the setup prompt + one (argument-less) prompt per skill. Returns count."""
    from fastmcp.prompts import Prompt

    mcp.add_prompt(
        Prompt.from_function(
            _make_render(_SETUP_PROMPT_BODY),
            name=SETUP_PROMPT_NAME,
            description=SETUP_PROMPT_DESCRIPTION,
        )
    )
    skills = load_skills()
    for skill in skills:
        mcp.add_prompt(
            Prompt.from_function(
                _make_render(skill.body), name=skill.name, description=skill.description
            )
        )
    return len(skills) + 1
