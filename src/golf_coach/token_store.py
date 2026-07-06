"""Local cache for the captured Trackman Bearer token.

Stores the token (and its decoded expiry) in a user-only-readable file so the
MCP can load it without the user re-pasting. The browser login flow writes here;
the server reads here (falling back to the TRACKMAN_TOKEN env var).

No secrets are logged. The token never leaves the local machine.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import storage

# Clock skew margin: treat a token as expired this many seconds early.
EXPIRY_SKEW_SECONDS = 60


def cache_dir() -> Path:
    """Directory for cached token + browser profile. Override via GOLF_COACH_CACHE_DIR."""
    override = os.environ.get("GOLF_COACH_CACHE_DIR")
    base = Path(override) if override else Path.home() / ".golf-coach"
    return storage.secure_dir(base)


def token_path() -> Path:
    return cache_dir() / "token.json"


def browser_profile_dir() -> Path:
    """Persistent browser profile so the portal session survives between logins."""
    return storage.secure_dir(cache_dir() / "browser-profile")


def decode_exp(token: str) -> int | None:
    """Read the `exp` claim from a JWT without verifying its signature."""
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)  # restore base64 padding
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = claims.get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None


@dataclass(frozen=True)
class CachedToken:
    access_token: str
    expires_at: int | None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False  # unknown expiry — let the API be the judge
        return time.time() >= (self.expires_at - EXPIRY_SKEW_SECONDS)


def save_token(access_token: str) -> CachedToken:
    """Persist a token to the cache (mode 0600) with its decoded expiry."""
    expires_at = decode_exp(access_token)
    data = {
        "access_token": access_token,
        "expires_at": expires_at,
        "captured_at": int(time.time()),
    }
    # Atomic, user-only (0600) write — never briefly world-readable.
    storage.write_secure(token_path(), json.dumps(data))
    return CachedToken(access_token=access_token, expires_at=expires_at)


def load_token() -> CachedToken | None:
    """Load the cached token, or None if absent/unreadable."""
    data = storage.read_json(token_path(), default=None)
    if not isinstance(data, dict):
        return None
    token = data.get("access_token")
    if not token:
        return None
    return CachedToken(access_token=token, expires_at=data.get("expires_at"))
