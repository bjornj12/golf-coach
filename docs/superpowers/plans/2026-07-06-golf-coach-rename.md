# Golf Coach — Stage 1: `golf-coach` Rename Sweep — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the product ids from `trackman-*` to `golf-coach` end-to-end (module, package, CLI, MCP server / plugin / registry, cache dir) while keeping every `TRACKMAN_*` credential and the Trackman client/API code, with the full test suite still green.

**Architecture:** Pure mechanical rename. `git mv` the module directory, run ordered case-sensitive `sed` passes over tracked text files, hand-fix the two files that need judgment (`pyproject.toml` entry point, `token_store.py` cache dir), regenerate the lockfile, and verify against the existing 165-test suite. This is the first of several staged plans that all land on the `rename-to-golf-coach` branch → one PR. The multi-source model/sources/analyzers/normalizer come in later stages.

**Tech Stack:** Python 3.12+, hatchling, `uv`, pytest, ruff.

## Global Constraints

- Python 3.12+. Tests: `uv run --extra dev pytest`. Lint: `uv run ruff check src tests`.
- **KEEP unchanged (data-source-specific — renaming misleads):** `TRACKMAN_TOKEN`, `TRACKMAN_USERNAME`, `TRACKMAN_PASSWORD`, `TRACKMAN_GRAPHQL_ENDPOINT`, `TRACKMAN_TIMEOUT_SECONDS`, all Trackman client/GraphQL code, and prose/brand references to "Trackman" (capitalized) and the Trackman data source. Tool names (`auth`, `gamebook_round`, `session_analysis`, …) are NOT touched in this stage — the tool-surface reorg is a later stage.
- **RENAME:** module `trackman_mcp`→`golf_coach`; package/CLI/PyPI id `trackman-mcp`→`golf-coach`; server/plugin/mcpb/`.mcp.json` id `trackman-golf`→`golf-coach`; registry `io.github.bjornj12/trackman-mcp`→`io.github.bjornj12/golf-coach`; repo URL `bjornj12/trackman-mcp-client`→`bjornj12/golf-coach`; cache dir default `~/.trackman-mcp`→`~/.golf-coach`; cache-dir env `TRACKMAN_CACHE_DIR`→`GOLF_COACH_CACHE_DIR`.
- **Sed ordering is load-bearing** (substring safety): `trackman-mcp-client` → then `trackman-golf` → then `trackman_mcp` → then `trackman-mcp` → then `TRACKMAN_CACHE_DIR`. Doing `trackman-mcp` before `trackman-mcp-client` would corrupt the repo URL to `golf-coach-client`.
- The suite must stay green (165 tests) and ruff clean after the rename — that IS the test.

---

### Task 1: Rename module + all ids to `golf-coach`

**Files:**
- Move: `src/trackman_mcp/` → `src/golf_coach/` (whole package dir)
- Modify (via sed): all tracked `*.py`, `*.toml`, `*.json`, `*.md`, `.mcp.json` except `uv.lock`
- Hand-verify: `pyproject.toml`, `src/golf_coach/token_store.py`
- Regenerate: `uv.lock`

**Interfaces:**
- Produces: the package importable as `golf_coach` (`from golf_coach import server`), CLI `golf-coach` (entry `golf_coach.server:main`), cache dir helper reading `GOLF_COACH_CACHE_DIR` defaulting to `~/.golf-coach`.
- Consumes: nothing (first task).

- [ ] **Step 1: Move the package directory**

