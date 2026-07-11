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

import math
from typing import Any

from ... import queries
from ...analysis import GAME_KINDS, classify_session
from ...client import TrackmanAuthError, TrackmanClient
from ...config import Config
from ...model import (
    TRACKMAN_CONTEXT,
    ClubGapping,
    Course,
    Coverage,
    Finding,
    Handicap,
    Hole,
    Metric,
    Profile,
    Round,
    RoundResult,
    Session,
    Shot,
    SourceContext,
)
from .. import registry

# Seconds to wait for a silent token refresh before giving up (mirrors the tools
# layer's `server.SILENT_REFRESH_TIMEOUT`; duplicated to keep this data-source
# layer independent of the tools layer — see the module docstring).
_SILENT_REFRESH_TIMEOUT = 30.0


def _has_saved_browser_session() -> bool:
    """True if a persisted browser profile from a prior login exists.

    Gates the silent-refresh attempt: with no saved session there is nothing to
    refresh from, so we skip straight to failing loudly instead of waiting out a
    doomed headless browser launch.
    """
    try:
        from ... import token_store

        profile = token_store.cache_dir() / "browser-profile"
        return profile.is_dir() and any(profile.iterdir())
    except Exception:
        return False


async def _try_silent_refresh() -> bool:
    """Refresh the token headlessly from the persisted browser session.

    Returns True only if a fresh token was captured. Mirrors the tools layer's
    `server._try_silent_refresh`, but gated on a saved session so a token-less /
    session-less caller fails fast instead of blocking on a browser launch.
    """
    if not _has_saved_browser_session():
        return False
    try:
        from ...login import capture_token

        await capture_token(headless=True, timeout_seconds=_SILENT_REFRESH_TIMEOUT)
        return True
    except Exception:
        return False


