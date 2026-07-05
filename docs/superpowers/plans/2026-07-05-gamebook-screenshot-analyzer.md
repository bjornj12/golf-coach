# GameBook Screenshot Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest user-pasted Golf GameBook round/statistics screenshots, extract a coverage-aware round record, store a rolling last-5, and feed scoring-led progress to the coaching skills.

**Architecture:** A new **skill** (`gamebook-screenshot-analysis`) does the vision extraction and calls a new local **MCP tool** (`gamebook_round`) that persists records to `~/.trackman-mcp/gamebook-rounds.json` (cap 5) and computes deterministic newest-vs-prior deltas via a new `gamebook_analysis.py`. All judgment stays in the coaching skills; the server computes measurement only. Mirrors the existing `session_store` + `session_analysis` + `analysis.py` trio.

**Tech Stack:** Python 3.12+, FastMCP, pytest (`asyncio_mode = "auto"`), `uv`. Stores use the existing `storage.py` (atomic, 0600) + `token_store.cache_dir()`.

## Global Constraints

- Store path: `~/.trackman-mcp/gamebook-rounds.json`, via `token_store.cache_dir()` (overridable by `TRACKMAN_CACHE_DIR`). Rolling window **MAX_ROUNDS = 5**, newest first.
- Server computes **no coaching verdicts** — only storage + deterministic deltas (CLAUDE.md boundary). Skills do all judgment.
- Coverage flags are `"full" | "partial" | "none"`; scoring is always `"full"`.
- Every skill dir needs `SKILL.md` (Claude Code) **and** `PROMPT.md` (served as an MCP prompt). **Served `PROMPT.md` bodies must NOT contain the words "subagent" or "forked"** — `tests/test_prompts.py::test_served_prompts_have_no_claude_code_only_language` enforces this. Subagent/fork mechanics live only in `SKILL.md`.
- Units: metric (already the repo convention). Coaching copy is specific, never vague.
- Run tests with `uv run --extra dev pytest` (the `dev` extra provides pytest).

---

### Task 1: Scoring analytics — `hole_result`, `coverage_flag`, `scoring_from_holes`

**Files:**
- Create: `src/trackman_mcp/gamebook_analysis.py`
- Test: `tests/test_gamebook_analysis.py`

**Interfaces:**
- Produces: `HOLE_RESULTS: tuple[str, ...]`; `hole_result(par: int, score: int) -> str`; `coverage_flag(tracked: int, eligible: int) -> str`; `scoring_from_holes(holes: list[dict]) -> dict` returning `{"to_par": int, "distribution": dict[str,int], "by_par_type": dict[str,float]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gamebook_analysis.py
from __future__ import annotations

from trackman_mcp import gamebook_analysis as ga


def test_hole_result_buckets():
    assert ga.hole_result(4, 2) == "eagle_or_better"
    assert ga.hole_result(4, 3) == "birdie"
    assert ga.hole_result(4, 4) == "par"
    assert ga.hole_result(4, 5) == "bogey"
    assert ga.hole_result(4, 6) == "double"
    assert ga.hole_result(4, 7) == "triple_plus"
    assert ga.hole_result(3, 9) == "triple_plus"


def test_coverage_flag_thresholds():
    assert ga.coverage_flag(0, 18) == "none"
    assert ga.coverage_flag(6, 12) == "partial"
    assert ga.coverage_flag(18, 18) == "full"
    assert ga.coverage_flag(17, 18) == "full"   # >= 90% counts as full
    assert ga.coverage_flag(1, 18) == "partial"
    assert ga.coverage_flag(5, 0) == "none"     # nothing eligible


def test_scoring_from_holes_reproduces_sample_round():
    # The 9 June sample: front 49, back 60, par 70, +39.
    holes = [
        {"hole": 1, "par": 4, "score": 7}, {"hole": 2, "par": 3, "score": 5},
        {"hole": 3, "par": 4, "score": 6}, {"hole": 4, "par": 4, "score": 6},
        {"hole": 5, "par": 3, "score": 4}, {"hole": 6, "par": 5, "score": 6},
        {"hole": 7, "par": 3, "score": 4}, {"hole": 8, "par": 4, "score": 5},
        {"hole": 9, "par": 5, "score": 6}, {"hole": 10, "par": 4, "score": 5},
        {"hole": 11, "par": 4, "score": 7}, {"hole": 12, "par": 4, "score": 5},
        {"hole": 13, "par": 5, "score": 8}, {"hole": 14, "par": 3, "score": 6},
        {"hole": 15, "par": 5, "score": 7}, {"hole": 16, "par": 3, "score": 9},
        {"hole": 17, "par": 4, "score": 6}, {"hole": 18, "par": 3, "score": 7},
    ]
    s = ga.scoring_from_holes(holes)
    assert s["to_par"] == 39
    assert s["distribution"] == {
        "eagle_or_better": 0, "birdie": 0, "par": 0,
        "bogey": 7, "double": 5, "triple_plus": 6,
    }
    assert s["by_par_type"] == {"par3": 2.83, "par4": 1.88, "par5": 1.75}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trackman_mcp.gamebook_analysis'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/trackman_mcp/gamebook_analysis.py
"""Deterministic analytics for GameBook rounds — measurement, not coaching.

GameBook reliably records only score-per-hole; every other dimension is only as
complete as what the golfer tapped in. These helpers turn the extracted holes
into scoring facts, flag how complete each dimension is, self-check a read, and
compute newest-vs-prior deltas. No coaching verdicts live here (see CLAUDE.md).
"""

from __future__ import annotations

from typing import Any

HOLE_RESULTS: tuple[str, ...] = (
    "eagle_or_better", "birdie", "par", "bogey", "double", "triple_plus",
)


def hole_result(par: int, score: int) -> str:
    """Bucket one hole's score relative to par."""
    diff = score - par
    if diff <= -2:
        return "eagle_or_better"
    if diff == -1:
        return "birdie"
    if diff == 0:
        return "par"
    if diff == 1:
        return "bogey"
    if diff == 2:
        return "double"
    return "triple_plus"


def coverage_flag(tracked: int, eligible: int) -> str:
    """How complete a dimension is: full (>=90% of eligible), partial, or none."""
    if eligible <= 0 or tracked <= 0:
        return "none"
    return "full" if tracked / eligible >= 0.9 else "partial"


def scoring_from_holes(holes: list[dict[str, Any]]) -> dict[str, Any]:
    """The always-reliable scoring block: to-par, result distribution, par-type avgs."""
    distribution = {k: 0 for k in HOLE_RESULTS}
    to_par = 0
    diffs_by_par: dict[int, list[int]] = {}
    for h in holes:
        par, score = int(h["par"]), int(h["score"])
        to_par += score - par
        distribution[hole_result(par, score)] += 1
        diffs_by_par.setdefault(par, []).append(score - par)
    by_par_type = {
        f"par{par}": round(sum(diffs) / len(diffs), 2)
        for par, diffs in sorted(diffs_by_par.items())
        if diffs
    }
    return {"to_par": to_par, "distribution": distribution, "by_par_type": by_par_type}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/gamebook_analysis.py tests/test_gamebook_analysis.py
git commit -m "feat: gamebook scoring analytics (hole_result, coverage_flag, scoring)"
```

---

### Task 2: Read self-check — `self_check`

