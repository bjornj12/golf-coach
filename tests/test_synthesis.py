"""Tests for the cross-source normalizer (`synthesis.align` / `synthesize`).

`align` is the deterministic Stage-2 normalizer: it pulls per-source
`Finding`s into one cross-source, context-aware view. It renders NO verdict —
alignment, context-tagging, and presence/coverage bookkeeping only (see
CLAUDE.md's core boundary; interpretation stays in the coaching skills).
"""

from __future__ import annotations

from typing import Any

from golf_coach.model import (
    GAMEBOOK_CONTEXT,
    TRACKMAN_CONTEXT,
    ClubGapping,
    CrossSourceView,
    Finding,
    Handicap,
    Profile,
    Round,
    Session,
    Shot,
)
from golf_coach.sources import registry
from golf_coach.synthesis import align, synthesize


def _finding(
    skill_area: str,
    source: str,
    context,
    *,
    metric: str = "metric",
    value: float | None = 1.0,
    coverage: str = "full",
) -> Finding:
    return Finding(
        skill_area=skill_area,
        source=source,
        context=context,
        metric=metric,
        value=value,
        coverage=coverage,
    )


# --------------------------------------------------------------------------- #
# align()
# --------------------------------------------------------------------------- #


def test_align_empty_returns_empty_view():
    view = align([])
    assert view == CrossSourceView()
    assert view.by_skill_area == {}
    assert view.cross_source_deltas == []
    assert view.context_notes == []
    assert view.coverage_summary == {}


def test_align_two_sources_same_area_produces_delta_and_context_note():
    trackman_finding = _finding(
        "approach", "trackman", TRACKMAN_CONTEXT, metric="dispersion", value=5.2
    )
    gamebook_finding = _finding(
        "approach", "gamebook", GAMEBOOK_CONTEXT, metric="gir_hit", value=3.0, coverage="partial"
    )

    view = align([trackman_finding, gamebook_finding])

    assert len(view.by_skill_area["approach"]) == 2
    assert view.by_skill_area["approach"] == [trackman_finding, gamebook_finding]

    assert len(view.cross_source_deltas) == 1
    delta = view.cross_source_deltas[0]
    assert delta["skill_area"] == "approach"
    assert set(delta["sources"]) == {"trackman", "gamebook"}
    assert delta["sources"]["trackman"] == {
        "metric": "dispersion",
        "value": 5.2,
        "coverage": "full",
        "setting": "controlled",
    }
    assert delta["sources"]["gamebook"] == {
        "metric": "gir_hit",
        "value": 3.0,
        "coverage": "partial",
        "setting": "on_course",
    }
    assert "context_note" in delta
    assert "lies" in delta["context_note"] or "pressure" in delta["context_note"]

    assert len(view.context_notes) == 1
    assert "clean-room" in view.context_notes[0] or "on-course" in view.context_notes[0]


def test_align_single_source_area_yields_no_delta():
    trackman_finding = _finding("gapping", "trackman", TRACKMAN_CONTEXT)

    view = align([trackman_finding])

    assert view.by_skill_area["gapping"] == [trackman_finding]
    assert view.cross_source_deltas == []
    assert view.context_notes == []


def test_align_mixed_areas_only_multi_source_area_gets_delta():
    driving_trackman = _finding("driving", "trackman", TRACKMAN_CONTEXT)
    driving_gamebook = _finding("driving", "gamebook", GAMEBOOK_CONTEXT)
    putting_trackman_only = _finding("putting", "trackman", TRACKMAN_CONTEXT)

    view = align([driving_trackman, driving_gamebook, putting_trackman_only])

    areas_with_deltas = {d["skill_area"] for d in view.cross_source_deltas}
    assert areas_with_deltas == {"driving"}
    assert len(view.by_skill_area["putting"]) == 1


def test_coverage_summary_maps_area_to_source_to_coverage():
    trackman_finding = _finding("scoring", "trackman", TRACKMAN_CONTEXT, coverage="full")
    gamebook_finding = _finding("scoring", "gamebook", GAMEBOOK_CONTEXT, coverage="partial")

    view = align([trackman_finding, gamebook_finding])

    assert view.coverage_summary == {
        "scoring": {"trackman": "full", "gamebook": "partial"}
    }


