"""The GameBook `Source` adapter: stored rounds -> the normalized model.

GameBook (via the gamebook-screenshot-analysis skill) extracts on-course
rounds from screenshots and persists them through `gamebook_store`. This
adapter reads whatever is already on disk and reshapes it into the shared
`..model` types tagged with `source="gamebook"` and `GAMEBOOK_CONTEXT` — it
does no scraping and no coaching, just normalization of an already-stored,
coverage-aware round record.

GameBook is scorecard-only: no shot-level launch data, no session log, no
profile/handicap/club data, no auth. `supports()` reflects that.
"""

from __future__ import annotations

from typing import Any

from ... import gamebook_store
from ...model import (
    GAMEBOOK_CONTEXT,
    ClubGapping,
    Course,
    Finding,
    Handicap,
    Hole,
    Metric,
    Profile,
    Round,
    RoundResult,
    Session,
    SourceContext,
)
from .. import registry


class GameBookSource:
    """Normalizes stored GameBook round records into the shared model."""

    name: str = "gamebook"
    context: SourceContext = GAMEBOOK_CONTEXT

    def supports(self) -> set[str]:
        return {"rounds"}

    # ----------------------------------------------------------------- #
    # rounds()
    # ----------------------------------------------------------------- #

    async def rounds(self, **filters: Any) -> list[Round]:
        records = gamebook_store.list_rounds()
        return [self._normalize_round(r) for r in records]

    def _normalize_round(self, record: dict[str, Any]) -> Round:
        course_raw = record.get("course") or {}
        course = Course(
            par=course_raw.get("par"),
            cr=course_raw.get("cr"),
            slope=course_raw.get("slope"),
            name=course_raw.get("name"),
        )

        result_raw = record.get("result") or {}
        result = RoundResult(
            gross=result_raw.get("gross"),
            net=result_raw.get("net"),
            to_par=result_raw.get("to_par"),
            position=result_raw.get("position"),
        )

        holes = [
            Hole(
                number=h.get("hole"),
                par=h.get("par"),
                score=h.get("score"),
                putts=h.get("putts"),
                fairway=h.get("fairway"),
                gir=h.get("gir"),
                bunkers=h.get("bunkers"),
                chips=h.get("chips"),
                penalties=h.get("penalties"),
            )
            for h in record.get("holes") or []
        ]

        dimensions = {
            name: self._normalize_dimension(name, dim)
            for name, dim in (record.get("dimensions") or {}).items()
        }

        return Round(
            source=self.name,
            context=self.context,
            id=str(record.get("id")),
            date=record.get("date"),
            course=course,
            result=result,
            holes=holes,
            scoring=dict(record.get("scoring") or {}),
            dimensions=dimensions,
            coverage=dict(record.get("coverage") or {}),
            notes=list(record.get("notes") or []),
        )

    @staticmethod
    def _normalize_dimension(name: str, dim: dict[str, Any]) -> Metric:
        """Stored dimension dicts don't share one value key (`value`, `total`,
        `hit`, ...) — pick the first present, in that priority order, so the
        common case (a single scalar) survives without losing the coverage
        flag. Lossless-enough, not a full re-encoding of every stored key."""
        if "value" in dim:
            value = dim["value"]
        elif "total" in dim:
            value = dim["total"]
        elif "hit" in dim:
            value = dim["hit"]
        else:
            value = None
        return Metric(name=name, value=value, coverage=dim.get("coverage", "none"))

    # ----------------------------------------------------------------- #
    # sessions() / profile() / handicap() / club_gapping() — unsupported
    # ----------------------------------------------------------------- #

    async def sessions(self, **filters: Any) -> list[Session]:
        return []

    async def profile(self) -> Profile | None:
        return None

    async def handicap(self) -> Handicap | None:
        return None

    async def club_gapping(self) -> ClubGapping | None:
        return None

    # ----------------------------------------------------------------- #
    # analyze() — the per-source expert analyzer, for `synthesis.synthesize()`
    # ----------------------------------------------------------------- #

    async def analyze(self) -> list[Finding]:
        from . import analyzer as gamebook_analyzer  # lazy: avoid import cycles

        rounds = await self.rounds()
        return gamebook_analyzer.analyze(rounds)


# Module-level singleton, registered at import time (see registry.register).
registry.register(GameBookSource())
