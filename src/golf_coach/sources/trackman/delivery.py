"""Driver-delivery facts: what the club did at impact, and how it sits against
efficient reference windows. This is the "why" behind the ball flight — path,
face-to-path, spin axis (the curve), and the spin/attack that govern distance.

Facts only (CLAUDE.md core boundary): every value is a measurement or a
measurement-vs-published-window comparison. Stating "spin 4219 rpm is above the
2000–2800 driver window" is a fact; the *fix* (the drill) is the coaching
skills' job, never here. Reference windows are established driver launch-condition
targets — tunable, not gospel.
"""

from __future__ import annotations

import math

from ...analysis import _avg
from ...model import TRACKMAN_CONTEXT, Finding, Session

# Efficient driver reference windows (facts, tunable).
SPIN_WINDOW = (2000.0, 2800.0)  # rpm
ATTACK_WINDOW = (2.0, 5.0)  # deg (up)


def _is_driver(club: str | None) -> bool:
    return bool(club) and "driver" in club.lower()


def _finding(metric: str, value: float, unit: str, detail: str) -> Finding:
    return Finding(
        skill_area="driving",
        source="trackman",
        context=TRACKMAN_CONTEXT,
        metric=metric,
        value=value,
        unit=unit,
        coverage="full",
        detail=detail,
    )


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def driver_delivery(sessions: list[Session]) -> list[Finding]:
    """Aggregate driver club-delivery facts across `sessions` (driver shots only).

    Emits one Finding per available metric — club path, face-to-path, spin axis
    (curve), spin rate, attack angle, dynamic loft — each with a factual
    window/flag in `detail`. Empty when there are no driver shots with delivery data.
    """
    shots = [s for sess in sessions for s in sess.shots if _is_driver(s.club)]
    if not shots:
        return []

    def avg(getter) -> float | None:
        vals = [v for v in (_num(getter(s)) for s in shots) if v is not None]
        return _avg(vals) if vals else None

    findings: list[Finding] = []

    path = avg(lambda s: s.club_path)
    if path is not None:
        side = "in-to-out" if path > 0 else "out-to-in" if path < 0 else "square"
        findings.append(_finding("club_path", path, "deg", f"{abs(path)}° {side}"))

    # face-to-path per shot (face angle relative to the swing path) then averaged.
    ftp = [
        s.face_angle - s.club_path
        for s in shots
        if _num(s.face_angle) is not None and _num(s.club_path) is not None
    ]
    if ftp:
        v = _avg(ftp)
        rel = "open to path" if v > 0 else "closed to path" if v < 0 else "square to path"
        findings.append(_finding("face_to_path", v, "deg", f"{abs(v)}° {rel}"))

    # spin axis per shot from side/back spin (the curve): +right, -left.
    axis = [
        math.degrees(math.atan2(s.side_spin, s.back_spin))
        for s in shots
        if _num(s.side_spin) is not None and _num(s.back_spin) not in (None, 0)
    ]
    if axis:
        v = round(_avg(axis), 2)
        curve = "right — curves right" if v > 0 else "left — curves left" if v < 0 else "straight"
        findings.append(_finding("spin_axis", v, "deg", f"{abs(v)}° tilt {curve}"))

    spin = avg(lambda s: s.spin if _num(s.spin) is not None else s.back_spin)
    if spin is not None:
        lo, hi = SPIN_WINDOW
        if spin > hi:
            flag = f"above the {lo:.0f}–{hi:.0f} rpm window (+{spin - hi:.0f})"
        elif spin < lo:
            flag = f"below the {lo:.0f}–{hi:.0f} rpm window (-{lo - spin:.0f})"
        else:
            flag = f"in the {lo:.0f}–{hi:.0f} rpm window"
        findings.append(_finding("spin_rate", spin, "rpm", flag))

    attack = avg(lambda s: s.attack_angle)
    if attack is not None:
        lo, hi = ATTACK_WINDOW
        if attack < lo:
            flag = f"shallow — below the +{lo:.0f}–+{hi:.0f}° up-attack window"
        elif attack > hi:
            flag = f"steep — above +{hi:.0f}°"
        else:
            flag = f"in the +{lo:.0f}–+{hi:.0f}° window"
        findings.append(_finding("attack_angle", attack, "deg", flag))

    dyn_loft = avg(lambda s: s.dynamic_loft)
    if dyn_loft is not None:
        findings.append(_finding("dynamic_loft", dyn_loft, "deg", f"{dyn_loft}° presented at impact"))

    return findings
