"""Tests for the Trackman source adapter — GraphQL responses -> normalized model.

The GraphQL fetch is mocked (no network): each test monkeypatches the source's
`_fetch` with a stand-in that returns a synthetic response shaped like the real
Trackman API (inferred from `queries.py` + how `server.py` reads the results).
"""

from __future__ import annotations

from typing import Any

import pytest

from golf_coach.client import TrackmanAuthError
from golf_coach.model import TRACKMAN_CONTEXT, Round, Session
from golf_coach.sources import registry
from golf_coach.sources import trackman as trackman_pkg  # noqa: F401
from golf_coach.sources.base import Source
from golf_coach.sources.trackman import source as tm_source_mod
from golf_coach.sources.trackman.source import TrackmanSource


def _fake_fetch(responses: dict[str, dict[str, Any]]):
    """Build a `_fetch` stand-in that dispatches on the GraphQL operation name."""

    async def fetch(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        for op_name, data in responses.items():
            if op_name in query:
                return data
        raise AssertionError(f"no fake response registered for query: {query[:60]!r}")

    return fetch


# --------------------------------------------------------------------------- #
# Identity / protocol conformance
# --------------------------------------------------------------------------- #


def test_name_and_context():
    source = TrackmanSource()
    assert source.name == "trackman"
    assert source.context == TRACKMAN_CONTEXT


def test_supports_declares_six_capabilities():
    source = TrackmanSource()
    assert source.supports() == {"rounds", "sessions", "profile", "handicap", "clubs", "auth"}


def test_conforms_to_source_protocol():
    assert isinstance(TrackmanSource(), Source)


def test_registers_itself_on_import():
    """Importing the module registers a module-level instance (force via reload
    of the `source` submodule, since the registry may have been cleared by
    another test module already, and reloading the parent package alone
    doesn't re-execute an already-imported submodule)."""
    import importlib

    import golf_coach.sources.trackman.source as source_mod

    registry.clear()
    try:
        importlib.reload(source_mod)
        registered = registry.get_source("trackman")
        assert registered is not None
        # Structural check (not identity — reload rebinds the class object).
        assert registered.name == "trackman"
        assert isinstance(registered, Source)
    finally:
        registry.clear()


# --------------------------------------------------------------------------- #
# rounds()
# --------------------------------------------------------------------------- #


COURSE_ROUNDS_RESPONSE = {
    "me": {
        "scorecards": [
            {
                "id": "sc1",
                "createdAt": "2026-06-01T08:00:00Z",
                "startedAt": "2026-06-01T10:00:00Z",
                "finishedAt": "2026-06-01T14:00:00Z",
                "course": {"displayName": "Example GC"},
                "teeName": "White",
                "par": 72,
                "numberOfHolesPlayed": 18,
                "isCompleted": True,
                "isInHcp": True,
                "grossScore": 88,
                "netScore": 80,
                "toPar": 16,
                "outScore": 44,
                "inScore": 44,
                "courseHcp": 12,
                "stat": {
                    "driveAverage": 210.5,
                    "driveMax": 250.0,
                    "driveTotal": 3157.5,
                    "driveCount": 15,
                    "highestBallSpeed": 62.1,
                    "fairwayHitFairway": 7,
                    "fairwayHitLeft": 3,
                    "fairwayHitRight": 4,
                    "greenInRegulation": 6,
                    "numberOfPutts": 32,
                    "averagePuttsPerHoleDecimal": 1.78,
                    "birdies": 0,
                    "pars": 6,
                    "bogeys": 8,
                    "doubleBogeys": 3,
                    "tripleBogeysOrWorse": 1,
                    "eagles": 0,
                },
                "holes": [
                    {
                        "holeNumber": 1,
                        "par": 4,
                        "strokeIndex": 7,
                        "distance": 350,
                        "grossScore": 5,
                        "netScore": 4,
                        "putts": 2,
                        "greenInRegulation": False,
                        "hcpStrokes": 1,
                    },
                    {
                        "holeNumber": 2,
                        "par": 3,
                        "strokeIndex": 15,
                        "distance": 150,
                        "grossScore": 3,
                        "netScore": 3,
                        "putts": 1,
                        "greenInRegulation": True,
                        "hcpStrokes": 0,
                    },
                    # An unplayed hole (no score yet) — must be skipped, not crash.
                    {
                        "holeNumber": 3,
                        "par": 4,
                        "strokeIndex": 3,
                        "distance": 400,
                        "grossScore": None,
                        "netScore": None,
                        "putts": None,
                        "greenInRegulation": None,
                        "hcpStrokes": 2,
                    },
                ],
            }
        ]
    }
}


async def test_rounds_normalizes_scorecard():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"CourseRounds": COURSE_ROUNDS_RESPONSE})

    rounds = await source.rounds()

    assert len(rounds) == 1
    r = rounds[0]
    assert isinstance(r, Round)
    assert r.source == "trackman"
    assert r.context == TRACKMAN_CONTEXT
    assert r.id == "sc1"
    assert r.course.par == 72
    assert r.course.name == "Example GC"
    assert r.result.gross == 88
    assert r.result.net == 80
    assert r.result.to_par == 16

    # The unplayed hole (no grossScore) is skipped.
    assert len(r.holes) == 2
    assert r.holes[0].number == 1
    assert r.holes[0].par == 4
    assert r.holes[0].score == 5
    assert r.holes[0].putts == 2
    assert r.holes[0].gir is False
    assert r.holes[1].gir is True

    assert r.dimensions["putts"].value == 32
    assert r.dimensions["putts"].coverage == "full"
    assert r.dimensions["fairways_hit_pct"].value == pytest.approx(50.0)
    assert r.coverage["fairways_hit_pct"] == "full"


