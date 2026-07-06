"""Full-flow tests for the MCP tools against mocked API responses.

Each test feeds a realistic GraphQL `data` payload through a MockTransport and
asserts the tool returns the right stats substructure — proving the extraction,
fail-loud, and no-token-echo behavior of the data, auth, and store tools without
needing a live token. (verify_training_progress has its own file.)
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from golf_coach import server
from golf_coach.client import TrackmanClient
from golf_coach.config import Config


@pytest.fixture
def patch_transport(monkeypatch):
    """Patch server._run to use a MockTransport returning a canned payload."""

    def _install(payload: dict):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": payload})

        transport = httpx.MockTransport(handler)

        async def fake_run(query, variables=None):
            cfg = Config(token="test-token")
            async with TrackmanClient(cfg, transport=transport) as client:
                return await client.execute(query, variables)

        monkeypatch.setattr(server, "_run", fake_run)

    return _install


@pytest.fixture
def capture_variables(monkeypatch):
    """Patch server._run to record the `variables` dict it's called with.

    Unlike `patch_transport`, this doesn't round-trip through httpx — the fake
    transport there ignores the request body, so nothing observes the `take`/
    `completed` actually forwarded to a GraphQL call. This fixture captures it
    directly, and returns a canned payload.
    """
    captured: dict[str, Any] = {}

    def _install(payload: dict):
        async def fake_run(query, variables=None):
            captured["variables"] = variables
            return payload

        monkeypatch.setattr(server, "_run", fake_run)

    return _install, captured


async def test_get_profile(patch_transport):
    patch_transport({"me": {
        "profile": {"fullName": "Pat Golfer", "outdoorHandicap": 8.4},
        "hcp": {"currentHcp": 8.2, "currentRecord": {"hcpNew": 8.2}},
    }})
    result = await server.trackman(action="profile")
    assert result["profile"]["fullName"] == "Pat Golfer"
    assert result["hcp"]["currentHcp"] == 8.2


async def test_get_handicap(patch_transport):
    patch_transport({"me": {"hcp": {
        "currentHcp": 8.2,
        "playerHistory": {"totalCount": 1, "items": [{"hcpNew": 8.2, "scoreDifferential": 7.1}]},
    }}})
    result = await server.trackman(action="handicap", take=5)
    assert result["playerHistory"]["totalCount"] == 1


async def test_list_sessions(patch_transport):
    patch_transport({"me": {"activities": {
        "totalCount": 2,
        "items": [
            {"id": "a1", "kind": "RANGE_PRACTICE", "numberOfStrokes": 40},
            {"id": "a2", "kind": "COURSE_PLAY", "grossScore": 82},
        ],
    }}})
    result = await server.trackman(action="sessions", take=25)
    assert result["totalCount"] == 2
    assert len(result["items"]) == 2


async def test_get_session(patch_transport):
    patch_transport({"node": {
        "__typename": "RangePracticeActivity",
        "id": "a1",
        "strokes": [{"club": "IRON7", "measurement": {"ballSpeed": 110.0, "carry": 165.0}}],
    }})
    result = await server.trackman(action="session", activity_id="a1")
    assert result["__typename"] == "RangePracticeActivity"
    assert result["strokes"][0]["measurement"]["carry"] == 165.0


async def test_get_course_rounds(patch_transport):
    patch_transport({"me": {"scorecards": [
        {"id": "s1", "grossScore": 82, "toPar": 10,
         "stat": {"greenInRegulation": 7, "numberOfPutts": 31}},
    ]}})
    result = await server.trackman(action="rounds", take=20)
    assert result["scorecards"][0]["stat"]["numberOfPutts"] == 31


async def test_get_club_stats(patch_transport):
    patch_transport({"me": {"equipment": {"clubs": [
        {"displayName": "7 Iron",
         "findMyDistance": {"numberOfShots": 30,
                            "clubStats": {"carry": 165.0, "standardDeviationCarry": 4.2}}},
    ]}}})
    result = await server.trackman(action="clubs")
    assert result["clubs"][0]["findMyDistance"]["clubStats"]["carry"] == 165.0


async def test_get_session_course_play_shots(patch_transport):
    # trackman(action="session") also covers what get_shot_data used to: per-shot metrics.
    patch_transport({"node": {
        "__typename": "CoursePlayActivity",
        "scorecard": {"holes": [{"shots": [
            {"club": "DRIVER", "measurement": {"ballSpeed": 165.0, "smashFactor": 1.48}},
        ]}]},
    }})
    result = await server.trackman(action="session", activity_id="a2")
    shot = result["scorecard"]["holes"][0]["shots"][0]
    assert shot["measurement"]["smashFactor"] == 1.48


async def test_get_activity_summary(patch_transport):
    patch_transport({"me": {"activitySummary": {
        "totalCount": 2,
        "items": [{"kind": "RANGE_PRACTICE", "activityCount": 12}],
    }}})
    result = await server.trackman(action="summary")
    assert result["items"][0]["activityCount"] == 12


async def test_trackman_take_defaults_per_action(capture_variables):
    """Each action preserves its own original `take` default when omitted.

    Regression test: the consolidated `trackman` tool's shared `take` param
    used to default to 20 for every action, silently changing `sessions`
    (originally 25) and `summary` (originally 50).
    """
    install, captured = capture_variables

    install({"me": {"activities": {"totalCount": 0, "items": []}}})
    await server.trackman(action="sessions")
    assert captured["variables"]["take"] == 25

    install({"me": {"activitySummary": {"totalCount": 0, "items": []}}})
    await server.trackman(action="summary")
    assert captured["variables"]["take"] == 50


async def test_trackman_explicit_take_overrides_default(capture_variables):
    install, captured = capture_variables

    install({"me": {"activities": {"totalCount": 0, "items": []}}})
    await server.trackman(action="sessions", take=7)
    assert captured["variables"]["take"] == 7


async def test_trackman_rounds_completed_none_is_valid(capture_variables):
    """`completed=None` (meaning "all rounds") must remain a valid input."""
    install, captured = capture_variables

    install({"me": {"scorecards": [
        {"id": "s1", "grossScore": 82, "toPar": 10,
         "stat": {"greenInRegulation": 7, "numberOfPutts": 31}},
    ]}})
    result = await server.trackman(action="rounds", completed=None)
    assert captured["variables"]["completed"] is None
    assert result["scorecards"][0]["stat"]["numberOfPutts"] == 31


async def test_auth_status_without_token(monkeypatch, tmp_path):
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))  # empty cache
    result = await server.auth(action="status")
    assert result["authenticated"] is False


async def test_get_session_raises_on_missing_node(patch_transport):
    # The API returns {"node": null} for an unknown id; fail loudly, don't
    # return None and pretend success.
    patch_transport({"node": None})
    with pytest.raises(ValueError, match="nope"):
        await server.trackman(action="session", activity_id="nope")


async def test_auth_status_success_never_echoes_token(monkeypatch):
    secret = "super.secret.jwt"

    async def fake_whoami(self):
        return {"sub": "u1", "name": "Pat", "email": "p@x.io"}

    monkeypatch.setenv("TRACKMAN_TOKEN", secret)
    monkeypatch.setattr(TrackmanClient, "whoami", fake_whoami)
    result = await server.auth(action="status")
    assert result["authenticated"] is True
    assert result["name"] == "Pat"
    # The bearer token must never appear anywhere in the tool response.
    assert secret not in repr(result)


async def test_session_analysis_analyze_and_list(patch_transport, monkeypatch, tmp_path):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    patch_transport({"node": {
        "__typename": "RangePracticeActivity", "kind": "RANGE_PRACTICE",
        "time": "2026-06-01T10:00:00Z",
        "strokes": [{"club": "DRIVER", "time": f"2026-06-01T10:{i:02d}:00Z",
                     "measurement": {"carry": 200.0 + i}} for i in range(0, 30, 2)],
    }})
    rec = await server.session_analysis(action="analyze", activity_id="r1")
    assert rec["session_id"] == "r1"
    listed = await server.session_analysis(action="list")
    assert listed["count"] == 1
    assert listed["latest_id"] == "r1"


async def test_session_analysis_analyze_requires_id():
    with pytest.raises(ValueError):
        await server.session_analysis(action="analyze")


async def test_training_plan_lifecycle(monkeypatch, tmp_path):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    saved = await server.training_plan(action="save",
                                       plan={"title": "Driver path", "focus": ["slice"]})
    pid = saved["id"]
    nxt = await server.training_plan(action="next")
    assert nxt["has_plan"] is True
    assert nxt["plan"]["id"] == pid
    done = await server.training_plan(action="done", plan_id=pid, result_session_id="r1")
    assert done["status"] == "done"
    assert (await server.training_plan(action="next"))["has_plan"] is False


async def test_training_plan_save_rejects_empty():
    with pytest.raises(ValueError):
        await server.training_plan(action="save", plan={})
