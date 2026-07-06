"""Delta-fires integration test: Trackman shot enrichment overlaps GameBook.

Proves the REAL `synthesize()` path now produces a NON-empty
`cross_source_deltas`. Before shot enrichment, Trackman emitted only `gapping`
Findings while GameBook emitted `scoring/putting/approach/driving` — no shared
skill area, so `align()` never created a delta. With `TrackmanSource.analyze()`
now enriching recent practice sessions with shot-level detail, Trackman emits
`driving`/`approach` dispersion Findings (from `Shot.side`/`club`) that share a
skill area with GameBook's on-course `driving`/`approach` Findings — so the
delta fires on its own, with no change to `align()` or the GameBook side.

Trackman's GraphQL is mocked at the source's `_fetch` (LIST_SESSIONS +
GET_SESSION + ClubStats); GameBook data is seeded on disk under an isolated
cache dir.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

import golf_coach.sources  # noqa: F401  — import-time registration of built-ins
from golf_coach import gamebook_store
from golf_coach.model import CrossSourceView
from golf_coach.sources import registry
from golf_coach.sources.gamebook import source as gamebook_source_mod
from golf_coach.sources.trackman import source as trackman_source_mod
from golf_coach.synthesis import synthesize


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Isolate the on-disk cache; no real Trackman token is needed (mocked)."""
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)


@pytest.fixture
def registered_sources():
    """Re-run the import-time registration so we get fresh, patchable instances
    even if another test module cleared the shared registry."""
    registry.clear()
    importlib.reload(trackman_source_mod)  # registry.register(TrackmanSource())
    importlib.reload(gamebook_source_mod)  # registry.register(GameBookSource())
    yield
    registry.clear()


# One recent RANGE_PRACTICE session (not a game) so enrichment fetches its detail.
LIST_RESPONSE = {
    "me": {
        "activities": {
            "totalCount": 1,
            "pageInfo": {"hasNextPage": False},
            "items": [
                {"id": "p1", "time": "2026-07-02T09:00:00Z", "kind": "RANGE_PRACTICE",
                 "isHidden": False, "numberOfStrokes": 3, "clubs": ["Driver", "Pitching Wedge"]},
            ],
        }
    }
}

# 2 driver strokes (-> driving) + 1 wedge stroke (-> approach), carrying the
# three fields dispersion keys on: club, totalSide (side), curve.
SESSION_DETAIL = {
    "node": {
        "__typename": "RangePracticeActivity",
        "id": "p1",
        "time": "2026-07-02T09:00:00Z",
        "kind": "RANGE_PRACTICE",
        "numberOfStrokes": 3,
        "strokes": [
            {"time": "2026-07-02T09:00:00Z", "club": "Driver",
             "measurement": {"totalSide": 9.0, "curve": 6.0, "carry": 242.0, "total": 258.0}},
            {"time": "2026-07-02T09:04:00Z", "club": "Driver",
             "measurement": {"totalSide": -4.0, "curve": -3.0, "carry": 236.0}},
            {"time": "2026-07-02T09:08:00Z", "club": "Pitching Wedge",
             "measurement": {"totalSide": 2.5, "curve": 1.0, "carry": 108.0}},
        ],
    }
}


def _fake_trackman_fetch():
    async def fetch(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        if "ListSessions" in query:
            return LIST_RESPONSE
        if "GetSession" in query:
            return SESSION_DETAIL
        if "ClubStats" in query:  # keep club_gapping() out of the picture
            return {"me": {"equipment": {"clubs": []}}}
        raise AssertionError(f"no fake response for query: {query[:60]!r}")

    return fetch


def _gamebook_round_with_driving_and_approach() -> dict:
    """A round whose `fairways` (-> driving) and `gir` (-> approach) dimensions
    have real coverage, so the GameBook analyzer emits driving + approach
    Findings that overlap Trackman's dispersion Findings."""
    return {
        "id": "round-2026-07-01",
        "date": "2026-07-01",
        "course": {"par": 72, "name": "Test Links"},
        "result": {"gross": 85, "net": 85, "to_par": 13},
        "holes": [],
        "scoring": {
            "to_par": 13,
            "distribution": {"par": 5, "bogey": 11, "double": 2},
        },
        "dimensions": {
            "fairways": {"value": 7, "coverage": "partial"},  # -> driving finding
            "gir": {"value": 6, "coverage": "partial"},       # -> approach finding
            "putts": {"value": 32, "coverage": "full"},
        },
        "coverage": {"scoring": "full", "fairways": "partial", "gir": "partial", "putts": "full"},
        "notes": [],
    }


async def test_synthesize_produces_cross_source_delta(registered_sources):
    gamebook_store.save_round(_gamebook_round_with_driving_and_approach())

    tm = registry.get_source("trackman")
    assert tm is not None
    tm._fetch = _fake_trackman_fetch()  # mock the GraphQL transport

    view = await synthesize()

    assert isinstance(view, CrossSourceView)
    assert view.cross_source_deltas, "expected a NON-empty cross_source_deltas"

    # At least one delta covers a skill area where BOTH trackman and gamebook
    # contributed — the whole point of the enrichment.
    overlapping = {
        d["skill_area"]
        for d in view.cross_source_deltas
        if set(d["sources"]) >= {"trackman", "gamebook"}
    }
    assert overlapping & {"driving", "approach"}, view.cross_source_deltas

    # And that delta correctly tags the context mix (controlled vs on-course).
    delta = next(
        d for d in view.cross_source_deltas
        if d["skill_area"] in {"driving", "approach"}
        and set(d["sources"]) >= {"trackman", "gamebook"}
    )
    assert delta["sources"]["trackman"]["setting"] == "controlled"
    assert delta["sources"]["gamebook"]["setting"] == "on_course"
    assert "context_note" in delta


async def test_trackman_analyze_alone_emits_driving_or_approach(registered_sources):
    """Focused: the enriched analyze path (through the registry instance) yields
    at least one driving/approach finding when sessions carry shots."""
    tm = registry.get_source("trackman")
    assert tm is not None
    tm._fetch = _fake_trackman_fetch()

    findings = await tm.analyze()

    areas = {f.skill_area for f in findings}
    assert areas & {"driving", "approach"}, areas
