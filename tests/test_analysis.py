"""Evals for the deterministic analysis engine (synthetic sessions).

These are the test-verifications of the analyzer's logic: warmup-vs-serious
classification, game analysis, and normalization against history.
"""

from __future__ import annotations

from golf_coach import analysis


def _practice(strokes: int, minutes: float, clubs: list[str], kind="RANGE_PRACTICE"):
    """Build a synthetic RangePractice node with N strokes spread over `minutes`."""
    out = []
    for i in range(strokes):
        t = f"2026-06-01T10:{int(i * minutes / max(strokes - 1, 1)):02d}:00Z"
        club = clubs[i % len(clubs)]
        out.append({
            "club": club,
            "time": t,
            "measurement": {"ballSpeed": 60.0 + i, "carry": 150.0 + (i % 5)},
        })
    # spread times across the window explicitly via first/last
    out[0]["time"] = "2026-06-01T10:00:00Z"
    out[-1]["time"] = f"2026-06-01T10:{int(minutes):02d}:00Z"
    return {"__typename": "RangePracticeActivity", "kind": kind,
            "time": "2026-06-01T10:00:00Z", "strokes": out}


def _game(to_par: int, gir: int, putts: int, par: int = 72):
    return {
        "__typename": "CoursePlayActivity", "kind": "COURSE_PLAY",
        "time": "2026-06-02T10:00:00Z",
        "scorecard": {
            "par": par, "grossScore": par + to_par, "toPar": to_par,
            "numberOfHolesPlayed": 18, "totalDistance": 6200.0, "courseHcp": 12.0,
            "course": {"displayName": "Test Links"},
            "stat": {"greenInRegulation": gir, "numberOfPutts": putts,
                     "driveAverage": 210.0, "fairwayHitFairway": 7,
                     "birdies": 1, "pars": 8, "bogeys": 6, "doubleBogeys": 3},
            "holes": [{"holeNumber": h, "par": 4, "grossScore": 5, "putts": 2,
                       "greenInRegulation": False,
                       "shots": [{"club": "DRIVER", "measurement": {"carry": 200.0}}]}
                      for h in range(1, 19)],
        },
    }


# --- classification -------------------------------------------------------

def test_short_warmup_is_not_improvement():
    c = analysis.classify_session(_practice(strokes=8, minutes=4, clubs=["IRON7"]))
    assert c["category"] == "warmup"
    assert c["is_improvement_attempt"] is False
    assert c["seriousness"] < 0.5


def test_long_multiclub_practice_is_serious():
    c = analysis.classify_session(
        _practice(strokes=50, minutes=40, clubs=["DRIVER", "IRON7", "WEDGE56", "IRON5"])
    )
    assert c["category"] == "practice"
    assert c["is_improvement_attempt"] is True
    assert c["seriousness"] >= 0.6


def test_shot_analysis_kind_is_serious_even_if_short():
    c = analysis.classify_session(
        _practice(strokes=10, minutes=8, clubs=["DRIVER"], kind="SHOT_ANALYSIS")
    )
    assert c["category"] == "practice"
    assert c["is_improvement_attempt"] is True


def test_short_serious_kind_is_still_a_warmup():
    # 7 strokes over 3 min — even a "serious" kind shouldn't count as training.
    c = analysis.classify_session(
        _practice(strokes=7, minutes=3, clubs=["DRIVER"], kind="MAP_MY_BAG")
    )
    assert c["category"] == "warmup"
    assert c["is_improvement_attempt"] is False


def test_game_is_classified_as_game():
    c = analysis.classify_session(_game(to_par=10, gir=5, putts=33))
    assert c["category"] == "game"
    assert c["is_improvement_attempt"] is False  # games tracked separately


def _strokes_no_time(n: int, clubs: list[str]) -> dict:
    """A practice node whose strokes carry NO parseable time."""
    out = [{"club": clubs[i % len(clubs)], "measurement": {"carry": 150.0}}
           for i in range(n)]
    return {"__typename": "RangePracticeActivity", "kind": "RANGE_PRACTICE",
            "time": "2026-06-01T10:00:00Z", "strokes": out}


