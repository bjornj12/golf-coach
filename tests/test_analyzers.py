"""Tests for the per-source expert analyzers (gamebook, trackman).

Each analyzer turns a source's already-normalized model objects (`Round` /
`Session`) into context-tagged `Finding`s — measurement, not coaching (see
CLAUDE.md's boundary). These tests build model objects directly; they don't
need the on-disk stores the sources normally read from.
"""

from __future__ import annotations

from golf_coach.model import (
    GAMEBOOK_CONTEXT,
    TRACKMAN_CONTEXT,
    ClubGapping,
    Course,
    Metric,
    Round,
    RoundResult,
    Session,
    Shot,
)
from golf_coach.sources.gamebook import analyzer as gamebook_analyzer
from golf_coach.sources.trackman import analyzer as trackman_analyzer


def _round(
    round_id: str,
    date: str,
    to_par: int,
    by_par_type: dict[str, float],
    *,
    putts_value: float = 27.0,
    putts_coverage: str = "full",
    gir_coverage: str = "partial",
    fairways_coverage: str = "none",
) -> Round:
    return Round(
        source="gamebook",
        context=GAMEBOOK_CONTEXT,
        id=round_id,
        date=date,
        course=Course(par=70),
        result=RoundResult(gross=70 + to_par, to_par=to_par),
        scoring={
            "to_par": to_par,
            "distribution": {"bogey": 7, "double": 5, "triple_plus": 6},
            "by_par_type": by_par_type,
        },
        dimensions={
            "putts": Metric(name="putts", value=putts_value, coverage=putts_coverage),
            "gir": Metric(name="gir", value=1.0, coverage=gir_coverage),
            "fairways": Metric(name="fairways", value=4.0, coverage=fairways_coverage),
        },
        coverage={
            "scoring": "full",
            "putts": putts_coverage,
            "gir": gir_coverage,
            "fairways": fairways_coverage,
        },
    )


# --------------------------------------------------------------------------- #
# GameBook analyzer
# --------------------------------------------------------------------------- #


def test_gamebook_analyze_empty_returns_empty():
    assert gamebook_analyzer.analyze([]) == []


