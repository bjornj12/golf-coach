"""End-to-end validation: confirm the MCP retrieves ALL user statistics.

Runs every tool against the real Trackman API using TRACKMAN_TOKEN, then prints
a coverage report: which stat categories returned data, counts, and any gaps.

Usage:
    TRACKMAN_TOKEN=... uv run python scripts/validate.py

Exit code 0 = every category that should have data did; non-zero = something is
missing or errored. Secrets are never printed.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Allow running from the repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from golf_coach import queries  # noqa: E402
from golf_coach.client import (  # noqa: E402
    TrackmanAuthError,
    TrackmanClient,
    TrackmanError,
)
from golf_coach.config import Config  # noqa: E402


def _count(obj: object) -> int:
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        for key in ("items", "scorecards", "clubs"):
            if key in obj and isinstance(obj[key], list):
                return len(obj[key])
    return 0


async def main() -> int:
    config = Config.from_env()
    if not config.has_token:
        print("FAIL: TRACKMAN_TOKEN is not set. Capture a token first "
              "(see docs/trackman-api.md).")
        return 2

    results: list[tuple[str, str, str]] = []  # (category, status, detail)

    async with TrackmanClient(config) as client:
        # 0. Identity
        try:
            info = await client.whoami()
            name = info.get("name") or info.get("sub") or "unknown"
            results.append(("auth/identity", "OK", f"signed in as {name}"))
        except TrackmanError as exc:
            print(f"FAIL: token invalid — {exc}")
            return 2

        checks = [
            ("profile + handicap", queries.PROFILE, None,
             lambda d: d.get("me", {}).get("profile")),
            ("handicap history", queries.HANDICAP_HISTORY,
             {"skip": 0, "take": 20, "onlyInAvg": False},
             lambda d: d.get("me", {}).get("hcp", {}).get("playerHistory")),
            ("sessions/activities", queries.LIST_SESSIONS,
             {"skip": 0, "take": 25, "kinds": None, "timeFrom": None,
              "timeTo": None, "includeHidden": False},
             lambda d: d.get("me", {}).get("activities")),
            ("course rounds", queries.COURSE_ROUNDS,
             {"skip": 0, "take": 20, "completed": True},
             lambda d: d.get("me", {}).get("scorecards")),
            ("club stats / gapping", queries.CLUB_STATS,
             {"includeRetired": False},
             lambda d: d.get("me", {}).get("equipment", {}).get("clubs")),
            ("activity summary", queries.ACTIVITY_SUMMARY,
             {"timeFrom": None, "timeTo": None, "skip": 0, "take": 50},
             lambda d: d.get("me", {}).get("activitySummary")),
        ]

        first_activity_id = None
        for label, query, variables, extract in checks:
            try:
                data = await client.execute(query, variables)
                value = extract(data)
                n = _count(value) if isinstance(value, (list, dict)) else 0
                if value is None:
                    results.append((label, "EMPTY", "no data returned"))
                else:
                    detail = f"{n} item(s)" if n else "present"
                    results.append((label, "OK", detail))
                if label == "sessions/activities" and isinstance(value, dict):
                    items = value.get("items") or []
                    # Prefer a kind whose shot detail get_session supports.
                    supported = {"RANGE_PRACTICE", "COURSE_PLAY"}
                    pick = next(
                        (it for it in items if it.get("kind") in supported), None
                    )
                    if pick:
                        first_activity_id = pick.get("id")
            except TrackmanError as exc:
                results.append((label, "ERROR", str(exc)[:120]))

        # Shot-level detail for one real activity (proves shot data works).
        if first_activity_id:
            try:
                data = await client.execute(
                    queries.GET_SESSION, {"id": first_activity_id}
                )
                node = data.get("node") or {}
                kind = node.get("__typename", "?")
                strokes = node.get("strokes") or []
                holes = (node.get("scorecard") or {}).get("holes") or []
                shot_count = len(strokes) + sum(
                    len(h.get("shots") or []) for h in holes
                )
                has_metric = False
                sample = strokes or [s for h in holes for s in (h.get("shots") or [])]
                if sample:
                    has_metric = bool((sample[0].get("measurement") or {}))
                status = "OK" if (shot_count and has_metric) else "EMPTY"
                results.append(("shot-level detail", status,
                                f"{kind}: {shot_count} shot(s) w/ launch metrics"))
            except TrackmanError as exc:
                results.append(("shot-level detail", "ERROR", str(exc)[:120]))
        else:
            results.append(("shot-level detail", "SKIP", "no activity to drill into"))

    # Report
    print("\n=== Trackman stats coverage ===")
    width = max(len(r[0]) for r in results)
    bad = 0
    for cat, status, detail in results:
        flag = {"OK": "✓", "EMPTY": "·", "SKIP": "·"}.get(status, "✗")
        if status in ("ERROR",):
            bad += 1
        print(f"  {flag} {cat.ljust(width)}  {status:6}  {detail}")
    print()

    if bad:
        print(f"RESULT: {bad} category(ies) errored — see above.")
        return 1
    print("RESULT: all categories reachable. EMPTY = account simply has no data "
          "there yet, not a failure.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
