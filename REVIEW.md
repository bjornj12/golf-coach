# Trackman MCP Server — Final Review Report

## 1. Executive summary

The server is a clean, well-scoped implementation of the "fetch-only MCP, judgment-in-skills" boundary, and it largely holds that line. **No critical or data-destroying-by-default defects were found.** Security is *mostly* sound for the intended single-user case — the bearer-token handling shows clear intent (0600 chmod, no token echo, synthetic test fixtures, clean secret hygiene) — but there are real local-multi-user exposure gaps (token written before chmod, cache dir not 0700, unprotected personal-data stores) and a genuine unescaped-injection bug in the HTML visualizer. Correctness has several **medium** accuracy bugs that silently mislead the coach: the swing-path diagram is mirrored for right-handers (the default), range sessions can never be graded, and sessions with missing timestamps get misclassified as warm-ups. Performance is fine for an interactive single-user stdio server; the only notable cost is a serial fan-out in `verify_training_progress`. **It is not ready for public/plugin distribution as-is** — but most distribution findings are *contingent*: nothing in CLAUDE.md/README states publishing or plugin packaging is a goal, so treat that whole dimension as a release-readiness checklist to action only if/when you decide to ship, not as defects in the current personal-use tool. The one runtime-protocol bug worth fixing regardless is `print()` to stdout in the login/refresh path, which can corrupt the JSON-RPC stream.

A note on overlap: several findings describe the same root cause from different dimensions (connection reuse, the verify fan-out, the token-perm race). They are consolidated below with all their stable ids retained.

---

## 2. Findings by severity

### Critical
None.

### High

**`pkg-no-server-json`** — No `server.json`; cannot publish to the MCP Registry · `MISSING:server.json` · *distribution*
- Impact: The server cannot be listed on `registry.modelcontextprotocol.io`. This is a hard blocker **only if** registry listing is a goal — which is not stated anywhere in the repo. Also requires the package to be on PyPI first (it is not).
- Fix: `mcp-publisher init`, then set `name` to `io.github.bjornj12/trackman-mcp`, a `packages[]` entry (`registryType: pypi`, `runtimeHint: uvx`, `transport:{type:stdio}`, `environmentVariables[TRACKMAN_TOKEN]{isSecret:true}`), and add the `<!-- mcp-name: ... -->` marker to README. Pull the live `$schema` date rather than hardcoding.

### Medium

**`sec-viz-html-xss`** — HTML/JS injection in generated visualization artifact · `src/trackman_mcp/visualize.py:260-266` (build_html), `:36-100` (template), `:240-249` (client JS) · *security*
- Impact: `build_html` does raw string substitution with no escaping. `title`/`subtitle`/`diagnosis` land directly in the HTML body (`<h1>__TITLE__</h1>`), so `title='<img src=x onerror=...>'` executes on load with no breakout trick. `json.dumps(data)` is injected into `<script>` and does not escape `</script>`, allowing script-context breakout. Client JS writes `${t.label}`/`${b.name}` via `innerHTML` and builds `<a href="${b.link}">` with no scheme check. Data flows from model-generated coaching text and partly venue-controlled Trackman fields (course/club display names). Self-contained sandboxed artifact caps blast radius.
- Fix: `html.escape()` on `title`/`subtitle`/`diagnosis`; for the embedded JSON escape the breakout sequence (`json.dumps(...).replace('</', '<\\/')`); in client JS build DOM via `textContent` and whitelist `link` to `http(s)` only.

**`sec-token-write-race-dir-perms` / `token-file-perm-race`** — Token written world-readable before chmod; cache dir and data stores not restricted · `src/trackman_mcp/token_store.py:76-79` (save_token), `:23-39` (cache_dir/browser_profile_dir) · *security / python*
- Impact: `save_token` does `path.write_text(...)` then `os.chmod(0o600)` — on first creation the token is briefly group/world-readable (note: only on first write; `write_text` truncates in place thereafter). The cache dir is created with default `mkdir` (≈0755), and the long-lived Playwright `browser-profile/` cookies (which mint fresh 7-day tokens) plus `session-analyses.json`/`training-plans.json` live there unprotected — the cookies are arguably more sensitive than the token. Requires a multi-user host to exploit.
- Fix: Create the token file atomically with restrictive mode (`os.open(path, O_WRONLY|O_CREAT|O_TRUNC, 0o600)`, or temp-file at 0600 + `os.replace`). Create cache/profile dirs with mode `0o700` and enforce on access.