**Files:**
- Modify: `src/trackman_mcp/gamebook_analysis.py`
- Test: `tests/test_gamebook_analysis.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `self_check(record: dict) -> list[str]` — returns a list of human-readable discrepancies (empty means the read is internally consistent).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gamebook_analysis.py

def _sample_record() -> dict:
    holes = [
        {"hole": 1, "par": 4, "score": 7}, {"hole": 2, "par": 3, "score": 5},
        {"hole": 3, "par": 4, "score": 6}, {"hole": 4, "par": 4, "score": 6},
        {"hole": 5, "par": 3, "score": 4}, {"hole": 6, "par": 5, "score": 6},
        {"hole": 7, "par": 3, "score": 4}, {"hole": 8, "par": 4, "score": 5},
        {"hole": 9, "par": 5, "score": 6}, {"hole": 10, "par": 4, "score": 5},
        {"hole": 11, "par": 4, "score": 7}, {"hole": 12, "par": 4, "score": 5},
        {"hole": 13, "par": 5, "score": 8}, {"hole": 14, "par": 3, "score": 6},
        {"hole": 15, "par": 5, "score": 7}, {"hole": 16, "par": 3, "score": 9},
        {"hole": 17, "par": 4, "score": 6}, {"hole": 18, "par": 3, "score": 7},
    ]
    return {"course": {"par": 70}, "result": {"gross": 109}, "holes": holes}


def test_self_check_passes_on_consistent_round():
    assert ga.self_check(_sample_record()) == []


def test_self_check_flags_gross_mismatch():
    rec = _sample_record()
    rec["result"]["gross"] = 108   # wrong
    problems = ga.self_check(rec)
    assert any("gross" in p for p in problems)


def test_self_check_flags_par_mismatch_and_hole_count():
    rec = _sample_record()
    rec["holes"] = rec["holes"][:17]  # 17 holes, pars now sum to 67
    problems = ga.self_check(rec)
    assert any("holes" in p for p in problems)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -k self_check -v`
Expected: FAIL — `AttributeError: module 'trackman_mcp.gamebook_analysis' has no attribute 'self_check'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/trackman_mcp/gamebook_analysis.py

def self_check(record: dict[str, Any]) -> list[str]:
    """Validate a read using GameBook's internal redundancy. Empty == consistent.

    Checks: hole scores sum to gross; hole pars sum to course par; hole count is
    9 or 18. A non-empty return means the extractor should re-check those holes
    with the user before saving.
    """
    problems: list[str] = []
    holes = record.get("holes") or []
    if len(holes) not in (9, 18):
        problems.append(f"expected 9 or 18 holes, got {len(holes)}")

    gross = sum(int(h["score"]) for h in holes)
    stated_gross = (record.get("result") or {}).get("gross")
    if stated_gross is not None and gross != int(stated_gross):
        problems.append(f"hole scores sum to {gross} but stated gross is {stated_gross}")

    par_total = sum(int(h["par"]) for h in holes)
    course_par = (record.get("course") or {}).get("par")
    if course_par is not None and par_total != int(course_par):
        problems.append(f"hole pars sum to {par_total} but course par is {course_par}")

    return problems
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -v`
Expected: PASS (6 tests total)

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/gamebook_analysis.py tests/test_gamebook_analysis.py
git commit -m "feat: gamebook read self-check (gross/par/hole-count reconciliation)"
```

---

### Task 3: Progress deltas — `compare_rounds`

**Files:**
- Modify: `src/trackman_mcp/gamebook_analysis.py`
- Test: `tests/test_gamebook_analysis.py`

**Interfaces:**
- Consumes: records with a `scoring` block (Task 1 shape) and a `coverage` map + `dimensions.putts` block.
- Produces: `compare_rounds(latest: dict, priors: list[dict]) -> dict` with `{round_id, n_priors, scoring: {to_par, par3?, par4?, par5?}, dimensions: {putts_per_hole|skip}, comparable: {fairways: bool, gir: bool}}`. Each scoring/dimension entry is `{"latest": float, "prior_mean": float, "delta": float, "direction": "better"|"worse"|"same"}`. Direction respects metric polarity (scoring/putts: lower is better).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gamebook_analysis.py

def _round(rid, to_par, par3, par4, par5, putts_total=None, putts_holes=0):
    cov_putts = ga.coverage_flag(putts_holes, 18)
    return {
        "id": rid,
        "scoring": {"to_par": to_par,
                    "by_par_type": {"par3": par3, "par4": par4, "par5": par5}},
        "coverage": {"scoring": "full", "putts": cov_putts},
        "dimensions": {"putts": {"total": putts_total, "holes_tracked": putts_holes,
                                 "coverage": cov_putts}},
    }


def test_compare_scoring_direction_lower_is_better():
    latest = _round("r3", 30, 2.0, 1.5, 1.5)
    priors = [_round("r1", 40, 2.8, 1.9, 1.8), _round("r2", 36, 2.6, 1.7, 1.6)]
    out = ga.compare_rounds(latest, priors)
    assert out["round_id"] == "r3"
    assert out["n_priors"] == 2
    assert out["scoring"]["to_par"]["prior_mean"] == 38.0
    assert out["scoring"]["to_par"]["delta"] == -8.0
    assert out["scoring"]["to_par"]["direction"] == "better"
    assert out["scoring"]["par4"]["direction"] == "better"


def test_compare_putts_gated_on_coverage():
    # latest has putts, but one prior has none -> not comparable, skipped.
    latest = _round("r3", 30, 2.0, 1.5, 1.5, putts_total=30, putts_holes=18)
    priors = [_round("r1", 40, 2.8, 1.9, 1.8, putts_total=33, putts_holes=18),
              _round("r2", 36, 2.6, 1.7, 1.6, putts_total=None, putts_holes=0)]
    out = ga.compare_rounds(latest, priors)
    assert out["dimensions"]["putts_per_hole"] == {"skipped": "coverage"}


def test_compare_putts_when_all_tracked():
    latest = _round("r3", 30, 2.0, 1.5, 1.5, putts_total=27, putts_holes=18)
    priors = [_round("r1", 40, 2.8, 1.9, 1.8, putts_total=36, putts_holes=18)]
    out = ga.compare_rounds(latest, priors)
    p = out["dimensions"]["putts_per_hole"]
    assert p["latest"] == 1.5           # 27/18
    assert p["prior_mean"] == 2.0       # 36/18
    assert p["direction"] == "better"   # fewer putts is better
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -k compare -v`
Expected: FAIL — `AttributeError: ... has no attribute 'compare_rounds'`

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/trackman_mcp/gamebook_analysis.py

_LOWER_IS_BETTER = {"to_par", "par3", "par4", "par5", "putts_per_hole"}


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _delta_block(metric: str, latest: float, prior_mean: float) -> dict[str, Any]:
    delta = round(latest - prior_mean, 2)
    if delta == 0:
        direction = "same"
    else:
        improved = delta < 0 if metric in _LOWER_IS_BETTER else delta > 0
        direction = "better" if improved else "worse"
    return {"latest": latest, "prior_mean": prior_mean, "delta": delta,
            "direction": direction}


def _tracked(round_: dict[str, Any], dim: str) -> bool:
    return (round_.get("coverage") or {}).get(dim, "none") != "none"


