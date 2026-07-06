from __future__ import annotations

import json
from pathlib import Path

from trackman_mcp import gamebook_analysis as ga

GOLDEN = Path(__file__).parent / "fixtures" / "gamebook" / "2026-06-09.json"


def test_hole_result_buckets():
    assert ga.hole_result(4, 2) == "eagle_or_better"
    assert ga.hole_result(4, 3) == "birdie"
    assert ga.hole_result(4, 4) == "par"
    assert ga.hole_result(4, 5) == "bogey"
    assert ga.hole_result(4, 6) == "double"
    assert ga.hole_result(4, 7) == "triple_plus"
    assert ga.hole_result(3, 9) == "triple_plus"


def test_coverage_flag_thresholds():
    assert ga.coverage_flag(0, 18) == "none"
    assert ga.coverage_flag(6, 12) == "partial"
    assert ga.coverage_flag(18, 18) == "full"
    assert ga.coverage_flag(17, 18) == "full"   # >= 90% counts as full
    assert ga.coverage_flag(1, 18) == "partial"
    assert ga.coverage_flag(5, 0) == "none"     # nothing eligible


def test_scoring_from_holes_reproduces_sample_round():
    # The 9 June sample: front 49, back 60, par 70, +39.
    holes = [
        {"hole": 1, "par": 4, "score": 7}, {"hole": 2, "par": 3, "score": 5},
        {"hole": 3, "par": 4, "score": 6}, {"hole": 4, "par": 4, "score": 6},
        {"hole": 5, "par": 3, "score": 4}, {"hole": 6, "par": 5, "score": 6},
        {"hole": 7, "par": 3, "score": 4}, {"hole": 8, "par": 4, "score": 5},
        {"hole": 9, "par": 5, "score": 6}, {"hole": 10, "par": 4, "score": 5},
        {"hole": 11, "par": 4, "score": 7}, {"hole": 12, "par": 4, "score": 5},
        {"hole": 13, "par": 5, "score": 8}, {"hole": 14, "par": 3, "score": 6},
        {"hole": 15, "par": 5, "score": 7}, {"hole": 16, "par": 3, "score": 9},
        {"hole": 17, "par": 4, "score": 6}, {"hole": 18, "par": 3, "score": 7},
    ]
    s = ga.scoring_from_holes(holes)
    assert s["to_par"] == 39
    assert s["distribution"] == {
        "eagle_or_better": 0, "birdie": 0, "par": 0,
        "bogey": 7, "double": 5, "triple_plus": 6,
    }
    assert s["by_par_type"] == {"par3": 2.83, "par4": 1.88, "par5": 1.75}


def _sample_record() -> dict:
    holes = [
        {"hole": 1, "par": 4, "score": 7}, {"hole": 2, "par": 3, "score": 5},
        {"hole": 3, "par": 4, "score": 6}, {"hole": 4, "par": 4, "score": 6},
        {"hole": 5, "par": 3, "score": 4}, {"hole": 6, "par": 5, "score": 6},
        {"hole": 7, "par": 3, "score": 4}, {"hole": 8, "par": 4, "score": 5},
        {"hole": 9, "par": 5, "score": 6}, {"hole": 10, "par": 4, "score": 5},
        {"hole": 11, "par": 4, "score": 7}, {"hole": 12, "par": 4, "score": 5},
        {"hole": 13, "par": 5, "score": 8}, {"hole": 14, "par": 3, "score": 6},
        {"hole": 15, "par": 5, "score": 7}, {"hole": 16, "par": 3, "score": 9},
        {"hole": 17, "par": 4, "score": 6}, {"hole": 18, "par": 3, "score": 7},
    ]
    return {"course": {"par": 70}, "result": {"gross": 109}, "holes": holes}


def test_self_check_passes_on_consistent_round():
    assert ga.self_check(_sample_record()) == []


def test_self_check_flags_gross_mismatch():
    rec = _sample_record()
    rec["result"]["gross"] = 108   # wrong
    problems = ga.self_check(rec)
    assert any("gross" in p for p in problems)


def test_self_check_flags_par_mismatch_and_hole_count():
    rec = _sample_record()
    rec["holes"] = rec["holes"][:17]  # 17 holes, pars now sum to 67
    problems = ga.self_check(rec)
    assert any("holes" in p for p in problems)


def test_self_check_flags_hole_missing_score():
    rec = {"course": {"par": 70}, "result": {"gross": 100},
           "holes": [{"hole": n, "par": 4, "score": 4} for n in range(1, 18)]
                    + [{"hole": 18, "par": 4}]}   # hole 18 missing score
    problems = ga.self_check(rec)                  # must not raise
    assert any("18" in p for p in problems)


def _round(rid, to_par, par3, par4, par5, putts_total=None, putts_holes=0):
    cov_putts = ga.coverage_flag(putts_holes, 18)
    return {
        "id": rid,
        "scoring": {"to_par": to_par,
                    "by_par_type": {"par3": par3, "par4": par4, "par5": par5}},
        "coverage": {"scoring": "full", "putts": cov_putts},
        "dimensions": {"putts": {"total": putts_total, "holes_tracked": putts_holes,
                                 "coverage": cov_putts}},
    }