async def test_rounds_passes_filters_through():
    captured: dict[str, Any] = {}

    async def fetch(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        captured["variables"] = variables
        return {"me": {"scorecards": []}}

    source = TrackmanSource()
    source._fetch = fetch
    result = await source.rounds(skip=5, take=10, completed=False)

    assert result == []
    assert captured["variables"] == {"skip": 5, "take": 10, "completed": False}


# --------------------------------------------------------------------------- #
# sessions()
# --------------------------------------------------------------------------- #


LIST_SESSIONS_RESPONSE = {
    "me": {
        "activities": {
            "totalCount": 2,
            "pageInfo": {"hasNextPage": False},
            "items": [
                {
                    "id": "a1",
                    "time": "2026-06-01T09:00:00Z",
                    "kind": "RANGE_PRACTICE",
                    "isHidden": False,
                    "numberOfStrokes": 40,
                    "clubs": ["7 Iron", "Driver"],
                    "location": {"name": "Bay 3"},
                },
                {
                    "id": "a2",
                    "time": "2026-06-02T09:00:00Z",
                    "kind": "COURSE_PLAY",
                    "isHidden": False,
                    "gameType": "STROKE",
                    "grossScore": 88,
                    "netScore": 80,
                    "toPar": 16,
                    "thruHole": 18,
                    "course": {"displayName": "Example GC"},
                },
            ],
        }
    }
}


async def test_sessions_normalizes_activities():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"ListSessions": LIST_SESSIONS_RESPONSE})

    sessions = await source.sessions()

    assert len(sessions) == 2
    s1, s2 = sessions
    assert isinstance(s1, Session)
    assert s1.source == "trackman"
    assert s1.context == TRACKMAN_CONTEXT
    assert s1.id == "a1"
    assert s1.kind == "RANGE_PRACTICE"
    assert s1.shots == []
    assert s1.metrics["stroke_count"].value == 40

    assert s2.id == "a2"
    assert s2.kind == "COURSE_PLAY"
    assert s2.metrics["gross_score"].value == 88
    assert s2.metrics["to_par"].value == 16


