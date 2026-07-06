from __future__ import annotations

import pytest

from trackman_mcp import gamebook_store as gs


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKMAN_CACHE_DIR", str(tmp_path))


def _round(rid: str, date: str) -> dict:
    return {"id": rid, "date": date, "result": {"gross": 100}}


def test_save_requires_id():
    with pytest.raises(ValueError):
        gs.save_round({"date": "2026-06-09"})


def test_save_and_list_newest_first():
    gs.save_round(_round("a", "2026-06-01"))
    gs.save_round(_round("c", "2026-06-09"))
    gs.save_round(_round("b", "2026-06-05"))
    assert [r["id"] for r in gs.list_rounds()] == ["c", "b", "a"]
    assert gs.latest_round()["id"] == "c"


def test_save_upserts_by_id():
    gs.save_round(_round("a", "2026-06-01"))
    again = _round("a", "2026-06-01")
    again["result"]["gross"] = 88
    gs.save_round(again)
    rounds = gs.list_rounds()
    assert len(rounds) == 1
    assert rounds[0]["result"]["gross"] == 88


def test_cap_keeps_most_recent_five():
    for i in range(8):
        gs.save_round(_round(f"r{i}", f"2026-06-0{i+1}"))
    rounds = gs.list_rounds()
    assert len(rounds) == gs.MAX_ROUNDS
    assert [r["id"] for r in rounds] == ["r7", "r6", "r5", "r4", "r3"]


def test_priors_of_returns_chronologically_earlier():
    for i in range(5):
        gs.save_round(_round(f"r{i}", f"2026-06-0{i+1}"))
    priors = gs.priors_of("r3")   # dates r0..r2 are earlier than r3
    assert [r["id"] for r in priors] == ["r2", "r1", "r0"]


def test_empty():
    assert gs.list_rounds() == []
    assert gs.latest_round() is None
    assert gs.get_round("nope") is None
