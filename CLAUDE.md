# Golf Coach

## Project Overview

**Name**: Golf Coach (product name). The technical ids stay `golf-coach` (MCP
server / plugin) and `golf-coach` (published package / module `golf_coach`) —
these are deliberately NOT renamed, so existing installs and the registry entry
keep working. "Trackman" references to the *data source* also stay (it genuinely
connects to Trackman).

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

**Note on delivery (not a boundary break):** the server *serves* the skill
markdown as **MCP prompts** (see `prompts.py`) so the coaching brain is available
in any MCP client, not only the Claude Code plugin. This is transport, not logic:
the server still computes no verdicts — it hands Claude the same skill text the
plugin would. The single source of truth stays in `skills/`.

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

The surface is **8 tools** (the 7 data/coaching tools below, plus `setup`).
`trackman` and `gamebook` each take an `action` parameter so the model picks one
tool with a mode rather than many near-duplicate tools.

`setup` is a one-call onboarding tool: it returns an always-on coach
`system_prompt` (to paste into a Project), the coaching `skills` as upload-ready
files, and per-client instructions. A matching `setup` MCP prompt drives it.
(Onboarding content only — still no computed verdicts; see the boundary note.)

| Tool | Backing (under `me`) | Returns |
|------|----------------------|---------|
| `auth(action: status\|login, open_browser?, source?)` | OIDC token capture / browser | `status`: validate the current token, report who you're signed in as (never echoes it). `login`: (re)authenticate — silent refresh first, else open a browser to sign in. `source` picks which data source to authenticate (default `trackman`; only Trackman needs auth — other sources, e.g. GameBook, are local). |
| `trackman(action: profile\|handicap\|sessions\|session\|rounds\|clubs\|summary, …)` | `profile`/`hcp`/`activities`/`scorecards`/`equipment`/`activitySummary` | Raw Trackman reads, one action each: `profile` — identity + current **handicap** (`hcp.currentHcp`); `handicap` — `hcp.playerHistory` record history; `sessions` — `activities(kinds,timeFrom,timeTo,skip,take)` list; `session` (needs `activity_id`) — one activity in full, **shot-level launch metrics** (ball/club speed, smash, launch, spin, carry, side, curve, landing angle, ~80 fields) or round detail; `rounds` — `scorecards(skip,take,completed)` per-hole scores, FIR/GIR, putts, `stat`; `clubs` — `equipment.clubs.findMyDistance` per-club **gapping** (carry/total, std-dev, dispersion); `summary` — `activitySummary(timeFrom,timeTo)` counts per activity kind. |
| `gamebook(action: save\|list\|get\|compare, round?, round_id?)` | local (deterministic) | On-course rounds ingested from Golf GameBook screenshots (save/list/get/compare), rolling last 5, coverage-aware — only score-per-hole is trusted. |
| `synthesize()` | local (deterministic, cross-source) | Runs each registered source's per-source expert analyzer (Trackman + GameBook) over its normalized data and aligns the resulting `Finding`s by skill area — cross-source deltas, coverage, and context notes (controlled/flat-lie vs on-course/variable). Still no verdicts; see "Sources & normalization" below. |
| `session_analysis(action, activity_id?)` | see below | Per-session analysis cluster. |
| `training_plan(action, …)` | see below | The coach's memory cluster. |
| `build_visualization(data)` | local (deterministic) | A self-contained animated HTML artifact of a diagnosis. |

### Sources & normalization

The multi-source backend behind `trackman`/`gamebook`/`synthesize` is pluggable:
each data source (Trackman, GameBook) implements the `Source` protocol
(`sources/base.py`), registers into `sources/registry.py`, and normalizes its own
raw shape into the shared model (`model.py`: `Session`, `Round`, `Profile`,
`Handicap`, `ClubGapping`), each tagged with a `SourceContext` (`controlled`/
`flat` lie + no conditions for Trackman, `on_course`/`variable` lie + real
conditions for GameBook). Each source also has a **per-source expert analyzer**
(`sources/*/analyzer.py`) that turns its normalized model objects into `Finding`s
— factual measurements (skill area, metric, value, coverage, direction), no
coaching opinions. `synthesis.synthesize()` (the `synthesize` tool) runs both
analyzers and calls `synthesis.align` to group `Finding`s by skill area, surface
cross-source deltas, and note the context each side was captured under — it
renders **no verdict**. The coach skills call `synthesize` to reason over the
aligned, cross-source view instead of juggling `trackman` and `gamebook` output
by hand.

### Session-analysis tools (local store, deterministic analytics)