# --------------------------------------------------------------------------- #
# profile() / handicap() / club_gapping()
# --------------------------------------------------------------------------- #


PROFILE_RESPONSE = {
    "me": {
        "profile": {
            "id": "p1",
            "dbId": 123,
            "playerName": "pat123",
            "fullName": "Pat Golfer",
            "firstName": "Pat",
            "lastName": "Golfer",
            "gender": "M",
            "email": "pat@example.com",
            "nationality": "US",
            "nationalityCode": "US",
            "birthDate": "1990-01-01",
            "picture": None,
            "outdoorHandicap": 12.3,
            "category": "AM",
            "dexterity": "RIGHT",
        },
        "hcp": {
            "currentHcp": 14.2,
            "currentRecord": {
                "hcpNew": 14.2,
                "scoreDifferential": 15.3,
                "adjustedGrossScore": 88,
                "createdAt": "2026-06-01T14:00:00Z",
            },
        },
    }
}


async def test_profile_maps_key_fields():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"Profile": PROFILE_RESPONSE})

    profile = await source.profile()

    assert profile is not None
    assert profile.source == "trackman"
    assert profile.name == "Pat Golfer"
    assert profile.player_id == "p1"
    assert profile.handicap == 14.2


HANDICAP_HISTORY_RESPONSE = {
    "me": {
        "hcp": {
            "currentHcp": 14.2,
            "playerHistory": {
                "totalCount": 1,
                "items": [
                    {
                        "createdAt": "2026-06-01T14:00:00Z",
                        "hcpOld": 14.5,
                        "hcpNew": 14.2,
                        "adjustedGrossScore": 88,
                        "scoreDifferential": 15.3,
                        "isInAvg": True,
                        "adjustment": 0,
                        "scorecard": {
                            "id": "sc1",
                            "course": {"displayName": "Example GC"},
                            "grossScore": 88,
                            "toPar": 16,
                        },
                    }
                ],
            },
        }
    }
}


async def test_handicap_maps_current_and_history():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"HandicapHistory": HANDICAP_HISTORY_RESPONSE})

    handicap = await source.handicap()

    assert handicap is not None
    assert handicap.source == "trackman"
    assert handicap.current == 14.2
    assert len(handicap.history) == 1
    assert handicap.history[0]["hcpNew"] == 14.2


CLUB_STATS_RESPONSE = {
    "me": {
        "equipment": {
            "clubs": [
                {
                    "id": "c1",
                    "displayName": "7 Iron",
                    "isRetired": False,
                    "brand": {"name": "Titleist"},
                    "clubHead": {"clubHeadKind": "IRON", "clubHeadType": "7"},
                    "findMyDistance": {
                        "numberOfShots": 42,
                        "clubStats": {
                            "carry": 150.2,
                            "total": 155.0,
                            "standardDeviationCarry": 5.1,
                            "standardDeviationTotal": 5.5,
                        },
                        "dispersionCircle": {
                            "centerX": 0,
                            "centerY": 150,
                            "minAxis": 5,
                            "maxAxis": 10,
                            "angle": 0,
                        },
                    },
                }
            ]
        }
    }
}


async def test_club_gapping_maps_carry_and_total():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"ClubStats": CLUB_STATS_RESPONSE})

    gapping = await source.club_gapping()

    assert gapping is not None
    assert gapping.source == "trackman"
    assert len(gapping.clubs) == 1
    club = gapping.clubs[0]
    assert club["name"] == "7 Iron"
    assert club["carry"] == 150.2
    assert club["total"] == 155.0


async def test_profile_returns_none_when_no_profile():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"Profile": {"me": {}}})
    assert await source.profile() is None


async def test_handicap_returns_none_when_no_hcp():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"HandicapHistory": {"me": {}}})
    assert await source.handicap() is None


