# Trackman Golf MCP

## Project Overview

**Name**: Trackman Golf MCP (working name)

**Purpose**: A Model Context Protocol (MCP) server that connects to Trackman's
golf platform using the user's own login, fetches their stats (course rounds,
practice sessions, shot-level launch-monitor data, club gapping, handicap), and
exposes them as MCP tools. On top of that data, a set of Claude **skills** act
as the user's golf coach — diagnosing weaknesses and giving actionable,
specific practice plans with example drills and YouTube links to follow.

**Who it's for**: The individual golfer who already practices on Trackman bays /
ranges or plays Trackman-enabled courses, and wants their data turned into a
concrete "what should I work on next" plan.

---

## The Core Boundary (read this first)

There is a **hard separation of concerns**. Respect it in every change:

- **The MCP server only fetches and returns raw data.** Authentication,
  HTTP calls to Trackman, and shaping responses into clean JSON. It contains
  **no coaching opinions, no drill recommendations, no analysis verdicts.**
- **The Claude skills do all the thinking.** They call the MCP tools to get
  data, then diagnose, plan, and coach in prompt/markdown.

Why: coaching logic should be tunable by editing markdown, not redeploying a
server. Keep judgment out of the server and data out of the skills.

If you find yourself adding "recommend a drill" logic to the MCP, stop — that
belongs in a skill. If you find yourself hardcoding shot data in a skill, stop —
that belongs behind an MCP tool.

---

## Status & Phases

This repo currently contains **documentation and skills only** — no server code
yet. Build in this order:

- **Phase 0 — API discovery (do this first).** Trackman has no public golf API.
  Before writing a single tool, discover the real endpoints and auth flow the
  web portal uses, and write them down. Use the `trackman-api-discovery` skill.
  Output: `docs/trackman-api.md` filled in.
- **Phase 1 — MCP server.** Implement the tools below against the discovered
  API. Python + FastMCP.
- **Phase 2 — Coaching skills.** Wire `trackman-stats-analysis` and
  `golf-coaching` to real tool output; grow the `drill-library`.

Do not skip Phase 0. Tool names and shapes below are **provisional** and will be
corrected by what discovery finds.

---

## Technology Stack