def test_missing_stroke_times_do_not_force_warmup():
    # 30 strokes across 4 clubs but no timestamps: duration is UNKNOWN, not 0.
    # A real practice session must not be demoted to warm-up by a data quirk.
    c = analysis.classify_session(_strokes_no_time(30, ["DRIVER", "IRON7", "WEDGE56", "IRON5"]))
    assert c["duration_minutes"] is None
    assert c["category"] == "practice"
    assert c["is_improvement_attempt"] is True


def test_identical_timestamps_treated_as_unknown_duration():
    strokes = [{"club": ["DRIVER", "IRON7", "WEDGE56", "IRON5"][i % 4],
                "time": "2026-06-01T10:00:00Z",
                "measurement": {"carry": 150.0}} for i in range(30)]
    node = {"__typename": "RangePracticeActivity", "kind": "RANGE_PRACTICE",
            "time": "2026-06-01T10:00:00Z", "strokes": strokes}
    c = analysis.classify_session(node)
    assert c["duration_minutes"] is None  # zero span = unknown, not 0
    assert c["category"] == "practice"


# --- metrics --------------------------------------------------------------

def test_practice_metrics_count_clubs_and_duration():
    m = analysis.session_metrics(
        _practice(strokes=20, minutes=30, clubs=["DRIVER", "IRON7"])
    )
    assert m["stroke_count"] == 20
    assert set(m["clubs_used"]) == {"DRIVER", "IRON7"}
    assert m["duration_minutes"] == 30
    assert "DRIVER" in m["per_club"]
    assert m["per_club"]["DRIVER"]["n"] >= 1


def test_game_metrics_and_difficulty():
    m = analysis.session_metrics(_game(to_par=8, gir=9, putts=30))
    assert m["to_par"] == 8
    assert m["green_in_regulation"] == 9
    assert m["putts"] == 30
    assert m["holes_played"] == 18
    assert 0.0 <= m["course_difficulty"]["score"] <= 1.0


# --- normalization --------------------------------------------------------

def test_normalize_value_against_history():
    n = analysis.normalize_value(12.0, history=[10.0, 8.0, 6.0])
    assert n["mean"] == 8.0
    assert n["delta"] == 4.0
    assert n["n"] == 3
    assert n["z"] is not None


def test_normalize_handles_empty_history():
    n = analysis.normalize_value(12.0, history=[])
    assert n["mean"] is None
    assert n["delta"] is None
    assert n["n"] == 0


# --- end-to-end analyze ---------------------------------------------------

def test_canonical_club_matches_bag_and_strokes():
    assert analysis.canonical_club("7Iron") == analysis.canonical_club("IRON7")
    assert analysis.canonical_club("52Wedge") == "WEDGE52"
    assert analysis.canonical_club("Driver") == "DRIVER"
    assert analysis.canonical_club("Pitching Wedge") == "PITCHINGWEDGE"


def test_analyze_flags_unused_clubs():
    detail = _practice(strokes=12, minutes=12, clubs=["IRON7", "DRIVER"])
    rec = analysis.analyze(
        detail, session_id="p1", history=[],
        clubs_available=["Driver", "7Iron", "52Wedge", "Putter"],
    )
    a = rec["analysis"]
    # 52Wedge and Putter weren't used; Driver and 7Iron were.
    assert "52Wedge" in a["clubs_unused"]
    assert "Putter" in a["clubs_unused"]
    assert "Driver" not in a["clubs_unused"]
    assert "7Iron" not in a["clubs_unused"]


def test_analyze_produces_record_with_summary():
    history = [
        {"session_id": "g0", "time": "2026-05-01T10:00:00Z", "kind": "COURSE_PLAY",
         "analysis": {"category": "game", "metrics": {"to_par": 14, "putts": 34,
                      "green_in_regulation": 4}}},
    ]
    rec = analysis.analyze(_game(to_par=8, gir=9, putts=30),
                           session_id="g1", history=history)
    assert rec["session_id"] == "g1"
    assert rec["analysis"]["category"] == "game"
    # to_par improved from 14 -> 8 vs history
    assert rec["analysis"]["normalized"]["to_par"]["delta"] == 8 - 14
    assert isinstance(rec["analysis"]["summary"], str) and rec["analysis"]["summary"]
