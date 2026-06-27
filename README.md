# trackman-mcp-client

An MCP server that logs into **Trackman Golf** with your own account and exposes
your stats — course rounds, practice sessions, shot-level launch-monitor data,
club gapping, and handicap — as MCP tools. On top of that, a set of Claude
**skills** act as your golf coach: they diagnose your weaknesses and hand you a
specific practice plan with drills and YouTube links for your next session.

## Design boundary

- **MCP server** = raw data fetch + auth only. No opinions.
- **Skills** = all the coaching (analysis, plans, drills).

See [`CLAUDE.md`](./CLAUDE.md) for the full architecture, the build phases, and
the auth/secret-handling rules.

## Status

- **Phase 0 — API discovery: done.** Trackman's private golf API is mapped in
  [`docs/trackman-api.md`](./docs/trackman-api.md) (GraphQL at
  `api.trackmangolf.com/graphql`, all player data under the `me` root).
- **Phase 1 — MCP server: done.** Python/FastMCP server with 9 tools, all
  queries schema-validated against the live API; unit tests pass.
- **Phase 2 — live validation:** run `scripts/validate.py` with your own token
  (see below).

## Setup

```bash
uv venv && uv pip install -e '.[dev]'   # install
cp .env.example .env                     # then paste your token into .env
```

**Get a token** (the portal uses a server-side OAuth client, so the MCP can't
log in for you — it uses a Bearer token from your session):
1. Log in at https://portal.trackmangolf.com
2. DevTools → Network → filter `graphql` → click a request to
   `api.trackmangolf.com/graphql`
3. Copy the `Authorization` header value into `TRACKMAN_TOKEN` (the part after
   `Bearer `; the leading `Bearer ` is tolerated too). Tokens last ~7 days.

## Run

```bash
trackman-mcp                                   # start the MCP (stdio)
TRACKMAN_TOKEN=… uv run python scripts/validate.py   # validate stats coverage
```

## MCP tools

`authenticate` · `get_profile` · `get_handicap` · `list_sessions` ·
`get_session` · `get_course_rounds` · `get_club_stats` · `get_shot_data` ·
`get_activity_summary`. All return raw data; see [`CLAUDE.md`](./CLAUDE.md).

## Skills

- `trackman-api-discovery` — reverse-engineer the portal's API (Phase 0)
- `trackman-stats-analysis` — diagnose weaknesses from the data
- `golf-coaching` — turn the diagnosis into an actionable practice plan
- `drill-library` — curated drills + vetted YouTube links, plus live search
