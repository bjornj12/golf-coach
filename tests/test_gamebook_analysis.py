from __future__ import annotations

from trackman_mcp import gamebook_analysis as ga


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
