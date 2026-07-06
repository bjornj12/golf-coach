"""The Trackman `Source` adapter: GraphQL responses -> the normalized model.

Fetches through the same `TrackmanClient` + `Config` the MCP tools use (see
`server.py`), but does not import `server` (that would be circular — `server`
is the tools layer, this is a data-source layer underneath it). Auth-retry
sophistication (silent refresh on 401) is intentionally NOT duplicated here;
that lives in the tools layer's `_run` helper. This adapter does a plain,
single-shot authenticated call per fetch.

No coaching opinions here — just shaping Trackman's raw GraphQL shapes into
`..model` types, tagged with `source="trackman"` and `TRACKMAN_CONTEXT`.
"""

from __future__ import annotations

from typing import Any

from ... import queries
from ...client import TrackmanClient
from ...config import Config
from ...model import (
    TRACKMAN_CONTEXT,
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


class TrackmanSource:
    """Normalizes Trackman's GraphQL data into the shared golf-coach model."""

    name: str = "trackman"
    context: SourceContext = TRACKMAN_CONTEXT

    def supports(self) -> set[str]:
        return {"rounds", "sessions", "profile", "handicap", "clubs", "auth"}

    # ----------------------------------------------------------------- #
    # Fetch (minimal — no retry; the tools layer's `_run` owns that)
    # ----------------------------------------------------------------- #

    async def _fetch(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        config = Config.from_env()
        async with TrackmanClient(config) as client:
            return await client.execute(query, variables)

    # ----------------------------------------------------------------- #
    # rounds()
    # ----------------------------------------------------------------- #

    async def rounds(self, **filters: Any) -> list[Round]:
        variables = {
            "skip": filters.get("skip", 0),
            "take": filters.get("take", 20),
            "completed": filters.get("completed", True),
        }
        data = await self._fetch(queries.COURSE_ROUNDS, variables)
        scorecards = (data.get("me") or {}).get("scorecards") or []
        return [self._normalize_round(sc) for sc in scorecards]

    def _normalize_round(self, sc: dict[str, Any]) -> Round:
        holes: list[Hole] = []
        for h in sc.get("holes") or []:
            if h.get("holeNumber") is None or h.get("par") is None or h.get("grossScore") is None:
                continue  # not yet played — nothing to normalize
            holes.append(
                Hole(
                    number=h["holeNumber"],
                    par=h["par"],
                    score=h["grossScore"],
                    putts=h.get("putts"),
                    gir=h.get("greenInRegulation"),
                )
            )

        course = Course(
            par=sc.get("par"),
            name=(sc.get("course") or {}).get("displayName"),
        )
        result = RoundResult(
            gross=sc.get("grossScore"),
            net=sc.get("netScore"),
            to_par=sc.get("toPar"),
        )

        stat = sc.get("stat") or {}
        dimensions: dict[str, Metric] = {}
        coverage: dict[str, str] = {}

        if stat.get("numberOfPutts") is not None:
            dimensions["putts"] = Metric(
                name="putts", value=float(stat["numberOfPutts"]), unit="count", coverage="full"
            )
            coverage["putts"] = "full"
        if stat.get("averagePuttsPerHoleDecimal") is not None:
            dimensions["putts_per_hole"] = Metric(
                name="putts_per_hole",
                value=float(stat["averagePuttsPerHoleDecimal"]),
                unit="count",
                coverage="full",
            )
            coverage["putts_per_hole"] = "full"
        if stat.get("greenInRegulation") is not None:
            dimensions["gir"] = Metric(
                name="gir", value=float(stat["greenInRegulation"]), unit="count", coverage="full"
            )
            coverage["gir"] = "full"

        fair_hit, fair_left, fair_right = (
            stat.get("fairwayHitFairway"),
            stat.get("fairwayHitLeft"),
            stat.get("fairwayHitRight"),
        )
        if fair_hit is not None and fair_left is not None and fair_right is not None:
            total_fairways = fair_hit + fair_left + fair_right
            pct = (fair_hit / total_fairways * 100) if total_fairways else None
            dimensions["fairways_hit_pct"] = Metric(
                name="fairways_hit_pct",
                value=pct,
                unit="pct",
                coverage="full",
                n=total_fairways,
            )
            coverage["fairways_hit_pct"] = "full"

        if stat.get("driveAverage") is not None:
            dimensions["drive_average"] = Metric(
                name="drive_average", value=stat["driveAverage"], unit="m", coverage="full"
            )
            coverage["drive_average"] = "full"

        scoring: dict[str, Any] = {"to_par": sc.get("toPar")}
        distribution: dict[str, Any] = {}
        for src_key, dst_key in (
            ("birdies", "birdie"),
            ("pars", "par"),
            ("bogeys", "bogey"),
            ("doubleBogeys", "double_bogey"),
            ("tripleBogeysOrWorse", "triple_plus"),
            ("eagles", "eagle"),
        ):
            if stat.get(src_key) is not None:
                distribution[dst_key] = stat[src_key]
        if distribution:
            scoring["distribution"] = distribution

        return Round(
            source=self.name,
            context=self.context,
            id=str(sc.get("id")),
            date=sc.get("startedAt") or sc.get("createdAt"),
            course=course,
            result=result,
            holes=holes,
            scoring=scoring,
            dimensions=dimensions,
            coverage=coverage,
        )

    # ----------------------------------------------------------------- #
    # sessions()
    # ----------------------------------------------------------------- #

    async def sessions(self, **filters: Any) -> list[Session]:
        variables = {
            "skip": filters.get("skip", 0),
            "take": filters.get("take", 25),
            "kinds": filters.get("kinds"),
            "timeFrom": filters.get("time_from"),
            "timeTo": filters.get("time_to"),
            "includeHidden": filters.get("include_hidden", False),
        }
        data = await self._fetch(queries.LIST_SESSIONS, variables)
        items = (data.get("me") or {}).get("activities", {}).get("items") or []
        return [self._normalize_session(item) for item in items]

    def _normalize_session(self, item: dict[str, Any]) -> Session:
        metrics: dict[str, Metric] = {}
        if item.get("numberOfStrokes") is not None:
            metrics["stroke_count"] = Metric(
                name="stroke_count",
                value=float(item["numberOfStrokes"]),
                unit="count",
                coverage="full",
            )
        if item.get("grossScore") is not None:
            metrics["gross_score"] = Metric(
                name="gross_score",
                value=float(item["grossScore"]),
                unit="strokes",
                coverage="full",
            )
        if item.get("netScore") is not None:
            metrics["net_score"] = Metric(
                name="net_score", value=float(item["netScore"]), unit="strokes", coverage="full"
            )
        if item.get("toPar") is not None:
            metrics["to_par"] = Metric(
                name="to_par", value=float(item["toPar"]), unit="strokes", coverage="full"
            )

        return Session(
            source=self.name,
            context=self.context,
            id=str(item.get("id")),
            time=item.get("time"),
            kind=item.get("kind"),
            shots=[],  # shot-level detail needs a per-session fetch; enrich later
            metrics=metrics,
        )

    # ----------------------------------------------------------------- #
    # profile() / handicap() / club_gapping()
    # ----------------------------------------------------------------- #

    async def profile(self) -> Profile | None:
        data = await self._fetch(queries.PROFILE)
        me = data.get("me") or {}
        prof = me.get("profile") or {}
        if not prof:
            return None
        hcp = me.get("hcp") or {}
        db_id = prof.get("dbId")
        player_id = prof.get("id") or (str(db_id) if db_id is not None else None)
        return Profile(
            source=self.name,
            name=prof.get("fullName") or prof.get("playerName"),
            player_id=player_id,
            handicap=hcp.get("currentHcp"),
        )

    async def handicap(self) -> Handicap | None:
        data = await self._fetch(
            queries.HANDICAP_HISTORY, {"skip": 0, "take": 20, "onlyInAvg": False}
        )
        hcp = (data.get("me") or {}).get("hcp") or {}
        if not hcp:
            return None
        history = (hcp.get("playerHistory") or {}).get("items") or []
        return Handicap(source=self.name, current=hcp.get("currentHcp"), history=history)

    async def club_gapping(self) -> ClubGapping | None:
        data = await self._fetch(queries.CLUB_STATS, {"includeRetired": False})
        clubs = ((data.get("me") or {}).get("equipment") or {}).get("clubs") or []
        if not clubs:
            return None
        return ClubGapping(source=self.name, clubs=[self._normalize_club(c) for c in clubs])

    def _normalize_club(self, club: dict[str, Any]) -> dict[str, Any]:
        fmd = club.get("findMyDistance") or {}
        stats = fmd.get("clubStats") or {}
        return {
            "name": club.get("displayName"),
            "retired": club.get("isRetired"),
            "carry": stats.get("carry"),
            "total": stats.get("total"),
            "carry_std_dev": stats.get("standardDeviationCarry"),
            "total_std_dev": stats.get("standardDeviationTotal"),
            "n_shots": fmd.get("numberOfShots"),
        }

    # ----------------------------------------------------------------- #
    # analyze() — the per-source expert analyzer, for `synthesis.synthesize()`
    # ----------------------------------------------------------------- #

    async def analyze(self) -> list[Finding]:
        """Run the Trackman expert analyzer over this source's current data.

        Deliberately does NOT fetch `sessions()` here: `sessions()` always
        comes back with `shots=[]` (shot-level detail needs a per-session
        fetch — see `_normalize_session`), so the analyzer would find nothing
        from it. That's a follow-up (shot-level session enrichment); gapping
        is the current Trackman signal, so it's the only fetch here.
        """
        from . import analyzer as trackman_analyzer  # lazy: avoid import cycles

        gapping = await self.club_gapping()
        return trackman_analyzer.analyze([], club_gapping=gapping)


# Module-level singleton, registered at import time (see registry.register).
registry.register(TrackmanSource())
