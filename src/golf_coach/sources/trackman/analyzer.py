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

from ...analysis import _avg, _std
from ...model import TRACKMAN_CONTEXT, ClubGapping, Finding, Session


def analyze(
    sessions: list[Session], club_gapping: ClubGapping | None = None
) -> list[Finding]:
    """Emit context-tagged Findings from Trackman shot/metric + gapping data.

    Every Finding here is `source="trackman"`, `context=TRACKMAN_CONTEXT`,
    `coverage="full"`. A session with no shots and no usable metrics
    contributes nothing. `club_gapping` (from `Source.club_gapping()`) is a
    shots-free cross-source signal: when provided, a per-club carry-spread
    `gapping` Finding is emitted so Trackman contributes even before shot-level
    enrichment lands. Empty inputs contribute nothing.
    """
    findings: list[Finding] = []
    for session in sessions:
        findings.extend(_gapping_findings(session))
        findings.extend(_dispersion_findings(session))
    if club_gapping is not None:
        findings.extend(_club_gapping_findings(club_gapping))
    return findings


def _club_gapping_findings(gapping: ClubGapping) -> list[Finding]:
    """One carry-spread `gapping` Finding from the per-club distance table.

    Uses the carry distances `ClubGapping` already carries (no shots needed):
    the spread between the shortest- and longest-carrying non-retired club, a
    factual gapping measurement the cross-source coach can weigh against
    GameBook's on-course scoring.
    """
    carries: list[tuple[str, float]] = []
    for club in gapping.clubs:
        if club.get("retired"):
            continue
        name = club.get("name")
        carry = club.get("carry")
        if name and isinstance(carry, (int, float)):
            carries.append((str(name), float(carry)))

    if not carries:
        return []

    carries.sort(key=lambda c: c[1])
    lo_name, lo = carries[0]
    hi_name, hi = carries[-1]
    spread = round(hi - lo, 2)
    detail = (
        f"{len(carries)} clubs; carry spans {lo_name} {lo}m .. {hi_name} {hi}m "
        f"(spread {spread}m)"
    )
    return [
        Finding(
            skill_area="gapping",
            source="trackman",
            context=TRACKMAN_CONTEXT,
            metric="club_carry_spread",
            value=spread,
            unit="m",
            coverage="full",
            detail=detail,
        )
    ]


def _gapping_findings(session: Session) -> list[Finding]:
    """Per-club carry gapping, from shot-level carry distances."""
    per_club: dict[str, list[float]] = {}
    for shot in session.shots:
        if shot.club and isinstance(shot.carry, (int, float)):
            per_club.setdefault(shot.club, []).append(float(shot.carry))

    if per_club:
        findings = []
        for club, carries in sorted(per_club.items()):
            avg = _avg(carries)
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
        # `_std` is population stdev for >=2 values but only defined for >=1;
        # a lone shot's "dispersion" is just its own magnitude from center.
        dispersion = _std(sides) if len(sides) >= 2 else round(abs(sides[0]), 2)
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
