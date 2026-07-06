"""Server-level tests for the training_plan(action="verify") orchestration.

Covers the no-specs guard, the explicit-activity path, the auto-select loop with
the clubs pre-filter (no wasted per-session fetches), and the no-data window
message. `analysis.verify_targets` is unit-tested separately in test_verify.py.
"""

from __future__ import annotations

import pytest

from golf_coach import server, training_store


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))


@pytest.fixture
def route_run(monkeypatch):
    """Patch server._run with a query-aware fake that records every call."""
    calls = []

    def _install(handler):
        async def fake_run(query, variables=None):
            calls.append((query, variables or {}))
            return handler(query, variables or {})
        monkeypatch.setattr(server, "_run", fake_run)
        return calls

    return _install


def _driver_strokes(paths):
    return [{"club": "DRIVER", "measurement": {"clubPath": p}} for p in paths]


DRIVER_SPEC = [{"metric": "clubPath", "club": "DRIVER", "op": "between",
                "low": -1, "high": 2, "label": "club path"}]


async def test_verify_requires_target_specs():
    plan = training_store.save_plan({"title": "no specs"})  # no target_specs
    out = await server.training_plan(action="verify", plan_id=plan["id"])
    assert "error" in out
    assert "target_specs" in out["error"]


async def test_verify_explicit_activity_grades_that_session(route_run):
    plan = training_store.save_plan({"title": "driver path", "target_specs": DRIVER_SPEC})

    def handler(query, variables):
        assert "SessionMeasurements" in query  # only the measurements query runs
        return {"node": {"time": "2026-06-01T10:00:00Z", "kind": "RANGE_PRACTICE",
                         "strokes": _driver_strokes([0.0, 1.0, 2.0])}}  # mean 1.0 -> met

    calls = route_run(handler)
    out = await server.training_plan(action="verify", plan_id=plan["id"], activity_id="act-1")
    assert out["checked_session"] == "act-1"
    assert out["has_data"] is True
    assert out["all_met"] is True
    assert "done" in out["recommendation"]  # suggests training_plan(action='done')
    assert len(calls) == 1  # no LIST_SESSIONS when an id is given


async def test_verify_autoselect_prefilters_by_clubs(route_run):
    plan = training_store.save_plan({"title": "driver path", "target_specs": DRIVER_SPEC})

    measurement_ids = []

    def handler(query, variables):
        if "ListSessions" in query:
            return {"me": {"activities": {"items": [
                {"id": "a1", "clubs": ["IRON7"]},      # no driver -> pre-filtered out
                {"id": "a2", "clubs": ["DRIVER"]},     # candidate
            ]}}}
        # SessionMeasurements
        measurement_ids.append(variables.get("id"))
        return {"node": {"time": "2026-06-02T10:00:00Z", "kind": "RANGE_PRACTICE",
                         "strokes": _driver_strokes([0.0, 1.0])}}

    route_run(handler)
    out = await server.training_plan(action="verify", plan_id=plan["id"])
    assert out["checked_session"] == "a2"
    assert out["has_data"] is True
    # a1 was skipped via the list-clubs pre-filter: no measurement fetch for it.
    assert measurement_ids == ["a2"]


async def test_verify_no_matching_session_reports_window(route_run):
    plan = training_store.save_plan({"title": "driver path", "target_specs": DRIVER_SPEC})

    def handler(query, variables):
        if "ListSessions" in query:
            return {"me": {"activities": {"items": [
                {"id": "a1", "clubs": ["IRON7"]},
                {"id": "a2", "clubs": ["WEDGE56"]},
            ]}}}
        raise AssertionError("should not fetch measurements when nothing matches")

    route_run(handler)
    out = await server.training_plan(action="verify", plan_id=plan["id"])
    assert out["has_data"] is False
    assert "20" in out["message"]  # the scan window is surfaced