def test_gamebook_analyze_single_round_has_no_direction():
    latest = _round("r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75})

    findings = gamebook_analyzer.analyze([latest])

    scoring = [f for f in findings if f.metric == "to_par"]
    assert len(scoring) == 1
    assert scoring[0].direction is None


def test_gamebook_analyze_scoring_finding_direction_better():
    prior = _round("r0", "2026-06-01", 45, {"par3": 3.0, "par4": 2.0, "par5": 2.0})
    latest = _round("r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75})

    findings = gamebook_analyzer.analyze([latest, prior])

    scoring = [f for f in findings if f.metric == "to_par"]
    assert len(scoring) == 1
    f = scoring[0]
    assert f.source == "gamebook"
    assert f.context == GAMEBOOK_CONTEXT
    assert f.skill_area == "scoring"
    assert f.value == 39.0
    assert f.coverage == "full"
    assert f.direction == "better"
    assert f.detail == "+39 to par; 7 bogey / 5 double / 6 triple+"


def test_gamebook_analyze_accepts_rounds_in_either_input_order():
    prior = _round("r0", "2026-06-01", 45, {"par3": 3.0, "par4": 2.0, "par5": 2.0})
    latest = _round("r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75})

    forward = gamebook_analyzer.analyze([prior, latest])
    reverse = gamebook_analyzer.analyze([latest, prior])

    assert forward == reverse
    assert any(f.metric == "to_par" and f.direction == "better" for f in forward)


def test_gamebook_analyze_none_coverage_dimension_yields_no_finding():
    latest = _round(
        "r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75},
        fairways_coverage="none",
    )

    findings = gamebook_analyzer.analyze([latest])

    assert not any(f.metric == "fairways_hit" for f in findings)
    assert not any(f.skill_area == "driving" for f in findings)


def test_gamebook_analyze_partial_coverage_dimension_yields_finding():
    latest = _round(
        "r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75},
        gir_coverage="partial",
    )

    findings = gamebook_analyzer.analyze([latest])

    gir = [f for f in findings if f.metric == "gir_hit"]
    assert len(gir) == 1
    assert gir[0].skill_area == "approach"
    assert gir[0].coverage == "partial"
    assert gir[0].source == "gamebook"
    assert gir[0].context == GAMEBOOK_CONTEXT


def test_gamebook_analyze_full_coverage_putting_finding():
    latest = _round(
        "r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75},
        putts_coverage="full",
    )

    findings = gamebook_analyzer.analyze([latest])

    putting = [f for f in findings if f.skill_area == "putting"]
    assert len(putting) == 1
    assert putting[0].metric == "putts"
    assert putting[0].value == 27.0
    assert putting[0].coverage == "full"


def test_gamebook_analyze_putting_direction_better_from_normalized_model():
    """I2: putting `direction` comes straight from the normalized model (fewer
    putts on the latest round than the priors' mean => "better"), not from
    `compare_rounds` (which reads raw keys the Metric doesn't carry)."""
    prior = _round(
        "r0", "2026-06-01", 45, {"par3": 3.0, "par4": 2.0, "par5": 2.0},
        putts_value=33.0, putts_coverage="full",
    )
    latest = _round(
        "r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75},
        putts_value=29.0, putts_coverage="full",
    )

    findings = gamebook_analyzer.analyze([latest, prior])

    putting = [f for f in findings if f.skill_area == "putting"]
    assert len(putting) == 1
    assert putting[0].direction == "better"


def test_gamebook_analyze_putting_direction_none_when_a_prior_untracked():
    """No putting direction unless putts coverage is real on latest AND every
    prior — an untracked prior makes the trend non-comparable."""
    prior = _round(
        "r0", "2026-06-01", 45, {"par3": 3.0, "par4": 2.0, "par5": 2.0},
        putts_value=33.0, putts_coverage="none",
    )
    latest = _round(
        "r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75},
        putts_value=29.0, putts_coverage="full",
    )

    findings = gamebook_analyzer.analyze([latest, prior])

    putting = [f for f in findings if f.skill_area == "putting"]
    assert len(putting) == 1
    assert putting[0].direction is None


def test_gamebook_analyze_by_par_type_findings():
    latest = _round("r1", "2026-06-09", 39, {"par3": 2.83, "par4": 1.88, "par5": 1.75})

    findings = gamebook_analyzer.analyze([latest])

    par3 = next(f for f in findings if f.metric == "par3")
    assert par3.skill_area == "scoring"
    assert par3.source == "gamebook"
    assert par3.value == 2.83
    assert par3.coverage == "full"


# --------------------------------------------------------------------------- #
# Trackman analyzer
# --------------------------------------------------------------------------- #


def test_trackman_analyze_empty_returns_empty():
    assert trackman_analyzer.analyze([]) == []


def test_trackman_analyze_dispersion_and_gapping_from_shots():
    session = Session(
        source="trackman",
        context=TRACKMAN_CONTEXT,
        id="a1",
        time="2026-06-01T09:00:00Z",
        kind="RANGE_PRACTICE",
        shots=[
            Shot(club="DRIVER", side=4.2, carry=245.0),
            Shot(club="DRIVER", side=-2.1, carry=238.0),
        ],
    )

    findings = trackman_analyzer.analyze([session])

    assert findings
    for f in findings:
        assert f.source == "trackman"
        assert f.context == TRACKMAN_CONTEXT
        assert f.coverage == "full"

    gapping = [f for f in findings if f.skill_area == "gapping"]
    assert len(gapping) == 1
    assert gapping[0].value == 241.5  # mean(245.0, 238.0)

    dispersion = [f for f in findings if f.metric == "dispersion"]
    assert len(dispersion) == 1
    assert dispersion[0].skill_area == "driving"


def test_trackman_analyze_session_with_no_shots_or_metrics_emits_nothing():
    session = Session(
        source="trackman", context=TRACKMAN_CONTEXT, id="a2", kind="RANGE_PRACTICE",
    )

    assert trackman_analyzer.analyze([session]) == []


def test_trackman_analyze_club_gapping_emits_gapping_finding():
    """I1: a `ClubGapping` gives Trackman a real, shots-free cross-source
    signal — a carry-spread `gapping` Finding — even with no sessions."""
    gapping = ClubGapping(
        source="trackman",
        clubs=[
            {"name": "Driver", "carry": 240.0, "retired": False},
            {"name": "7 Iron", "carry": 150.0, "retired": False},
            {"name": "Pitching Wedge", "carry": 110.0, "retired": False},
            {"name": "Old 3 Wood", "carry": 200.0, "retired": True},  # ignored
        ],
    )

    findings = trackman_analyzer.analyze([], club_gapping=gapping)

    gap = [f for f in findings if f.skill_area == "gapping"]
    assert len(gap) == 1
    f = gap[0]
    assert f.source == "trackman"
    assert f.context == TRACKMAN_CONTEXT
    assert f.coverage == "full"
    assert f.metric == "club_carry_spread"
    assert f.value == 130.0  # 240 (Driver) - 110 (PW); retired 3 Wood excluded
    assert "Driver" in f.detail and "Pitching Wedge" in f.detail


def test_trackman_analyze_without_club_gapping_emits_no_gapping_finding():
    assert trackman_analyzer.analyze([]) == []
    assert trackman_analyzer.analyze([], club_gapping=None) == []


def test_trackman_analyze_empty_club_gapping_emits_nothing():
    empty = ClubGapping(source="trackman", clubs=[])
    assert trackman_analyzer.analyze([], club_gapping=empty) == []
