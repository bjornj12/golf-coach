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
