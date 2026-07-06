"""Configuration loaded from environment variables.

Secrets come from the environment only — never hardcode or log them.
See .env.example for the full list.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from urllib.parse import urlparse

GRAPHQL_ENDPOINT = "https://api.trackmangolf.com/graphql"
OIDC_ISSUER = "https://login.trackmangolf.com"
USERINFO_ENDPOINT = f"{OIDC_ISSUER}/connect/userinfo"

# The public web-portal client id, observed from the portal's login redirect.
# Used only for reference / future OAuth work; the MCP does not run the exchange.
WEB_PORTAL_CLIENT_ID = "golf-portal.2dad6810-ef7c-4a0d-9c0a-0eaae2fb9e98"

# Hosts for which a plaintext (http) endpoint is tolerated — local testing only.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _cached_token() -> str | None:
    """Return a non-expired cached token, if one exists. Never raises."""
    try:
        from . import token_store

        cached = token_store.load_token()
    except Exception:  # cache is best-effort; never break config loading
        return None
    if cached and not cached.is_expired():
        return cached.access_token
    return None


def _resolve_token(env_raw: str | None) -> str | None:
    """Pick the token to use, preferring a fresh one.

    A token in TRACKMAN_TOKEN normally wins, but if it is *decodably expired*
    and a non-expired cached token exists, the cache wins — otherwise the silent
    refresh path is dead (the env token always shadows the freshly-cached one).
    """
    if not env_raw:
        return _cached_token()
    env = env_raw.strip()
    if env.lower().startswith("bearer "):
        env = env[7:].strip()

    from .token_store import EXPIRY_SKEW_SECONDS, decode_exp

    exp = decode_exp(env)
    if exp is not None and time.time() >= (exp - EXPIRY_SKEW_SECONDS):
        return _cached_token() or env  # expired env token: prefer fresh cache
    return env


def _validate_endpoint(endpoint: str, has_token: bool) -> None:
    """Refuse to ship a bearer token to a plaintext / unexpected endpoint (SSRF).

    https is always allowed; http is allowed only for localhost (mock/proxy
    testing). A non-default host gets a one-line stderr warning. With no token
    there is nothing to leak, so the check is skipped.
    """
    if not has_token:
        return
    parsed = urlparse(endpoint)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" and host not in _LOCAL_HOSTS:
        raise ValueError(
            f"Refusing to send your Trackman token to {endpoint!r}: only https "
            "(or http://localhost for testing) is allowed. Check "
            "TRACKMAN_GRAPHQL_ENDPOINT."
        )
    if endpoint != GRAPHQL_ENDPOINT:
        print(
            f"golf-coach: using non-default GraphQL endpoint {endpoint!r}.",
            file=sys.stderr,
        )


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the Trackman MCP."""

    token: str | None
    graphql_endpoint: str = GRAPHQL_ENDPOINT
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> Config:
        token = _resolve_token(os.environ.get("TRACKMAN_TOKEN"))
        endpoint = os.environ.get("TRACKMAN_GRAPHQL_ENDPOINT", GRAPHQL_ENDPOINT)
        _validate_endpoint(endpoint, has_token=bool(token))
        timeout = float(os.environ.get("TRACKMAN_TIMEOUT_SECONDS", "30"))
        return cls(token=token, graphql_endpoint=endpoint, timeout_seconds=timeout)

    @property
    def has_token(self) -> bool:
        return bool(self.token)