def compare_rounds(latest: dict[str, Any], priors: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic newest-vs-prior deltas. Scoring is always compared; other
    dimensions only when BOTH the latest and every prior actually tracked them.

    Returns per-metric {latest, prior_mean, delta, direction}. No narrative — the
    coaching skill turns this into progress/regression talk.
    """
    out: dict[str, Any] = {
        "round_id": latest.get("id"),
        "n_priors": len(priors),
        "scoring": {},
        "dimensions": {},
        "comparable": {},
    }
    ls = latest["scoring"]
    out["scoring"]["to_par"] = _delta_block(
        "to_par", float(ls["to_par"]),
        _mean([float(p["scoring"]["to_par"]) for p in priors]),
    )
    for k in ("par3", "par4", "par5"):
        lv = ls["by_par_type"].get(k)
        pv = _mean([p["scoring"]["by_par_type"][k] for p in priors
                    if k in p["scoring"]["by_par_type"]])
        if lv is not None and pv is not None:
            out["scoring"][k] = _delta_block(k, float(lv), pv)

    # Putts/hole — only if latest and ALL priors tracked putts.
    if _tracked(latest, "putts") and all(_tracked(p, "putts") for p in priors):
        def pph(r: dict[str, Any]) -> float:
            d = r["dimensions"]["putts"]
            return round(d["total"] / max(d["holes_tracked"], 1), 2)
        out["dimensions"]["putts_per_hole"] = _delta_block(
            "putts_per_hole", pph(latest), _mean([pph(p) for p in priors])
        )
    else:
        out["dimensions"]["putts_per_hole"] = {"skipped": "coverage"}

    # Report (but don't compute) whether accuracy dims are comparable.
    for dim in ("fairways", "gir"):
        out["comparable"][dim] = _tracked(latest, dim) and all(
            _tracked(p, dim) for p in priors
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -v`
Expected: PASS (9 tests total)

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/gamebook_analysis.py tests/test_gamebook_analysis.py
git commit -m "feat: gamebook compare_rounds (scoring-led, coverage-gated deltas)"
```

---

### Task 4: The rolling last-5 store — `gamebook_store.py`

**Files:**
- Create: `src/trackman_mcp/gamebook_store.py`
- Test: `tests/test_gamebook_store.py`

**Interfaces:**
- Produces: `MAX_ROUNDS = 5`; `store_path() -> Path`; `save_round(record: dict) -> dict` (upsert by `id`, requires `id`, evict oldest beyond 5, newest-first by `date`); `list_rounds() -> list[dict]` (newest first); `get_round(round_id: str) -> dict | None`; `latest_round() -> dict | None`; `priors_of(round_id: str) -> list[dict]` (rounds chronologically before `round_id`, newest first).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gamebook_store.py
from __future__ import annotations

import pytest

from trackman_mcp import gamebook_store as gs


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKMAN_CACHE_DIR", str(tmp_path))


def _round(rid: str, date: str) -> dict:
    return {"id": rid, "date": date, "result": {"gross": 100}}


def test_save_requires_id():
    with pytest.raises(ValueError):
        gs.save_round({"date": "2026-06-09"})


def test_save_and_list_newest_first():
    gs.save_round(_round("a", "2026-06-01"))
    gs.save_round(_round("c", "2026-06-09"))
    gs.save_round(_round("b", "2026-06-05"))
    assert [r["id"] for r in gs.list_rounds()] == ["c", "b", "a"]
    assert gs.latest_round()["id"] == "c"


def test_save_upserts_by_id():
    gs.save_round(_round("a", "2026-06-01"))
    again = _round("a", "2026-06-01")
    again["result"]["gross"] = 88
    gs.save_round(again)
    rounds = gs.list_rounds()
    assert len(rounds) == 1
    assert rounds[0]["result"]["gross"] == 88


def test_cap_keeps_most_recent_five():
    for i in range(8):
        gs.save_round(_round(f"r{i}", f"2026-06-0{i+1}"))
    rounds = gs.list_rounds()
    assert len(rounds) == gs.MAX_ROUNDS
    assert [r["id"] for r in rounds] == ["r7", "r6", "r5", "r4", "r3"]


def test_priors_of_returns_chronologically_earlier():
    for i in range(5):
        gs.save_round(_round(f"r{i}", f"2026-06-0{i+1}"))
    priors = gs.priors_of("r3")   # dates r0..r2 are earlier than r3
    assert [r["id"] for r in priors] == ["r2", "r1", "r0"]


def test_empty():
    assert gs.list_rounds() == []
    assert gs.latest_round() is None
    assert gs.get_round("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'trackman_mcp.gamebook_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/trackman_mcp/gamebook_store.py
"""Local store of extracted GameBook rounds — a rolling window of the last 5.

The gamebook-screenshot-analysis skill extracts a round from screenshots and
saves it here so the coach can track direction of travel across recent rounds.
Records are keyed by `id`, ordered by `date` (newest first), and only the 5 most
recent are kept. Holds derived data only; lives under the MCP cache dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import storage
from .token_store import cache_dir

MAX_ROUNDS = 5


def store_path() -> Path:
    return cache_dir() / "gamebook-rounds.json"


def _read() -> list[dict[str, Any]]:
    data = storage.read_json(store_path(), default=[])
    return data if isinstance(data, list) else []


def _write(rounds: list[dict[str, Any]]) -> None:
    storage.write_secure(store_path(), json.dumps(rounds, indent=2))


def _sorted_desc(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # ISO dates sort as strings; tie-break by id for stability.
    return sorted(rounds, key=lambda r: (r.get("date") or "", r.get("id") or ""),
                  reverse=True)


def save_round(record: dict[str, Any]) -> dict[str, Any]:
    """Upsert a round by `id`; keep the newest 5 by date. Requires `id`."""
    if not record.get("id"):
        raise ValueError("gamebook round record needs an 'id'")
    rounds = [r for r in _read() if r.get("id") != record["id"]]
    rounds.append(record)
    rounds = _sorted_desc(rounds)[:MAX_ROUNDS]
    _write(rounds)
    return record


def list_rounds() -> list[dict[str, Any]]:
    """All stored rounds, newest first."""
    return _sorted_desc(_read())


def latest_round() -> dict[str, Any] | None:
    rounds = list_rounds()
    return rounds[0] if rounds else None


def get_round(round_id: str) -> dict[str, Any] | None:
    for r in _read():
        if r.get("id") == round_id:
            return r
    return None


def priors_of(round_id: str) -> list[dict[str, Any]]:
    """Rounds chronologically before `round_id` (by date), newest first."""
    rounds = _sorted_desc(_read())
    target = next((r for r in rounds if r.get("id") == round_id), None)
    if target is None:
        return []
    tdate = target.get("date") or ""
    return [r for r in rounds if (r.get("date") or "") < tdate]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_gamebook_store.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/gamebook_store.py tests/test_gamebook_store.py
git commit -m "feat: gamebook-rounds store (rolling last-5, newest first)"
```

---

### Task 5: The `gamebook_round` MCP tool

**Files:**
- Modify: `src/trackman_mcp/server.py` (add `_WRITE_LOCAL` preset near line 40; add tool + helpers before the "Skill prompts" section at line 556)
- Test: `tests/test_gamebook_tool.py`

**Interfaces:**
- Consumes: `gamebook_store` (Task 4), `gamebook_analysis` (Tasks 1–3).
- Produces: MCP tool `gamebook_round(action, round=None, round_id=None) -> dict` with actions `save | list | get | compare`. `save` derives `id` from `date` (suffixing `-2`, `-3`… if that id already exists for a *different* round), runs `self_check`, refuses to save when checks fail (returns `{"saved": False, "problems": [...]}`), computes+attaches `scoring`, and stores. `compare` returns `compare_rounds(latest, priors)` for `round_id` (default latest).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gamebook_tool.py
from __future__ import annotations

import pytest

from trackman_mcp import server


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKMAN_CACHE_DIR", str(tmp_path))


def _holes():
    pars = [4, 3, 4, 4, 3, 5, 3, 4, 5, 4, 4, 4, 5, 3, 5, 3, 4, 3]
    scores = [7, 5, 6, 6, 4, 6, 4, 5, 6, 5, 7, 5, 8, 6, 7, 9, 6, 7]
    return [{"hole": i + 1, "par": p, "score": s}
            for i, (p, s) in enumerate(zip(pars, scores))]


def _round(date="2026-06-09", gross=109):
    return {"date": date, "course": {"par": 70}, "result": {"gross": gross},
            "holes": _holes(),
            "coverage": {"scoring": "full", "putts": "partial"},
            "dimensions": {"putts": {"total": 27, "holes_tracked": 12,
                                     "coverage": "partial"}}}


async def test_save_computes_scoring_and_stores():
    res = await server.gamebook_round(action="save", round=_round())
    assert res["saved"] is True
    assert res["round"]["id"] == "2026-06-09"
    assert res["round"]["scoring"]["to_par"] == 39
    assert res["round"]["scoring"]["distribution"]["bogey"] == 7
    assert res["stored_count"] == 1


async def test_save_rejects_inconsistent_read():
    bad = _round(gross=108)  # gross disagrees with hole sum (109)
    res = await server.gamebook_round(action="save", round=bad)
    assert res["saved"] is False
    assert any("gross" in p for p in res["problems"])


async def test_same_day_second_round_gets_suffixed_id():
    await server.gamebook_round(action="save", round=_round(gross=109))
    r2 = _round(gross=100)
    r2["holes"][0]["score"] = 6   # make hole sum 108, then fix gross to match
    r2["result"]["gross"] = 108
    res = await server.gamebook_round(action="save", round=r2)
    assert res["round"]["id"] == "2026-06-09-2"


async def test_list_and_get():
    await server.gamebook_round(action="save", round=_round())
    listed = await server.gamebook_round(action="list")
    assert listed["count"] == 1
    assert listed["items"][0]["to_par"] == 39
    got = await server.gamebook_round(action="get", round_id="2026-06-09")
    assert got["result"]["gross"] == 109


async def test_compare_two_rounds():
    await server.gamebook_round(action="save", round=_round(date="2026-06-01", gross=109))
    better = _round(date="2026-06-09", gross=100)
    # lower all scores by making one par: change hole 16 from 9 to 3 (gross 103)
    better["holes"][15]["score"] = 3
    better["result"]["gross"] = 103
    await server.gamebook_round(action="save", round=better)
    cmp = await server.gamebook_round(action="compare")
    assert cmp["round_id"] == "2026-06-09"
    assert cmp["scoring"]["to_par"]["direction"] == "better"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_tool.py -v`
Expected: FAIL — `AttributeError: module 'trackman_mcp.server' has no attribute 'gamebook_round'`

- [ ] **Step 3a: Add the `_WRITE_LOCAL` annotation preset**

In `src/trackman_mcp/server.py`, after the line defining `_WRITE_API` (line 40), add:

```python
_WRITE_LOCAL = {"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False}
```

- [ ] **Step 3b: Add the tool + helpers** before the `# Skill prompts` divider (line 556)

```python
# --------------------------------------------------------------------------- #
# GameBook rounds (on-course data ingested from screenshots)
# --------------------------------------------------------------------------- #


def _gamebook_save(record: dict[str, Any]) -> dict[str, Any]:
    from . import gamebook_analysis as ga
    from . import gamebook_store

    record = dict(record)
    problems = ga.self_check(record)
    if problems:
        return {"saved": False, "problems": problems,
                "message": "Read failed self-check — re-check these holes before saving."}

    record["scoring"] = ga.scoring_from_holes(record.get("holes") or [])
    record.setdefault("source", "golf-gamebook")

    # Derive id from date, suffixing on same-day collisions with a different round.
    base = record.get("id") or record.get("date") or "round"
    rid, n = base, 1
    while (existing := gamebook_store.get_round(rid)) is not None and existing.get("date") != record.get("date") or \
            (gamebook_store.get_round(rid) is not None and rid != base and False):
        n += 1
        rid = f"{base}-{n}"
    # Simpler, correct collision handling: only suffix when a DIFFERENT round holds the id.
    rid, n = base, 1
    while True:
        existing = gamebook_store.get_round(rid)
        if existing is None or existing.get("result", {}).get("gross") == record.get("result", {}).get("gross"):
            break
        n += 1
        rid = f"{base}-{n}"
    record["id"] = rid

    saved = gamebook_store.save_round(record)
    return {"saved": True, "round": saved,
            "stored_count": len(gamebook_store.list_rounds())}


def _gamebook_list() -> dict[str, Any]:
    from . import gamebook_store

    rounds = gamebook_store.list_rounds()
    items = [
        {"id": r.get("id"), "date": r.get("date"),
         "course_par": (r.get("course") or {}).get("par"),
         "gross": (r.get("result") or {}).get("gross"),
         "net": (r.get("result") or {}).get("net"),
         "to_par": (r.get("scoring") or {}).get("to_par"),
         "coverage": r.get("coverage")}
        for r in rounds
    ]
    return {"count": len(items),
            "latest_id": items[0]["id"] if items else None, "items": items}


def _gamebook_compare(round_id: str | None) -> dict[str, Any]:
    from . import gamebook_analysis as ga
    from . import gamebook_store

    latest = gamebook_store.get_round(round_id) if round_id else gamebook_store.latest_round()
    if latest is None:
        return {"error": "no stored rounds to compare"}
    priors = gamebook_store.priors_of(latest["id"])
    if not priors:
        return {"round_id": latest["id"], "n_priors": 0,
                "message": "First stored round — nothing earlier to compare against yet."}
    return ga.compare_rounds(latest, priors)


@mcp.tool(annotations=_WRITE_LOCAL)
async def gamebook_round(
    action: Literal["save", "list", "get", "compare"],
    round: dict[str, Any] | None = None,
    round_id: str | None = None,
) -> dict[str, Any]:
    """On-course rounds ingested from Golf GameBook screenshots (local, last 5).

    The `gamebook-screenshot-analysis` skill extracts a round from screenshots
    and saves it here. Only score-per-hole is trusted; every other dimension
    carries a `coverage` flag (`full`|`partial`|`none`) and analysis respects it.

    Actions:
    - `save` (needs `round`): a coverage-aware record — {date, course:{par,cr,slope},
      result:{gross,net,to_par,position}, holes:[{hole,par,score,putts?,fairway?,
      gir?,bunkers?,chips?,penalties?}], coverage:{...}, dimensions:{...}}. Runs a
      self-check (hole sums vs gross/par); refuses inconsistent reads. Computes the
      `scoring` block, stores it (last 5), returns the stored record.
    - `list`: index of stored rounds (id, date, gross, net, to_par, coverage), newest first.
    - `get` (needs `round_id`): one full stored round.
    - `compare` (optional `round_id`, default latest): deterministic deltas vs the
      rounds before it — scoring always, other dimensions only where both tracked
      them. Returns measurement; the coach narrates progress from it.
    """
    from . import gamebook_store

    if action == "save":
        if not isinstance(round, dict) or not round:
            raise ValueError("gamebook_round(action='save') needs a non-empty `round`.")
        return _gamebook_save(round)
    if action == "list":
        return _gamebook_list()
    if action == "get":
        if not round_id:
            raise ValueError("gamebook_round(action='get') needs a `round_id`.")
        return gamebook_store.get_round(round_id) or {"error": f"no round {round_id}"}
    return _gamebook_compare(round_id)
```

Note: replace the tangled first `while` block above with only the second, correct one — the final implementation should contain a single collision loop:

```python
    base = record.get("id") or record.get("date") or "round"
    rid, n = base, 1
    while True:
        existing = gamebook_store.get_round(rid)
        same_round = existing is not None and \
            existing.get("result", {}).get("gross") == record.get("result", {}).get("gross")
        if existing is None or same_round:
            break
        n += 1
        rid = f"{base}-{n}"
    record["id"] = rid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_gamebook_tool.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/server.py tests/test_gamebook_tool.py
git commit -m "feat: gamebook_round tool (save/list/get/compare, self-check gate)"
```

---

### Task 6: The `gamebook-screenshot-analysis` skill + golden fixture

**Files:**
- Create: `skills/gamebook-screenshot-analysis/SKILL.md`
- Create: `skills/gamebook-screenshot-analysis/PROMPT.md`
- Create: `tests/fixtures/gamebook/2026-06-09.json`
- Test: `tests/test_gamebook_skill.py`

**Interfaces:**
- Consumes: the `gamebook_round` tool contract (Task 5).
- Produces: two skill docs and a golden record fixture. SKILL.md may use subagent language; PROMPT.md may NOT.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gamebook_skill.py
from __future__ import annotations

import json
from pathlib import Path

from trackman_mcp import gamebook_analysis as ga
from trackman_mcp import prompts

FIXTURE = Path(__file__).parent / "fixtures" / "gamebook" / "2026-06-09.json"


def _skill_body(name: str) -> str:
    return next(s for s in prompts.load_skills() if s.name == name).body.lower()


def test_skill_is_served_as_prompt():
    names = {s.name for s in prompts.load_skills()}
    assert "gamebook-screenshot-analysis" in names


def test_skill_prompt_has_no_claude_code_only_language():
    body = _skill_body("gamebook-screenshot-analysis")
    assert "subagent" not in body
    assert "forked" not in body


def test_skill_mentions_coverage_and_scoring_truth():
    body = _skill_body("gamebook-screenshot-analysis")
    assert "coverage" in body
    assert "gamebook_round" in body
    assert "self-check" in body or "self check" in body


def test_golden_fixture_matches_analytics():
    record = json.loads(FIXTURE.read_text())
    assert ga.self_check(record) == []
    scoring = ga.scoring_from_holes(record["holes"])
    assert scoring == record["scoring"]
    assert record["coverage"]["scoring"] == "full"
    assert record["coverage"]["gir"] in ("partial", "none")
    assert record["dimensions"]["sand_save"]["coverage"] == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_skill.py -v`
Expected: FAIL — `StopIteration` / file-not-found (skill + fixture missing)

- [ ] **Step 3a: Write the golden fixture** `tests/fixtures/gamebook/2026-06-09.json`

```json
{
  "id": "2026-06-09",
  "date": "2026-06-09",
  "source": "golf-gamebook",
  "course": {"par": 70, "cr": 68.1, "slope": 119, "name": null},
  "result": {"gross": 109, "net": 62, "to_par": 39, "position": "1/4"},
  "holes": [
    {"hole": 1, "par": 4, "score": 7, "putts": 2, "fairway": "hit", "gir": false, "bunkers": 0, "chips": 0, "penalties": 0},
    {"hole": 2, "par": 3, "score": 5, "putts": 2, "fairway": "na", "gir": false, "bunkers": 0, "chips": 2, "penalties": 0},
    {"hole": 3, "par": 4, "score": 6, "putts": 2, "fairway": "hit", "gir": false, "bunkers": 0, "chips": 2, "penalties": 0},
    {"hole": 4, "par": 4, "score": 6, "putts": null, "fairway": null, "gir": false, "bunkers": 0, "chips": 0, "penalties": 0},
    {"hole": 5, "par": 3, "score": 4, "putts": 3, "fairway": "na", "gir": true, "bunkers": 0, "chips": 1, "penalties": 0},
    {"hole": 6, "par": 5, "score": 6, "putts": 2, "fairway": "hit", "gir": false, "bunkers": 0, "chips": 1, "penalties": 0},
    {"hole": 7, "par": 3, "score": 4, "putts": 2, "fairway": "na", "gir": false, "bunkers": 0, "chips": 1, "penalties": 0},
    {"hole": 8, "par": 4, "score": 5, "putts": 2, "fairway": "miss_right", "gir": false, "bunkers": 0, "chips": 2, "penalties": 0},
    {"hole": 9, "par": 5, "score": 6, "putts": 2, "fairway": "miss_right", "gir": false, "bunkers": 0, "chips": 0, "penalties": 0},
    {"hole": 10, "par": 4, "score": 5, "putts": 2, "fairway": "hit", "gir": false, "bunkers": 0, "chips": 2, "penalties": 0},
    {"hole": 11, "par": 4, "score": 7, "putts": null, "fairway": null, "gir": false, "bunkers": 0, "chips": null, "penalties": 0},
    {"hole": 12, "par": 4, "score": 5, "putts": null, "fairway": null, "gir": false, "bunkers": 0, "chips": null, "penalties": 0},
    {"hole": 13, "par": 5, "score": 8, "putts": 4, "fairway": null, "gir": false, "bunkers": 0, "chips": 1, "penalties": 0},
    {"hole": 14, "par": 3, "score": 6, "putts": null, "fairway": "na", "gir": false, "bunkers": 0, "chips": null, "penalties": 0},
    {"hole": 15, "par": 5, "score": 7, "putts": 2, "fairway": null, "gir": false, "bunkers": 0, "chips": 0, "penalties": 0},
    {"hole": 16, "par": 3, "score": 9, "putts": null, "fairway": "na", "gir": false, "bunkers": 3, "chips": 0, "penalties": 0},
    {"hole": 17, "par": 4, "score": 6, "putts": 2, "fairway": null, "gir": false, "bunkers": 0, "chips": 0, "penalties": 0},
    {"hole": 18, "par": 3, "score": 7, "putts": null, "fairway": "na", "gir": false, "bunkers": 0, "chips": 0, "penalties": 1}
  ],
  "scoring": {
    "to_par": 39,
    "distribution": {"eagle_or_better": 0, "birdie": 0, "par": 0, "bogey": 7, "double": 5, "triple_plus": 6},
    "by_par_type": {"par3": 2.83, "par4": 1.88, "par5": 1.75}
  },
  "dimensions": {
    "putts": {"total": 27, "holes_tracked": 12, "coverage": "partial"},
    "fairways": {"hit": 4, "tracked": 6, "eligible": 12, "coverage": "partial"},
    "gir": {"hit": 1, "tracked": 12, "coverage": "partial"},
    "bunkers": {"total": 3, "coverage": "partial"},
    "chips": {"total": 12, "coverage": "partial"},
    "penalties": {"total": 1, "coverage": "partial"},
    "sand_save": {"value": null, "coverage": "none"},
    "up_and_down": {"value": null, "coverage": "none"},
    "scrambling": {"value": null, "coverage": "none"}
  },
  "coverage": {"scoring": "full", "putts": "partial", "fairways": "partial", "gir": "partial", "short_game": "none"},
  "notes": [
    "GIR: scorecard shows 1/18 (hole 5) but the Stats dial reads ~8% — treated as low-confidence.",
    "Sand save / up-and-down / scrambling shown as 0.0% with no hole-level data -> coverage none, not a real zero."
  ]
}
```

- [ ] **Step 3b: Write** `skills/gamebook-screenshot-analysis/SKILL.md`

````markdown
---
name: gamebook-screenshot-analysis
description: Use to ingest Golf GameBook round screenshots (Round Summary + Statistics) into the coach. Extracts a coverage-aware round from the images, self-checks the read, stores it via the gamebook_round MCP tool (rolling last 5), and returns a normalized summary plus scoring-led progress vs prior rounds. Only score-per-hole is trusted; every other stat is flagged by how completely it was tracked.
---

# GameBook Screenshot Analysis

Turn the user's Golf GameBook screenshots into a structured on-course round the
coach can use. GameBook has no export/API, but the data is on the user's phone as
screenshots — read them directly.

## The one rule that governs everything

GameBook reliably records only **score-per-hole**. Putts, fairways, GIR, chips,
bunkers, scrambling, up-and-down and sand saves are only as complete as what the
golfer tapped in during the round. **Never analyze a dimension that wasn't really
tracked.** A "0.0%" sand-save/up-and-down/scrambling with no supporting hole data
means "not entered," not a genuine zero. Flag coverage; do not invent.

## Run this off the main thread

This reads several images (large tokens). In Claude Code, the main agent should
dispatch ONE fresh subagent (Task/Agent tool, `general-purpose`) whose prompt is:
"Follow the gamebook-screenshot-analysis skill end to end on these image paths:
<paths> and return only the final summary." The subagent does the work and
returns just the summary. If you are that dispatched worker, proceed.

## Reading the screens (legend)

- **Header:** the big number is **gross** (it may sit partly behind the "Net
  score" label — it's still the round total; confirm it equals Out+In). "Net
  score" + a coloured +/- chip = net and net-to-par. "Position x/y" = group finish.
- **Scorecard rows:** HCP, Par, Score, Net, then Putts, Fairways, GIR, Bunkers,
  Chips, Penalties, with an Out/In total column. A **blank cell means not entered
  → `null`, never 0.**
- **Fairway icons:** ✓ = hit, → = missed right, ← = missed left; blank on a par 3
  = `na`. The Out/In fairway total (e.g. 3/5) counts only *tracked* driving holes.
- **GIR icons:** ✓ = green hit; an arrow (↑ ↓ ← →) = missed that way (still a
  miss). If the per-hole card and the Statistics dial disagree, **trust the card**
  (this round: card 1/18 vs dial 8%).
- **Statistics → Scores** gives bogey/double/worse counts and par-type averages —
  use them to **cross-check** the per-hole read, not as the source.
- **The 0.0% trap:** Scrambling / Up-and-Down / Sand save at 0.0% with no
  hole-level chip/bunker data means *not tracked* → coverage `none`, not a real 0.

## Workflow

1. **Group the images into one round.** A round is usually 2 scorecard halves
   (front/back) plus optional Statistics pages. The **scorecard is the source of
   truth**; Statistics pages are used only to validate and to read miss-direction
   splits. If only the scorecard is provided, that's fine — you still get the
   reliable scoring dimension.

2. **Extract per hole** from the scorecard: `par`, `score`, and when present
   `putts`, `fairway` (`hit`/`miss_left`/`miss_right`/`na` on par 3s),
   `gir` (bool), `bunkers`, `chips`, `penalties`. Use `null` for any hole where a
   value isn't shown. Read the course `par`, `CR`, `slope`, and the header
   `gross`/`net`/`position`.

3. **Assign coverage per dimension** (`full`/`partial`/`none`): full if tracked on
   ~90%+ of eligible holes (fairways exclude par 3s), partial if some, none if
   zero. Any Statistics-page rate (sand save, up-and-down, scrambling) with no
   hole-level backing is `none`. If a Statistics number contradicts the
   scorecard, keep the scorecard and add a `notes` entry.

4. **Self-check before saving.** Confirm hole scores sum to gross, hole pars sum
   to course par, and there are 9 or 18 holes. If anything fails, show the user
   the holes you're unsure about and fix the read — do not save a wrong round.

5. **Save** by calling `gamebook_round(action="save", round=<record>)`. The record
   shape is in the tool docs; the tool computes the `scoring` block and stores it
   (rolling last 5). If it returns `saved: false`, resolve the `problems` and retry.

6. **Report progress.** Call `gamebook_round(action="compare")`. Summarize the
   latest round and its direction of travel vs prior rounds — **confidently on
   scoring, and on any other dimension only where `comparable` is true** — then
   hand off to `golf-coaching` for the practice prescription.

## Output format (this skill's return value)

```
## GameBook round — <date> (<course par>, gross <gross> / net <net>)

<one-line headline: to-par and the scoring shape>

**Scoring (reliable):** +<to_par>; <bogey>/<double>/<triple_plus> spread;
par-3 <+x.xx>, par-4 <+x.xx>, par-5 <+x.xx>.

**Tracked this round:** putts <coverage>, fairways <coverage>, GIR <coverage>,
short game <coverage>. <one line naming what's too sparse to judge>

**Progress vs last <n> rounds:** <to-par direction + par-type direction; putts
direction only if comparable; "accuracy not comparable — not tracked in enough
rounds" otherwise>

<Notes: any scorecard-vs-stats discrepancies>
```

Keep it factual. No drills here — `golf-coaching` prescribes from this.
````

- [ ] **Step 3c: Write** `skills/gamebook-screenshot-analysis/PROMPT.md` (served body — **no** "subagent"/"forked" words)

````markdown
# GameBook Screenshot Analysis

Turn the user's Golf GameBook screenshots into a structured on-course round the
coach can use. GameBook has no export/API — read the screenshots directly.

## The one rule that governs everything

GameBook reliably records only **score-per-hole**. Putts, fairways, GIR, chips,
bunkers, scrambling, up-and-down and sand saves are only as complete as what the
golfer tapped in. **Never analyze a dimension that wasn't really tracked.** A
"0.0%" sand-save/up-and-down/scrambling with no supporting hole data means "not
entered," not a genuine zero. Flag coverage; do not invent.

## Reading the screens (legend)

- **Header:** the big number is **gross** (it may sit partly behind the "Net
  score" label — it's still the round total; confirm it equals Out+In). "Net
  score" + a coloured +/- chip = net and net-to-par. "Position x/y" = group finish.
- **Scorecard rows:** HCP, Par, Score, Net, then Putts, Fairways, GIR, Bunkers,
  Chips, Penalties, with an Out/In total column. A **blank cell means not entered
  → `null`, never 0.**
- **Fairway icons:** ✓ = hit, → = missed right, ← = missed left; blank on a par 3
  = `na`. The Out/In fairway total counts only *tracked* driving holes.
- **GIR icons:** ✓ = green hit; an arrow (↑ ↓ ← →) = missed that way (still a
  miss). If the per-hole card and the Statistics dial disagree, **trust the card**.
- **Statistics → Scores** gives bogey/double/worse counts and par-type averages —
  use them to **cross-check** the per-hole read, not as the source.
- **The 0.0% trap:** Scrambling / Up-and-Down / Sand save at 0.0% with no
  hole-level data means *not tracked* → coverage `none`, not a real 0.

## Workflow

1. **Group the images into one round** — usually 2 scorecard halves plus optional
   Statistics pages. The **scorecard is the source of truth**; Statistics pages
   only validate and give miss-direction splits. Scorecard-only is fine.

2. **Extract per hole** from the scorecard: `par`, `score`, and when shown
   `putts`, `fairway` (`hit`/`miss_left`/`miss_right`/`na`), `gir`, `bunkers`,
   `chips`, `penalties` — `null` where absent. Read course `par`/`CR`/`slope` and
   the header `gross`/`net`/`position`.

3. **Assign coverage per dimension** (`full`/`partial`/`none`): full at ~90%+ of
   eligible holes (fairways exclude par 3s), partial if some, none if zero. Any
   Statistics rate with no hole-level backing is `none`. Scorecard wins ties;
   record contradictions in `notes`.

4. **Self-check before saving:** hole scores sum to gross, hole pars sum to
   course par, 9 or 18 holes. If anything fails, confirm the shaky holes with the
   user and fix the read first.

5. **Save** with `gamebook_round(action="save", round=<record>)` (the tool computes
   the scoring block and keeps the last 5). If it returns `saved: false`, fix the
   `problems` and retry.

6. **Report progress** with `gamebook_round(action="compare")` — confidently on
   scoring, and on other dimensions only where `comparable` is true — then use the
   `golf-coaching` prompt for the practice prescription.

Keep the summary factual and lead with the reliable scoring story. No drills
here — `golf-coaching` prescribes from this.
````

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev pytest tests/test_gamebook_skill.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
# Raw PNGs under tests/fixtures/gamebook/2026-06-09/ are gitignored (personal);
# commit the golden JSON + the eval-set manifest only.
git add skills/gamebook-screenshot-analysis \
        tests/fixtures/gamebook/2026-06-09.json \
        tests/fixtures/gamebook/2026-06-09/README.md \
        tests/test_gamebook_skill.py
git commit -m "feat: gamebook-screenshot-analysis skill + golden fixture"
```

> The 8 real screenshots (`tests/fixtures/gamebook/2026-06-09/*.png`) are already
> staged locally as the live-eval set and are gitignored; the golden JSON is the
> committed ground truth that the grader (Task 7) scores against.

---

### Task 7: Extraction grader + real-image eval harness

**Files:**
- Modify: `src/trackman_mcp/gamebook_analysis.py` (add `grade_extraction`)
- Create: `scripts/gamebook_eval.py`
- Test: `tests/test_gamebook_analysis.py`

**Why:** the extraction itself is done by Claude's vision (the skill), which can't
run in pytest. So we make the *scoring* deterministic: `grade_extraction` compares
an extracted record against the hand-verified golden fixture (Task 6) and returns
an objective accuracy score + the exact per-hole/coverage mismatches. That turns
"is the skill reading these screens right?" into a number, so the prompt can be
iterated against the real 9-June images (`tests/fixtures/gamebook/2026-06-09/`).

**Interfaces:**
- Consumes: `scoring_from_holes` (Task 1); the golden fixture (Task 6).
- Produces: `grade_extraction(extracted: dict, golden: dict) -> dict` returning
  `{"score": float, "holes_correct": int, "holes_total": int, "scoring_ok": bool,
  "coverage_ok": bool, "mismatches": list[str]}`. Weighting: per-hole par+score
  exact match 70%, scoring block 15%, coverage flags 15%.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gamebook_analysis.py
import json
from pathlib import Path

GOLDEN = Path(__file__).parent / "fixtures" / "gamebook" / "2026-06-09.json"


def test_grade_perfect_extraction_scores_100():
    golden = json.loads(GOLDEN.read_text())
    report = ga.grade_extraction(golden, golden)
    assert report["score"] == 100.0
    assert report["holes_correct"] == report["holes_total"] == 18
    assert report["mismatches"] == []


def test_grade_flags_a_wrong_hole():
    golden = json.loads(GOLDEN.read_text())
    extracted = json.loads(GOLDEN.read_text())
    extracted["holes"][15]["score"] = 5          # hole 16 was 9
    report = ga.grade_extraction(extracted, golden)
    assert report["holes_correct"] == 17
    assert report["score"] < 100.0
    assert any("hole 16" in m for m in report["mismatches"])


def test_grade_flags_wrong_coverage():
    golden = json.loads(GOLDEN.read_text())
    extracted = json.loads(GOLDEN.read_text())
    extracted["coverage"]["sand_save"] = "full"  # the 0.0% trap: should stay none/absent
    report = ga.grade_extraction(extracted, golden)
    assert report["coverage_ok"] is False
    assert any("sand_save" in m for m in report["mismatches"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -k grade -v`
Expected: FAIL — `AttributeError: ... has no attribute 'grade_extraction'`

- [ ] **Step 3a: Implement the grader**

```python
# append to src/trackman_mcp/gamebook_analysis.py

def grade_extraction(extracted: dict[str, Any], golden: dict[str, Any]) -> dict[str, Any]:
    """Score an extracted round against a hand-verified golden record.

    Weights per-hole score/par most (that's the reliable ground truth), then the
    derived scoring block, then coverage flags (getting `none` right on untracked
    dimensions matters as much as the numbers). Returns a 0–100 score and the
    exact mismatches so the skill prompt can be iterated.
    """
    mismatches: list[str] = []

    g_holes = {int(h["hole"]): h for h in golden.get("holes", [])}
    e_holes = {int(h["hole"]): h for h in extracted.get("holes", [])}
    holes_total = len(g_holes)
    holes_correct = 0
    for hole, gh in sorted(g_holes.items()):
        eh = e_holes.get(hole)
        if eh and int(eh.get("par", -1)) == int(gh["par"]) \
                and int(eh.get("score", -2)) == int(gh["score"]):
            holes_correct += 1
        else:
            got = f"{eh.get('par')}/{eh.get('score')}" if eh else "—/—"
            mismatches.append(
                f"hole {hole}: expected par {gh['par']}/score {gh['score']}, got {got}"
            )
    holes_score = holes_correct / holes_total if holes_total else 0.0

    gs = golden.get("scoring") or {}
    es = extracted.get("scoring") or scoring_from_holes(extracted.get("holes", []))
    scoring_ok = (
        es.get("to_par") == gs.get("to_par")
        and es.get("distribution") == gs.get("distribution")
        and es.get("by_par_type") == gs.get("by_par_type")
    )
    if not scoring_ok:
        mismatches.append(
            f"scoring: to_par {es.get('to_par')} vs {gs.get('to_par')}, "
            f"distribution {es.get('distribution')} vs {gs.get('distribution')}"
        )

    gc = golden.get("coverage") or {}
    ec = extracted.get("coverage") or {}
    cov_wrong = [k for k in set(gc) | set(ec) if gc.get(k) != ec.get(k)]
    coverage_ok = not cov_wrong
    for k in sorted(cov_wrong):
        mismatches.append(f"coverage[{k}]: expected {gc.get(k)!r}, got {ec.get(k)!r}")

    score = round(
        100 * (0.70 * holes_score
               + 0.15 * (1.0 if scoring_ok else 0.0)
               + 0.15 * (1.0 if coverage_ok else 0.0)),
        1,
    )
    return {"score": score, "holes_correct": holes_correct, "holes_total": holes_total,
            "scoring_ok": scoring_ok, "coverage_ok": coverage_ok, "mismatches": mismatches}
```

- [ ] **Step 3b: Write the eval harness** `scripts/gamebook_eval.py`

```python
"""Grade a live GameBook extraction against the 9-June golden fixture.

Vision extraction runs live (the gamebook-screenshot-analysis skill reads the
images in tests/fixtures/gamebook/2026-06-09/); this script measures that
extraction so the skill can be iterated objectively:

  1. Have the skill extract the fixture images to a JSON round record.
  2. python scripts/gamebook_eval.py path/to/extracted.json
  3. Read the score + mismatches, sharpen skills/gamebook-screenshot-analysis, repeat.

Exit code is nonzero when the score is below PASS_THRESHOLD.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from trackman_mcp import gamebook_analysis as ga

GOLDEN = Path(__file__).resolve().parent.parent / "tests/fixtures/gamebook/2026-06-09.json"
PASS_THRESHOLD = 95.0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: gamebook_eval.py <extracted-round.json>", file=sys.stderr)
        return 2
    extracted = json.loads(Path(argv[1]).read_text())
    golden = json.loads(GOLDEN.read_text())
    r = ga.grade_extraction(extracted, golden)
    print(f"score: {r['score']}/100  holes {r['holes_correct']}/{r['holes_total']}  "
          f"scoring_ok={r['scoring_ok']}  coverage_ok={r['coverage_ok']}")
    for m in r["mismatches"]:
        print(f"  - {m}")
    return 0 if r["score"] >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 4: Run tests + a self-eval of the golden fixture**

Run: `uv run --extra dev pytest tests/test_gamebook_analysis.py -v`
Expected: PASS (12 tests total)

Sanity-check the harness against the golden record itself (must score 100):

Run: `uv run python scripts/gamebook_eval.py tests/fixtures/gamebook/2026-06-09.json`
Expected: `score: 100.0/100  holes 18/18  scoring_ok=True  coverage_ok=True` (exit 0)

- [ ] **Step 5: Commit**

```bash
git add src/trackman_mcp/gamebook_analysis.py scripts/gamebook_eval.py tests/test_gamebook_analysis.py
git commit -m "feat: gamebook extraction grader + eval harness (scored vs golden)"
```

---

### Task 8: Wire on-course rounds into the coaching skills

**Files:**
- Modify: `skills/golf-coaching/SKILL.md`, `skills/golf-coaching/PROMPT.md`
- Modify: `skills/trackman-stats-analysis/SKILL.md`, `skills/trackman-stats-analysis/PROMPT.md`
- Test: `tests/test_gamebook_skill.py`

**Interfaces:**
- Consumes: `gamebook_round` compare output; the coverage principle.
- Produces: coaching guidance that reads GameBook rounds and respects coverage.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_gamebook_skill.py

def test_golf_coaching_reads_gamebook_rounds():
    body = _skill_body("golf-coaching")
    assert "gamebook_round" in body
    assert "coverage" in body            # must respect coverage flags


def test_stats_analysis_mentions_on_course_rounds():
    body = _skill_body("trackman-stats-analysis")
    assert "gamebook_round" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev pytest tests/test_gamebook_skill.py -k "coaching or stats" -v`
Expected: FAIL — assertions on missing `gamebook_round` text.

- [ ] **Step 3a: Add an on-course section to `skills/golf-coaching/SKILL.md` and `skills/golf-coaching/PROMPT.md`**

Append this identical block near the data-sources part of each file (adapt the surrounding heading level to match the file):

```markdown
## On-course rounds (Golf GameBook)

Real course rounds live in the `gamebook_round` tool, ingested from the user's
GameBook screenshots (see the gamebook-screenshot-analysis prompt). Call
`gamebook_round(action="compare")` to get the direction of travel across their
last few rounds.

**Lead with scoring** — to-par, the bogey/double/triple spread, and par-type
averages are always reliable. Speak to putts/fairways/greens **only where
`comparable` is true** (both rounds actually tracked it); otherwise say so plainly
("not tracked in enough rounds to judge"). Never build a drill off a `none`-coverage
stat or a "0.0%" that just means nothing was entered. Turn a backslide on a
reliable signal (e.g. par-3 scoring, triple-bogey count) into a specific practice
nudge, pulling drills from the drill-library.
```

- [ ] **Step 3b: Add a short pointer to `skills/trackman-stats-analysis/SKILL.md` and `.../PROMPT.md`**

Append to each:

```markdown
## On-course rounds

Trackman covers practice and launch-monitor data. The user's real course rounds
come from Golf GameBook via the `gamebook_round` tool (screenshot-ingested). When
diagnosing scoring/course trends, include `gamebook_round(action="compare")`, but
trust only the scoring dimension unless a stat's `coverage` is not `none`.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev pytest tests/test_gamebook_skill.py -v`
Expected: PASS (6 tests)

Then run the served-prompt guard to confirm no Claude-Code-only language leaked
into any PROMPT.md:

Run: `uv run --extra dev pytest tests/test_prompts.py -v`
Expected: PASS (existing suite still green; `gamebook-screenshot-analysis` served)

- [ ] **Step 5: Commit**

```bash
git add skills/golf-coaching skills/trackman-stats-analysis tests/test_gamebook_skill.py
git commit -m "feat: coaching skills read on-course rounds, scoring-led + coverage-gated"
```

---

### Task 9: Full-suite green + docs touch-up

**Files:**
- Modify: `CLAUDE.md` (add the skill + tool to the skill/tool listings), `README.md` (one line under skills, if it lists them)

**Interfaces:** none.

- [ ] **Step 1: Run the whole suite**

Run: `uv run --extra dev pytest -q`
Expected: PASS (all existing + new tests). If `tests/test_prompts.py` or
`tests/test_skill_content.py` assert an exact skill *set*, they use subset
(`<=`) checks, so a new skill won't break them — confirm they're still green.

- [ ] **Step 2: Update `CLAUDE.md`**

Add `gamebook_round` to the MCP Tools table (a local, deterministic tool like
`build_visualization`) and `gamebook-screenshot-analysis` to the Skills list,
with a one-line description matching this plan. Note the `gamebook-rounds.json`
store (cap 5) next to the other stores.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: document gamebook_round tool + screenshot-analysis skill"
```

- [ ] **Step 4: Final verification**

Run: `uv run --extra dev pytest -q && uv run ruff check src tests`
Expected: tests PASS; ruff clean (fix any lint before finishing).

---

## Self-Review

**Spec coverage** (against `docs/superpowers/specs/2026-07-05-gamebook-screenshot-analyzer-design.md`):
- Skill that ingests screenshots → Task 6 (SKILL.md + PROMPT.md).
- Coverage-aware record (full/partial/none) → Task 1 `coverage_flag`, Task 6 fixture + skill rules.
- Arithmetic self-check before save → Task 2 `self_check`, gated in Task 5 tool.
- Rolling last-5 store at `~/.trackman-mcp/gamebook-rounds.json` → Task 4.
- `gamebook_round(save/list/get/compare)` → Task 5.
- Scoring-led, coverage-gated newest-vs-prior deltas → Task 3 `compare_rounds` + Task 5 `compare`.
- Coaching integration, scoring-led + coverage-respecting → Task 8.
- Served as an MCP prompt like the others, no CC-only language in PROMPT.md → Task 6 test + Task 8 guard run.
- Testing (extraction contract, self-check reject, store cap, compare) → Tasks 1–6 tests + Task 9 full run.
- Extraction grader + real-image eval harness (score an extraction vs the golden 9-June round; iterate the skill objectively) → Task 7 + `tests/fixtures/gamebook/2026-06-09/` eval set + reading-legend added to the skill.
- Boundary compliance (skill extracts, server measures, skills judge) → structural across tasks.

**Placeholder scan:** No TBD/TODO; every code step has full code. The one hazard is Task 5 Step 3b, where I show a tangled collision loop then explicitly instruct to replace it with the single correct loop that follows — the implementer writes only the corrected version.

**Type consistency:** `coverage_flag/hole_result/scoring_from_holes/self_check/compare_rounds` names match between definition (Tasks 1–3) and use (Task 5). Store functions `save_round/list_rounds/get_round/latest_round/priors_of` match between Task 4 and Task 5. Record field names (`scoring.to_par`, `coverage`, `dimensions.putts.{total,holes_tracked,coverage}`) are consistent across the fixture (Task 6), analytics (Tasks 1–3), and tool (Task 5).

## Open decisions carried from the spec (already resolved here)
1. Round id = date, `-N` suffix only when a *different* round holds that date (Task 5).
2. Store path `~/.trackman-mcp/gamebook-rounds.json` (Task 4).
3. Subagent extraction lives in SKILL.md only; PROMPT.md stays client-agnostic (Task 6).