**`mcp-stdout-print-corrupts-stdio`** — `print()` in login/refresh path writes to stdout and can corrupt the JSON-RPC stream · `src/trackman_mcp/login.py:50,116` · *mcp*
- Impact: `capture_token()` prints to stdout. It is reachable at server runtime via the `login` tool (`server.py:121,132`) and via `_try_silent_refresh` (`server.py:47`), which `_run` invokes on every data tool's auth-expiry retry (`server.py:67`). A stdio MCP server must emit only JSON-RPC on stdout; on the routine 7-day token expiry path these prints inject non-JSON bytes and can break client parsing. (The CLI prints in `_login_cmd` are fine — they run before `mcp.run()`.)
- Fix: Route all human-facing diagnostics in `login.py` to stderr (`file=sys.stderr` or a stderr logging handler). Never write to stdout from code reachable by a tool call.

**`store-non-atomic-writes`** — JSON stores truncate-in-place; an interrupted write silently wipes the coach's memory · `training_store.py:38-39`, `session_store.py:37-38`, `token_store.py:76-79` · *python*
- Impact: `_write` does a single `write_text` (no temp+rename), and `_read` swallows corruption (`except (ValueError, OSError): return []`). A crash or a concurrent `login` refresh racing a tool write mid-write leaves a truncated file; next load silently returns `[]`/`None`, losing up to 50 training plans / 30 analyses or wiping the cached token — data loss masked as empty success.
- Fix: Write atomically (temp file in same dir + `os.replace`). Distinguish "file missing" from "file unparseable" — log/raise on parse failure instead of returning empty.

**`viz-swing-path-mirrored-rh`** — Swing-path diagram is horizontally mirrored for right-handed golfers · `src/trackman_mcp/visualize.py:168` (ang), `:176-182` (line), `:188-190` (clubhead) · *accuracy*
- Impact: `ang(a)=(RH?-a:a)*…`. For a RH golfer a `+2` in-to-out clubPath renders UP-LEFT when it should go UP-RIGHT. RH is the default (`:101`), so the headline "why your ball curves" panel is flipped left-for-right for almost every user, and it contradicts the panel's own caption (`:212-213`) and the ball-flight panel's convention (`:126`). Face line and ideal line are mirrored by the same root.
- Fix: Drop the RH negation in `ang()` (use `a*…`, negate only for LH) so the swing-path sign matches the ball-flight panel. Add a fixed-input test asserting the rendered x-offset sign per handedness.

**`queries-session-measurements-missing-range`** — `verify_training_progress` can never grade range-practice sessions · `src/trackman_mcp/queries.py:229-256` (SESSION_MEASUREMENTS) · *accuracy*
- Impact: `SESSION_MEASUREMENTS` has no inline fragments for `RangePracticeActivity`/`RangeFindMyDistanceActivity`, so those nodes resolve only `PlayerActivity{id time kind}` with no `strokes`. In `verify_training_progress`, range sessions yield empty strokes and are skipped / report `has_data=False` — even when the plan targets a metric the range *does* capture (carry, ballSpeed, totalSide, curve, all present in `GET_SESSION`). The range is the project's primary venue, so the coach can never grade those plans done.
- Fix: Add the two range fragments to `SESSION_MEASUREMENTS` selecting the metrics they expose, or explicitly say "verification is bay-only" instead of a generic no-data message. (Note: clubPath/faceAngle are bay-only regardless, so partial bay-only behavior is by design.)

**`analysis-duration-zero-warmup`** — Missing/unparseable stroke times collapse duration to 0 and misclassify a serious session as warm-up · `src/trackman_mcp/analysis.py:97-101` (_duration_minutes), `:114-116` (_is_warmup_sized), `:164` (classify_session) · *accuracy*
- Impact: `_duration_minutes` returns 0 when <2 times parse; `_is_warmup_sized` is `strokes<8 OR minutes<5`. A 30-stroke multi-club serious session whose strokes lack parseable `time` → minutes=0 → `0<5` True → classified warm-up, `is_improvement_attempt=False`, even for a SERIOUS_KIND (the warm-up floor at `:164` precedes the serious branch). Also triggers when all timestamps are identical. Dropped from improvement tracking purely due to a data quirk.
- Fix: Treat un-computable duration as *unknown*, not 0 — apply the `minutes<5` floor only when ≥2 times parse; otherwise fall back to stroke count. Add a test with strokes lacking `time`.

