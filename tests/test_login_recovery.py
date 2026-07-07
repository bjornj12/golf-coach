"""Tests for auth auto-recovery and the `login` MCP tool (no real browser)."""

from __future__ import annotations

import asyncio

import pytest

from golf_coach import login as login_mod
from golf_coach import server
from golf_coach.client import TrackmanAuthError


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    # Never leak a login task between tests.
    server._LOGIN_TASK = None
    yield
    task = server._LOGIN_TASK
    if task is not None and not task.done():
        task.cancel()
    server._LOGIN_TASK = None


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
    # Already signed in (valid token) -> synchronous confirm, no browser.
    monkeypatch.setenv("TRACKMAN_TOKEN", "tok")

    async def fake_whoami(self):
        return {"name": "Pat Golfer", "sub": "s1"}
    monkeypatch.setattr("golf_coach.client.TrackmanClient.whoami", fake_whoami)

    res = await server.auth(action="login")
    assert res["success"] is True
    assert res["name"] == "Pat Golfer"


async def test_login_returns_immediately_and_runs_browser_in_background(monkeypatch):
    """Regression: an interactive sign-in must NOT block the tool call.

    Claude Desktop cancels long-running tool calls; when the browser login was
    awaited inside the tool call, cancellation tore the sign-in window down after
    a few seconds. The tool must return promptly and drive the browser from a
    background task that outlives the request.
    """
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"silent": 0, "headed": 0}

    async def fake_capture(headless=False, timeout_seconds=300.0):
        if headless:  # silent refresh — first-time user has no saved session
            calls["silent"] += 1
            raise RuntimeError("no saved session")
        calls["headed"] += 1
        started.set()
        await release.wait()  # the human takes minutes to finish signing in
        return "tok"

    monkeypatch.setattr(login_mod, "capture_token", fake_capture)

    # No token -> not already signed in. The call must return well before the
    # (blocked) browser login finishes.
    res = await asyncio.wait_for(server.auth(action="login"), timeout=1.0)
    assert res.get("success") is not True
    assert "sign in" in res["message"].lower() or "browser" in res["message"].lower()

    # The headed browser login is running in the background, not awaited.
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert calls["headed"] == 1
    assert server._login_in_progress() is True

    # Let the background task finish cleanly.
    release.set()
    await asyncio.wait_for(server._LOGIN_TASK, timeout=1.0)
    assert server._login_in_progress() is False


async def test_first_time_user_skips_silent_refresh_and_opens_window(monkeypatch):
    """A first-time user (no saved browser profile) shouldn't wait out the silent
    refresh — open the sign-in window straight away."""
    release = asyncio.Event()
    calls = {"silent": 0, "headed": 0}

    async def fake_capture(headless=False, timeout_seconds=300.0):
        if headless:
            calls["silent"] += 1
            raise RuntimeError("no saved session")
        calls["headed"] += 1
        await release.wait()
        return "tok"

    monkeypatch.setattr(login_mod, "capture_token", fake_capture)

    await asyncio.wait_for(server.auth(action="login"), timeout=1.0)
    # Give the background task a moment to reach capture_token.
    for _ in range(50):
        if calls["headed"]:
            break
        await asyncio.sleep(0.01)
    release.set()
    await asyncio.wait_for(server._LOGIN_TASK, timeout=1.0)
    assert calls["headed"] == 1
    assert calls["silent"] == 0  # no saved profile -> silent refresh skipped


async def test_returning_user_tries_silent_refresh_first(monkeypatch, tmp_path):
    """A returning user (saved browser profile) refreshes silently, no window."""
    # Simulate a persisted browser profile from a prior login.
    profile = tmp_path / "browser-profile"
    profile.mkdir()
    (profile / "Cookies").write_text("x")

    calls = {"silent": 0, "headed": 0}

    async def fake_capture(headless=False, timeout_seconds=300.0):
        if headless:
            calls["silent"] += 1
            return "tok"  # saved session still valid -> silent success
        calls["headed"] += 1
        return "tok"

    monkeypatch.setattr(login_mod, "capture_token", fake_capture)

    await asyncio.wait_for(server.auth(action="login"), timeout=1.0)
    await asyncio.wait_for(server._LOGIN_TASK, timeout=1.0)
    assert calls["silent"] == 1
    assert calls["headed"] == 0  # silent refresh worked -> no window opened


async def test_login_does_not_start_a_second_browser_when_one_is_in_progress(monkeypatch):
    release = asyncio.Event()
    calls = {"headed": 0}

    async def fake_capture(headless=False, timeout_seconds=300.0):
        if headless:
            raise RuntimeError("no saved session")
        calls["headed"] += 1
        await release.wait()
        return "tok"

    monkeypatch.setattr(login_mod, "capture_token", fake_capture)

    first = await asyncio.wait_for(server.auth(action="login"), timeout=1.0)
    assert first.get("success") is not True
    # Second call while the first browser is still open must not spawn another.
    second = await asyncio.wait_for(server.auth(action="login"), timeout=1.0)
    assert second.get("success") is not True

    release.set()
    await asyncio.wait_for(server._LOGIN_TASK, timeout=1.0)
    assert calls["headed"] == 1
