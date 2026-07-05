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
