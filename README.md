<!-- mcp-name: io.github.bjornj12/trackman-mcp -->

# trackman-mcp

An MCP server that logs into **Trackman Golf** with your own account and exposes
your stats — course rounds, practice sessions, shot-level launch-monitor data,
club gapping, and handicap — as MCP tools. On top of that, a set of Claude
**skills** act as your golf coach: they diagnose your weaknesses and hand you a
specific practice plan with drills and YouTube links for your next session.

> [!IMPORTANT]
> **Unofficial.** This project is not affiliated with or endorsed by Trackman.
> It talks to Trackman's **private** web API using a token from *your own*
> authenticated session, and automates a browser login on your behalf. This may
> conflict with Trackman's Terms of Service — use it on your own account, at your
> own risk. Never use it to access anyone else's data.

## Design boundary

- **MCP server** = raw data fetch + auth only. No opinions.
- **Skills** = all the coaching (analysis, plans, drills).

See [`CLAUDE.md`](./CLAUDE.md) for the full architecture and auth/secret rules.

## Install

Pick the path for how you use Claude. Each takes about two minutes, then do the
one-time [Authentication](#authentication-one-time) step.

### 🖥️ Claude Desktop — one-click (recommended)

1. **Download [`trackman-golf.mcpb`](https://github.com/bjornj12/trackman-mcp-client/releases/latest/download/trackman-golf.mcpb)** (from the [latest release](https://github.com/bjornj12/trackman-mcp-client/releases/latest)).
2. Open **Claude Desktop → Settings → Extensions** and drag the file in (or just
   double-click the downloaded `.mcpb`). Click **Install**.
3. In the install dialog you can paste a Trackman token now, or leave it blank
   and sign in via the terminal once — see [Authentication](#authentication-one-time).
4. Ask Claude: *"What's my Trackman handicap?"*

Claude Desktop runs everything for you — it manages Python and dependencies via
`uv`, so there's **nothing to install** and no config file to edit. (You may see
a note that the extension is unsigned / from outside the directory — that's
expected for one installed from a file.)

### ⌨️ Claude Code — plugin (server **and** coaching skills)

```text
/plugin marketplace add bjornj12/trackman-mcp-client
/plugin install trackman-golf@trackman-golf
```

Installs the MCP server (run via `uvx`) and all six coaching skills.

### 🔌 Other MCP clients (or Claude Desktop without the extension)

Requires [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
Add this to your client's MCP config:

```json
{
  "mcpServers": {
    "trackman-golf": { "command": "uvx", "args": ["trackman-mcp"] }
  }
}
```

> For **Claude Desktop's manual config** (`~/Library/Application Support/Claude/claude_desktop_config.json`
> on macOS), use the **absolute path** to `uvx` — e.g. `/opt/homebrew/bin/uvx` —
> because the app doesn't inherit your shell `PATH`. The `.mcpb` install above
> avoids this entirely.

## Authentication (one-time)

However you installed it, the server needs a token for **your** Trackman account.
Trackman has no public login API, so you capture a token from a real signed-in
session once; it's then cached locally and can refresh itself. Your password is
never seen or stored by the tool, and nothing leaves your machine.

### Recommended — sign in once (stays fresh on its own)

```bash
uv tool install "trackman-mcp[login]"
trackman-mcp login            # opens a browser; sign in with your Trackman email + password
```

This caches the token at `~/.trackman-mcp/token.json` (mode `0600`) — **every**
install (Desktop, Code, CLI) reads it. Keep it fresh automatically (tokens last
~7 days):

```bash
scripts/install-refresh-schedule.sh     # twice-weekly headless refresh (macOS launchd / Linux cron)
# …or manually any time:
trackman-mcp login --headless
```

No Google Chrome? The flow falls back to Playwright's bundled Chromium — run
`playwright install chromium` once. Windows: schedule `scripts/refresh-token.sh`
via Task Scheduler.

### No-terminal alternative — paste a token

`portal.trackmangolf.com` → DevTools → **Network** → click a `graphql` request →
copy the `Authorization: Bearer …` value, then:

- **Desktop extension:** paste it into the **Trackman token** field of the install dialog.
- **Manual config:** add `"env": { "TRACKMAN_TOKEN": "eyJ…" }` to the server entry.

Heads-up: tokens expire after **~7 days**, so you'll re-paste weekly — the
sign-in-once path above avoids that.

### Verify it worked

Ask Claude *"Am I signed in to Trackman?"* — it runs the `authenticate` tool and
replies with your name (never the token).

## MCP tools

All tools return **raw data only**; the skills interpret it.

**Data (read-only):** `authenticate` · `get_profile` · `get_handicap` ·
`list_sessions` · `get_session` · `get_course_rounds` · `get_club_stats` ·
`get_shot_data` · `get_activity_summary`

**Auth:** `login`

**Session analysis (local store, deterministic):** `analyze_and_store_session` ·
`list_session_analyses` · `get_session_analysis`

**Training-plan memory:** `save_training_plan` · `get_next_training` ·
`list_training_plans` · `mark_training_done` · `verify_training_progress`

**Visualization:** `build_visualization` (self-contained animated HTML artifact)

See [`CLAUDE.md`](./CLAUDE.md) for the full table and backing GraphQL.

## Skills

Bundled under [`skills/`](./skills) (installed automatically with the plugin):

- `trackman-api-discovery` — reverse-engineer the portal's API (Phase 0)
- `trackman-stats-analysis` — diagnose weaknesses from the data
- `golf-coaching` — turn the diagnosis into an actionable practice plan
- `drill-library` — curated drills + vetted YouTube links, plus live search
- `trackman-session-analyzer` — ingest + normalize recent sessions (runs forked)
- `trackman-visualizer` — animate a diagnosis as an HTML artifact

## Development

```bash
uv venv && uv pip install -e '.[login,dev]'   # [login] = Playwright, [dev] = test/lint tools

trackman-mcp                       # run the MCP server (stdio)
uv run python scripts/validate.py  # sanity-check stats coverage with your token

uv run pytest        # tests
uv run ruff check    # lint
uv run mypy          # type-check
```

Releasing (PyPI + MCP Registry + the Desktop `.mcpb`) is one command —
`scripts/release.sh patch` — see [`PUBLISHING.md`](./PUBLISHING.md).

## License

[MIT](./LICENSE)