async def test_club_gapping_returns_none_when_no_clubs():
    source = TrackmanSource()
    source._fetch = _fake_fetch({"ClubStats": {"me": {"equipment": {"clubs": []}}}})
    assert await source.club_gapping() is None


# --------------------------------------------------------------------------- #
# analyze() — shot-level enrichment (`_recent_practice_shots`)
# --------------------------------------------------------------------------- #


# List has 3 RANGE_PRACTICE candidates (p1, p2, p3) plus a COURSE_PLAY game
# (g1). With the default limit of 2, only the two newest practice candidates
# should ever have their per-session detail fetched — never the game, never p3.
ENRICH_LIST_RESPONSE = {
    "me": {
        "activities": {
            "totalCount": 4,
            "pageInfo": {"hasNextPage": False},
            "items": [
                {"id": "p1", "time": "2026-07-03T09:00:00Z", "kind": "RANGE_PRACTICE",
                 "isHidden": False, "numberOfStrokes": 2, "clubs": ["Driver"]},
                {"id": "g1", "time": "2026-07-02T09:00:00Z", "kind": "COURSE_PLAY",
                 "isHidden": False, "grossScore": 88, "toPar": 16},
                {"id": "p2", "time": "2026-07-01T09:00:00Z", "kind": "RANGE_PRACTICE",
                 "isHidden": False, "numberOfStrokes": 1, "clubs": ["Pitching Wedge"]},
                {"id": "p3", "time": "2026-06-30T09:00:00Z", "kind": "RANGE_PRACTICE",
                 "isHidden": False, "numberOfStrokes": 3, "clubs": ["7 Iron"]},
            ],
        }
    }
}

DRIVER_STROKES = [
    {"time": "2026-07-03T09:00:00Z", "club": "Driver",
     "measurement": {"totalSide": 8.0, "carrySide": 7.0, "curve": 5.0,
                     "carry": 240.0, "total": 255.0, "ballSpeed": 68.0,
                     "clubSpeed": 46.0, "smashFactor": 1.48}},
    {"time": "2026-07-03T09:05:00Z", "club": "Driver",
     "measurement": {"totalSide": -3.0, "curve": -2.0, "carry": 235.0}},
]
WEDGE_STROKES = [
    {"time": "2026-07-01T09:00:00Z", "club": "Pitching Wedge",
     "measurement": {"carrySide": 2.0, "curve": 1.0, "carry": 110.0}},  # totalSide absent -> carrySide
]

_ENRICH_DETAILS = {
    "p1": {"__typename": "RangePracticeActivity", "id": "p1",
           "time": "2026-07-03T09:00:00Z", "kind": "RANGE_PRACTICE",
           "numberOfStrokes": 2, "strokes": DRIVER_STROKES},
    "p2": {"__typename": "RangePracticeActivity", "id": "p2",
           "time": "2026-07-01T09:00:00Z", "kind": "RANGE_PRACTICE",
           "numberOfStrokes": 1, "strokes": WEDGE_STROKES},
    "p3": {"__typename": "RangePracticeActivity", "id": "p3",
           "time": "2026-06-30T09:00:00Z", "kind": "RANGE_PRACTICE",
           "numberOfStrokes": 3, "strokes": DRIVER_STROKES},
}


