"""Live eval: run the session analyzer over the user's REAL last-30 sessions.

Verifies the analyzer end-to-end against personal data: pulls sessions, analyzes
+ stores each, and asserts invariants (store cap, well-formed records, valid
categories, normalization present). Prints a report + the latest-session summary
to the console only — it writes no personal data into the repo.

Usage:  uv run python scripts/eval_analyzer.py   (uses the cached login token)
Exit 0 if all checks pass.
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from trackman_mcp import analysis, queries, session_store  # noqa: E402
from trackman_mcp.client import TrackmanClient, TrackmanError  # noqa: E402
from trackman_mcp.config import Config  # noqa: E402

VALID_CATEGORIES = {"game", "practice", "warmup", "other"}


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  {'✓' if ok else '✗'} {label}" + (f" — {detail}" if detail else ""))
    return ok


async def main() -> int:
    config = Config.from_env()
    if not config.has_token:
        print("FAIL: no token. Run `trackman-mcp login` first.")
        return 2

    async with TrackmanClient(config) as client:
        try:
            who = await client.whoami()
        except TrackmanError as exc:
            print(f"FAIL: token invalid — {exc}")
            return 2
        print(f"Signed in as {who.get('name') or who.get('sub')}\n")

        # Available clubs (once).
        clubs_available = None
        try:
            equip = (await client.execute(queries.CLUB_STATS, {"includeRetired": False})) \
                .get("me", {}).get("equipment", {})
            clubs_available = [c.get("displayName") for c in (equip.get("clubs") or [])
                               if c.get("displayName")]
        except TrackmanError:
            pass

        # Pull recent sessions (newest first).
        acts = (await client.execute(queries.LIST_SESSIONS, {
            "skip": 0, "take": 30, "kinds": None,
            "timeFrom": None, "timeTo": None, "includeHidden": False,
        })).get("me", {}).get("activities", {})
        items = acts.get("items") or []
        print(f"Fetched {len(items)} recent sessions "
              f"(totalCount {acts.get('totalCount')}).\n")

        # Analyze + store each OLDEST-first so each session's history (the
        # sessions before it) is already stored when we normalize it.
        errors = 0
        analyzed = 0
        for it in reversed(items):
            sid = it.get("id")
            if not sid:
                continue
            try:
                node = (await client.execute(queries.GET_SESSION, {"id": sid})).get("node") or {}
                if not node:
                    continue
                history = [r for r in session_store.list_analyses()
                           if r.get("session_id") != sid]
                rec = analysis.analyze(node, session_id=sid, history=history,
                                       clubs_available=clubs_available)
                session_store.save_analysis(rec)
                analyzed += 1
            except TrackmanError as exc:
                errors += 1
                print(f"  ! error on {sid}: {str(exc)[:80]}")

    stored = session_store.list_analyses()

    # --- invariant checks (the eval) ---
    print("\n=== Eval checks ===")
    results = [
        check("analyzed at least one session", analyzed > 0, f"{analyzed} analyzed"),
        check("store capped at 30", len(stored) <= 30, f"{len(stored)} stored"),
        check("no fetch errors", errors == 0, f"{errors} errors"),
        check("all categories valid",
              all((r.get("analysis") or {}).get("category") in VALID_CATEGORIES
                  for r in stored)),
        check("stored newest-first",
              [r.get("time") or "" for r in stored]
              == sorted((r.get("time") or "" for r in stored), reverse=True)),
        check("clubs captured", bool(clubs_available), f"{len(clubs_available or [])} clubs"),
    ]
    latest = stored[0] if stored else None
    if latest:
        a = latest.get("analysis") or {}
        results.append(check("latest has normalized stats", "normalized" in a))
        results.append(check("latest has a summary", bool(a.get("summary"))))

    # --- category breakdown + latest summary (console only) ---
    from collections import Counter
    cats = Counter((r.get("analysis") or {}).get("category") for r in stored)
    print("\n=== Category breakdown (last 30) ===")
    for c, n in cats.most_common():
        print(f"  {c}: {n}")

    if latest:
        a = latest["analysis"]
        print("\n=== Latest session summary (personal — console only) ===")
        print(f"  {latest.get('time')}  [{a.get('category')}]")
        print(f"  {a.get('summary')}")
        if a.get("normalized"):
            print("  normalized vs history:")
            for k, v in a["normalized"].items():
                print(f"    {k}: value={v['value']} mean={v['mean']} "
                      f"delta={v['delta']} (n={v['n']})")

    passed = all(results)
    print(f"\nRESULT: {'PASS' if passed else 'FAIL'} "
          f"({sum(results)}/{len(results)} checks)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