def test_compare_scoring_direction_lower_is_better():
    latest = _round("r3", 30, 2.0, 1.5, 1.5)
    priors = [_round("r1", 40, 2.8, 1.9, 1.8), _round("r2", 36, 2.6, 1.7, 1.6)]
    out = ga.compare_rounds(latest, priors)
    assert out["round_id"] == "r3"
    assert out["n_priors"] == 2
    assert out["scoring"]["to_par"]["prior_mean"] == 38.0
    assert out["scoring"]["to_par"]["delta"] == -8.0
    assert out["scoring"]["to_par"]["direction"] == "better"
    assert out["scoring"]["par4"]["direction"] == "better"


def test_compare_putts_gated_on_coverage():
    # latest has putts, but one prior has none -> not comparable, skipped.
    latest = _round("r3", 30, 2.0, 1.5, 1.5, putts_total=30, putts_holes=18)
    priors = [_round("r1", 40, 2.8, 1.9, 1.8, putts_total=33, putts_holes=18),
              _round("r2", 36, 2.6, 1.7, 1.6, putts_total=None, putts_holes=0)]
    out = ga.compare_rounds(latest, priors)
    assert out["dimensions"]["putts_per_hole"] == {"skipped": "coverage"}


def test_compare_skips_putts_when_total_null():
    latest = {"id": "r2", "scoring": {"to_par": 30,
              "by_par_type": {"par3": 2.0, "par4": 1.5, "par5": 1.5}},
              "coverage": {"scoring": "full", "putts": "partial"},
              "dimensions": {"putts": {"total": None, "holes_tracked": 0,
                                       "coverage": "partial"}}}
    prior = {"id": "r1", "scoring": {"to_par": 40,
             "by_par_type": {"par3": 2.8, "par4": 1.9, "par5": 1.8}},
             "coverage": {"scoring": "full", "putts": "partial"},
             "dimensions": {"putts": {"total": 30, "holes_tracked": 18,
                                      "coverage": "partial"}}}
    out = ga.compare_rounds(latest, [prior])        # must not raise
    assert out["dimensions"]["putts_per_hole"] == {"skipped": "coverage"}


def test_compare_putts_when_all_tracked():
    latest = _round("r3", 30, 2.0, 1.5, 1.5, putts_total=27, putts_holes=18)
    priors = [_round("r1", 40, 2.8, 1.9, 1.8, putts_total=36, putts_holes=18)]
    out = ga.compare_rounds(latest, priors)
    p = out["dimensions"]["putts_per_hole"]
    assert p["latest"] == 1.5           # 27/18
    assert p["prior_mean"] == 2.0       # 36/18
    assert p["direction"] == "better"   # fewer putts is better


def test_compare_no_priors_is_safe():
    latest = _round("r1", 40, 2.8, 1.9, 1.8)
    out = ga.compare_rounds(latest, [])
    assert out["round_id"] == "r1"
    assert out["n_priors"] == 0
    assert out["scoring"] == {}
    assert out["dimensions"] == {}


def test_grade_perfect_extraction_scores_100():
    golden = json.loads(GOLDEN.read_text())
    report = ga.grade_extraction(golden, golden)
    assert report["score"] == 100.0
    assert report["holes_correct"] == report["holes_total"] == 18
    assert report["mismatches"] == []


def test_grade_flags_a_wrong_hole():
    golden = json.loads(GOLDEN.read_text())
    extracted = json.loads(GOLDEN.read_text())
    extracted["holes"][15]["score"] = 5          # hole 16 was 9
    report = ga.grade_extraction(extracted, golden)
    assert report["holes_correct"] == 17
    assert report["score"] < 100.0
    assert any("hole 16" in m for m in report["mismatches"])


def test_grade_flags_wrong_coverage():
    golden = json.loads(GOLDEN.read_text())
    extracted = json.loads(GOLDEN.read_text())
    extracted["coverage"]["sand_save"] = "full"  # the 0.0% trap: should stay none/absent
    report = ga.grade_extraction(extracted, golden)
    assert report["coverage_ok"] is False
    assert any("sand_save" in m for m in report["mismatches"])


def test_grade_survives_null_hole_field():
    golden = json.loads(GOLDEN.read_text())
    extracted = json.loads(GOLDEN.read_text())
    extracted["holes"][15]["score"] = None          # hole 16 unreadable
    report = ga.grade_extraction(extracted, golden)  # must not raise
    assert report["holes_correct"] == 17
    assert report["score"] < 100.0
    assert any("hole 16" in m for m in report["mismatches"])


def test_grade_scoring_mismatch_message_names_by_par_type():
    golden = json.loads(GOLDEN.read_text())
    extracted = json.loads(GOLDEN.read_text())
    extracted["scoring"]["by_par_type"]["par3"] = 9.99   # only by_par_type differs
    report = ga.grade_extraction(extracted, golden)
    assert report["scoring_ok"] is False
    assert any("by_par_type" in m for m in report["mismatches"])