def _enrich_fetch(counter: list[str] | None = None):
    """Fake `_fetch` dispatching ListSessions / GetSession(by id) / ClubStats."""

    async def fetch(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if "ListSessions" in query:
            return ENRICH_LIST_RESPONSE
        if "GetSession" in query:
            aid = (variables or {}).get("id")
            if counter is not None:
                counter.append(aid)
            return {"node": _ENRICH_DETAILS[aid]}
        if "ClubStats" in query:
            return {"me": {"equipment": {"clubs": []}}}
        raise AssertionError(f"no fake response for query: {query[:60]!r}")

    return fetch


async def test_stroke_to_shot_maps_side_curve_and_metrics():
    shot = TrackmanSource._stroke_to_shot(DRIVER_STROKES[0])
    assert shot.club == "Driver"
    assert shot.side == 8.0          # totalSide preferred
    assert shot.curve == 5.0
    assert shot.carry == 240.0
    assert shot.total == 255.0
    assert shot.ball_speed == 68.0
    assert shot.club_speed == 46.0
    assert shot.smash == 1.48


async def test_stroke_to_shot_side_falls_back_to_carry_side():
    shot = TrackmanSource._stroke_to_shot(WEDGE_STROKES[0])
    assert shot.side == 2.0          # totalSide absent -> carrySide


async def test_analyze_emits_dispersion_findings_from_enriched_sessions():
    source = TrackmanSource()
    source._fetch = _enrich_fetch()

    findings = await source.analyze()

    areas = {f.skill_area for f in findings}
    assert "driving" in areas    # Driver shots' totalSide -> driving dispersion
    assert "approach" in areas   # wedge shot's carrySide -> approach dispersion

    dispersion = [f for f in findings if f.metric == "dispersion"]
    assert dispersion, "expected >=1 dispersion finding from enriched shots"
    for f in dispersion:
        assert f.source == "trackman"
        assert f.context == TRACKMAN_CONTEXT
        assert f.coverage == "full"


async def test_recent_practice_shots_fetches_detail_only_for_selected():
    calls: list[str] = []
    source = TrackmanSource()
    source._fetch = _enrich_fetch(counter=calls)

    sessions = await source._recent_practice_shots(limit=2)

    # Only the two newest PRACTICE candidates had detail fetched — the game
    # (g1) was excluded up front and the extra practice (p3) is beyond limit.
    assert calls == ["p1", "p2"]
    assert "g1" not in calls
    assert "p3" not in calls
    assert len(sessions) == 2
    assert all(s.shots for s in sessions)
    assert sessions[0].shots[0].club == "Driver"


async def test_recent_practice_shots_empty_when_only_games():
    only_games = {
        "me": {"activities": {"items": [
            {"id": "g1", "time": "2026-07-02T09:00:00Z", "kind": "COURSE_PLAY"},
        ]}}
    }

    async def fetch(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        assert "GetSession" not in query, "must not fetch detail for a game"
        if "ListSessions" in query:
            return only_games
        raise AssertionError(f"unexpected query: {query[:40]!r}")

    source = TrackmanSource()
    source._fetch = fetch
    assert await source._recent_practice_shots() == []


# --------------------------------------------------------------------------- #
# _stroke_to_shot() — club-delivery fields + derived spin components
# --------------------------------------------------------------------------- #


DELIVERY_STROKES = [
    {"club": "Driver", "measurement": {
        "clubPath": -5.0, "faceAngle": -1.0, "attackAngle": 0.5, "dynamicLoft": 19.0,
        "spinRate": 4200.0, "spinAxis": 10.0, "totalSide": 8.0, "carry": 250.0}},
    {"club": "Driver", "measurement": {
        "clubPath": -4.0, "faceAngle": -0.5, "attackAngle": 1.0, "dynamicLoft": 19.5,
        "spinRate": 4300.0, "spinAxis": 8.0, "totalSide": -6.0, "carry": 248.0}},
]


def test_stroke_to_shot_populates_club_delivery_fields():
    shot = TrackmanSource._stroke_to_shot(DELIVERY_STROKES[0])
    assert shot.club_path == -5.0
    assert shot.face_angle == -1.0
    assert shot.attack_angle == 0.5
    assert shot.dynamic_loft == 19.0
    assert shot.spin == 4200.0


def test_stroke_to_shot_derives_side_and_back_spin_from_axis():
    import math

    shot = TrackmanSource._stroke_to_shot(DELIVERY_STROKES[0])
    # +axis (10°) tilts right -> positive side spin; back spin stays positive.
    assert shot.side_spin is not None and shot.side_spin > 0
    assert shot.back_spin is not None and shot.back_spin > 0
    # The derivation is the exact inverse of the delivery module's atan2 — it
    # round-trips back to the reported spin axis.
    assert round(math.degrees(math.atan2(shot.side_spin, shot.back_spin)), 1) == 10.0


def test_stroke_to_shot_no_spin_axis_leaves_components_none():
    shot = TrackmanSource._stroke_to_shot({"club": "Driver", "measurement": {"spinRate": 4000.0}})
    assert shot.side_spin is None
    assert shot.back_spin is None


def _delivery_fetch():
    """Fake `_fetch` serving a Shot-Analysis session of driver deliveries."""

    async def fetch(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if "ListSessions" in query:
            return {"me": {"activities": {"items": [
                {"id": "p1", "time": "2026-07-03T09:00:00Z", "kind": "SHOT_ANALYSIS",
                 "strokeCount": 2, "clubs": ["Driver"]},
            ]}}}
        if "GetSession" in query:
            return {"node": {"__typename": "ShotAnalysisSessionActivity", "id": "p1",
                             "time": "2026-07-03T09:00:00Z", "kind": "SHOT_ANALYSIS",
                             "strokeCount": 2, "strokes": DELIVERY_STROKES}}
        if "ClubStats" in query:
            return {"me": {"equipment": {"clubs": []}}}
        raise AssertionError(f"no fake response for query: {query[:60]!r}")

    return fetch


async def test_analyze_emits_driver_delivery_findings():
    from golf_coach.sources.trackman.delivery import DELIVERY_METRICS

    source = TrackmanSource()
    source._fetch = _delivery_fetch()

    findings = await source.analyze()

    delivery = [f for f in findings if f.metric in DELIVERY_METRICS]
    metrics = {f.metric for f in delivery}
    assert {"club_path", "face_to_path", "spin_axis", "attack_angle", "spin_rate"} <= metrics
    for f in delivery:
        assert f.source == "trackman"
        assert f.skill_area == "driving"
        assert f.context == TRACKMAN_CONTEXT


# --------------------------------------------------------------------------- #
# _fetch() — silent-refresh-on-401 then retry, else surface the auth error loudly
# --------------------------------------------------------------------------- #


async def test_fetch_retries_once_after_silent_refresh(monkeypatch):
    calls = {"n": 0}

    async def fake_execute(self, query, variables=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TrackmanAuthError("expired")
        return {"ok": True}

    monkeypatch.setattr("golf_coach.client.TrackmanClient.execute", fake_execute)

    async def refreshed() -> bool:
        return True
    monkeypatch.setattr(tm_source_mod, "_try_silent_refresh", refreshed)

    result = await TrackmanSource()._fetch("query { __typename }")
    assert result == {"ok": True}
    assert calls["n"] == 2  # failed once, refreshed, retried once


async def test_fetch_raises_loudly_when_refresh_fails(monkeypatch):
    async def always_auth_error(self, query, variables=None):
        raise TrackmanAuthError("expired")
    monkeypatch.setattr("golf_coach.client.TrackmanClient.execute", always_auth_error)

    async def no_refresh() -> bool:
        return False
    monkeypatch.setattr(tm_source_mod, "_try_silent_refresh", no_refresh)

    with pytest.raises(TrackmanAuthError):
        await TrackmanSource()._fetch("query { __typename }")


async def test_try_silent_refresh_false_without_saved_session(monkeypatch, tmp_path):
    """No persisted browser profile -> skip the (doomed) headless launch entirely
    and report failure fast, so a token-less caller never blocks on a browser."""
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))

    called = {"capture": False}

    async def fake_capture(*a, **k):
        called["capture"] = True
        return "tok"
    monkeypatch.setattr("golf_coach.login.capture_token", fake_capture)

    assert await tm_source_mod._try_silent_refresh() is False
    assert called["capture"] is False  # gated out before any browser launch
