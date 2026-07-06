"""Tests for auth auto-recovery and the `login` MCP tool (no real browser)."""

from __future__ import annotations

import pytest

from golf_coach import login as login_mod
from golf_coach import server
from golf_coach.client import TrackmanAuthError


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)


async def test_silent_refresh_false_when_capture_raises(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("no session")
    monkeypatch.setattr(login_mod, "capture_token", boom)
    assert await server._try_silent_refresh() is False


async def test_silent_refresh_true_when_capture_succeeds(monkeypatch):
    async def ok(*a, **k):
        return "tok"
    monkeypatch.setattr(login_mod, "capture_token", ok)
    assert await server._try_silent_refresh() is True


async def test_run_retries_after_refresh(monkeypatch):
    calls = {"n": 0}

    async def fake_execute(self, query, variables=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TrackmanAuthError("expired")
        return {"ok": True}

    monkeypatch.setattr("golf_coach.client.TrackmanClient.execute", fake_execute)

    async def refreshed():
        return True
    monkeypatch.setattr(server, "_try_silent_refresh", refreshed)

    result = await server._run("query { __typename }")
    assert result == {"ok": True}
    assert calls["n"] == 2  # failed once, retried once


async def test_run_raises_when_refresh_fails(monkeypatch):
    async def always_auth_error(self, query, variables=None):
        raise TrackmanAuthError("expired")
    monkeypatch.setattr("golf_coach.client.TrackmanClient.execute", always_auth_error)

    async def no_refresh():
        return False
    monkeypatch.setattr(server, "_try_silent_refresh", no_refresh)

    with pytest.raises(TrackmanAuthError):
        await server._run("query { __typename }")


async def test_login_action_reports_failure_without_browser(monkeypatch):
    async def boom(*a, **k):
        raise login_mod.TrackmanLoginError("session expired")
    monkeypatch.setattr(login_mod, "capture_token", boom)
    res = await server.auth(action="login", open_browser=False)
    assert res["success"] is False
    assert "expired" in res["message"].lower() or "terminal" in res["message"].lower()


async def test_login_action_success_path(monkeypatch):
    # capture succeeds silently; whoami returns identity via mocked transport.
    async def ok(*a, **k):
        return "tok"
    monkeypatch.setattr(login_mod, "capture_token", ok)
    monkeypatch.setenv("TRACKMAN_TOKEN", "tok")

    async def fake_whoami(self):
        return {"name": "Pat Golfer", "sub": "s1"}
    monkeypatch.setattr("golf_coach.client.TrackmanClient.whoami", fake_whoami)

    res = await server.auth(action="login")
    assert res["success"] is True
    assert res["name"] == "Pat Golfer"
