"""One-call setup kit: an always-on coach system prompt + installable skills.

An MCP server can't itself create a Project or switch on Claude Skills (no
protocol primitive for that). What it *can* do is hand the client everything
needed to set that up in one step: a ready-to-paste project **system prompt**
that turns any Project / Custom GPT into the Trackman coach, the coaching
**skills** as upload-ready files, and per-client **instructions**. In an agentic
client (Claude Code) the model can write the files directly from this kit.
"""

from __future__ import annotations

from typing import Any

from .prompts import load_skills

# The always-on coach. Paste into a Claude Project / ChatGPT Project's custom
# instructions; with the trackman-golf MCP connected, every chat in that project
# is the coach. Self-contained — works even without the separate skills.
COACH_SYSTEM_PROMPT = """\
You are the user's personal golf coach, powered by their real Trackman data
through the connected `trackman-golf` MCP. Always work from real data — never
invent numbers. If a tool says you're not signed in, tell the user to run
`trackman-mcp login` (or paste a token) and stop.

Your loop:
1. Sign-in check — call `auth` (action="status").
2. Diagnose — pull `get_profile`, `get_handicap`, `get_club_stats`,
   `get_course_rounds`, and `list_sessions` + `get_session`. Find where the user
   loses strokes — club gapping, dispersion, scoring leaks, launch efficiency —
   ranked by stroke impact, each tied to the specific number behind it. For a
   normalized per-session view use `session_analysis` (action="analyze"/"list").
   For real on-course rounds the user shares as **Golf GameBook screenshots**, use
   `gamebook_round` (action="save" to ingest one coverage-aware round, "compare"
   for scoring-led progress vs recent rounds) — lead with scoring; GameBook
   reliably tracks only score-per-hole, so trust a non-scoring stat (putts,
   fairways, GIR, short game) only where its `coverage` isn't `none` — a 0.0% that
   just means "not entered" is never a real zero.
3. Prescribe — turn the top 2–3 gaps into ONE specific, measurable practice
   session: per block give club, distances, reps, a Trackman target, a drill
   (with a real YouTube link — never invent URLs), and the strokes it saves.
4. Remember — save the plan with `training_plan` (action="save") including
   `target_specs`. Recall it with action="next", grade a later session with
   action="verify", and complete it with action="done".
5. Visualize when it helps — `build_visualization(data)` returns a self-contained
   animated HTML artifact (ball flight, swing path, target progress).

Style: specific and honest — "10 balls, 56°, 50/70/90 m ladder, log carry," never
"practice your wedges." Don't credit warm-ups as training. If the data is too
thin to judge something, say so. When the user asks "what's today's training?",
recall and grade the saved plan — don't re-diagnose from scratch.
"""


def _skill_file(name: str, description: str, body: str) -> str:
    """Compose an upload-ready SKILL.md (front matter + clean body)."""
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"


_INSTRUCTIONS = {
    "claude_project": (
        "Claude Projects (claude.ai / Desktop): create a Project → paste "
        "`system_prompt` into the project's custom instructions → add the "
        "trackman-golf connector. Every chat in that project is then the coach."
    ),
    "claude_desktop_skills": (
        "Claude Desktop / claude.ai Skills (optional, for auto-activation): "
        "Settings → Capabilities → Skills → upload each item in `skills` "
        "(filename + content) as its own skill."
    ),
    "claude_code": (
        "Claude Code: install the plugin (`/plugin marketplace add "
        "bjornj12/trackman-mcp-client` then `/plugin install "
        "trackman-golf@trackman-golf`) — it ships the skills. Or write each "
        "`skills` entry to `.claude/skills/<name>/SKILL.md` and `system_prompt` "
        "to CLAUDE.md."
    ),
    "chatgpt": (
        "ChatGPT: create a Project (or Custom GPT) → paste `system_prompt` into "
        "its instructions. Connecting the MCP needs a *remote* (HTTP) MCP server; "
        "the local stdio server isn't reachable by ChatGPT — see the README."
    ),
}


def build_setup_kit() -> dict[str, Any]:
    """Everything a client needs to set up the coach in one step."""
    skills = [
        {
            "name": s.name,
            "description": s.description,
            "filename": f"{s.name}/SKILL.md",
            "content": _skill_file(s.name, s.description, s.body),
        }
        for s in load_skills()
    ]
    return {
        "summary": (
            "Set up the Trackman golf coach: (1) create a Project and paste "
            "`system_prompt` into its custom instructions, (2) connect the "
            "trackman-golf MCP, (3) optionally upload `skills` for auto-activation. "
            "In Claude Code, the model can write these files for you."
        ),
        "system_prompt": COACH_SYSTEM_PROMPT,
        "skills": skills,
        "instructions": _INSTRUCTIONS,
    }
