"""Tests for driver-delivery facts (golf_coach.sources.trackman.delivery).

Facts only: measurements + window flags, no coaching.
"""

from __future__ import annotations

from golf_coach.model import TRACKMAN_CONTEXT, Session, Shot
from golf_coach.sources.trackman.delivery import driver_delivery


def _session(shots: list[Shot]) -> Session:
    return Session(source="trackman", context=TRACKMAN_CONTEXT, id="s", shots=shots)


def _driver(**kw) -> Shot:
    return Shot(club="Driver", **kw)


def _by_metric(findings):
    return {f.metric: f for f in findings}


def test_no_driver_shots_yields_nothing():
    assert driver_delivery([]) == []
    iron = _session([Shot(club="7Iron", club_path=-3.0)])
    assert driver_delivery([iron]) == []


def test_club_path_out_to_in_is_a_fact():
    s = _session([_driver(club_path=-6.0), _driver(club_path=-4.0)])
    path = _by_metric(driver_delivery([s]))["club_path"]
    assert path.value == -5.0
    assert "out-to-in" in path.detail


def test_face_to_path_derived_from_face_and_path():
    # face_angle - club_path: (-1 - -6)=5, (-1 - -4)=3 -> avg 4 (open to path)
    s = _session([_driver(face_angle=-1.0, club_path=-6.0), _driver(face_angle=-1.0, club_path=-4.0)])
    ftp = _by_metric(driver_delivery([s]))["face_to_path"]
    assert ftp.value == 4.0
    assert "open to path" in ftp.detail


def test_spin_rate_above_window_is_flagged():
    s = _session([_driver(spin=4000.0), _driver(spin=4400.0)])
    spin = _by_metric(driver_delivery([s]))["spin_rate"]
    assert spin.value == 4200.0
    assert "above" in spin.detail


def test_attack_angle_below_window_is_shallow():
    s = _session([_driver(attack_angle=0.0), _driver(attack_angle=1.0)])
    attack = _by_metric(driver_delivery([s]))["attack_angle"]
    assert attack.value == 0.5
    assert "shallow" in attack.detail


def test_spin_axis_right_from_side_and_back_spin():
    s = _session([_driver(side_spin=900.0, back_spin=4000.0)])
    axis = _by_metric(driver_delivery([s]))["spin_axis"]
    assert axis.value > 0  # positive side spin -> right tilt
    assert "right" in axis.detail


def test_all_facts_no_coaching_words():
    s = _session([_driver(club_path=-5.2, face_angle=-0.9, spin=4219.0, attack_angle=0.5,
                          dynamic_loft=19.7, side_spin=920.0, back_spin=4100.0)])
    findings = driver_delivery([s])
    metrics = {f.metric for f in findings}
    assert {"club_path", "face_to_path", "spin_rate", "attack_angle", "spin_axis", "dynamic_loft"} <= metrics
    # facts only — no drill/verdict language leaks into the detail strings
    blob = " ".join(f.detail for f in findings).lower()
    for word in ("should", "drill", "practice", "work on", "fix"):
        assert word not in blob