These persist and serve a per-session *analysis*. The analytics are
**deterministic** (in `analysis.py`) — classification and measurement, not
coaching. Coaching narrative still lives in the skills. The store is JSON at
`~/.golf-coach/session-analyses.json`, capped at the **last 30**, latest first.

One tool, `session_analysis(action, activity_id?)`:

| action | Does |
|--------|------|
| `analyze` (needs `activity_id`) | Fetch a session, classify (warm-up vs serious practice vs game), compute metrics + course difficulty, normalize vs previously stored sessions, flag used-vs-available clubs, store, return the record. |
| `list` | Index of stored analyses (id, time, kind, category, seriousness, summary), latest first. |
| `get` (needs `activity_id`) | One full stored analysis record. |

Classification (see `analysis.py`): a session is a **warm-up** (not an
improvement attempt) if under ~8 strokes or ~5 minutes — even for an otherwise
"serious" kind; **serious practice** if it has real volume/duration/club variety
or is a focused kind (shot analysis, find-my-distance, sim/virtual-range, etc.);
**game** for played rounds. Normalization is always against sessions
*chronologically before* the one analyzed. Units are metric (m/s, meters).

### Training-plan tools (the coach's memory)

The coach saves prescribed practice sessions so they can be recalled later
("what's today's training?"). Store is JSON at `~/.golf-coach/training-plans.json`
(`training_store.py`), an ordered queue capped at the most recent 50.

One tool, `training_plan(action, plan?, plan_id?, status?, activity_id?, result_session_id?)`:

| action | Does |
|--------|------|
| `save` (needs `plan`) | Persist a prescribed plan (title, focus, diagnosis, blocks, targets, `target_specs`) to the pending queue. |
| `next` | Return the next pending plan — the answer to "what's today's training?". |
| `list` (optional `status`) | List plans (oldest→newest), optional `pending`/`done` filter. |
| `done` (needs `plan_id`) | Complete a plan; the next pending one becomes current. |
| `verify` (needs `plan_id`, optional `activity_id`) | Grade a recent session's real shot metrics against the plan's structured `target_specs` (e.g. driver `clubPath` between -1 and +2). Returns per-target session-mean vs target, `all_met`, and a recommendation. |

Plans carry **`target_specs`** — machine-readable targets (`{metric, club?, op,
value|low/high}`, ops `< <= > >= between abs< abs<=`) graded deterministically by
`analysis.verify_targets` against a session's `Measurement` fields (queried via
`SESSION_MEASUREMENTS`, which includes face/path/spin).

`golf-coaching` writes here (Prescribe → `training_plan(action="save")` with
`target_specs`) and reads here (Recall → `training_plan(action="next")` →
`training_plan(action="verify")`, then `training_plan(action="done")` once every
target is met).

### Gamebook tool (local store, deterministic)

The `gamebook-screenshot-analysis` skill extracts an on-course round from Golf
GameBook screenshots and saves it here so the coach can track scoring across
recent rounds. Store is JSON at `~/.golf-coach/gamebook-rounds.json`
(`gamebook_store.py`), a rolling window of the **last 5** rounds, keyed by `id`.

One tool, `gamebook(action, round?, round_id?)`:

| action | Does |
|--------|------|
| `save` (needs `round`) | Runs a self-check (hole sums vs gross/par) on a coverage-aware record, refuses inconsistent reads, computes the `scoring` block, stores it (last 5), returns the stored record. |
| `list` | Index of stored rounds (id, date, gross, net, to_par, coverage), newest first. |
| `get` (needs `round_id`) | One full stored round. |
| `compare` (optional `round_id`, default latest) | Deterministic scoring + coverage-respecting deltas vs the rounds before it; the coach narrates progress from it. |

Only score-per-hole is reliably tracked by GameBook; every other dimension
(putts, fairways, GIR, chips, bunkers, penalties) carries a `coverage` flag
(`full`/`partial`/`none`), and analysis never treats an untracked stat as zero.

**Auth reality**: the web portal uses a *confidential* OIDC client (backend-for-
frontend), so the MCP cannot run the OAuth exchange itself. It authenticates with
a **Bearer access token captured from an authenticated portal session**, attached
as `Authorization: Bearer …`. Tokens last ~7 days (observed `iat`→`exp` =
604800s); on `401` the tool returns a clear "re-capture token" error.

**Recovery when expired**: data tools auto-retry once after a silent headless
refresh (`_try_silent_refresh`), so a stale 7-day token renews invisibly while the
browser session is still valid. When the browser session itself expires, tools
return a clear "session expired — use auth(action='login')" message, and that
action opens a sign-in window (falling back from a fast silent attempt).

