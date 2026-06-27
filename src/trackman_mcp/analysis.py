"""Deterministic session analysis: classification, metrics, normalization.

Pure functions over the data returned by the MCP's `get_session` tool. Kept
deterministic (no LLM) so the analyzer's judgments can be unit-tested and
eval'd. The analyzer *skill* layers narrative/coaching on top of this; this
module makes no coaching recommendations — it classifies and measures.

Distances/speeds are metric (meters, m/s), matching the Trackman API.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# Activity kinds that are inherently "serious" practice regardless of length.
SERIOUS_KINDS = {
    "SHOT_ANALYSIS", "RANGE_FIND_MY_DISTANCE", "PERFORMANCE_CENTER",
    "COMBINE_TEST", "MAP_MY_BAG", "PERFORMANCE_PUTTING",
}
# Activity kinds that are games (played rounds), analyzed separately.
GAME_KINDS = {"COURSE_PLAY", "ON_COURSE", "VIRTUAL_GOLF_PLAY"}

# Thresholds (tunable). A session below these and not a serious kind is a warm-up.
FULL_STROKES = 40      # strokes for a full "volume" score
FULL_MINUTES = 30      # minutes for a full "duration" score
FULL_CLUBS = 4         # distinct clubs for a full "variety" score
SERIOUS_THRESHOLD = 0.5  # seriousness at/above this counts as an improvement attempt

# Hard warm-up floor: a session this small is a warm-up / quick check and is NOT
# an attempt to improve — even for an otherwise "serious" kind. This is the
# "don't count a 5-minute warm-up as training" rule.
WARMUP_MAX_STROKES = 8   # fewer strokes than this …
WARMUP_MAX_MINUTES = 5   # … or shorter than this → warm-up regardless of kind


# --- small numeric helpers ------------------------------------------------

def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _std(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    mean = sum(values) / len(values)
    return round((sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5, 2)


def canonical_club(name: str | None) -> str | None:
    """Normalize club names so the bag ("7Iron") matches stroke data ("IRON7")."""
    if not name:
        return None
    s = re.sub(r"[\s\-_]", "", str(name).upper())
    if "DRIVER" in s:
        return "DRIVER"
    if "PUTTER" in s:
        return "PUTTER"
    loft = re.search(r"(50|52|54|56|58|60)", s)
    if "WEDGE" in s and loft:
        return f"WEDGE{loft.group(1)}"
    if "PITCHING" in s or s == "PW":
        return "PITCHINGWEDGE"
    if "SAND" in s or s == "SW":
        return "SANDWEDGE"
    if ("LOB" in s and "WEDGE" in s) or s == "LW":
        return "LOBWEDGE"
    digit = re.search(r"(\d)", s)
    for family in ("HYBRID", "IRON", "WOOD"):
        if family in s and digit:
            return f"{family}{digit.group(1)}"
    return s


def _parse_time(s: Any) -> datetime | None:
    if not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# --- structure helpers ----------------------------------------------------

def _is_game(detail: dict) -> bool:
    if detail.get("kind") in GAME_KINDS:
        return True
    return bool(detail.get("scorecard"))


def _extract_strokes(detail: dict) -> list[dict]:
    return detail.get("strokes") or []


def _duration_minutes(strokes: list[dict]) -> int:
    times = [t for t in (_parse_time(s.get("time")) for s in strokes) if t]
    if len(times) < 2:
        return 0
    return round((max(times) - min(times)).total_seconds() / 60)


def _seriousness(strokes: int, minutes: float, n_clubs: int, kind: str | None) -> float:
    s_strokes = min(strokes / FULL_STROKES, 1.0)
    s_minutes = min(minutes / FULL_MINUTES, 1.0)
    s_clubs = min(n_clubs / FULL_CLUBS, 1.0)
    score = 0.5 * s_strokes + 0.3 * s_minutes + 0.2 * s_clubs
    if kind in SERIOUS_KINDS:
        score = min(score + 0.2, 1.0)  # focused kinds rank higher, but no hard floor
    return round(score, 2)


def _is_warmup_sized(strokes: int, minutes: float) -> bool:
    """True if the session is too small to be a genuine improvement attempt."""
    return strokes < WARMUP_MAX_STROKES or minutes < WARMUP_MAX_MINUTES


def _course_difficulty(scorecard: dict) -> dict:
    basis: list[str] = []
    dist = scorecard.get("totalDistance")
    score = None
    if isinstance(dist, (int, float)) and dist > 0:
        score = max(0.0, min((dist - 5000) / 2000, 1.0))
        basis.append(f"length {dist:.0f}m")
    hcp = scorecard.get("courseHcp")
    if isinstance(hcp, (int, float)):
        basis.append(f"courseHcp {hcp}")
    stimp = scorecard.get("greenStimp")
    if isinstance(stimp, (int, float)) and stimp:
        basis.append(f"green stimp {stimp}")
    if score is None:
        score = 0.5
        basis.append("limited difficulty data")
    return {"score": round(score, 2), "basis": basis}


# --- public API -----------------------------------------------------------

def classify_session(detail: dict) -> dict:
    """Classify a session as game / practice / warm-up / other.

    Returns category, seriousness (0..1), whether it's an improvement attempt,
    and the reasons behind the call.
    """
    kind = detail.get("kind")
    if _is_game(detail):
        return {
            "category": "game", "kind": kind, "seriousness": None,
            "is_improvement_attempt": False,
            "reasons": ["course play — analyzed as a game, not practice"],
            "stroke_count": None, "duration_minutes": None, "clubs_used": [],
        }

    strokes = _extract_strokes(detail)
    n = len(strokes)
    minutes = _duration_minutes(strokes)
    clubs = sorted({s.get("club") for s in strokes if s.get("club")})
    seriousness = _seriousness(n, minutes, len(clubs), kind)

    if n == 0:
        category, improve = "other", False
        reasons = ["no stroke data on this session"]
    elif _is_warmup_sized(n, minutes):
        # Hard floor: too small to be training, even for a "serious" kind.
        category, improve = "warmup", False
        note = (
            f"only {n} strokes over {minutes} min — a warm-up / quick check, "
            "not counted as an attempt to improve"
        )
        if kind in SERIOUS_KINDS:
            note += f" (despite being a {kind} session)"
        reasons = [note]
    elif seriousness >= SERIOUS_THRESHOLD or kind in SERIOUS_KINDS:
        category, improve = "practice", True
        reasons = [f"{n} strokes over {minutes} min across {len(clubs)} club(s)"]
        if kind in SERIOUS_KINDS:
            reasons.append(f"{kind} session (inherently focused practice)")
    else:
        category, improve = "warmup", False
        reasons = [
            f"only {n} strokes over {minutes} min, {len(clubs)} club(s) — "
            "below the practice threshold (treated as a warm-up, not an "
            "attempt to improve)"
        ]

    return {
        "category": category, "kind": kind, "seriousness": seriousness,
        "is_improvement_attempt": improve, "reasons": reasons,
        "stroke_count": n, "duration_minutes": minutes, "clubs_used": clubs,
    }


def session_metrics(detail: dict) -> dict:
    """Aggregate per-session stats (shape depends on game vs practice)."""
    if _is_game(detail):
        sc = detail.get("scorecard") or {}
        stat = sc.get("stat") or {}
        holes = sc.get("holes") or []
        return {
            "type": "game",
            "course_name": (sc.get("course") or {}).get("displayName"),
            "holes_played": sc.get("numberOfHolesPlayed") or len(holes),
            "par": sc.get("par"),
            "gross_score": sc.get("grossScore"),
            "to_par": sc.get("toPar"),
            "net_to_par": sc.get("netToPar"),
            "green_in_regulation": stat.get("greenInRegulation"),
            "putts": stat.get("numberOfPutts"),
            "fairways_hit": stat.get("fairwayHitFairway"),
            "drive_average": stat.get("driveAverage"),
            "drive_max": stat.get("driveMax"),
            "score_distribution": {
                k: stat.get(k) for k in
                ("eagles", "birdies", "pars", "bogeys", "doubleBogeys",
                 "tripleBogeysOrWorse")
            },
            "clubs_used": sorted({
                s.get("club") for h in holes for s in (h.get("shots") or [])
                if s.get("club")
            }),
            "course_difficulty": _course_difficulty(sc),
        }

    strokes = _extract_strokes(detail)
    per_club: dict[str, dict] = {}
    carries: list[float] = []
    for s in strokes:
        club = s.get("club")
        m = s.get("measurement") or {}
        carry = m.get("carry")
        speed = m.get("ballSpeed")
        if isinstance(carry, (int, float)):
            carries.append(carry)
        if not club:
            continue
        slot = per_club.setdefault(club, {"carries": [], "speeds": [], "n": 0})
        slot["n"] += 1
        if isinstance(carry, (int, float)):
            slot["carries"].append(carry)
        if isinstance(speed, (int, float)):
            slot["speeds"].append(speed)
    per_club_out = {
        club: {
            "n": d["n"],
            "carry_avg": _avg(d["carries"]),
            "carry_std": _std(d["carries"]),
            "ball_speed_avg": _avg(d["speeds"]),
        }
        for club, d in per_club.items()
    }
    return {
        "type": "practice",
        "stroke_count": len(strokes),
        "duration_minutes": _duration_minutes(strokes),
        "clubs_used": sorted(per_club.keys()),
        "avg_carry": _avg(carries),
        "per_club": per_club_out,
    }


def normalize_value(value: float, history: list[float]) -> dict:
    """Express `value` relative to a history series (mean, delta, z, n)."""
    if not history:
        return {"value": value, "mean": None, "delta": None, "z": None, "n": 0}
    mean = sum(history) / len(history)
    std = (sum((x - mean) ** 2 for x in history) / len(history)) ** 0.5
    z = (value - mean) / std if std > 0 else None
    return {
        "value": value,
        "mean": round(mean, 2),
        "delta": round(value - mean, 2),
        "z": round(z, 2) if z is not None else None,
        "n": len(history),
    }


def _history_values(history: list[dict], category: str, key: str) -> list[float]:
    out: list[float] = []
    for rec in history:
        a = rec.get("analysis") or {}
        if a.get("category") != category:
            continue
        val = (a.get("metrics") or {}).get(key)
        if isinstance(val, (int, float)):
            out.append(float(val))
    return out


# Which metrics to normalize per category.
_NORMALIZE_KEYS = {
    "game": ["to_par", "putts", "green_in_regulation", "drive_average"],
    "practice": ["stroke_count", "duration_minutes", "avg_carry"],
}


def _normalize_metrics(category: str, metrics: dict, history: list[dict]) -> dict:
    out = {}
    for key in _NORMALIZE_KEYS.get(category, []):
        val = metrics.get(key)
        if isinstance(val, (int, float)):
            out[key] = normalize_value(float(val), _history_values(history, category, key))
    return out


def _summary(classification: dict, metrics: dict, normalized: dict) -> str:
    cat = classification["category"]
    if cat == "game":
        course = metrics.get("course_name") or "an unknown course"
        bits = [
            f"Round at {course}: {metrics.get('to_par')} to par over "
            f"{metrics.get('holes_played')} holes."
        ]
        tp = normalized.get("to_par")
        if tp and tp.get("delta") is not None:
            d = tp["delta"]
            trend = "better" if d < 0 else "worse" if d > 0 else "even"
            bits.append(f"That's {abs(d):.0f} {trend} than your recent average.")
        bits.append(
            f"GIR {metrics.get('green_in_regulation')}, "
            f"putts {metrics.get('putts')}, "
            f"course difficulty {metrics.get('course_difficulty', {}).get('score')}."
        )
        return " ".join(bits)
    if cat == "practice":
        return (
            f"Practice session: {metrics.get('stroke_count')} strokes over "
            f"{metrics.get('duration_minutes')} min across "
            f"{len(metrics.get('clubs_used', []))} clubs "
            f"(seriousness {classification['seriousness']}). Counted as an "
            "attempt to improve."
        )
    if cat == "warmup":
        return (
            f"Warm-up only: {classification['stroke_count']} strokes over "
            f"{classification['duration_minutes']} min — not counted as an "
            "improvement session."
        )
    return "No analyzable shot data for this session."


def analyze(
    detail: dict,
    session_id: str,
    history: list[dict] | None = None,
    clubs_available: list[str] | None = None,
) -> dict:
    """Produce a complete, storable analysis record for one session.

    Args:
        detail: the `get_session` node for this session.
        session_id: stable id to key the stored record.
        history: previously stored analysis records (for normalization).
        clubs_available: the player's bag (to flag used vs unused clubs).

    Returns a record shaped for `session_store.save_analysis`.
    """
    history = history or []
    classification = classify_session(detail)
    metrics = session_metrics(detail)
    # Normalize only against sessions chronologically BEFORE this one, so the
    # result is "vs your previous sessions" regardless of ingestion order.
    this_time = detail.get("time") or ""
    prior = [r for r in history if (r.get("time") or "") < this_time] if this_time \
        else history
    normalized = _normalize_metrics(classification["category"], metrics, prior)
    summary = _summary(classification, metrics, normalized)

    analysis_obj: dict[str, Any] = {
        "category": classification["category"],
        "kind": classification["kind"],
        "seriousness": classification["seriousness"],
        "is_improvement_attempt": classification["is_improvement_attempt"],
        "reasons": classification["reasons"],
        "clubs_used": metrics.get("clubs_used", classification.get("clubs_used", [])),
        "metrics": metrics,
        "normalized": normalized,
        "summary": summary,
    }
    if clubs_available is not None:
        used_canon = {canonical_club(c) for c in analysis_obj["clubs_used"]}
        analysis_obj["clubs_available"] = sorted(clubs_available)
        analysis_obj["clubs_unused"] = sorted(
            c for c in clubs_available if canonical_club(c) not in used_canon
        )

    return {
        "session_id": session_id,
        "time": detail.get("time"),
        "kind": classification["kind"],
        "analysis": analysis_obj,
    }