```bash
cd /Users/bjorn/bjorn/workspace/golf-coach   # repo now renamed; path may still be .../trackman-mcp-client locally
git mv src/trackman_mcp src/golf_coach
```
(If the local checkout directory is still named `trackman-mcp-client`, that's fine — only the module path matters. Use whatever the repo root is.)

- [ ] **Step 2: Run the ordered rename passes over tracked text files**

```bash
FILES=$(git ls-files '*.py' '*.toml' '*.json' '*.md' '.mcp.json' | grep -v '^uv.lock$')
# Order matters — longest/most-specific first to avoid substring corruption.
perl -pi -e 's/trackman-mcp-client/golf-coach/g' $FILES     # repo URL first
perl -pi -e 's/trackman-golf/golf-coach/g'        $FILES     # server/plugin/mcpb ids
perl -pi -e 's/trackman_mcp/golf_coach/g'         $FILES     # python module (underscore)
perl -pi -e 's/trackman-mcp/golf-coach/g'         $FILES     # package/CLI/pypi id + ~/.trackman-mcp path
perl -pi -e 's/TRACKMAN_CACHE_DIR/GOLF_COACH_CACHE_DIR/g' $FILES   # app-level cache env (uppercase, targeted)
```
Lowercase passes never touch the uppercase creds (`TRACKMAN_TOKEN`, etc.), and `TRACKMAN_CACHE_DIR` is renamed explicitly.

- [ ] **Step 3: Verify the credentials + brand refs survived, and no stray old ids remain**

```bash
# These MUST still be present (kept):
grep -rq 'TRACKMAN_TOKEN' src/golf_coach && echo "OK TRACKMAN_TOKEN kept"
grep -rq 'TRACKMAN_GRAPHQL_ENDPOINT' src/golf_coach && echo "OK endpoint kept"
# These must be GONE (renamed) outside uv.lock:
! git ls-files '*.py' '*.toml' '*.json' '*.md' | grep -v uv.lock | xargs grep -l 'trackman_mcp\|trackman-golf\|trackman-mcp' 2>/dev/null && echo "OK no stray old ids"
```
Expected: `OK TRACKMAN_TOKEN kept`, `OK endpoint kept`, `OK no stray old ids`. If the last line prints file paths, inspect them — they may be legitimate capital-"Trackman" brand refs (fine) or a missed spot (fix).

- [ ] **Step 4: Hand-check `pyproject.toml`**

Confirm these now read exactly (the seds produce them, but verify):
```toml
name = "golf-coach"
[project.scripts]
golf-coach = "golf_coach.server:main"
[tool.hatch.build.targets.wheel]
packages = ["src/golf_coach"]
[tool.hatch.build.targets.wheel.force-include]
"skills" = "golf_coach/skills"
```
`keywords` may keep `"trackman"` (it genuinely connects to Trackman) — leave as-is.

- [ ] **Step 5: Hand-check `src/golf_coach/token_store.py` cache dir**

Confirm the cache-dir helper now reads:
```python
override = os.environ.get("GOLF_COACH_CACHE_DIR")
base = Path(override) if override else Path.home() / ".golf-coach"
```
and its docstring says "Override via `GOLF_COACH_CACHE_DIR`".

- [ ] **Step 6: Regenerate the lockfile for the new package name**

```bash
uv lock
```
Expected: `uv.lock` updates the root package entry from `trackman-mcp` to `golf-coach`; no dependency changes.

- [ ] **Step 7: Run the full suite + lint (this is the test for the rename)**

```bash
uv run --extra dev pytest -q
uv run ruff check src tests
```
Expected: **165 passed**; ruff **All checks passed!**. Tests that `monkeypatch.setenv("GOLF_COACH_CACHE_DIR", …)` and `from golf_coach import …` now resolve. If any test still references `trackman_mcp`/`TRACKMAN_CACHE_DIR`, the sed missed it — fix and re-run.

- [ ] **Step 8: Verify the CLI entry + import resolve**

```bash
uv run python -c "import golf_coach.server as s; import asyncio; print('tools:', len(asyncio.run(s.mcp.list_tools())))"
uv run golf-coach --help >/dev/null 2>&1 && echo "OK golf-coach entry" || echo "check entry point"
```
Expected: prints a tool count (13); `OK golf-coach entry` (or the `--help` path exits cleanly).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "rename: trackman-mcp -> golf-coach (module, ids, cache dir; keep TRACKMAN_* creds)"
```

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-07-06-multi-source-normalization-design.md`, "The rename (folded in)" table):
- Package/module/CLI/server/plugin/registry/repo-URL → `golf-coach` → Task 1 Steps 1–2, 4.
- Cache dir `~/.golf-coach` + `GOLF_COACH_CACHE_DIR` → Steps 2, 5.
- Keep `TRACKMAN_*` credentials + endpoint + client code → Global Constraints + Step 3 verification.
- Suite green + ruff clean → Steps 7–8.
- (The display rebrand "Golf Coach" in README/CLAUDE/manifests already landed on this branch — untouched by the lowercase seds.)

**Placeholder scan:** none — every step is an exact command with expected output.

**Ordering hazard:** the sed order (client → golf → _mcp → -mcp → CACHE_DIR) is called out explicitly in Global Constraints and Step 2; running `-mcp` before `-mcp-client` is the one way to corrupt the repo URL and is guarded against.

## Not in this stage (later plans, same branch → same PR)
model.py · sources/ + Source protocol + registry · Trackman/GameBook adapters · per-source analyzers · synthesis.py · tool-surface reorg (`trackman(action)`/`gamebook(action)`/`synthesize`) · skills + system-prompt updates. Each ships as its own staged plan.