**Getting the token** — two paths (`Config.from_env`: `TRACKMAN_TOKEN` env wins,
else the cached token):
- **Browser login (recommended)**: `golf-coach login` opens an isolated
  Playwright browser; the user signs in once; the token is captured from the
  GraphQL traffic and cached at `~/.golf-coach/token.json` (mode `0600`). The
  browser profile persists the session, so `golf-coach login --headless`
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
golf-coach/
├── CLAUDE.md                      # this file
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docs/
│   └── trackman-api.md            # discovered endpoints (Phase 0 output)
├── src/
│   └── golf_coach/
│       ├── __init__.py
│       ├── server.py              # FastMCP app + tool registration
│       ├── client.py              # Trackman HTTP client + auth/session
│       ├── tools/                 # one module per tool group
│       └── models.py              # pydantic response models
├── tests/
│   ├── fixtures/                  # scrubbed recorded responses
│   └── test_tools.py
├── .claude-plugin/               # Claude Code plugin + marketplace manifests
├── .mcp.json                     # MCP server declaration (for the plugin)
├── server.json                   # MCP Registry manifest
└── skills/                       # coaching brain (see below); plugin-root layout
```

---

## Skills (the coaching brain)

Skills live in `skills/` (the Claude Code plugin-root layout, so they ship with
the plugin). Each has a `SKILL.md`. They are **also served as MCP prompts** by
the server (`prompts.py`), so any MCP client (e.g. Claude Desktop) can use them —
all except the dev-only `trackman-api-discovery`.

- **`trackman-api-discovery`** — Phase 0. Reverse-engineer the portal's auth +
  data endpoints via the browser network panel; write them into
  `docs/trackman-api.md`.
- **`trackman-stats-analysis`** — Pull stats through the MCP and diagnose weak
  areas (dispersion, gapping, scoring trends, handicap movement). Analysis only.
- **`golf-coaching`** — Turn the diagnosis into specific, actionable practice.
  The coach persona — **visual-first** (visualizes by default), includes an
  at-home/no-ball option, and **grades progress proactively** against the saved
  plan.
- **`drill-library`** — Curated drills + vetted YouTube links (incl. an
  **at-home / no-ball** set), plus the live-search procedure for fresh videos.
- **`golf-practice-at-home`** — A **thin pointer** for at-home / no-ball
  practice (yard/living room, just a club): routes to `golf-coaching`'s at-home
  mode and `drill-library`'s no-ball set to build a short daily routine, animated
  per drill, saved as a training plan. The routine-building logic lives in those
  skills, not here — this skill only keeps the at-home path from drifting.
- **`at-home-practice-feedback`** — A single **mobile-first drill card** for a
  diagnosed fault: fault → root cause → drill → feedback method (prop + cue) →
  equipment budget tier → validation checkpoint → video. Optimized for reading
  on a phone between reps (deliberately no animations — an explicit exception
  to the visual-first default). Drills/videos come from `drill-library`; for a
  full daily routine use `golf-practice-at-home` instead.
- **`trackman-session-analyzer`** — Ingests recent sessions, stores a per-session
  analysis (last 30) via the MCP, and returns a normalized summary of the latest
  session. **Context-forked / data-collection skill: must run in a subagent,
  never on the main thread.**
- **`gamebook-screenshot-analysis`** — Ingests Golf GameBook round screenshots
  into a coverage-aware round record via `gamebook` (rolling last 5), for
  scoring-led progress that feeds the coach. **Context-forked / data-collection
  skill: must run in a subagent, never on the main thread.**

Typical flow: `auth(action="status")` → `trackman-stats-analysis` (diagnose,
pulling `trackman`/`gamebook` data through `synthesize` for the cross-source
view) → `golf-coaching` (prescribe, pulling from `drill-library`). For
per-session ingest + a normalized latest-session report, dispatch
`trackman-session-analyzer` as a subagent (in Claude Code; in other clients
invoke the prompt directly). For on-course rounds from GameBook screenshots,
dispatch `gamebook-screenshot-analysis` the same way; it feeds
`golf-coaching`'s scoring-led progress narrative.

---

## Conventions

- Keep tools small and single-purpose; one concern per module.
- Tools fail loudly with clear errors (auth expired, endpoint changed) rather
  than returning empty success.
- Prefer async `httpx`; don't block the event loop.
- When the API shape is uncertain, write a fixture-backed test from a real
  (scrubbed) response so regressions are caught when Trackman changes things.
- Coaching is **specific**: "10 balls, 7-iron, alternate target 130/150 m, log
  carry dispersion" — never "practice your irons."

---

*Last updated: 2026-06-27 · Version 0.1.0 (scaffolding)*
