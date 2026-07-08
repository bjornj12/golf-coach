"""Normalized, coverage- and context-aware data model shared across sources.

Every source (Trackman, GameBook, ...) normalizes its raw shape into these
types before a per-source analyzer looks at it. The model carries no coaching
opinions — just data, tagged with *where it came from* (`source`), *under what
conditions* (`context`: controlled range vs. on-course, real weather or not),
and *how much of it there is* (`coverage`) — so a downstream cross-source
normalizer can reason about how much to trust any given number instead of
silently averaging a range-mat carry with a wind-blown one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Coverage = Literal["full", "partial", "none"]


class SourceContext(BaseModel):
    """The load-bearing context metadata a data point was captured under."""

    setting: Literal["controlled", "on_course"]
    lie: Literal["flat", "variable"]
    conditions: Literal["none", "real"]  # wind/weather/pressure
    granularity: Literal["shot", "scorecard"]


TRACKMAN_CONTEXT = SourceContext(
    setting="controlled", lie="flat", conditions="none", granularity="shot"
)
GAMEBOOK_CONTEXT = SourceContext(
    setting="on_course", lie="variable", conditions="real", granularity="scorecard"
)


class Metric(BaseModel):
    """An atomic, coverage-aware stat."""

    name: str
    value: float | None = None
    unit: str | None = None
    coverage: Coverage = "none"
    n: int | None = None


class Hole(BaseModel):
    number: int
    par: int
    score: int
    putts: int | None = None
    fairway: Literal["hit", "miss_left", "miss_right", "na"] | None = None
    gir: bool | None = None
    bunkers: int | None = None
    chips: int | None = None
    penalties: int | None = None


class Shot(BaseModel):
    """A launch-monitor shot (Trackman only). Extra launch fields allowed."""

    model_config = ConfigDict(extra="allow")

    club: str | None = None
    ball_speed: float | None = None
    club_speed: float | None = None
    smash: float | None = None
    launch_angle: float | None = None
    spin: float | None = None
    carry: float | None = None
    total: float | None = None
    side: float | None = None
    curve: float | None = None
    landing_angle: float | None = None
    max_height: float | None = None
    hang_time: float | None = None
    # Club-delivery metrics (what the club did at impact) — the "why" behind the
    # ball flight. All optional; a source fills what it measures.
    attack_angle: float | None = None  # deg; + = up (driver wants +)
    club_path: float | None = None  # deg; - = out-to-in, + = in-to-out
    face_angle: float | None = None  # deg to target; - = closed (left), + = open (right)
    dynamic_loft: float | None = None  # deg presented at impact
    back_spin: float | None = None  # rpm
    side_spin: float | None = None  # rpm; - = left, + = right


class Course(BaseModel):
    par: int | None = None
    cr: float | None = None
    slope: int | None = None
    name: str | None = None


class RoundResult(BaseModel):
    gross: int | None = None
    net: int | None = None
    to_par: int | None = None
    position: str | None = None


class Round(BaseModel):
    source: str
    context: SourceContext
    id: str
    date: str | None = None
    course: Course = Field(default_factory=Course)
    result: RoundResult = Field(default_factory=RoundResult)
    holes: list[Hole] = Field(default_factory=list)
    scoring: dict[str, Any] = Field(default_factory=dict)  # {to_par, distribution, by_par_type}
    dimensions: dict[str, Metric] = Field(default_factory=dict)
    coverage: dict[str, Coverage] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Session(BaseModel):
    source: str
    context: SourceContext
    id: str
    time: str | None = None
    kind: str | None = None
    category: str | None = None
    seriousness: float | None = None
    shots: list[Shot] = Field(default_factory=list)
    metrics: dict[str, Metric] = Field(default_factory=dict)


class Profile(BaseModel):
    source: str
    name: str | None = None
    player_id: str | None = None
    handicap: float | None = None


class Handicap(BaseModel):
    source: str
    current: float | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


class ClubGapping(BaseModel):
    source: str
    clubs: list[dict[str, Any]] = Field(default_factory=list)


class Finding(BaseModel):
    """What a per-source analyzer emits: factual, not coaching."""

    skill_area: Literal["driving", "approach", "short_game", "putting", "scoring", "gapping"]
    source: str
    context: SourceContext
    metric: str
    value: float | None = None
    unit: str | None = None
    coverage: Coverage = "none"
    direction: Literal["better", "worse", "same"] | None = None
    detail: str = ""


class CrossSourceView(BaseModel):
    """The normalizer's output: findings grouped by skill area, plus deltas."""

    by_skill_area: dict[str, list[Finding]] = Field(default_factory=dict)
    cross_source_deltas: list[dict[str, Any]] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    coverage_summary: dict[str, Any] = Field(default_factory=dict)
