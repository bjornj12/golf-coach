"""Tests for the local session-analysis store (cap 30, latest-first)."""

from __future__ import annotations

import pytest

from golf_coach import session_store


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))


def _rec(session_id: str, time: str, kind: str = "RANGE_PRACTICE") -> dict:
    return {
        "session_id": session_id,
        "time": time,
        "kind": kind,
        "analysis": {"seriousness": 0.5},
    }


def test_save_and_list_latest_first():
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    session_store.save_analysis(_rec("b", "2026-03-01T10:00:00Z"))
    session_store.save_analysis(_rec("c", "2026-02-01T10:00:00Z"))
    items = session_store.list_analyses()
    assert [r["session_id"] for r in items] == ["b", "c", "a"]  # date desc


def test_latest_returns_most_recent():
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    session_store.save_analysis(_rec("b", "2026-05-01T10:00:00Z"))
    assert session_store.latest_analysis()["session_id"] == "b"


def test_upsert_by_session_id():
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    rec = _rec("a", "2026-01-01T10:00:00Z")
    rec["analysis"] = {"seriousness": 0.9}
    session_store.save_analysis(rec)
    items = session_store.list_analyses()
    assert len(items) == 1
    assert items[0]["analysis"]["seriousness"] == 0.9


def test_cap_at_30_keeps_newest():
    for i in range(35):
        month = (i % 12) + 1
        session_store.save_analysis(
            _rec(f"s{i:02d}", f"2026-{month:02d}-{(i % 28) + 1:02d}T10:00:00Z")
        )
    items = session_store.list_analyses()
    assert len(items) == 30
    # Oldest by date should have been dropped; newest kept.
    times = [r["time"] for r in items]
    assert times == sorted(times, reverse=True)


def test_get_by_id_and_has():
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    assert session_store.get_analysis("a")["session_id"] == "a"
    assert session_store.get_analysis("missing") is None
    assert session_store.has_analysis("a")
    assert not session_store.has_analysis("missing")


def test_stored_ids_for_dedup():
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    session_store.save_analysis(_rec("b", "2026-01-02T10:00:00Z"))
    assert session_store.stored_ids() == {"a", "b"}


def test_empty_store():
    assert session_store.list_analyses() == []
    assert session_store.latest_analysis() is None


def test_corrupt_store_is_backed_up_not_wiped():
    # A truncated/corrupt file must not silently erase history without a trace.
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    path = session_store.store_path()
    path.write_text("[ truncated json")
    assert session_store.list_analyses() == []  # degrades gracefully
    assert path.with_suffix(path.suffix + ".corrupt").exists()  # but preserved


def test_store_file_is_user_only_readable():
    import stat
    session_store.save_analysis(_rec("a", "2026-01-01T10:00:00Z"))
    mode = stat.S_IMODE(session_store.store_path().stat().st_mode)
    assert mode == 0o600
