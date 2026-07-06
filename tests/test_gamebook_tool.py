# tests/test_gamebook_tool.py
from __future__ import annotations

import pytest

from trackman_mcp import server


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKMAN_CACHE_DIR", str(tmp_path))


def _holes():
    pars = [4, 3, 4, 4, 3, 5, 3, 4, 5, 4, 4, 4, 5, 3, 5, 3, 4, 3]
    scores = [7, 5, 6, 6, 4, 6, 4, 5, 6, 5, 7, 5, 8, 6, 7, 9, 6, 7]
    return [{"hole": i + 1, "par": p, "score": s}
            for i, (p, s) in enumerate(zip(pars, scores, strict=True))]


def _round(date="2026-06-09", gross=109):
    return {"date": date, "course": {"par": 70}, "result": {"gross": gross},
            "holes": _holes(),
            "coverage": {"scoring": "full", "putts": "partial"},
            "dimensions": {"putts": {"total": 27, "holes_tracked": 12,
                                     "coverage": "partial"}}}


async def test_save_computes_scoring_and_stores():
    res = await server.gamebook_round(action="save", round=_round())
    assert res["saved"] is True
    assert res["round"]["id"] == "2026-06-09"
    assert res["round"]["scoring"]["to_par"] == 39
    assert res["round"]["scoring"]["distribution"]["bogey"] == 7
    assert res["stored_count"] == 1


async def test_save_rejects_inconsistent_read():
    bad = _round(gross=108)  # gross disagrees with hole sum (109)
    res = await server.gamebook_round(action="save", round=bad)
    assert res["saved"] is False
    assert any("gross" in p for p in res["problems"])


async def test_same_day_second_round_gets_suffixed_id():
    await server.gamebook_round(action="save", round=_round(gross=109))
    r2 = _round(gross=100)
    r2["holes"][0]["score"] = 6   # make hole sum 108, then fix gross to match
    r2["result"]["gross"] = 108
    res = await server.gamebook_round(action="save", round=r2)
    assert res["round"]["id"] == "2026-06-09-2"


async def test_list_and_get():
    await server.gamebook_round(action="save", round=_round())
    listed = await server.gamebook_round(action="list")
    assert listed["count"] == 1
    assert listed["items"][0]["to_par"] == 39
    got = await server.gamebook_round(action="get", round_id="2026-06-09")
    assert got["result"]["gross"] == 109


async def test_compare_two_rounds():
    await server.gamebook_round(action="save", round=_round(date="2026-06-01", gross=109))
    better = _round(date="2026-06-09", gross=100)
    # lower all scores by making one par: change hole 16 from 9 to 3 (gross 103)
    better["holes"][15]["score"] = 3
    better["result"]["gross"] = 103
    await server.gamebook_round(action="save", round=better)
    cmp = await server.gamebook_round(action="compare")
    assert cmp["round_id"] == "2026-06-09"
    assert cmp["scoring"]["to_par"]["direction"] == "better"
