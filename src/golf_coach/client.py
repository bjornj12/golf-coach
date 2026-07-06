"""Thin async GraphQL client for the Trackman Golf API.

Responsibilities (and nothing more):
- attach the captured Bearer token,
- POST GraphQL queries,
- turn auth/transport/GraphQL errors into clear exceptions.

No coaching, no analysis, no opinions. Raw data only.
"""

from __future__ import annotations

from typing import Any

import httpx

from .config import USERINFO_ENDPOINT, Config


class TrackmanError(Exception):
    """Base error for Trackman client problems."""


class TrackmanAuthError(TrackmanError):
    """Missing/expired/invalid token. The fix is always: re-capture the token."""


class TrackmanGraphQLError(TrackmanError):
    """The API returned GraphQL `errors`."""

    def __init__(self, message: str, errors: list[dict[str, Any]]):
        super().__init__(message)
        self.errors = errors


class TrackmanClient:
    """Authenticated GraphQL client. Use as an async context manager."""

    def __init__(
        self, config: Config, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._config = config
        self._transport = transport  # injectable for tests
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> TrackmanClient:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._config.token:
            headers["Authorization"] = f"Bearer {self._config.token}"
        self._client = httpx.AsyncClient(
            timeout=self._config.timeout_seconds,
            headers=headers,
            transport=self._transport,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_token(self) -> None:
        if not self._config.token:
            raise TrackmanAuthError(
                "No Trackman token configured. Set TRACKMAN_TOKEN to a Bearer "
                "access token captured from an authenticated portal session "
                "(see docs/trackman-api.md)."
            )

    async def execute(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run a GraphQL query and return the `data` object.

        Raises TrackmanAuthError on 401/403, TrackmanGraphQLError on GraphQL
        errors, TrackmanError on other transport failures.
        """
        self._require_token()
        assert self._client is not None, "client used outside `async with`"
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            resp = await self._client.post(self._config.graphql_endpoint, json=payload)
        except httpx.HTTPError as exc:  # network/timeout/etc.
            raise TrackmanError(f"Trackman request failed: {exc}") from exc

        if resp.status_code in (401, 403):
            raise TrackmanAuthError(
                f"Trackman returned {resp.status_code} — your session is expired "
                "or invalid. Use the `login` tool (or run `golf-coach login`) "
                "to sign in again."
            )
        if resp.status_code >= 400:
            raise TrackmanError(
                f"Trackman HTTP {resp.status_code}: {resp.text[:500]}"
            )

        body = resp.json()
        if body.get("errors"):
            messages = "; ".join(
                e.get("message", "unknown") for e in body["errors"]
            )
            raise TrackmanGraphQLError(
                f"Trackman GraphQL error: {messages}", body["errors"]
            )
        return body.get("data") or {}

    async def whoami(self) -> dict[str, Any]:
        """Hit the OIDC userinfo endpoint to confirm the token is valid.

        Returns the userinfo claims (sub, name, email, …). Used by the
        `authenticate` tool to verify the captured token without touching data.
        """
        self._require_token()
        assert self._client is not None
        try:
            resp = await self._client.get(USERINFO_ENDPOINT)
        except httpx.HTTPError as exc:
            raise TrackmanError(f"userinfo request failed: {exc}") from exc
        if resp.status_code in (401, 403):
            raise TrackmanAuthError(
                f"Token rejected by userinfo ({resp.status_code}). Re-capture "
                "TRACKMAN_TOKEN."
            )
        if resp.status_code >= 400:
            raise TrackmanError(f"userinfo HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()
