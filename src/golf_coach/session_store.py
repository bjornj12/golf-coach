"""Local store of per-session *analyses*, capped at the last 30, latest first.

This persists the analyzer's computed analysis for each Trackman session so the
analyzer can compare a new session against recent history without re-fetching
and re-computing everything. Records are keyed by `session_id` and ordered by
`time` (most recent first). Only the 30 most recent are kept.

The store holds derived analysis, not raw API payloads. It lives next to the
token cache under the MCP cache dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import storage
from .token_store import cache_dir

MAX_SESSIONS = 30


def store_path() -> Path:
    return cache_dir() / "session-analyses.json"


def _read() -> list[dict[str, Any]]:
    data = storage.read_json(store_path(), default=[])
    return data if isinstance(data, list) else []


def _write(records: list[dict[str, Any]]) -> None:
    storage.write_secure(store_path(), json.dumps(records, indent=2))


def _sorted_desc(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # ISO-8601 timestamps sort correctly as strings; missing time sinks to bottom.
    return sorted(records, key=lambda r: r.get("time") or "", reverse=True)


def save_analysis(record: dict[str, Any]) -> dict[str, Any]:
    """Upsert an analysis record by session_id, keep newest 30 by time."""
    if "session_id" not in record:
        raise ValueError("analysis record needs a 'session_id'")
    records = [r for r in _read() if r.get("session_id") != record["session_id"]]
    records.append(record)
    records = _sorted_desc(records)[:MAX_SESSIONS]
    _write(records)
    return record


def list_analyses() -> list[dict[str, Any]]:
    """All stored analyses, most recent first."""
    return _sorted_desc(_read())


def latest_analysis() -> dict[str, Any] | None:
    items = list_analyses()
    return items[0] if items else None


def get_analysis(session_id: str) -> dict[str, Any] | None:
    for r in _read():
        if r.get("session_id") == session_id:
            return r
    return None


def has_analysis(session_id: str) -> bool:
    return get_analysis(session_id) is not None


def stored_ids() -> set[str]:
    return {str(sid) for r in _read() if (sid := r.get("session_id"))}
