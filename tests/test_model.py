"""Tests for the normalized, coverage- and context-aware golf data model.

This model is the shared vocabulary every source (Trackman, GameBook, ...)
normalizes into. It carries no coaching opinions — just data plus enough
metadata (source, context, coverage) that a downstream analyzer can reason
about how much to trust a given number.
"""

from __future__ import annotations

import json

from golf_coach.model import (
    GAMEBOOK_CONTEXT,
    TRACKMAN_CONTEXT,
    Course,
    Finding,
    Hole,
    Metric,
    Round,
    RoundResult,
    Session,
    Shot,
    SourceContext,
)


def test_metric_defaults_coverage_to_none():
    m = Metric(name="carry_std_dev")
    assert m.name == "carry_std_dev"
    assert m.value is None
    assert m.unit is None
    assert m.coverage == "none"
    assert m.n is None


def test_metric_with_explicit_values():
    m = Metric(name="fairways_hit", value=8.0, unit="count", coverage="full", n=14)
    assert m.value == 8.0
    assert m.unit == "count"
    assert m.coverage == "full"
    assert m.n == 14


def test_round_builds_and_round_trips_to_plain_json_serializable_dict():
    holes = [
        Hole(number=1, par=4, score=5, putts=2, fairway="hit", gir=False),
        Hole(number=2, par=3, score=3, putts=1, fairway="na", gir=True),
    ]
    r = Round(
        source="gamebook",
        context=GAMEBOOK_CONTEXT,
        id="round-2026-06-09",
        date="2026-06-09",
        course=Course(par=70, cr=69.5, slope=128, name="Example GC"),
        result=RoundResult(gross=88, net=88, to_par=18, position=None),
        holes=holes,
        scoring={"to_par": 18, "distribution": {"par": 10, "bogey": 6}},
        dimensions={"gir_pct": Metric(name="gir_pct", value=33.3, unit="pct", coverage="full")},
        coverage={"gir_pct": "full"},
        notes=["front nine rough"],
    )

    assert r.source == "gamebook"
    assert r.context == GAMEBOOK_CONTEXT
    assert len(r.holes) == 2
    assert r.holes[0].fairway == "hit"

    dumped = r.model_dump()
    # Must be plain-dict / JSON-serializable (no custom objects escaping).
    encoded = json.dumps(dumped)
    reloaded = json.loads(encoded)
    assert reloaded["source"] == "gamebook"
    assert reloaded["id"] == "round-2026-06-09"
    assert reloaded["holes"][0]["par"] == 4
    assert reloaded["dimensions"]["gir_pct"]["value"] == 33.3
    assert reloaded["context"]["setting"] == "on_course"


def test_session_shot_with_extra_field_survives_because_extra_allow():
    shot = Shot(club="driver", ball_speed=68.2, carry=245.1, spin_axis=2.1)
    session = Session(
        source="trackman",
        context=TRACKMAN_CONTEXT,
        id="activity-123",
        time="2026-06-09T14:00:00Z",
        kind="range",
        shots=[shot],
    )

    assert session.source == "trackman"
    assert session.context == TRACKMAN_CONTEXT
    assert session.shots[0].club == "driver"

    dumped = session.model_dump()
    assert dumped["shots"][0]["spin_axis"] == 2.1
    # Round-trips through JSON too.
    reloaded = json.loads(json.dumps(dumped))
    assert reloaded["shots"][0]["spin_axis"] == 2.1


def test_trackman_context_expected_values():
    assert TRACKMAN_CONTEXT == SourceContext(
        setting="controlled", lie="flat", conditions="none", granularity="shot"
    )
    assert TRACKMAN_CONTEXT.setting == "controlled"
    assert TRACKMAN_CONTEXT.lie == "flat"
    assert TRACKMAN_CONTEXT.conditions == "none"
    assert TRACKMAN_CONTEXT.granularity == "shot"


def test_gamebook_context_expected_values():
    assert GAMEBOOK_CONTEXT == SourceContext(
        setting="on_course", lie="variable", conditions="real", granularity="scorecard"
    )
    assert GAMEBOOK_CONTEXT.setting == "on_course"
    assert GAMEBOOK_CONTEXT.lie == "variable"
    assert GAMEBOOK_CONTEXT.conditions == "real"
    assert GAMEBOOK_CONTEXT.granularity == "scorecard"


def test_finding_approach_worse():
    f = Finding(
        skill_area="approach",
        source="gamebook",
        context=GAMEBOOK_CONTEXT,
        metric="gir_pct",
        value=28.0,
        unit="pct",
        coverage="full",
        direction="worse",
        detail="GIR% down 10pts vs prior 5 rounds",
    )
    assert f.skill_area == "approach"
    assert f.direction == "worse"
    assert f.context.granularity == "scorecard"

    dumped = f.model_dump()
    json.dumps(dumped)  # must be JSON-serializable
