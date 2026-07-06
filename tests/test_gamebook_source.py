"""Tests for the GameBook source adapter — stored rounds -> normalized model.

GameBook is scorecard-only: no shot-level data, no sessions, no auth. This
adapter reads whatever `gamebook_store` already has on disk (the
gamebook-screenshot-analysis skill writes there) and maps it into the shared
`..model` types tagged with `source="gamebook"` and `GAMEBOOK_CONTEXT`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from golf_coach import gamebook_store as gs
from golf_coach.model import GAMEBOOK_CONTEXT, Metric, Round
from golf_coach.sources.base import Source
from golf_coach.sources.gamebook.source import GameBookSource

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "gamebook" / "2026-06-09.json"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


# --------------------------------------------------------------------------- #
# Identity / protocol conformance
# --------------------------------------------------------------------------- #


def test_name_and_context():
    source = GameBookSource()
    assert source.name == "gamebook"
    assert source.context == GAMEBOOK_CONTEXT


def test_supports_declares_rounds_only():
    assert GameBookSource().supports() == {"rounds"}


def test_conforms_to_source_protocol():
    assert isinstance(GameBookSource(), Source)


def test_registers_itself_on_import():
    import importlib

    import golf_coach.sources.gamebook.source as source_mod
    from golf_coach.sources import registry

    registry.clear()
    try:
        importlib.reload(source_mod)
        registered = registry.get_source("gamebook")
        assert registered is not None
        assert registered.name == "gamebook"
        assert isinstance(registered, Source)
    finally:
        registry.clear()


# --------------------------------------------------------------------------- #
# rounds()
# --------------------------------------------------------------------------- #


async def test_rounds_empty_store():
    assert await GameBookSource().rounds() == []


async def test_rounds_normalizes_stored_round():
    record = _load_fixture()
    gs.save_round(record)

    rounds = await GameBookSource().rounds()

    assert len(rounds) == 1
    r = rounds[0]
    assert isinstance(r, Round)
    assert r.source == "gamebook"
    assert r.context == GAMEBOOK_CONTEXT
    assert r.id == "2026-06-09"
    assert r.date == "2026-06-09"

    # course / result preserved
    assert r.course.par == 70
    assert r.course.cr == 68.1
    assert r.course.slope == 119
    assert r.result.gross == 109
    assert r.result.net == 62
    assert r.result.to_par == 39
    assert r.result.position == "1/4"

    # holes: `hole` (stored) -> `number` (model), Nones pass through
    assert len(r.holes) == 18
    h1 = r.holes[0]
    assert h1.number == 1
    assert h1.par == 4
    assert h1.score == 7
    assert h1.putts == 2
    assert h1.fairway == "hit"
    assert h1.gir is False

    h4 = r.holes[3]  # hole 4 has putts/fairway/gir all null in the fixture
    assert h4.number == 4
    assert h4.putts is None
    assert h4.fairway is None
    assert h4.gir is None

    # scoring passed through
    assert r.scoring["to_par"] == 39
    assert r.scoring["distribution"]["bogey"] == 7
    assert r.scoring["by_par_type"]["par3"] == 2.83

    # dimensions mapped into Metric
    assert isinstance(r.dimensions["putts"], Metric)
    assert r.dimensions["putts"].name == "putts"
    assert r.dimensions["putts"].value == 27
    assert r.dimensions["putts"].coverage == "partial"
    assert r.dimensions["putts"].n == 12  # holes_tracked carried onto Metric.n

    assert r.dimensions["fairways"].value == 4  # falls back to `hit`
    assert r.dimensions["fairways"].coverage == "partial"
    assert r.dimensions["fairways"].n == 6  # `tracked` carried onto Metric.n

    assert r.dimensions["bunkers"].value == 3  # falls back to `total`
    assert r.dimensions["bunkers"].n is None  # no holes_tracked/tracked key
    assert r.dimensions["sand_save"].value is None  # explicit `value` key
    assert r.dimensions["sand_save"].coverage == "none"

    # top-level coverage + notes passed through
    assert r.coverage["scoring"] == "full"
    assert r.coverage["putts"] == "partial"
    assert len(r.notes) == 2


async def test_rounds_does_not_crash_on_missing_dimension_keys():
    record = {
        "id": "minimal",
        "date": "2026-01-01",
        "course": {},
        "result": {},
        "holes": [],
        "scoring": {},
        "dimensions": {"weird": {"coverage": "none"}},
        "coverage": {},
        "notes": [],
    }
    gs.save_round(record)

    rounds = await GameBookSource().rounds()

    assert len(rounds) == 1
    assert rounds[0].dimensions["weird"].value is None
    assert rounds[0].dimensions["weird"].coverage == "none"


# --------------------------------------------------------------------------- #
# sessions() / profile() / handicap() / club_gapping()
# --------------------------------------------------------------------------- #


async def test_sessions_is_always_empty():
    assert await GameBookSource().sessions() == []


async def test_profile_handicap_clubs_are_none():
    source = GameBookSource()
    assert await source.profile() is None
    assert await source.handicap() is None
    assert await source.club_gapping() is None
