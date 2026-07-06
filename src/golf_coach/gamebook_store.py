"""Local store of extracted GameBook rounds — a rolling window of the last 5.

The gamebook-screenshot-analysis skill extracts a round from screenshots and
saves it here so the coach can track direction of travel across recent rounds.
Records are keyed by `id`, ordered by `date` (newest first), and only the 5 most
recent are kept. Holds derived data only; lives under the MCP cache dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import storage
from .token_store import cache_dir

MAX_ROUNDS = 5


def store_path() -> Path:
    return cache_dir() / "gamebook-rounds.json"


def _read() -> list[dict[str, Any]]:
    data = storage.read_json(store_path(), default=[])
    return data if isinstance(data, list) else []


def _write(rounds: list[dict[str, Any]]) -> None:
    storage.write_secure(store_path(), json.dumps(rounds, indent=2))


def _sorted_desc(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # ISO dates sort as strings; tie-break by id for stability.
    return sorted(rounds, key=lambda r: (r.get("date") or "", r.get("id") or ""),
                  reverse=True)


def save_round(record: dict[str, Any]) -> dict[str, Any]:
    """Upsert a round by `id`; keep the newest 5 by date. Requires `id`."""
    if not record.get("id"):
        raise ValueError("gamebook round record needs an 'id'")
    rounds = [r for r in _read() if r.get("id") != record["id"]]
    rounds.append(record)
    rounds = _sorted_desc(rounds)[:MAX_ROUNDS]
    _write(rounds)
    return record


def list_rounds() -> list[dict[str, Any]]:
    """All stored rounds, newest first."""
    return _sorted_desc(_read())


def latest_round() -> dict[str, Any] | None:
    rounds = list_rounds()
    return rounds[0] if rounds else None


def get_round(round_id: str) -> dict[str, Any] | None:
    for r in _read():
        if r.get("id") == round_id:
            return r
    return None


def priors_of(round_id: str) -> list[dict[str, Any]]:
    """Rounds chronologically before `round_id` (by date), newest first."""
    rounds = _sorted_desc(_read())
    target = next((r for r in rounds if r.get("id") == round_id), None)
    if target is None:
        return []
    tdate = target.get("date") or ""
    return [r for r in rounds if (r.get("date") or "") < tdate]