**`perf-verify-n-plus-1-fanout`** — `verify_training_progress` fans out up to ~21 sequential GraphQL round-trips, each on a fresh TLS connection · `src/trackman_mcp/server.py:460-484` · *performance* (consolidates `mcp-client-per-call-and-sequential-fanout`)
- Impact: With no `activity_id`, it runs `LIST_SESSIONS(take=20)` then sequentially `await`s `_strokes_for(aid)` for each activity, each opening/closing its own client. Worst case (no early match) = ~21 serialized HTTPS requests with ~21 TLS handshakes. The early `break` makes the common case 1-2 fetches, so the 21-call path is the rare no-match case. The list response already carries `clubs` for `RangePracticeActivity` (`queries.py:58-60`) but it is never used to pre-filter.
- Fix: Pre-filter range candidates using the `clubs` field already returned by `LIST_SESSIONS` (add `clubs` to other list fragments to extend it). Reuse a single client across the loop (see `perf-no-connection-reuse`). Consider a smaller `take` for the scan.

**`docs-readme-stale-toolcount`** — README claims "9 tools", omits 10 shipped tools and 2 skills · `README.md:22-23,80-92` · *tests-docs*
- Impact: `server.py` registers 19 `@mcp.tool` functions; README lists only the 9 fetch tools and omits `login`, the 3 session-analysis tools, the 5 training-plan tools, and `build_visualization`, plus the `trackman-session-analyzer` and `trackman-visualizer` skills. CLAUDE.md is current, so the README is the single stale source of truth — a reader gets a materially wrong picture of the surface area.
- Fix: Update the count and tool/skill lists, or point them at CLAUDE.md to avoid duplication.

