# Golf Coach — Multi-Source Normalized Backend — Design

*2026-07-06*

## Problem

The project began as a single-source Trackman MCP. Adding GameBook (screenshots,
no API) already broke that assumption — GameBook lives as its own `gamebook_round`
tool with its own data shape, and the coach hand-stitches Trackman and GameBook
outputs in prose. There is no shared data model, and analysis is split by source
with no way to reason *across* them.

The product is now a **stats-driven golf coach** (rename: "Golf Coach") that
should treat Trackman and GameBook as two **sources** of the same underlying
thing — the user's golf — and get smarter by combining them. Critically, the
sources are not equivalent: **Trackman is a clean room** (flat lie, no wind, no
pressure, shot-level launch precision) while **GameBook is the real course**
(variable lies, weather, pressure, scorecard-level, coverage-limited). A good
coach knows the difference. The reconstruction must preserve that context, not
average it away.

## Goals

- **Rename** the product to `golf-coach` end-to-end (package, module, MCP server,
  plugin, registry) while **keeping `TRACKMAN_*` and the Trackman client naming**
  (Trackman is one source, and its token really is a Trackman token).
- A **normalized, coverage-aware data model** (`Round`, `Session`, `Shot`,
  `Hole`, `Metric`) that every source maps into, each object carrying its
  **source** and **context** (controlled vs on-course, shot-level vs scorecard).
- A **`Source` abstraction** + registry so a third source is one new module.
- **Per-source expert analyzers** — each an expert in its own source's context —
  emitting context-tagged **findings**.
- A deterministic **normalizer** (`synthesize`) that aligns those findings across
  sources by skill area, tags each with its context, and computes cross-source
  deltas — *without rendering a verdict*.
- Consolidated **tool surface**: `trackman(action=…)`, `gamebook(action=…)`,
  `auth(source=…)`, `synthesize`, plus the unchanged source-agnostic
  `training_plan`, `build_visualization`, `setup`.
- Ship as **one PR**, built in staged, TDD commits.

## Non-goals

- **No speculative source framework.** Everything is designed from the two real
  sources (Trackman, GameBook); nothing is built that they don't need. Two
  examples is thin for an abstraction — staying grounded in the real two is the
  discipline.
- **No coaching verdicts in the server.** The normalizer aligns and contextualizes
  facts; the interpretation stays in the coaching skills (CLAUDE.md boundary).
- **No unified mega-store.** Keep the per-purpose JSON stores.
- **No new third source** in this work (Foresight/Garmin/etc.) — only the
  structure that makes adding one clean.
- **No behavior loss.** Every capability today (profile, handicap, sessions, shot
  metrics, rounds, gapping, session analysis, gamebook ingest/compare, plans,
  viz) survives, re-homed onto the model.

## Architecture

```
raw source data
   │  (Trackman GraphQL API / GameBook local store fed by the extraction skill)
   ▼
[ Source adapter ]  sources/<name>/source.py   → normalizes into the MODEL
   │
   ▼
Round / Session / Shot / Hole / Metric   (golf_coach/model.py, coverage + context)
   │
   ▼
[ Per-source expert analyzer ]  sources/<name>/analyzer.py
   │   Trackman: mechanics (gapping, dispersion, launch/spin) — "controlled"
   │   GameBook: scoring/tendencies (coverage-aware)          — "on-course"
   │   emits context-tagged Findings
   ▼
[ Normalizer ]  golf_coach/synthesis.py   (deterministic)
   │   aligns Findings by skill area, tags source+context, cross-source deltas
   ▼
CrossSourceView  ──►  coaching SKILL interprets (verdict + practice plan)
```

Layers, each independently testable:

1. **Model** (`golf_coach/model.py`) — the shared vocabulary.
2. **Sources** (`golf_coach/sources/<name>/`) — adapter (raw→model) + analyzer
   (model→findings). A `registry` lists available sources.
3. **Synthesis** (`golf_coach/synthesis.py`) — the normalizer across sources.
4. **Tools** (`golf_coach/server.py`) — thin dispatch over the above.
5. **Skills** — the coaching brain, reasoning over `synthesize`'s output.

### The rename (folded in)

| Kind | From | To |
|------|------|----|
| Package (PyPI, available) | `trackman-mcp` | `golf-coach` |
| Module | `trackman_mcp` | `golf_coach` |
| CLI entry | `trackman-mcp` | `golf-coach` |
| MCP server / plugin / mcpb / `.mcp.json` id | `trackman-golf` | `golf-coach` |
| Registry id | `io.github.bjornj12/trackman-mcp` | `io.github.bjornj12/golf-coach` |
| Cache dir + its env | `~/.trackman-mcp/` · `TRACKMAN_CACHE_DIR` | `~/.golf-coach/` · `GOLF_COACH_CACHE_DIR` |

