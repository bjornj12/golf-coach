"""Unit tests for the Trackman client and config — no network required."""

from __future__ import annotations

import httpx
import pytest

from golf_coach.client import (
    TrackmanAuthError,
    TrackmanClient,
    TrackmanGraphQLError,
)
from golf_coach.config import Config


def _config(token: str | None = "test-token") -> Config:
    return Config(token=token)


def test_config_strips_bearer_prefix(monkeypatch):
    monkeypatch.setenv("TRACKMAN_TOKEN", "Bearer abc.def.ghi")
    cfg = Config.from_env()
    assert cfg.token == "abc.def.ghi"
    assert cfg.has_token


def test_config_no_token(monkeypatch, tmp_path):
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))  # empty cache
    cfg = Config.from_env()
    assert cfg.token is None
    assert not cfg.has_token


def test_config_falls_back_to_cached_token(monkeypatch, tmp_path):
    import time

    from golf_coach import token_store

    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    # A token whose exp is in the future should be picked up.
    import base64
    import json

    def b64(o: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")

    jwt = f"{b64({'alg': 'none'})}.{b64({'exp': int(time.time()) + 600})}.s"
    token_store.save_token(jwt)
    cfg = Config.from_env()
    assert cfg.has_token
    assert cfg.token == jwt


async def test_execute_returns_data():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"data": {"me": {"profile": {"fullName": "Pat"}}}})

    transport = httpx.MockTransport(handler)
    async with TrackmanClient(_config(), transport=transport) as client:
        data = await client.execute("query { me { profile { fullName } } }")
    assert data["me"]["profile"]["fullName"] == "Pat"


async def test_execute_raises_on_401():
    transport = httpx.MockTransport(lambda r: httpx.Response(401, text="nope"))
    async with TrackmanClient(_config(), transport=transport) as client:
        with pytest.raises(TrackmanAuthError):
            await client.execute("query { me { profile { fullName } } }")


async def test_execute_raises_on_graphql_errors():
    body = {"errors": [{"message": "boom"}], "data": None}
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=body))
    async with TrackmanClient(_config(), transport=transport) as client:
        with pytest.raises(TrackmanGraphQLError):
            await client.execute("query { me { profile { fullName } } }")


async def test_execute_requires_token():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"data": {}}))
    async with TrackmanClient(_config(token=None), transport=transport) as client:
        with pytest.raises(TrackmanAuthError):
            await client.execute("query { __typename }")


async def test_whoami_returns_claims():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"sub": "u1", "name": "Pat Golfer", "email": "p@x.io"})

    transport = httpx.MockTransport(handler)
    async with TrackmanClient(_config(), transport=transport) as client:
        info = await client.whoami()
    assert info["sub"] == "u1"
    assert info["name"] == "Pat Golfer"


async def test_whoami_raises_auth_error_on_401():
    transport = httpx.MockTransport(lambda r: httpx.Response(401, text="expired"))
    async with TrackmanClient(_config(), transport=transport) as client:
        with pytest.raises(TrackmanAuthError):
            await client.whoami()