- **Runtime**: Python 3.12+
- **MCP framework**: [FastMCP](https://github.com/jlowin/fastmcp) / the official
  `mcp` Python SDK
- **HTTP client**: `httpx` (async)
- **Auth/session**: `httpx` cookie/token session; tokens stored locally only
- **Data shaping**: plain dicts / `pydantic` models; `pandas` is allowed in
  *skills'* helper scripts for analysis, not required in the server
- **Package/deps**: `uv` (preferred) or `pip` + `pyproject.toml`
- **Tests**: `pytest`; record real API responses as fixtures (with secrets
  scrubbed) and test tools against those.

---

## MCP Tools (confirmed against the real API — see `docs/trackman-api.md`)

All tools return **raw, structured data only**. No prose, no advice. Every tool
calls the single GraphQL endpoint `POST https://api.trackmangolf.com/graphql`
under the signed-in user's `me` root.

| Tool | Backing (under `me`) | Returns |
|------|----------------------|---------|
| `authenticate` | OIDC token capture | Validates the captured Bearer token (`TRACKMAN_TOKEN`); reports who you're signed in as. Never echoes the token. |
| `get_profile` | `profile` + `hcp` | Identity + current **handicap** (`hcp.currentHcp`). |
| `get_handicap` | `hcp.playerHistory` | Handicap record history (differentials, trend). |
| `list_sessions` | `activities(kinds,timeFrom,timeTo,skip,take)` | Practice + course activities (id, time, kind, summary). |
| `get_session` | `node(id)` / `activities` | One activity in full: range strokes or round detail. |
| `get_course_rounds` | `scorecards(skip,take,completed)` | Scorecards: per-hole scores, FIR/GIR, putts, `stat`. |
| `get_club_stats` | `equipment.clubs.findMyDistance` | Per-club **gapping**: carry/total, std-dev, dispersion. |
| `get_shot_data` | `*.measurement` (`Measurement`) | Shot launch metrics: ball/club speed, smash, launch, spin, carry, side, curve, landing angle (~80 fields). |
| `get_activity_summary` | `activitySummary(timeFrom,timeTo)` | Counts per activity kind over a window. |

### Session-analysis tools (local store, deterministic analytics)

These persist and serve a per-session *analysis*. The analytics are
**deterministic** (in `analysis.py`) — classification and measurement, not
coaching. Coaching narrative still lives in the skills. The store is JSON at
`~/.trackman-mcp/session-analyses.json`, capped at the **last 30**, latest first.

| Tool | Does |
|------|------|
| `analyze_and_store_session(activity_id)` | Fetch a session, classify (warm-up vs serious practice vs game), compute metrics + course difficulty, normalize vs previously stored sessions, flag used-vs-available clubs, store, return the record. |
| `list_session_analyses()` | Index of stored analyses (id, time, kind, category, seriousness, summary), latest first. |
| `get_session_analysis(activity_id)` | One full stored analysis record. |

Classification (see `analysis.py`): a session is a **warm-up** (not an
improvement attempt) if under ~8 strokes or ~5 minutes — even for an otherwise
"serious" kind; **serious practice** if it has real volume/duration/club variety
or is a focused kind (shot analysis, find-my-distance, sim/virtual-range, etc.);
**game** for played rounds. Normalization is always against sessions
*chronologically before* the one analyzed. Units are metric (m/s, meters).

### Training-plan tools (the coach's memory)

The coach saves prescribed practice sessions so they can be recalled later
("what's today's training?"). Store is JSON at `~/.trackman-mcp/training-plans.json`
(`training_store.py`), an ordered queue capped at the most recent 50.

| Tool | Does |
|------|------|
| `save_training_plan(plan)` | Persist a prescribed plan (title, focus, diagnosis, blocks, targets) to the pending queue. |
| `get_next_training()` | Return the next pending plan — the answer to "what's today's training?". |
| `list_training_plans(status?)` | List plans (oldest→newest), optional `pending`/`done` filter. |
| `mark_training_done(plan_id, result_session_id?)` | Complete a plan; the next pending one becomes current. |

`golf-coaching` writes here (Prescribe → `save_training_plan`) and reads here
(Recall → `get_next_training`, then `mark_training_done` once a session hits the
plan's target metrics).

**Auth reality**: the web portal uses a *confidential* OIDC client (backend-for-
frontend), so the MCP cannot run the OAuth exchange itself. It authenticates with
a **Bearer access token captured from an authenticated portal session**, attached
as `Authorization: Bearer …`. Tokens last ~7 days (observed `iat`→`exp` =
604800s); on `401` the tool returns a clear "re-capture token" error.

**Getting the token** — two paths (`Config.from_env`: `TRACKMAN_TOKEN` env wins,
else the cached token):
- **Browser login (recommended)**: `trackman-mcp login` opens an isolated
  Playwright browser; the user signs in once; the token is captured from the
  GraphQL traffic and cached at `~/.trackman-mcp/token.json` (mode `0600`). The
  browser profile persists the session, so `trackman-mcp login --headless`
  refreshes silently with no re-login (cron-friendly). Code: `login.py`,
  `token_store.py`. Playwright is the optional `[login]` extra.
- **Manual**: set `TRACKMAN_TOKEN` from a captured portal session (`.env.example`).

Full detail and example GraphQL queries live in `docs/trackman-api.md`.

---

## Authentication & Secrets — Rules

Treat the user's Trackman login as sensitive. **Non-negotiable:**

- **Never commit credentials, tokens, cookies, or session dumps.** They go in
  `.env` (gitignored) or the OS keychain — never in source or fixtures.
- The MCP reads credentials from environment variables only
  (`TRACKMAN_USERNAME`, `TRACKMAN_PASSWORD`, or a captured `TRACKMAN_TOKEN`).
  See `.env.example` once Phase 1 starts.
- **Do not return raw auth material to the model.** Tools may say "authenticated
  as <name>" but must not echo passwords or bearer tokens.
- **Scrub fixtures.** Any recorded API response saved for tests must have
  tokens, cookies, emails, and player IDs redacted or faked.
- Cache sessions locally under a gitignored path (e.g. `.cache/`), not in the
  repo tree.
- This MCP is for a user accessing **their own** Trackman account. Don't build
  anything that scrapes or accesses other users' data.

---

## Project Structure (target, once Phase 1 begins)

```
trackman-mcp-client/
├── CLAUDE.md                      # this file
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docs/
│   └── trackman-api.md            # discovered endpoints (Phase 0 output)
├── src/
│   └── trackman_mcp/
│       ├── __init__.py
│       ├── server.py              # FastMCP app + tool registration
│       ├── client.py              # Trackman HTTP client + auth/session
│       ├── tools/                 # one module per tool group
│       └── models.py              # pydantic response models
├── tests/
│   ├── fixtures/                  # scrubbed recorded responses
│   └── test_tools.py
└── .claude/
    └── skills/                    # coaching brain (see below)
```

---

## Skills (the coaching brain)

Project-local skills live in `.claude/skills/`. Each has a `SKILL.md`.

- **`trackman-api-discovery`** — Phase 0. Reverse-engineer the portal's auth +
  data endpoints via the browser network panel; write them into
  `docs/trackman-api.md`.
- **`trackman-stats-analysis`** — Pull stats through the MCP and diagnose weak
  areas (dispersion, gapping, scoring trends, handicap movement). Analysis only.
- **`golf-coaching`** — Turn the diagnosis into specific, actionable practice:
  an example session, drills, and YouTube links. The coach persona.
- **`drill-library`** — Curated drills + vetted YouTube links, plus the
  procedure for live web-searching fresh videos matched to a weakness.
- **`trackman-session-analyzer`** — Ingests recent sessions, stores a per-session
  analysis (last 30) via the MCP, and returns a normalized summary of the latest
  session. **Context-forked / data-collection skill: must run in a subagent,
  never on the main thread.**

Typical flow: `authenticate` → `trackman-stats-analysis` (diagnose) →
`golf-coaching` (prescribe, pulling from `drill-library`). For per-session
ingest + a normalized latest-session report, dispatch `trackman-session-analyzer`
as a subagent.

---

## Conventions

- Keep tools small and single-purpose; one concern per module.
- Tools fail loudly with clear errors (auth expired, endpoint changed) rather
  than returning empty success.
- Prefer async `httpx`; don't block the event loop.
- When the API shape is uncertain, write a fixture-backed test from a real
  (scrubbed) response so regressions are caught when Trackman changes things.
- Coaching is **specific**: "10 balls, 7-iron, alternate target 140/160y, log
  carry dispersion" — never "practice your irons."

---

*Last updated: 2026-06-27 · Version 0.1.0 (scaffolding)*