**Kept as `TRACKMAN_*`** (data-source-specific, renaming would mislead):
`TRACKMAN_TOKEN`, `TRACKMAN_USERNAME`, `TRACKMAN_PASSWORD`,
`TRACKMAN_GRAPHQL_ENDPOINT`, `TRACKMAN_TIMEOUT_SECONDS`, and all Trackman
client/API code and "connects to Trackman" copy. The display rebrand ("Golf
Coach" in README/CLAUDE.md/manifests) is already on this branch.

Consequences (accepted, we're at 0.x): the published `trackman-mcp` PyPI package
and the old registry entry are orphaned (can't rename a published package); a
fresh `golf-coach` publish + registry entry are needed; the plugin install
command changes; existing local `~/.trackman-mcp/` state is not migrated (one-time
re-login).

### The normalized model (`golf_coach/model.py`)

Coverage-aware, source- and context-tagged. Implemented as pydantic models
(fastmcp already brings pydantic; `.model_dump()` gives tool JSON, validation for
free).

- `Metric{name, value, unit, coverage: "full"|"partial"|"none", n?}` — atomic stat.
- `Hole{number, par, score, putts?, fairway?, gir?, bunkers?, chips?, penalties?}`
  — `None` where a source didn't track it.
- `Shot{club, ball_speed, club_speed, smash, launch_angle, spin, carry, total,
  side, curve, landing_angle, max_height?, hang_time?, …}` — **Trackman only**;
  the ~80-field launch measurement.
- `Round{source, context, id, date, course{par,cr,slope,name?},
  result{gross,net,to_par,position?}, holes[], scoring{to_par,distribution,
  by_par_type}, dimensions{name→Metric}, coverage{dim→flag}, notes[]}` —
  generalizes today's GameBook round; Trackman scorecards map straight in.
- `Session{source, context, id, time, kind, category, seriousness?, shots[]?,
  metrics{name→Metric}}` — Trackman practice; GameBook produces none.
- `Profile`, `Handicap`, `ClubGapping` — normalized identity/handicap/gapping.

**`SourceContext`** (carried by every Round/Session, the load-bearing metadata):
```
{ setting: "controlled" | "on_course",
  lie:     "flat" | "variable",
  conditions: "none" | "real",      # wind / weather / pressure
  granularity: "shot" | "scorecard" }
```
Trackman = `controlled/flat/none/shot`; GameBook = `on_course/variable/real/scorecard`.

### Source abstraction (`golf_coach/sources/`)

```python
class Source(Protocol):
    name: str                         # "trackman" | "gamebook"
    context: SourceContext
    def supports(self) -> set[str]    # {"rounds","sessions","profile","handicap","clubs","auth"}
    async def rounds(self, **f) -> list[Round]
    async def sessions(self, **f) -> list[Session]     # [] if unsupported
    async def profile(self) -> Profile | None
    async def handicap(self) -> Handicap | None
    async def club_gapping(self) -> ClubGapping | None
    # auth is optional (Trackman implements; GameBook has none)
```

- `sources/trackman/` — today's `client.py` + `queries.py` move here; the adapter
  normalizes GraphQL → model. `supports()` = everything. Keeps `TRACKMAN_TOKEN`
  auth (`sources/trackman/auth.py` from today's `login.py`/`token_store.py`).
- `sources/gamebook/` — today's `gamebook_store` + the extraction skill's target;
  the adapter serves stored rounds as `Round`s. `supports()` = `{"rounds"}`. No auth.
- `sources/registry.py` — `available_sources()`, `get_source(name)`. Adding a
  source = drop a module in `sources/` + register it.

### Per-source expert analyzers (`sources/<name>/analyzer.py`)

Each is an expert in *its* source's context and emits a common `Finding`:
```
Finding{ skill_area: "driving"|"approach"|"short_game"|"putting"|"scoring"|"gapping",
         source, context, metric, value, unit?, coverage,
         direction?: "better"|"worse"|"same",   # for progress findings
         detail }                                # factual, never coaching
```
- **Trackman analyzer** (subsumes today's `analysis.py`): classify session
  (warm-up/practice/game), metrics, normalize vs history, gapping/dispersion —
  all tagged `controlled`. `verify_targets` lives here.
- **GameBook analyzer** (subsumes today's `gamebook_analysis.py`): scoring
  distribution, by-par-type, coverage-gated `compare_rounds`, `grade_extraction`
  — tagged `on_course`, coverage-aware.

### Normalizer (`golf_coach/synthesis.py`) — deterministic

`synthesize(analyses) -> CrossSourceView`:
```
CrossSourceView{
  by_skill_area: { area: [Finding, …] },     # findings from all sources, aligned
  cross_source_deltas: [ {skill_area, trackman, gamebook, gap, context_note} ],
  context_notes: [ … ],                        # e.g. "Trackman is flat-lie; course isn't"
  coverage_summary: { … } }
```
It **aligns** findings by skill area, **tags** each with source + context,
computes cross-source **deltas** where the areas are comparable, and flags the
context gaps (e.g. Trackman-clean vs on-course). It renders **no verdict** — the
"your swing's fine, you leak it under pressure" call is the coaching skill's, now
made over a genuinely cross-source, context-aware view.

### Tool surface (7 tools, down from 13)

- `auth(action: status|login, source="trackman")` — source-scoped auth.
- `trackman(action: profile|handicap|sessions|session|rounds|clubs|summary|analyze, …)`
  — Trackman reads (normalized to the model) + its expert analysis. (Mega-action,
  per decision; mirrors the shipped `gamebook`.)
- `gamebook(action: save|list|get|compare, …)` — ingest + read + GameBook's
  expert analysis. (Rename of `gamebook_round`.)
- `synthesize(…)` — runs each available source's expert analyzer (via the
  registry), then the normalizer over their combined findings → `CrossSourceView`.
  This is the one tool that reaches across sources.
- `training_plan(action: …)` — unchanged (source-agnostic memory).
- `build_visualization(data)` — unchanged.
- `setup()` — unchanged (dynamically enumerates skills).

### Stores (`~/.golf-coach/`)

Per-purpose JSON, unchanged in shape: `token.json` (Trackman),
`gamebook-rounds.json`, `training-plans.json`, `session-analyses.json`.

### Skills + docs

Update every skill + `COACH_SYSTEM_PROMPT` to the new tool names
(`trackman(…)`, `gamebook(…)`, `synthesize`), and teach the coach to call
`synthesize` for the cross-source, context-aware picture before prescribing.
Rewrite the CLAUDE.md architecture section around sources + model + analyzers +
normalizer. Served-prompt (`PROMPT.md`) bodies still must contain no
"subagent"/"forked".

### Testing

- **Model**: validators (coverage flags, required fields, `None`-tracking).
- **Adapters** (fixture-backed): scrubbed Trackman GraphQL responses → `Round`/
  `Session`/`Shot`; the GameBook golden fixture → `Round`. Assert the context tags.
- **Analyzers**: Trackman classify/metrics/normalize; GameBook scoring/compare/
  grade — over normalized objects.
- **Synthesis**: a real cross-source case — a Trackman session + a GameBook round
  → aligned `by_skill_area`, correct cross-source delta, context notes present.
- **Tools**: each mega-action dispatches correctly; `auth(source=…)`; `synthesize`.
- **Skills/prompts**: tool-name references updated; no CC-only language in PROMPT.md.

### Boundary compliance

Model, adapters, analyzers, and the normalizer are all deterministic data +
analytics — no verdicts, no drills. The normalizer contextualizes but does not
judge. All coaching interpretation stays in the skills.

## Build stages (one PR, staged commits)

1. Rename sweep → `golf_coach` / `golf-coach` (module move, ids, cache dir; keep
   `TRACKMAN_*`). Suite stays green.
2. `model.py` — normalized types + validators + tests.
3. `sources/` scaffold — `Source` protocol, `SourceContext`, `registry` + tests.
4. Trackman source: move `client.py`/`queries.py`/auth into `sources/trackman/`;
   adapter normalizes → model + fixture tests.
5. GameBook source: move store into `sources/gamebook/`; adapter serves rounds →
   model + tests.
6. Analyzers: `analysis.py` → `sources/trackman/analyzer.py`; `gamebook_analysis.py`
   → `sources/gamebook/analyzer.py`; emit `Finding`s + tests.
7. `synthesis.py` — the normalizer + cross-source tests.
8. Tool surface reorg — `trackman`/`gamebook`/`auth`/`synthesize` + tool tests.
9. Skills + `COACH_SYSTEM_PROMPT` + CLAUDE.md/README + prompt-guard tests.
10. Full-suite green + ruff + docs pass.

## Open decisions (resolved)

1. **Analysis = per-source expert analyzers + a normalizer** (not one flat
   engine). Each source stays the expert on its own data; `synthesize` reconciles.
2. **`trackman(action=…)` mega-action** — confirmed (mirrors `gamebook`).
3. **Keep `TRACKMAN_*` credentials/endpoint; rename the app-level cache dir** to
   `~/.golf-coach/` (`GOLF_COACH_CACHE_DIR`).
4. **Model as pydantic**; per-purpose stores kept; no third source built now.
