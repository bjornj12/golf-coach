"""Tests for the deterministic biggest-leak ranking (golf_coach.ranking).

Facts-only: the ranking orders skill areas by a documented severity heuristic
over the analyzer's Findings. It emits no drills/verdicts — interpretation
stays in the coaching skills (CLAUDE.md's core boundary).
"""

from __future__ import annotations

from golf_coach.model import TRACKMAN_CONTEXT, ClubGapping, Finding, Session, Shot
from golf_coach.ranking import RankedLeak, rank_leaks
from golf_coach.sources.trackman import analyzer as trackman_analyzer


def _disp(area: str, value: float, coverage: str = "full") -> Finding:
    return Finding(
        skill_area=area,
        source="trackman",
        context=TRACKMAN_CONTEXT,
        metric="dispersion",
        value=value,
        unit="m",
        coverage=coverage,
    )


def test_empty_findings_rank_to_empty_list():
    assert rank_leaks([]) == []


def test_dispersion_severity_orders_biggest_leak_first():
    # approach 18m -> (18-8)/(25-8) = 0.588 ; driving 30m -> (30-15)/(45-15) = 0.5
    leaks = rank_leaks([_disp("driving", 30.0), _disp("approach", 18.0)])
    assert [leak.skill_area for leak in leaks] == ["approach", "driving"]
    assert [leak.rank for leak in leaks] == [1, 2]
    assert leaks[0].severity > leaks[1].severity


def test_dispersion_band_clamps_low_and_high():
    tight = rank_leaks([_disp("approach", 5.0)])[0]   # below the good baseline
    wide = rank_leaks([_disp("approach", 40.0)])[0]    # above the bad baseline
    assert tight.severity == 0.0
    assert wide.severity == 1.0


def test_higher_dispersion_is_a_bigger_leak():
    small = rank_leaks([_disp("approach", 12.0)])[0].severity
    big = rank_leaks([_disp("approach", 22.0)])[0].severity
    assert big > small


def test_gapping_is_informational_and_ranks_below_a_scored_leak():
    findings = [
        Finding(
            skill_area="gapping",
            source="trackman",
            context=TRACKMAN_CONTEXT,
            metric="club_carry_spread",
            value=140.0,
            unit="m",
            coverage="full",
        ),
        _disp("approach", 20.0),
    ]
    leaks = rank_leaks(findings)
    by_area = {leak.skill_area: leak for leak in leaks}
    assert by_area["gapping"].severity == 0.0
    assert by_area["approach"].severity > 0.0
    assert by_area["approach"].rank < by_area["gapping"].rank


def test_ties_break_alphabetically_by_skill_area():
    # approach 16.5 -> (16.5-8)/17 = 0.5 ; driving 30 -> (30-15)/30 = 0.5
    leaks = rank_leaks([_disp("driving", 30.0), _disp("approach", 16.5)])
    assert leaks[0].severity == leaks[1].severity
    assert [leak.skill_area for leak in leaks] == ["approach", "driving"]


def test_ranks_are_contiguous_from_one():
    leaks = rank_leaks([_disp("approach", 22.0), _disp("driving", 25.0)])
    assert [leak.rank for leak in leaks] == [1, 2]


def test_coverage_is_carried_through():
    leak = rank_leaks([_disp("approach", 18.0, coverage="partial")])[0]
    assert leak.coverage == "partial"


def test_ranking_is_deterministic():
    findings = [_disp("driving", 22.0), _disp("approach", 19.0)]
    assert rank_leaks(findings) == rank_leaks(findings)


def test_ranked_leak_carries_facts_not_coaching():
    leak = rank_leaks([_disp("approach", 18.0)])[0]
    # A leak is a measurement: a metric, a value, and a factual basis — no
    # drill/plan/recommendation field may exist on this model.
    fields = set(RankedLeak.model_fields)
    assert {"skill_area", "severity", "metric", "value", "basis", "rank"} <= fields
    assert not (fields & {"drill", "drills", "plan", "recommendation", "prescription"})
    assert leak.value == 18.0
    assert "18" in leak.headline


def test_ranks_real_analyzer_findings_end_to_end():
    """The intended StrokeDelta seam: pure analyzer output -> ranked leaks,
    with zero provider API contact (analyzer is a pure function over shots)."""
    session = Session(
        source="trackman",
        context=TRACKMAN_CONTEXT,
        id="s1",
        shots=[
            Shot(club="Driver", carry=250.0, side=30.0),
            Shot(club="Driver", carry=245.0, side=-28.0),
            Shot(club="7Iron", carry=150.0, side=20.0),
            Shot(club="7Iron", carry=152.0, side=-22.0),
        ],
    )
    gapping = ClubGapping(
        source="trackman",
        clubs=[
            {"name": "Driver", "carry": 248.0, "retired": False},
            {"name": "7Iron", "carry": 151.0, "retired": False},
        ],
    )
    findings = trackman_analyzer.analyze([session], club_gapping=gapping)
    leaks = rank_leaks(findings)

    assert leaks, "expected at least one ranked leak"
    assert all(0.0 <= leak.severity <= 1.0 for leak in leaks)
    by_area = {leak.skill_area: leak for leak in leaks}
    # 7-iron side spread (~21m) is a bigger approach leak than driver (~29m
    # driving) relative to their bands -> approach outranks driving.
    assert by_area["approach"].rank < by_area["driving"].rank
    assert by_area["gapping"].severity == 0.0
