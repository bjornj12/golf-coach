# Publishing

`trackman-mcp` ships through three channels. The PyPI release is automated via
GitHub Actions + PyPI **Trusted Publishing** (OIDC) — no API token is ever
stored. You authorize the workflow once on PyPI, then every `vX.Y.Z` tag
publishes.

## One-time setup: authorize the GitHub workflow on PyPI

Because the project doesn't exist on PyPI yet, use the **pending publisher** flow:

1. Sign in to PyPI → <https://pypi.org/manage/account/publishing/>.
2. Under **Add a new pending publisher**, fill in exactly:

   | Field | Value |
   |-------|-------|
   | PyPI Project Name | `trackman-mcp` |
   | Owner | `bjornj12` |
   | Repository name | `trackman-mcp-client` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. Save. (Optional but recommended: in GitHub → Settings → Environments, create
   the `pypi` environment and add yourself as a required reviewer — that turns
   each release into a one-click manual approval before upload.)

That's all the PyPI side needs — no token to generate or paste.

## Cut a release

The tag must match `version` in `pyproject.toml` (the workflow enforces it).

```bash
# bump the version in pyproject.toml first if needed, commit it, then:
git tag v0.1.0
git push origin v0.1.0
```

The `Publish to PyPI` workflow then runs ruff + mypy + pytest, builds the sdist
and wheel, and uploads them to PyPI over OIDC. After it succeeds, anyone can:

```bash
uvx trackman-mcp            # or: uv tool install trackman-mcp / pipx install trackman-mcp
```

## Manual publish (fallback)

```bash
uv build
uv publish                 # prompts for a PyPI API token
```

## List on the MCP Registry (after the PyPI release)

`server.json` is already validated against the registry schema. Once the PyPI
package exists:

```bash
# install the publisher CLI (see github.com/modelcontextprotocol/registry)
mcp-publisher login github      # authorizes the io.github.bjornj12/* namespace
mcp-publisher publish           # reads ./server.json
```

Bump the `version` in **both** `pyproject.toml` and `server.json` for each
release so the registry entry tracks the PyPI package.

## Claude Code plugin

No release step — the plugin builds from the repo via `uvx --from`, so it tracks
`main`. Bump `version` in `.claude-plugin/plugin.json` (and `marketplace.json`)
when you want to signal a new plugin version to users.
