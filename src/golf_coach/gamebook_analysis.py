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

    bad_holes = []
    for i, h in enumerate(holes):
        try:
            int(h["score"])
            int(h["par"])
        except (KeyError, TypeError, ValueError):
            bad_holes.append(h.get("hole", i + 1))
    if bad_holes:
        problems.append(f"holes with missing or unreadable par/score: {bad_holes}")
        return problems

    gross = sum(int(h["score"]) for h in holes)
    stated_gross = (record.get("result") or {}).get("gross")
    if stated_gross is not None and gross != int(stated_gross):
        problems.append(f"hole scores sum to {gross} but stated gross is {stated_gross}")

    par_total = sum(int(h["par"]) for h in holes)
    course_par = (record.get("course") or {}).get("par")
    if course_par is not None and par_total != int(course_par):
        problems.append(f"hole pars sum to {par_total} but course par is {course_par}")

    return problems


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
    if not priors:
        return {"round_id": latest.get("id"), "n_priors": 0,
                "scoring": {}, "dimensions": {}, "comparable": {}}
    out: dict[str, Any] = {
        "round_id": latest.get("id"),
        "n_priors": len(priors),
        "scoring": {},
        "dimensions": {},
        "comparable": {},
    }
    ls = latest["scoring"]
    to_par_mean = _mean([float(p["scoring"]["to_par"]) for p in priors])
    if to_par_mean is not None:
        out["scoring"]["to_par"] = _delta_block(
            "to_par", float(ls["to_par"]), to_par_mean
        )
    for k in ("par3", "par4", "par5"):
        lv = ls["by_par_type"].get(k)
        pv = _mean([p["scoring"]["by_par_type"][k] for p in priors
                    if k in p["scoring"]["by_par_type"]])
        if lv is not None and pv is not None:
            out["scoring"][k] = _delta_block(k, float(lv), pv)

    # Putts/hole — only if latest and ALL priors tracked putts with a numeric total.
    def _has_putts(r):
        d = (r.get("dimensions") or {}).get("putts") or {}
        return _tracked(r, "putts") and isinstance(d.get("total"), (int, float))

    if _has_putts(latest) and all(_has_putts(p) for p in priors):
        def pph(r: dict[str, Any]) -> float:
            d = r["dimensions"]["putts"]
            return round(d["total"] / max(d["holes_tracked"], 1), 2)
        pph_mean = _mean([pph(p) for p in priors])
        if pph_mean is not None:
            out["dimensions"]["putts_per_hole"] = _delta_block(
                "putts_per_hole", pph(latest), pph_mean
            )
    else:
        out["dimensions"]["putts_per_hole"] = {"skipped": "coverage"}

    # Report (but don't compute) whether accuracy dims are comparable.
    for dim in ("fairways", "gir"):
        out["comparable"][dim] = _tracked(latest, dim) and all(
            _tracked(p, dim) for p in priors
        )
    return out


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
        matched = False
        if eh:
            try:
                matched = int(eh.get("par")) == int(gh["par"]) \
                    and int(eh.get("score")) == int(gh["score"])
            except (TypeError, ValueError):
                matched = False
        if matched:
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
            f"distribution {es.get('distribution')} vs {gs.get('distribution')}, "
            f"by_par_type {es.get('by_par_type')} vs {gs.get('by_par_type')}"
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
