"""Tests for the token cache + JWT expiry logic (no browser needed)."""

from __future__ import annotations

import base64
import json
import time

from golf_coach import token_store


def _make_jwt(exp: int) -> str:
    """Build an unsigned JWT-shaped string with the given exp claim."""
    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{b64({'alg': 'none'})}.{b64({'exp': exp})}.sig"


def test_decode_exp_reads_claim():
    exp = 1783167039
    assert token_store.decode_exp(_make_jwt(exp)) == exp


def test_decode_exp_handles_garbage():
    assert token_store.decode_exp("not-a-jwt") is None
    assert token_store.decode_exp("") is None


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    future = int(time.time()) + 600
    token_store.save_token(_make_jwt(future))
    cached = token_store.load_token()
    assert cached is not None
    assert cached.access_token.endswith(".sig")
    assert cached.expires_at == future
    assert not cached.is_expired()


def test_expired_token_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    past = int(time.time()) - 10
    token_store.save_token(_make_jwt(past))
    cached = token_store.load_token()
    assert cached is not None
    assert cached.is_expired()


def test_load_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    assert token_store.load_token() is None


def test_token_file_is_user_only_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    token_store.save_token(_make_jwt(int(time.time()) + 600))
    mode = (token_store.token_path().stat().st_mode) & 0o777
    assert mode == 0o600