**`tests-verify-training-progress-tool-untested`** — The `verify_training_progress` tool orchestration is untested · `tests/test_verify.py` vs `server.py:433-506` · *tests-docs*
- Impact: Tests cover the inner `analysis.verify_targets` thoroughly but never exercise the server tool: the no-`target_specs` guard (`:453-456`), the newest-first session-selection loop (`:464-484`), the no-data branch (`:486-489`), and recommendation assembly (`:501-505`). This is the deterministic grading path `golf-coaching` relies on to mark plans done; a regression ships silently.
- Fix: Add a monkeypatched-`_run` test (mirroring `test_server.py`'s `patch_transport`) asserting: no-specs error, explicit-`activity_id` path, auto-select-newest path, no-data branch, all_met recommendation.

**`pkg-no-ci-lint-type`** — No GitHub Actions CI and no ruff/mypy tooling · `MISSING:.github/workflows` · *distribution*
- Impact: No automated test/lint/type gate. `.gitignore` references `.mypy_cache/`/`.ruff_cache/` but neither tool is configured. Quality regressions can land unnoticed.
- Fix: Add `.github/workflows/ci.yml` (uv + pytest on 3.11/3.12, `ruff check`, `mypy`); configure `[tool.ruff]`/`[tool.mypy]` in pyproject. (Registry/PyPI publish workflow only if publishing is adopted.)

**`pkg-no-plugin-json`** — No `.claude-plugin/plugin.json`/`.mcp.json` to bundle the server + 6 skills as a Claude Code plugin · `MISSING` · *distribution* (severity contingent)
- Impact: Cannot install as a Claude Code plugin. **Only a defect if plugin packaging is a goal** — it is not stated in CLAUDE.md/README, which document a working uvx/pip + stdio-MCP model. If it is a goal, high; otherwise an optional enhancement.
- Fix: Add `.claude-plugin/plugin.json` (kebab `name`), a root `.mcp.json` (`uvx --from ${CLAUDE_PLUGIN_ROOT} trackman-mcp`, `env.TRACKMAN_TOKEN=${user_config.trackman_token}`), move/symlink `.claude/skills/` → top-level `skills/` (Claude Code auto-discovers `skills/`), and declare a `userConfig` `trackman_token` with `sensitive:true`.

**`pkg-readme-no-client-config`** — README has no copy-paste MCP client config · `README.md:73-84` · *distribution*
- Impact: A non-author cannot wire this into Claude Desktop / any MCP client; the install story is dev-only. ("Public-place" framing is the reviewer's premise, not a stated goal.)
- Fix: Add an "Add to your MCP client" block matching the *actual* model: the `trackman-mcp` console script (absolute `.venv/bin/trackman-mcp` or `uv run --directory <repo> trackman-mcp`), note that no env is required because the server auto-loads `~/.trackman-mcp/token.json` after `trackman-mcp login` (TRACKMAN_TOKEN only as override), and give the macOS config path. Add a `uvx` variant only after PyPI publish.

### Low

- **`sec-graphql-endpoint-ssrf`** — `TRACKMAN_GRAPHQL_ENDPOINT` unvalidated; bearer token sent to any host/scheme · `config.py:53`, `client.py:48-49,85` · *security*. A poisoned config (e.g. an env-only template that can't read the 0600 token cache but can redirect) could exfiltrate the cached token. Fix: reject non-https when a token is present; warn loudly on any override from the default host. Do **not** hard-pin the host (breaks local mock/proxy testing).
- **`sec-plist-xml-unescaped-path`** — launchd plist interpolates filesystem paths into XML without escaping · `scripts/install-refresh-schedule.sh:24-46` · *security*. A path with `&`/`<`/`>` corrupts the LaunchAgent → refresh silently never runs → token expiry. Not command injection. Fix: XML-escape values or generate via `plutil`/`defaults`; `plutil -lint` the real install path.
- **`mcp-empty-success-on-missing-node`** — `get_session`/`get_shot_data` return `None` for a not-found id · `server.py:216,258` · *mcp*. `data.get("node", {})` yields `None` (not `{}`) for `{"node": null}`, violating the dict return contract and the fail-loud rule. (The `get_profile`/`me` schema-drift case is *not* a real silent-success path — `client.execute` already raises on GraphQL `errors`.) Fix: when `data.get("node")` is None, raise a clear "No activity found for id X".
- **`mcp-no-tool-annotations`** — No `readOnlyHint`/`idempotentHint`/`title` on any tool · `server.py` decorators · *mcp*. Hosts can't auto-gate safe read tools. Fix: add annotations (read-only+idempotent on fetch tools; `readOnlyHint=False` on the mutating store/training tools).
- **`mcp-untyped-return-shapes`** — All tools return bare `dict[str, Any]`; no `models.py` exists despite CLAUDE.md · `server.py` signatures · *mcp*. No structured-output schema; upstream shape drift is silent. Fix: add pydantic/TypedDict models for the shapes the skills depend on (don't model all ~80 fields).
- **`mcp-unbounded-shot-data`** — `get_session`/`get_shot_data` return all strokes with no limit · `server.py:208-217,249-258` · *mcp*. A 100+-stroke range session is one large payload; list tools paginate but per-session detail does not. Fix: add stroke `skip`/`take` or a summary mode with `totalCount`.
- **`mcp-build-visualization-undocumented-and-boundary`** — `build_visualization` absent from CLAUDE.md tool tables; transforms rather than fetches · `server.py:509-526` · *mcp*. Deterministic presentation (like `analysis.py`), not a hard boundary break, but undocumented → harder to audit. Fix: add it to the table noting "deterministic presentation, no coaching opinion".
- **`analysis-verify-mean-masks-dispersion`** — Targets graded on the arithmetic mean, hiding scatter · `analysis.py:398-428` · *accuracy*. clubPath of -10 and +12 → mean +1.0 passes `between -1..2`, prematurely graduating a consistency fault. Documented as session-mean, so design limitation. Fix: also compute/surface std and consider a "fraction of shots within target" pass rule.
- **`analysis-population-std`** — Population std (÷N) understates dispersion and inflates z-scores · `analysis.py:44-48,267` · *accuracy*. Material only at the small N this code uses. Fix: use sample std (÷(N-1)) or document the choice.
- **`server-verify-take20-cap`** — Auto-selected verification session capped to 20 most-recent activities · `server.py:470-484` · *accuracy*. A qualifying session older than 20 activities is silently reported as none. Fix: page further, or state the 20-window in the no-data message.
- **`viz-launchdx-dead-ternary`** — Dead handedness ternary `RH?launchDx:launchDx` · `visualize.py:142-143` · *accuracy*. No-op; the bend is already handedness-correct via `sx`. Cosmetic. Fix: remove the dead ternary.
- **`tests-op-and-edge-coverage-gaps`** — Analytics tests omit `>`,`>=`,`<=`,`abs<=` ops and key edges · `tests/test_verify.py:18-24`, `test_analysis.py` · *tests-docs*. No test for duration=0 misclassification, lookahead exclusion in normalization, range-session verify, or mixed has_data. Fix: a case per op + a lookahead-exclusion test + a missing-times classification test.
- **`async-blocking-file-io`** — Sync file I/O on the event loop in every store-backed tool · `server.py:332,389,401-405`; stores · *python*. Tiny files, single-user, so minor, but violates the don't-block convention. Fix: wrap store calls in `asyncio.to_thread` (low urgency).
- **`silent-refresh-dead-with-env-token`** — Silent refresh never helps when `TRACKMAN_TOKEN` is set · `server.py:62-69`, `config.py:44-52` · *python*. Env token takes precedence with no expiry check, so the retry re-reads the same expired token after a wasted (headless) browser launch. Fix: prefer a non-expired cached token over an expired env token, or skip refresh and emit "unset TRACKMAN_TOKEN to allow auto-refresh".
- **`login-fireforget-task`** — Unreferenced `asyncio.create_task` may be GC'd; errors swallowed · `login.py:69-70,53-67` · *python*. Low impact (parallel `poll_storage` path + token rides every request). Fix: keep task refs in a set with a done-callback; log unexpected exceptions instead of blanket `pass`.
- **`perf-no-connection-reuse`** — New `httpx.AsyncClient`/TLS per GraphQL call · `server.py:53-69` · *performance* (consolidates `httpx-client-per-request`). No keep-alive; ~100-300ms handshake per request, multiplied in multi-call tools. Fix: reuse one client within a tool invocation. **Caveat:** any long-lived/shared client must re-read the token (rebuild or update the `Authorization` header) on `Config.from_env()` so the silent-refresh retry still works.
- **`perf-token-reload-per-call`** — Token cache re-read (file `mkdir`/stat/read) on every `_run` · `config.py:21-55` · *performance*. Note: there is **no** JWT re-decode on the read path (the finding's "re-decoded" framing is wrong — `decode_exp` runs only in `save_token`). Micro-cost amplified by the fan-out. Fix: resolve `Config` once per tool invocation and thread it through.
- **`perf-store-redundant-reads-full-rewrite`** — Stores re-read the whole file twice per op and rewrite in full · `training_store.py:38-79`, `server.py:401-406` · *performance*. Bounded by 30/50 caps. Fix: read once per op (e.g. `get_next_training` reuses a single read).
- **`tests-training-session-tool-wrappers-untested`** — No server-level tests for the session-analysis/training-plan wrappers · `tests/test_server.py` · *tests-docs*. The stores/analysis are covered; the glue (index projection, equipment-fetch fallback, history filter) is not. Fix: a couple of monkeypatched-`_run` tests including the equipment-raises fallback.
- **`tests-visualize-no-pytest-coverage`** — `build_html`/`build_visualization` has no pytest gate · `visualize.py`, `server.py:509-526` · *tests-docs*. Only a Playwright+Chrome script checks it, outside `testpaths`. Fix: a browserless test asserting non-empty, self-contained (no external http(s) URLs), marker-bearing HTML.
- **`tests-authenticate-success-and-whoami-untested`** — `authenticate()` success path and `client.whoami()` untested · `tests/test_server.py:122-127`, `client.py:110-128` · *tests-docs*. The "never echo the token" guarantee and whoami's 401→re-capture mapping are unverified. Fix: a test asserting the response has name/sub/email but no token-like value; a MockTransport test for whoami 200/401.
- **`pkg-no-license-file`** — No LICENSE and no `license` field · `MISSING` · *distribution*. Note: MIT is **not** referenced anywhere in the repo (the original "MIT everywhere" claim was false) — the license choice is open. Unlicensed = all-rights-reserved, blocking redistribution if published. Fix: pick a license, add `LICENSE` + SPDX `license` + `authors` in pyproject. Release-readiness item, not a current blocker.
- **`pkg-pyproject-metadata-thin`** — No authors/license/keywords/classifiers/`[project.urls]` · `pyproject.toml:1-10` · *distribution*. Only `license` has value independent of publishing; the rest matter only on PyPI. Fix: add `license`+`authors` now; defer the rest until a publish decision.
- **`pkg-no-mcpb-manifest`** — No `manifest.json`/`.mcpb` for Claude Desktop one-click · `MISSING` · *distribution*. Lowest-priority channel; the Playwright browser-login + cron-refresh flow can't run inside a self-contained extension (only the manual-token-paste path would work). Defer.
- **`pkg-uvx-name-mismatch`** — Distribution name `trackman-mcp-client` ≠ script `trackman-mcp` · `pyproject.toml:2,13` · *distribution*. `uvx trackman-mcp` would fail; needs `uvx --from trackman-mcp-client trackman-mcp`. Harmless under the documented `uv pip install -e .` path. Fix (optional): rename the dist to `trackman-mcp`, or document the `--from` form, if/when uvx install is documented.
- **`pkg-readme-missing-playwright-install`** — README `[login]` setup omits the browser-binary step · `README.md:29-37` · *distribution*. Note: `login.py:104-109` tries installed Chrome first, so **most users are unaffected**; only users without Chrome hit it (and the code prints the remedy at runtime). Fix: add a *fallback* note "if you don't have Chrome, run `playwright install chromium`" — do **not** make it mandatory.
- **`pkg-uvlock-gitignored`** — `uv.lock` (262 KB, present on disk) is gitignored · `.gitignore:33-34` · *distribution*. Non-reproducible dev/CI installs with loose ranges (`fastmcp>=2.0.0`, `httpx>=0.27`). Fix: un-ignore and commit `uv.lock`; keep loose ranges in pyproject.

### Info

- **`sec-token-capture-host-trust`** — Login captures bearer from any `'trackman' in url` rather than the known host · `login.py:53-67,47-51` · *security*. `GRAPHQL_HOST` exists but is unused for filtering; `'trackman' in url` would match `nottrackman.evil.com`. Low real risk (isolated profile, user-driven). Fix: allowlist `urlparse(url).netloc`.
- **`mcp-weak-param-validation`** — Free-form string/dict params lack enums/schema · `server.py:178,372,410,510` · *mcp*. Apply only: `status: Literal['pending','done']|None` on `list_training_plans`. Leave `kinds` as `list[str]` (ActivityKind is an external open GraphQL enum). Leave `build_visualization`'s `data` and `save_training_plan`'s `plan` open (intentionally flexible); at most a light "require non-empty title" check on save.
- **`store-path-missing-return-type`** — `store_path()` helpers lack `-> Path` · `session_store.py:22-23`, `training_store.py:23-24` · *python*. Fix: annotate and import `Path`.
- **`perf-get-session-overfetch`** — `GET_SESSION` always pulls full per-stroke/per-hole measurements; `get_shot_data` re-issues the same query · `queries.py:74-179` · *performance*. Single-activity fetch, GraphQL already field-scoped, and the full set is what the analysis skills consume — not a real perf problem. Optional: have `get_shot_data` delegate to `get_session` to dedupe.
- **`tests-respx-declared-unused`** — `respx>=0.21` declared but never used (tests use `httpx.MockTransport`) · `pyproject.toml:22` · *tests-docs*. Fix: drop it or adopt it.
- **`docs-testfile-docstring-stale`** — `test_server.py` docstring claims it proves "all 9 tools" (and line 1 "every MCP tool") · `tests/test_server.py:1,4-7` · *tests-docs*. Fix: reword to "the 9 read-only data tools".
- **`docs-fixture-hygiene-clean`** ✅ (positive) — No real tokens/emails/player IDs in docs/tests/`.env.example`; synthetic `alg:none` JWTs; the only id is a public OIDC client_id · *tests-docs*. No action; keep scrubbing future fixtures.

### Cross-cutting gaps (raised by completeness review — not yet investigated by a reviewer)

- **`gap-skill-content-review`** — The entire `.claude/skills/*` prose half (where CLAUDE.md says *all* judgment lives) got zero review. Concrete risks: `golf-coaching` emits YouTube links with no resolve/verify step and `drill-library` has 0 vetted links (relies on live search) → hallucinated/dead "vetted" links; Trackman free-text (course/club names) flows unescaped into the coaching LLM context → prompt-injection surface; the "`trackman-session-analyzer` MUST run in a forked subagent" rule has no enforcement, only prose. *Suggestion:* add a skill-content review dimension — grep each SKILL.md against the fetch-only boundary, gate emitted links through a fetch/verify step, treat tool output as untrusted in prompts.
- **`gap-legal-tos`** — The premise (reverse-engineered private API + automated Playwright token capture) likely violates Trackman's ToS and risks the user's real account; no disclaimer anywhere. *Suggestion:* add a prominent README disclaimer (unofficial, private API, own-account-only, at your own risk) and conservative request pacing.
- **`gap-pii-store-hygiene`** — `session-analyses.json`/`training-plans.json` are written with default perms (only `token.json` is chmod'd); no "forget me" / wipe path. *Suggestion:* factor a shared atomic+chmod-0600 write helper used by all stores; create the cache dir 0700; add a wipe tool/CLI. (Overlaps `sec-token-write-race-dir-perms`.)
- **`gap-multiprocess-locking`** — The cron/launchd refresher and the live server (or two clients) can race the same token/JSON files; no `fcntl.flock` anywhere. *Suggestion:* advisory locks around read-modify-write, plus atomic rename. (Compounds `store-non-atomic-writes`.)
- **`gap-store-schema-versioning`** — No schema version field; any shape change or single bad byte silently wipes history via the `except → return []` path. *Suggestion:* `{"version":N,"records":[...]}` envelope, migrate on version, back up unparseable files to `.corrupt` and log.
- **`gap-shell-robustness`** — `refresh-token.sh` uses `set -u` but not `-e`/`-o pipefail`; refresh/cron logs grow unbounded; cron idempotency `grep -vF "$REFRESH"` strips any unrelated line containing that path substring. *Suggestion:* `set -eo pipefail`, log rotation/size cap, match a labeled marker comment for cron removal.
- **`gap-windows-portability`** — Refresh scheduling bails on Windows and `chmod 0o600` is a no-op under Windows ACLs, so token + data stores have no real protection there. *Suggestion:* document Windows as supported-with-caveats — a Task Scheduler refresh equivalent, and either Windows ACL hardening or a clear "POSIX-only file hardening" warning.

---

## 3. Distribution & plugin readiness checklist

**Important:** nothing in CLAUDE.md/README states public/registry/plugin/Desktop distribution is a goal — the documented model is a personal source install (`uv pip install -e '.[login]'` → `trackman-mcp` over stdio). Treat this section as the gating checklist to action **only if you decide to ship**, in the order below. Items marked **(do anyway)** have value even for the personal tool.

- [ ] **LICENSE + `license`/`authors` in pyproject** *(do anyway)* — pick a license; legal clarity for a public GitHub repo.
- [ ] **CI (`ci.yml`: uv + pytest 3.11/3.12 + ruff + mypy) and `[tool.ruff]`/`[tool.mypy]` config** *(do anyway)* — close the quality-gate gap; the cache dirs are already gitignored.
- [ ] **Commit `uv.lock`** *(do anyway)* — reproducible dev/CI installs.
- [ ] **README: "Add to your MCP client" block** *(do anyway)* — matching the real install + cached-token auth model (not an assumed PyPI/uvx flow).
- [ ] **PyPI publish** — fill pyproject metadata (keywords, classifiers, `[project.urls]`), `uv build` + `uv publish`. Decide the distribution name (`trackman-mcp` vs `trackman-mcp-client`) to fix the uvx mismatch. Add `<!-- mcp-name: io.github.bjornj12/trackman-mcp -->` to README for registry ownership.
- [ ] **MCP Registry** — `server.json` (depends on PyPI):

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.bjornj12/trackman-mcp",
  "description": "Fetch Trackman golf stats and coach from them",
  "version": "0.1.0",
  "packages": [{
    "registryType": "pypi", "registryBaseUrl": "https://pypi.org",
    "identifier": "trackman-mcp-client", "version": "0.1.0",
    "runtimeHint": "uvx", "transport": { "type": "stdio" },
    "environmentVariables": [
      { "name": "TRACKMAN_TOKEN", "description": "Captured portal bearer token", "isSecret": true }
    ]
  }]
}
```

- [ ] **Claude Code plugin** (only if plugin packaging is a goal) — `.claude-plugin/plugin.json` (kebab `name`) + root `.mcp.json`, and move `.claude/skills/` → top-level `skills/`:

```json
// .mcp.json
{ "mcpServers": { "trackman": {
  "command": "uvx",
  "args": ["--from", "${CLAUDE_PLUGIN_ROOT}", "trackman-mcp"],
  "env": { "TRACKMAN_TOKEN": "${user_config.trackman_token}" }
}}}
```

- [ ] **MCPB / Claude Desktop one-click** (lowest priority) — `manifest.json` (manifest_version 0.3) bundling Python deps under `server/lib/`; note browser-login can't run inside the bundle, so only the manual-token path works via `user_config`.

---

## 4. Prioritized action plan

1. **Stop corrupting the protocol stream** — route `login.py` prints to stderr (`mcp-stdout-print-corrupts-stdio`). Highest-value runtime fix; affects normal token-refresh operation.
2. **Fix the visualizer injection** — escape `title`/`subtitle`/`diagnosis`, escape the embedded JSON breakout, switch client JS to `textContent` + `http(s)`-only links (`sec-viz-html-xss`).
3. **Harden local secret storage** — atomic 0600 token write, cache/profile dirs 0700, and chmod 0600 on the session/training stores via a shared write helper (`sec-token-write-race-dir-perms`/`token-file-perm-race` + `gap-pii-store-hygiene`).
4. **Make writes atomic and corruption loud** — temp+`os.replace` for all stores and the token cache; distinguish missing from unparseable; add a schema-version envelope and `.corrupt` backup; add `fcntl.flock` around read-modify-write to cover the cron-refresher race (`store-non-atomic-writes` + `gap-store-schema-versioning` + `gap-multiprocess-locking`).
5. **Fix the correctness bugs the coach reasons over** — un-mirror the swing-path diagram (`viz-swing-path-mirrored-rh`); add range fragments to `SESSION_MEASUREMENTS` (`queries-session-measurements-missing-range`); treat un-computable duration as unknown (`analysis-duration-zero-warmup`); raise on not-found node (`mcp-empty-success-on-missing-node`).
6. **Tighten the verify path** — pre-filter via `clubs` + reuse one client across the loop (`perf-verify-n-plus-1-fanout` / `perf-no-connection-reuse`, preserving the refresh retry); surface the 20-activity window (`server-verify-take20-cap`); surface dispersion alongside the mean (`analysis-verify-mean-masks-dispersion`).
7. **Close the test gaps on deterministic paths** — `verify_training_progress` orchestration, store/analysis wrappers, `authenticate` success + `whoami`, all `evaluate_target` ops + lookahead/missing-times edges, and a browserless `build_html` test (`tests-*`).
8. **Lower-risk security/ergonomics hardening** — https-enforce + warn-on-override for the GraphQL endpoint (`sec-graphql-endpoint-ssrf`); allowlist token-capture host (`sec-token-capture-host-trust`); XML-escape the plist + `set -eo pipefail`/log rotation/marker-based cron removal in the scripts (`sec-plist-xml-unescaped-path` + `gap-shell-robustness`); prefer cached over expired env token (`silent-refresh-dead-with-env-token`); add tool annotations and the `status` Literal (`mcp-no-tool-annotations`, `mcp-weak-param-validation`).
9. **Audit the skill/coaching half** — the entirely-unreviewed `.claude/skills/*`: boundary compliance, YouTube-link verification, untrusted-data-in-prompts, and the forked-subagent rule (`gap-skill-content-review`).
10. **Docs + housekeeping** — fix the README tool/skill counts, stale test docstring, the Playwright-fallback note, the unused `respx`, and the missing `-> Path` hints (`docs-readme-stale-toolcount`, `docs-testfile-docstring-stale`, `pkg-readme-missing-playwright-install`, `tests-respx-declared-unused`, `store-path-missing-return-type`).
11. **Release-readiness (only if shipping)** — in order: LICENSE + CI + commit `uv.lock` + README client-config (do-anyway) → ToS disclaimer (`gap-legal-tos`) → PyPI metadata + publish → `server.json`/registry → optional plugin/MCPB → Windows-caveats doc (`gap-windows-portability`).