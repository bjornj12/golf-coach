"""Tests for the Source protocol conformance and the in-process source registry.

The registry is how tools discover which data sources (Trackman, GameBook, ...)
are available at runtime, without importing any concrete source module.
"""

from __future__ import annotations

from typing import Any

import pytest

from golf_coach.model import (
    GAMEBOOK_CONTEXT,
    ClubGapping,
    Finding,
    Handicap,
    Profile,
    Round,
    Session,
)
from golf_coach.sources import registry
from golf_coach.sources.base import Source


class FakeSource:
    """Minimal Source conformance for tests — no real data behind it."""

    def __init__(self, name: str = "fake") -> None:
        self.name = name
        self.context = GAMEBOOK_CONTEXT

    def supports(self) -> set[str]:
        return {"rounds"}

    async def rounds(self, **filters: Any) -> list[Round]:
        return []

    async def sessions(self, **filters: Any) -> list[Session]:
        return []

    async def profile(self) -> Profile | None:
        return None

    async def handicap(self) -> Handicap | None:
        return None

    async def club_gapping(self) -> ClubGapping | None:
        return None

    async def analyze(self) -> list[Finding]:
        return []


@pytest.fixture(autouse=True)
def _isolate_registry():
    registry.clear()
    yield
    registry.clear()


def test_fake_source_conforms_to_protocol():
    assert isinstance(FakeSource(), Source)


def test_register_and_get_source():
    source = FakeSource(name="fake")
    registry.register(source)
    assert registry.get_source("fake") is source
    assert source in registry.available_sources()
    assert registry.get_source("nope") is None


def test_available_sources_sorted_by_name():
    registry.register(FakeSource(name="z"))
    registry.register(FakeSource(name="a"))
    assert [s.name for s in registry.available_sources()] == ["a", "z"]


def test_register_is_idempotent_last_wins():
    first = FakeSource(name="dup")
    second = FakeSource(name="dup")
    registry.register(first)
    registry.register(second)
    assert registry.get_source("dup") is second
    assert len(registry.available_sources()) == 1


def test_clear_empties_registry():
    registry.register(FakeSource(name="fake"))
    registry.clear()
    assert registry.available_sources() == []
    assert registry.get_source("fake") is None
