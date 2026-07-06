"""Config loading: token precedence and the endpoint SSRF guard."""

from __future__ import annotations

import base64
import json
import time

import pytest

from golf_coach import token_store
from golf_coach.config import Config


def _jwt(exp: int) -> str:
    def b64(o: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'exp': exp})}.sig"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)
    monkeypatch.delenv("TRACKMAN_GRAPHQL_ENDPOINT", raising=False)


# --- token precedence ------------------------------------------------------

def test_fresh_env_token_wins(monkeypatch):
    fresh = _jwt(int(time.time()) + 600)
    monkeypatch.setenv("TRACKMAN_TOKEN", fresh)
    assert Config.from_env().token == fresh


def test_expired_env_token_falls_back_to_fresh_cache(monkeypatch):
    cached_fresh = _jwt(int(time.time()) + 600)
    token_store.save_token(cached_fresh)
    monkeypatch.setenv("TRACKMAN_TOKEN", _jwt(int(time.time()) - 10))
    # An expired env token is useless; prefer the fresh cached one.
    assert Config.from_env().token == cached_fresh


def test_expired_env_token_used_when_no_cache(monkeypatch):
    expired = _jwt(int(time.time()) - 10)
    monkeypatch.setenv("TRACKMAN_TOKEN", expired)
    assert Config.from_env().token == expired


def test_bearer_prefix_is_stripped(monkeypatch):
    fresh = _jwt(int(time.time()) + 600)
    monkeypatch.setenv("TRACKMAN_TOKEN", f"Bearer {fresh}")
    assert Config.from_env().token == fresh


# --- SSRF guard ------------------------------------------------------------

def test_http_endpoint_with_token_is_rejected(monkeypatch):
    monkeypatch.setenv("TRACKMAN_TOKEN", _jwt(int(time.time()) + 600))
    monkeypatch.setenv("TRACKMAN_GRAPHQL_ENDPOINT", "http://attacker.example/graphql")
    with pytest.raises(ValueError):
        Config.from_env()


def test_http_localhost_allowed_for_testing(monkeypatch):
    monkeypatch.setenv("TRACKMAN_TOKEN", _jwt(int(time.time()) + 600))
    monkeypatch.setenv("TRACKMAN_GRAPHQL_ENDPOINT", "http://localhost:8080/graphql")
    assert Config.from_env().graphql_endpoint.startswith("http://localhost")


def test_https_override_allowed(monkeypatch):
    monkeypatch.setenv("TRACKMAN_TOKEN", _jwt(int(time.time()) + 600))
    monkeypatch.setenv("TRACKMAN_GRAPHQL_ENDPOINT", "https://staging.trackman.example/graphql")
    assert Config.from_env().graphql_endpoint.startswith("https://")


def test_no_token_skips_endpoint_guard(monkeypatch):
    # Without a token there's nothing to exfiltrate; don't block config loading.
    monkeypatch.setenv("TRACKMAN_GRAPHQL_ENDPOINT", "http://attacker.example/graphql")
    assert Config.from_env().token is None