class TrackmanSource:
    """Normalizes Trackman's GraphQL data into the shared golf-coach model."""

    name: str = "trackman"
    context: SourceContext = TRACKMAN_CONTEXT

    def supports(self) -> set[str]:
        return {"rounds", "sessions", "profile", "handicap", "clubs", "auth"}

    # ----------------------------------------------------------------- #
    # Fetch — silent-refresh-on-401 then retry once, mirroring the tools
    # layer's `server._run`. On a genuine expiry (refresh fails too) the
    # `TrackmanAuthError` propagates LOUDLY rather than degrading to an
    # empty, successful-looking view (see `synthesis.synthesize`).
    # ----------------------------------------------------------------- #

    async def _fetch(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        _allow_refresh: bool = True,
    ) -> dict[str, Any]:
        config = Config.from_env()
        try:
            async with TrackmanClient(config) as client:
                return await client.execute(query, variables)
        except TrackmanAuthError:
            if _allow_refresh and await _try_silent_refresh():
                return await self._fetch(query, variables, _allow_refresh=False)
            raise

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
        coverage: dict[str, Coverage] = {}

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

    def _normalize_session(
        self, item: dict[str, Any], shots: list[Shot] | None = None
    ) -> Session:
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
            # shots=[] on the cheap list path; `_recent_practice_shots` passes
            # the per-session detail's mapped strokes here for the analyze path.
            shots=shots or [],
            metrics=metrics,
        )

    @staticmethod
    def _stroke_to_shot(stroke: dict[str, Any]) -> Shot:
        """Map one GET_SESSION stroke -> a `Shot`.

        Populates the three fields `_dispersion_findings` keys on — `club`,
        `side` (`totalSide`, falling back to `carrySide`), `curve` — plus the
        ball/club launch metrics and the club-delivery metrics (`clubPath`,
        `faceAngle`, `attackAngle`, `dynamicLoft`) the bay/sim detail carries.
        `spin` reads range kinds' `ballSpin` first, then sim kinds' `spinRate`;
        missing fields stay None.

        `side_spin`/`back_spin` are DERIVED (pure trig, no judgment) from total
        `spin` and the reported `spinAxis` (degrees) — the inverse of the
        delivery module's `atan2(side, back)` — so the driver spin-axis fact can
        be computed from the axis Trackman actually reports. When the monitor
        gives no axis, both stay None and the axis fact is simply omitted.
        """
        m = stroke.get("measurement") or {}
        side = m.get("totalSide")
        if side is None:
            side = m.get("carrySide")
        spin = m.get("ballSpin")
        if spin is None:
            spin = m.get("spinRate")

        spin_axis = m.get("spinAxis")
        side_spin = back_spin = None
        if isinstance(spin, (int, float)) and isinstance(spin_axis, (int, float)):
            rad = math.radians(spin_axis)
            back_spin = round(spin * math.cos(rad), 2)
            side_spin = round(spin * math.sin(rad), 2)

        return Shot(
            club=stroke.get("club"),
            side=side,
            curve=m.get("curve"),
            carry=m.get("carry"),
            total=m.get("total"),
            ball_speed=m.get("ballSpeed"),
            club_speed=m.get("clubSpeed"),
            launch_angle=m.get("launchAngle"),
            spin=spin,
            landing_angle=m.get("landingAngle"),
            max_height=m.get("maxHeight"),
            hang_time=m.get("hangTime"),
            smash=m.get("smashFactor"),
            attack_angle=m.get("attackAngle"),
            club_path=m.get("clubPath"),
            face_angle=m.get("faceAngle"),
            dynamic_loft=m.get("dynamicLoft"),
            side_spin=side_spin,
            back_spin=back_spin,
        )

    async def _recent_practice_shots(self, limit: int = 2) -> list[Session]:
        """Recent *practice* sessions enriched with shot-level detail.

        The plain `sessions()` list is deliberately shot-free (`shots=[]`) — a
        cheap single call. This is the analyze-only enrichment: it fetches the
        recent activities list, drops played rounds/games by `kind`, takes the
        newest `limit` practice candidates, and only then fetches each one's
        `GET_SESSION` detail to map strokes -> `Shot`s. Detail is fetched for at
        most `limit` sessions, never for the whole list. Returns `[]` when no
        practice session qualifies.
        """
        variables = {
            "skip": 0,
            "take": 15,
            "kinds": None,
            "timeFrom": None,
            "timeTo": None,
            "includeHidden": False,
        }
        data = await self._fetch(queries.LIST_SESSIONS, variables)
        items = (data.get("me") or {}).get("activities", {}).get("items") or []

        # Bound the per-session detail fetches: pre-filter on the cheap list
        # data (exclude games by kind), then take at most `limit` candidates.
        candidates = [item for item in items if item.get("kind") not in GAME_KINDS][:limit]

        enriched: list[Session] = []
        for item in candidates:
            node = await self._fetch(queries.GET_SESSION, {"id": item.get("id")})
            detail = node.get("node") or {}
            if not detail:
                continue
            # Belt-and-suspenders: a course-play node carries a `scorecard`, so
            # classify_session flags it as a game even if the list `kind` didn't.
            if classify_session(detail).get("category") == "game":
                continue
            shots = [self._stroke_to_shot(s) for s in (detail.get("strokes") or [])]
            enriched.append(self._normalize_session(item, shots=shots))
        return enriched

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

        Enriches the analyze path with shot-level detail: `_recent_practice_shots`
        pulls the newest couple of *practice* sessions WITH their strokes mapped
        to `Shot`s, so the analyzer emits `driving`/`approach` dispersion Findings
        (from `Shot.side`/`club`) — the shared skill areas that let
        `synthesize()` produce real cross-source deltas against GameBook. Club
        `gapping` is still fetched as the shots-free carry-spread signal. The
        plain `sessions()` list stays shot-free (cheap); enrichment is here only.
        """
        from . import analyzer as trackman_analyzer  # lazy: avoid import cycles
        from . import delivery as trackman_delivery

        sessions = await self._recent_practice_shots()
        gapping = await self.club_gapping()
        findings = trackman_analyzer.analyze(sessions, club_gapping=gapping)
        # Club-delivery facts (path / face-to-path / spin-axis / attack / spin) —
        # pure measurements over the same enriched driver shots. `synthesize`
        # also surfaces these in a dedicated `delivery` section.
        findings.extend(trackman_delivery.driver_delivery(sessions))
        return findings


# Module-level singleton, registered at import time (see registry.register).
registry.register(TrackmanSource())
