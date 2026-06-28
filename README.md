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
uv venv && uv pip install -e '.[login]'   # install (the [login] extra adds Playwright)
```

### Sign in (recommended: browser login)

```bash
trackman-mcp login            # opens a browser; sign in once with email+password
```

A browser window opens (an **isolated** profile, not your normal Chrome). Sign
in once; the MCP captures the access token and caches it at
`~/.trackman-mcp/token.json` (mode `0600`). The session persists, so to refresh
later (tokens last ~7 days) just run:

```bash
trackman-mcp login --headless   # silent refresh, no window
```

The MCP loads the cached token automatically — no env var needed.

### Keep it fresh automatically (optional)

Schedule the headless refresh so you never think about tokens (twice weekly,
margin on the ~7-day token). Portable — paths are derived at install time:

```bash
scripts/install-refresh-schedule.sh dry-run    # preview what gets installed
scripts/install-refresh-schedule.sh            # install (macOS launchd / Linux cron)
scripts/install-refresh-schedule.sh uninstall  # remove
```

Run a headed `trackman-mcp login` **once** first to establish the browser
session; the schedule then refreshes it silently. If the saved session itself
expires, the refresh logs a clear message (`~/.trackman-mcp/refresh.log`) and you
just run a headed login again. Windows: schedule `scripts/refresh-token.sh` via
Task Scheduler.

### Alternative: paste a token manually

If you'd rather not use the browser flow, set `TRACKMAN_TOKEN` (it overrides the
cache). Get it from portal.trackmangolf.com → DevTools → Network → a `graphql`
request → the `Authorization` header value. See `.env.example`.

## Run

```bash
trackman-mcp                              # start the MCP (stdio)
uv run python scripts/validate.py         # validate stats coverage (uses cached token)
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
