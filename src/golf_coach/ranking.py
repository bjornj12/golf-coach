"""Deterministic "biggest-leak" ranking: order skill areas by leak severity.

Stage-3 of the deterministic core, downstream of the per-source analyzers
(`sources/*/analyzer.py`) and `synthesis.align`. It answers the one question
the free tier turns on — *which measured gap is costing the most* — as a
**fact**, computed from the analyzer's `Finding`s against documented,
tunable baseline bands. Like the rest of the core it renders **no verdict and
no coaching**: it ranks measurements, it does not prescribe drills or say
"you should" (see CLAUDE.md's core boundary). Interpretation stays in the
coaching skills.

Heuristic v1 scores **lateral dispersion** (the analyzer's highest-signal
shot-level measurement) per skill area. Bag *gapping* severity — which needs
the full per-club carry table to judge adjacency holes honestly — is carried
as informational (severity 0) rather than guessed from sparse shot pairs; a
strokes-gained-style model is the documented evolution. Deterministic:
identical findings in, identical ranking out.
"""

from __future__ import annotations

from pydantic import BaseModel

from .model import Coverage, Finding

# Lateral dispersion (m): at/below GOOD is tight; at/above BAD is a big leak.
# Approach shots want a tighter window than the driver, so their band is
# tighter. Tunable — v1 anchors, not gospel.
DISPERSION_BAND: dict[str, tuple[float, float]] = {
    "approach": (8.0, 25.0),
    "driving": (15.0, 45.0),
}


class RankedLeak(BaseModel):
    """One skill area, scored and ranked by measured leak severity.

    A measurement, not coaching: `severity` (0..1) and `basis` are derived
    facts; there is deliberately no drill/plan/recommendation field.
    """

    rank: int
    skill_area: str
    severity: float
    metric: str | None = None
    value: float | None = None
    unit: str | None = None
    coverage: Coverage = "none"
    headline: str = ""
    basis: str = ""


def _band_severity(value: float | None, good: float, bad: float) -> float:
    """Fraction of the way `value` sits from the GOOD to the BAD baseline,
    clamped to [0, 1]. None or a degenerate band -> 0.0."""
    if value is None or bad == good:
        return 0.0
    return round(max(0.0, min((value - good) / (bad - good), 1.0)), 3)


def _score_area(area: str, findings: list[Finding]) -> RankedLeak:
    """Score one skill area from its findings (severity + a factual basis)."""
    dispersion = [f for f in findings if f.metric == "dispersion" and f.value is not None]
    if area in DISPERSION_BAND and dispersion:
        worst = max(dispersion, key=lambda f: f.value or 0.0)
        good, bad = DISPERSION_BAND[area]
        severity = _band_severity(worst.value, good, bad)
        unit = worst.unit or "m"
        return RankedLeak(
            rank=0,
            skill_area=area,
            severity=severity,
            metric=worst.metric,
            value=worst.value,
            unit=unit,
            coverage=worst.coverage,
            headline=f"{area} lateral dispersion {worst.value} {unit}",
            basis=(
                f"σ {worst.value} {unit} vs a {good}–{bad} {unit} band "
                f"→ severity {severity}"
            ),
        )

    # Unscored in v1 (gapping / on-course areas): carry a representative fact,
    # severity 0. Prefer a bag-level spread finding for the headline when present.
    rep = next((f for f in findings if f.metric == "club_carry_spread"), findings[0])
    unit = rep.unit or ""
    return RankedLeak(
        rank=0,
        skill_area=area,
        severity=0.0,
        metric=rep.metric,
        value=rep.value,
        unit=rep.unit,
        coverage=rep.coverage,
        headline=f"{area}: {rep.metric} {rep.value} {unit}".rstrip(),
        basis="not scored in v1 (informational — needs the full per-club table)",
    )


def rank_leaks(findings: list[Finding]) -> list[RankedLeak]:
    """Rank skill areas by measured leak severity, biggest leak first.

    Groups `findings` by `skill_area`, scores each area, then sorts by severity
    descending with an alphabetical `skill_area` tie-break for determinism, and
    numbers the results from 1. Facts only — no coaching.
    """
    by_area: dict[str, list[Finding]] = {}
    for finding in findings:
        by_area.setdefault(finding.skill_area, []).append(finding)

    leaks = [_score_area(area, area_findings) for area, area_findings in by_area.items()]
    leaks.sort(key=lambda leak: (-leak.severity, leak.skill_area))
    for i, leak in enumerate(leaks, start=1):
        leak.rank = i
    return leaks
