"""GameBook per-source analyzer: on-course Findings from stored rounds.

GameBook is the on-course expert — the scoring truth, at the cost of only
partial coverage on everything else (putts, fairways, GIR — see
`gamebook_analysis.py`'s module docstring for why). This module turns the
latest stored round into `Finding`s a downstream cross-source normalizer can
align against Trackman's controlled-range Findings.

No coaching opinions here (see CLAUDE.md's core boundary) — scoring facts and
coverage-gated dimension facts only, with `direction` set from the existing
deterministic `compare_rounds` helper rather than anything re-derived here.
"""

from __future__ import annotations

from typing import Any, Literal

from ...gamebook_analysis import _mean, compare_rounds
from ...model import GAMEBOOK_CONTEXT, Finding, Round

_SkillArea = Literal["driving", "approach", "short_game", "putting", "scoring", "gapping"]
_Direction = Literal["better", "worse", "same"]

# (distribution key, human label) for the "worse than par" bucket summary in
# the scoring Finding's `detail` — eagle/birdie/par aren't newsworthy there.
_WORSE_THAN_PAR_LABELS: tuple[tuple[str, str], ...] = (
    ("bogey", "bogey"),
    ("double", "double"),
    ("triple_plus", "triple+"),
)

# (dimension key in Round.dimensions/coverage, skill_area, Finding.metric, detail label)
_DIMENSION_FINDINGS: tuple[tuple[str, _SkillArea, str, str], ...] = (
    ("putts", "putting", "putts", "Putts"),
    ("gir", "approach", "gir_hit", "GIR"),
    ("fairways", "driving", "fairways_hit", "Fairways hit"),
)


def analyze(rounds: list[Round]) -> list[Finding]:
    """Emit context-tagged Findings for the latest GameBook round.

    `rounds` need not already be sorted — the latest is picked by `date`
    (ties/missing dates fall back to input order). With >= 2 rounds, the
    scoring Findings (and the putting Finding, when comparable) carry a
    `direction` from `compare_rounds` against every round older than the
    latest. Dimension Findings (putting/approach/driving) are only emitted
    when that dimension's coverage isn't "none".
    """
    if not rounds:
        return []

    ordered = sorted(rounds, key=lambda r: r.date or "", reverse=True)
    latest, *priors = ordered

    comparison: dict[str, Any] | None = None
    if priors:
        comparison = compare_rounds(latest.model_dump(), [p.model_dump() for p in priors])

    findings = _scoring_findings(latest, comparison)
    findings.extend(_dimension_findings(latest, priors))
    return findings


def _scoring_findings(latest: Round, comparison: dict[str, Any] | None) -> list[Finding]:
    scoring = latest.scoring or {}
    to_par = scoring.get("to_par")
    findings = [
        Finding(
            skill_area="scoring",
            source="gamebook",
            context=GAMEBOOK_CONTEXT,
            metric="to_par",
            value=float(to_par) if to_par is not None else None,
            coverage="full",
            direction=_direction(comparison, "scoring", "to_par"),
            detail=_to_par_detail(to_par, scoring.get("distribution") or {}),
        )
    ]

    by_par_type = scoring.get("by_par_type") or {}
    for key in ("par3", "par4", "par5"):
        if key not in by_par_type:
            continue
        avg = by_par_type[key]
        findings.append(
            Finding(
                skill_area="scoring",
                source="gamebook",
                context=GAMEBOOK_CONTEXT,
                metric=key,
                value=float(avg),
                coverage="full",
                direction=_direction(comparison, "scoring", key),
                detail=f"{key}: avg {avg:+.2f} vs par",
            )
        )
    return findings


def _dimension_findings(latest: Round, priors: list[Round]) -> list[Finding]:
    findings: list[Finding] = []
    for dim_key, skill_area, metric, label in _DIMENSION_FINDINGS:
        metric_obj = latest.dimensions.get(dim_key)
        if metric_obj is None or metric_obj.coverage == "none":
            continue
        direction = _putting_direction(latest, priors) if dim_key == "putts" else None
        findings.append(
            Finding(
                skill_area=skill_area,
                source="gamebook",
                context=GAMEBOOK_CONTEXT,
                metric=metric,
                value=metric_obj.value,
                unit=metric_obj.unit,
                coverage=metric_obj.coverage,
                direction=direction,
                detail=f"{label}: {metric_obj.value}",
            )
        )
    return findings


def _putting_direction(latest: Round, priors: list[Round]) -> _Direction | None:
    """Putting trend from the normalized model directly (fewer putts = better).

    Compares the latest round's `dimensions["putts"].value` to the mean of the
    priors' — but only when putts coverage is real (not "none") and a value is
    present on the latest AND every prior. Otherwise the trend isn't
    comparable, so we return None. (Computed here rather than via
    `compare_rounds`, which reads raw `total`/`holes_tracked` keys the
    normalized `Metric` doesn't carry.)
    """
    if not priors:
        return None
    latest_putts = latest.dimensions.get("putts")
    if latest_putts is None or latest_putts.coverage == "none" or latest_putts.value is None:
        return None

    prior_values: list[float] = []
    for prior in priors:
        putts = prior.dimensions.get("putts")
        if putts is None or putts.coverage == "none" or putts.value is None:
            return None
        prior_values.append(putts.value)

    prior_mean = _mean(prior_values)
    if prior_mean is None:  # unreachable (prior_values is non-empty here), but keeps mypy happy
        return None
    if latest_putts.value < prior_mean:
        return "better"
    if latest_putts.value > prior_mean:
        return "worse"
    return "same"


def _direction(comparison: dict[str, Any] | None, block: str, key: str) -> _Direction | None:
    """Pull `direction` out of a `compare_rounds` block, or None if not comparable."""
    if not comparison:
        return None
    entry = (comparison.get(block) or {}).get(key)
    if not entry:
        return None
    direction = entry.get("direction")
    if direction in ("better", "worse", "same"):
        return direction
    return None


def _to_par_detail(to_par: int | float | None, distribution: dict[str, Any]) -> str:
    if to_par is None:
        return "to par: n/a"
    bits = [f"{to_par:+.0f} to par"]
    worse = [
        f"{distribution[key]} {label}"
        for key, label in _WORSE_THAN_PAR_LABELS
        if distribution.get(key)
    ]
    if worse:
        bits.append(" / ".join(worse))
    return "; ".join(bits)