def test_align_same_source_multiple_findings_uses_first_for_delta_and_coverage():
    first = _finding("driving", "trackman", TRACKMAN_CONTEXT, metric="dispersion", value=1.0)
    second = _finding("driving", "trackman", TRACKMAN_CONTEXT, metric="carry_avg", value=2.0)
    gamebook_finding = _finding("driving", "gamebook", GAMEBOOK_CONTEXT, metric="fairways_hit")

    view = align([first, second, gamebook_finding])

    assert len(view.by_skill_area["driving"]) == 3
    delta = next(d for d in view.cross_source_deltas if d["skill_area"] == "driving")
    assert delta["sources"]["trackman"]["metric"] == "dispersion"  # first, not second
    assert view.coverage_summary["driving"]["trackman"] == "full"


def test_align_no_context_note_when_both_sources_share_setting():
    """Two sources in one area, but neither controlled+on_course mix, means no
    context_note on the delta (and no global note)."""
    a = _finding("gapping", "trackman", TRACKMAN_CONTEXT)
    b = _finding("gapping", "another_trackman_like_source", TRACKMAN_CONTEXT)

    view = align([a, b])

    delta = view.cross_source_deltas[0]
    assert "context_note" not in delta
    assert view.context_notes == []


# --------------------------------------------------------------------------- #
# synthesize() — light, isolated (fake sources; no real network/disk)
# --------------------------------------------------------------------------- #


class _FakeTrackmanSource:
    name = "trackman"
    context = TRACKMAN_CONTEXT

    def supports(self) -> set[str]:
        return {"sessions"}

    async def rounds(self, **filters: Any) -> list[Round]:
        return []

    async def sessions(self, **filters: Any) -> list[Session]:
        return [
            Session(
                source="trackman",
                context=TRACKMAN_CONTEXT,
                id="s1",
                kind="RANGE_PRACTICE",
                shots=[Shot(club="DRIVER", side=2.0, carry=240.0)],
            )
        ]

    async def profile(self) -> Profile | None:
        return None

    async def handicap(self) -> Handicap | None:
        return None

    async def club_gapping(self) -> ClubGapping | None:
        return None

    async def analyze(self) -> list[Finding]:
        from golf_coach.sources.trackman import analyzer as trackman_analyzer

        sessions = await self.sessions()
        return trackman_analyzer.analyze(sessions)


class _FakeGameBookSource:
    name = "gamebook"
    context = GAMEBOOK_CONTEXT

    def supports(self) -> set[str]:
        return {"rounds"}

    async def rounds(self, **filters: Any) -> list[Round]:
        return [
            Round(
                source="gamebook",
                context=GAMEBOOK_CONTEXT,
                id="r1",
                date="2026-06-01",
                scoring={"to_par": 5},
            )
        ]

    async def sessions(self, **filters: Any) -> list[Session]:
        return []

    async def profile(self) -> Profile | None:
        return None

    async def handicap(self) -> Handicap | None:
        return None

    async def club_gapping(self) -> ClubGapping | None:
        return None

    async def analyze(self) -> list[Finding]:
        from golf_coach.sources.gamebook import analyzer as gamebook_analyzer

        rounds = await self.rounds()
        return gamebook_analyzer.analyze(rounds)


class _RaisingSource:
    name = "gamebook"
    context = GAMEBOOK_CONTEXT

    def supports(self) -> set[str]:
        return {"rounds"}

    async def rounds(self, **filters: Any) -> list[Round]:
        raise RuntimeError("boom")

    async def sessions(self, **filters: Any) -> list[Session]:
        return []

    async def profile(self) -> Profile | None:
        return None

    async def handicap(self) -> Handicap | None:
        return None

    async def club_gapping(self) -> ClubGapping | None:
        return None

    async def analyze(self) -> list[Finding]:
        raise RuntimeError("boom")


async def test_synthesize_returns_empty_view_when_no_sources_registered():
    registry.clear()
    try:
        view = await synthesize()
    finally:
        registry.clear()

    assert view == CrossSourceView()


async def test_synthesize_combines_registered_fake_sources():
    registry.clear()
    try:
        registry.register(_FakeTrackmanSource())
        registry.register(_FakeGameBookSource())
        view = await synthesize()
    finally:
        registry.clear()

    assert isinstance(view, CrossSourceView)
    assert "scoring" in view.by_skill_area
    sources_present = {f.source for fs in view.by_skill_area.values() for f in fs}
    assert sources_present == {"trackman", "gamebook"}


async def test_synthesize_skips_source_that_raises_without_crashing():
    registry.clear()
    try:
        registry.register(_RaisingSource())
        view = await synthesize()
    finally:
        registry.clear()

    # The view must not crash, must carry no findings from the failed source,
    # and must record the failure observably (I3) — naming only the exception
    # type, never a secret.
    assert isinstance(view, CrossSourceView)
    assert view.by_skill_area == {}
    assert view.cross_source_deltas == []
    assert view.context_notes == ["gamebook source unavailable: RuntimeError"]
