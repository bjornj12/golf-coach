"""Local store of prescribed training plans (the coach's memory).

When the golf-coaching skill prescribes a practice session, it saves the plan
here. Later, "what's today's training?" pulls the next pending plan back. Plans
form an ordered queue: oldest pending first; mark one done and the next becomes
current.

Stored as JSON under the MCP cache dir, capped at the most recent 50.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from . import storage
from .token_store import cache_dir

MAX_PLANS = 50


def store_path() -> Path:
    return cache_dir() / "training-plans.json"


def _read() -> list[dict[str, Any]]:
    data = storage.read_json(store_path(), default=[])
    return data if isinstance(data, list) else []


def _write(plans: list[dict[str, Any]]) -> None:
    storage.write_secure(store_path(), json.dumps(plans, indent=2))


def _by_created(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(plans, key=lambda p: p.get("created_at") or 0)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "plan").lower()).strip("-")
    return slug[:40] or "plan"


def save_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Upsert a training plan. Assigns id/created_at/status if missing."""
    plan = dict(plan)
    plan.setdefault("created_at", int(time.time()))
    plan.setdefault("status", "pending")
    plan.setdefault("completed_at", None)
    plan.setdefault("result_session_id", None)
    if not plan.get("id"):
        plan["id"] = f"{_slugify(plan.get('title', 'plan'))}-{plan['created_at']}"

    plans = [p for p in _read() if p.get("id") != plan["id"]]
    plans.append(plan)
    plans = _by_created(plans)[-MAX_PLANS:]
    _write(plans)
    return plan


def list_plans(status: str | None = None) -> list[dict[str, Any]]:
    """Plans ordered oldest→newest, optionally filtered by status."""
    plans = _by_created(_read())
    if status:
        plans = [p for p in plans if p.get("status") == status]
    return plans


def next_pending() -> dict[str, Any] | None:
    """The next training session to do: the oldest pending plan."""
    pending = list_plans(status="pending")
    return pending[0] if pending else None


def get_plan(plan_id: str) -> dict[str, Any] | None:
    for p in _read():
        if p.get("id") == plan_id:
            return p
    return None


def mark_done(plan_id: str, result_session_id: str | None = None) -> dict[str, Any] | None:
    """Mark a plan completed (optionally linking the session that did it)."""
    plans = _read()
    updated = None
    for p in plans:
        if p.get("id") == plan_id:
            p["status"] = "done"
            p["completed_at"] = int(time.time())
            if result_session_id is not None:
                p["result_session_id"] = result_session_id
            updated = p
            break
    if updated is not None:
        _write(plans)
    return updated
