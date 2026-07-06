"""Trackman per-source analyzer: shot-level Findings from the controlled range.

Trackman is the clean-room, high-precision expert — every Finding it emits
carries `coverage="full"`. There's no partial-coverage story on this source
the way there is for GameBook: if a session doesn't carry enough shot/metric
data to compute something, we simply emit nothing for it rather than guess.

No coaching opinions here (see CLAUDE.md's core boundary) — just measurement
over the shots/metrics the `Session` model already carries.
"""

from __future__ import annotations

from typing import Literal

from ...model import TRACKMAN_CONTEXT, Finding, Session


def analyze(sessions: list[Session]) -> list[Finding]:
    """Emit context-tagged Findings from Trackman shot/metric data.

    Every Finding here is `source="trackman"`, `context=TRACKMAN_CONTEXT`,
    `coverage="full"`. A session with no shots and no usable metrics
    contributes nothing.
    """
    findings: list[Finding] = []
    for session in sessions:
        findings.extend(_gapping_findings(session))
        findings.extend(_dispersion_findings(session))
    return findings


def _gapping_findings(session: Session) -> list[Finding]:
    """Per-club carry gapping, from shot-level carry distances."""
    per_club: dict[str, list[float]] = {}
    for shot in session.shots:
        if shot.club and isinstance(shot.carry, (int, float)):
            per_club.setdefault(shot.club, []).append(float(shot.carry))

    if per_club:
        findings = []
        for club, carries in sorted(per_club.items()):
            avg = _mean(carries)
            findings.append(
                Finding(
                    skill_area="gapping",
                    source="trackman",
                    context=TRACKMAN_CONTEXT,
                    metric="carry_avg",
                    value=avg,
                    unit="m",
                    coverage="full",
                    detail=f"{club}: avg carry {avg}m over {len(carries)} shot(s)",
                )
            )
        return findings

    # No shot-level carry data on this session — fall back to a session-level
    # carry metric, if the source happened to attach one.
    carry_metric = session.metrics.get("avg_carry")
    if carry_metric is not None and carry_metric.value is not None:
        unit = carry_metric.unit or "m"
        return [
            Finding(
                skill_area="gapping",
                source="trackman",
                context=TRACKMAN_CONTEXT,
                metric="carry_avg",
                value=carry_metric.value,
                unit=unit,
                coverage="full",
                detail=f"avg carry {carry_metric.value}{unit}",
            )
        ]
    return []


def _dispersion_findings(session: Session) -> list[Finding]:
    """Lateral miss-pattern (side) dispersion, grouped driving vs. approach."""
    by_skill_area: dict[Literal["driving", "approach"], list[float]] = {}
    for shot in session.shots:
        if not isinstance(shot.side, (int, float)):
            continue
        by_skill_area.setdefault(_dispersion_skill_area(shot.club), []).append(float(shot.side))

    findings = []
    for skill_area in sorted(by_skill_area):
        sides = by_skill_area[skill_area]
        dispersion = _stdev(sides)
        findings.append(
            Finding(
                skill_area=skill_area,
                source="trackman",
                context=TRACKMAN_CONTEXT,
                metric="dispersion",
                value=dispersion,
                unit="m",
                coverage="full",
                detail=f"lateral dispersion {dispersion}m over {len(sides)} shot(s)",
            )
        )
    return findings


def _dispersion_skill_area(club: str | None) -> Literal["driving", "approach"]:
    return "driving" if club and "driver" in club.lower() else "approach"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _stdev(values: list[float]) -> float:
    """Population stdev for >=2 values; the plain magnitude for a single shot."""
    if len(values) < 2:
        return round(abs(values[0]), 2)
    mean = sum(values) / len(values)
    return round((sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5, 2)
