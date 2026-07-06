"""Tests for the training-plan store (saved coaching prescriptions)."""

from __future__ import annotations

import pytest

from golf_coach import training_store


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))


def _plan(title: str, created_at: int, status: str = "pending", plan_id=None) -> dict:
    p = {"title": title, "created_at": created_at, "status": status,
         "blocks": [{"name": "drill", "reps": 10}]}
    if plan_id:
        p["id"] = plan_id
    return p


def test_save_assigns_id_and_defaults():
    saved = training_store.save_plan({"title": "Fix slice", "created_at": 100})
    assert saved["id"]
    assert saved["status"] == "pending"
    assert training_store.get_plan(saved["id"])["title"] == "Fix slice"


def test_save_upserts_by_id():
    training_store.save_plan(_plan("v1", 100, plan_id="p1"))
    training_store.save_plan(_plan("v2", 100, plan_id="p1"))
    plans = training_store.list_plans()
    assert len(plans) == 1
    assert plans[0]["title"] == "v2"


def test_list_ordered_and_filtered():
    training_store.save_plan(_plan("a", 100, plan_id="a"))
    training_store.save_plan(_plan("b", 300, status="done", plan_id="b"))
    training_store.save_plan(_plan("c", 200, plan_id="c"))
    assert [p["id"] for p in training_store.list_plans()] == ["a", "c", "b"]
    assert [p["id"] for p in training_store.list_plans(status="pending")] == ["a", "c"]


def test_next_pending_is_oldest_pending():
    training_store.save_plan(_plan("old-done", 100, status="done", plan_id="x"))
    training_store.save_plan(_plan("first-pending", 200, plan_id="y"))
    training_store.save_plan(_plan("second-pending", 300, plan_id="z"))
    nxt = training_store.next_pending()
    assert nxt["id"] == "y"


def test_next_pending_none_when_all_done():
    training_store.save_plan(_plan("done", 100, status="done", plan_id="d"))
    assert training_store.next_pending() is None


def test_mark_done_advances_queue():
    training_store.save_plan(_plan("first", 100, plan_id="p1"))
    training_store.save_plan(_plan("second", 200, plan_id="p2"))
    assert training_store.next_pending()["id"] == "p1"
    done = training_store.mark_done("p1", result_session_id="sess-1")
    assert done["status"] == "done"
    assert done["result_session_id"] == "sess-1"
    assert done["completed_at"] is not None
    assert training_store.next_pending()["id"] == "p2"


def test_cap_keeps_most_recent():
    for i in range(training_store.MAX_PLANS + 5):
        training_store.save_plan(_plan(f"p{i}", 100 + i, plan_id=f"p{i}"))
    plans = training_store.list_plans()
    assert len(plans) == training_store.MAX_PLANS
    # oldest dropped
    assert all(p["id"] != "p0" for p in plans)


def test_empty():
    assert training_store.list_plans() == []
    assert training_store.next_pending() is None
    assert training_store.get_plan("nope") is None
