"""Trackman Golf MCP server (FastMCP).

Exposes the user's Trackman golf data as MCP tools. The server ONLY fetches and
returns raw data — coaching/analysis lives in the Claude skills. See CLAUDE.md.

Run:  trackman-mcp           (stdio transport)
Auth: set TRACKMAN_TOKEN to a Bearer access token captured from an authenticated
      portal session (see docs/trackman-api.md).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import FastMCP

from . import queries
from .client import TrackmanAuthError, TrackmanClient
from .config import Config

mcp = FastMCP(
    name="trackman-golf",
    instructions=(
        "Fetches the signed-in user's Trackman Golf statistics: profile and "
        "handicap, practice/course sessions, scorecards, shot-level launch "
        "metrics, and club gapping. Returns raw data only — interpret it with "
        "the golf coaching skills. Call `authenticate` first to confirm the "
        "token works."
    ),
)


async def _run(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query with a fresh authenticated client."""
    config = Config.from_env()
    async with TrackmanClient(config) as client:
        return await client.execute(query, variables)


@mcp.tool
async def authenticate() -> dict[str, Any]:
    """Verify the configured Trackman token and report who you're signed in as.

    Does not perform a password login (the portal client is server-side only).
    It validates the Bearer token in TRACKMAN_TOKEN against the OIDC userinfo
    endpoint. If this fails, re-capture the token from an authenticated portal
    session.
    """
    config = Config.from_env()
    if not config.has_token:
        return {
            "authenticated": False,
            "reason": "TRACKMAN_TOKEN is not set.",
            "how_to_fix": (
                "Log in at https://portal.trackmangolf.com, capture the Bearer "
                "access token the page sends to api.trackmangolf.com/graphql, "
                "and set it as TRACKMAN_TOKEN. See docs/trackman-api.md."
            ),
        }
    async with TrackmanClient(config) as client:
        info = await client.whoami()
    # Return identity claims only; never echo the token.
    return {
        "authenticated": True,
        "subject": info.get("sub"),
        "name": info.get("name"),
        "email": info.get("email"),
    }


@mcp.tool
async def get_profile() -> dict[str, Any]:
    """Get the player's profile and current handicap.

    Returns identity (name, email, nationality, dexterity, category) and the
    current handicap (`hcp.currentHcp`, plus the most recent handicap record).
    """
    data = await _run(queries.PROFILE)
    return data.get("me", {})


@mcp.tool
async def get_handicap(skip: int = 0, take: int = 20, only_in_avg: bool = False) -> dict[str, Any]:
    """Get handicap history: per-round differentials and how the index moved.

    Args:
        skip: paging offset.
        take: number of records to return.
        only_in_avg: only records counted in the handicap average.
    """
    data = await _run(
        queries.HANDICAP_HISTORY,
        {"skip": skip, "take": take, "onlyInAvg": only_in_avg},
    )
    return data.get("me", {}).get("hcp", {})


@mcp.tool
async def list_sessions(
    skip: int = 0,
    take: int = 25,
    kinds: list[str] | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """List the player's activities (practice sessions and course rounds).

    Args:
        skip / take: paging.
        kinds: optional ActivityKind filter, e.g. ["RANGE_PRACTICE", "COURSE_PLAY"].
        time_from / time_to: ISO-8601 timestamps to bound the window.
        include_hidden: include activities the user has hidden.

    Returns totalCount and a page of items (id, time, kind, plus a per-kind
    summary). Use `get_session` with an item's id for full detail.
    """
    data = await _run(
        queries.LIST_SESSIONS,
        {
            "skip": skip,
            "take": take,
            "kinds": kinds,
            "timeFrom": time_from,
            "timeTo": time_to,
            "includeHidden": include_hidden,
        },
    )
    return data.get("me", {}).get("activities", {})


@mcp.tool
async def get_session(activity_id: str) -> dict[str, Any]:
    """Get one activity in full by its id.

    For RANGE_PRACTICE: every stroke with its launch-monitor measurement.
    For COURSE_PLAY: the scorecard with per-hole scores and per-shot metrics.
    """
    data = await _run(queries.GET_SESSION, {"id": activity_id})
    return data.get("node", {})


@mcp.tool
async def get_course_rounds(
    skip: int = 0, take: int = 20, completed: bool | None = True
) -> dict[str, Any]:
    """Get the player's course rounds (scorecards).

    Each round includes per-hole scores (score, putts, GIR, hcp strokes) and
    round aggregates (`stat`: driving, FIR, GIR, putts, score distribution).

    Args:
        skip / take: paging.
        completed: filter by completion (True = finished rounds only).
    """
    data = await _run(
        queries.COURSE_ROUNDS, {"skip": skip, "take": take, "completed": completed}
    )
    return {"scorecards": data.get("me", {}).get("scorecards", [])}


@mcp.tool
async def get_club_stats(include_retired: bool = False) -> dict[str, Any]:
    """Get per-club gapping and dispersion ("My Bag" / Find My Distance).

    For each club: average carry and total, carry/total standard deviation, and
    the dispersion ellipse. This is the source for gapping analysis.
    """
    data = await _run(queries.CLUB_STATS, {"includeRetired": include_retired})
    return data.get("me", {}).get("equipment", {})


@mcp.tool
async def get_shot_data(activity_id: str) -> dict[str, Any]:
    """Get shot-level launch-monitor metrics for one activity.

    Convenience wrapper over `get_session` that returns the same full detail
    (strokes/shots with ball speed, club speed, smash, launch, spin, carry,
    side, curve, landing angle, …). Pass a RANGE_PRACTICE or COURSE_PLAY id.
    """
    data = await _run(queries.GET_SESSION, {"id": activity_id})
    return data.get("node", {})


@mcp.tool
async def get_activity_summary(
    time_from: str | None = None,
    time_to: str | None = None,
    skip: int = 0,
    take: int = 50,
) -> dict[str, Any]:
    """Get activity counts grouped by kind over an optional time window."""
    data = await _run(
        queries.ACTIVITY_SUMMARY,
        {"timeFrom": time_from, "timeTo": time_to, "skip": skip, "take": take},
    )
    return data.get("me", {}).get("activitySummary", {})


async def _login_cmd(headless: bool) -> int:
    """Run the browser login, cache the token, and confirm identity."""
    from .login import TrackmanLoginError, capture_token

    mode = "headless" if headless else "a browser window"
    print(f"Opening Trackman login ({mode})… sign in if prompted.")
    try:
        await capture_token(headless=headless)
    except TrackmanLoginError as exc:
        print(f"Login failed: {exc}")
        return 1

    # Confirm the captured token works (and show who it belongs to).
    config = Config.from_env()
    async with TrackmanClient(config) as client:
        info = await client.whoami()
    print(f"✓ Logged in as {info.get('name') or info.get('sub')}. "
          "Token cached — the MCP will use it automatically.")
    return 0


@mcp.tool
async def analyze_and_store_session(activity_id: str) -> dict[str, Any]:
    """Analyze one session, store the analysis locally, and return it.

    Fetches the session detail, runs the deterministic analyzer (classify
    warm-up vs serious practice vs game; per-session metrics; course difficulty;
    normalization against previously stored sessions; used vs available clubs),
    saves the result to the local store (kept to the last 30, latest first), and
    returns the stored record. Intended to be driven by the analyzer skill.
    """
    from . import analysis, session_store

    node = (await _run(queries.GET_SESSION, {"id": activity_id})).get("node") or {}
    if not node:
        return {"error": f"no session found for id {activity_id}"}

    clubs_available: list[str] | None = None
    try:
        equip = (await _run(queries.CLUB_STATS, {"includeRetired": False})) \
            .get("me", {}).get("equipment", {})
        clubs_available = [
            c.get("displayName") for c in (equip.get("clubs") or [])
            if c.get("displayName")
        ]
    except Exception:  # club data is a nice-to-have, not required
        clubs_available = None

    history = [
        r for r in session_store.list_analyses()
        if r.get("session_id") != activity_id
    ]
    record = analysis.analyze(
        node, session_id=activity_id, history=history,
        clubs_available=clubs_available,
    )
    session_store.save_analysis(record)
    return record


@mcp.tool
async def list_session_analyses() -> dict[str, Any]:
    """List stored session analyses, most recent first (max 30).

    Returns a lightweight index (id, time, kind, category, seriousness, summary)
    plus the total count. Use `get_session_analysis` for a full record.
    """
    from . import session_store

    items = session_store.list_analyses()
    index = [
        {
            "session_id": r.get("session_id"),
            "time": r.get("time"),
            "kind": r.get("kind"),
            "category": (r.get("analysis") or {}).get("category"),
            "seriousness": (r.get("analysis") or {}).get("seriousness"),
            "summary": (r.get("analysis") or {}).get("summary"),
        }
        for r in items
    ]
    return {"count": len(index), "latest_id": index[0]["session_id"] if index else None,
            "items": index}


@mcp.tool
async def get_session_analysis(activity_id: str) -> dict[str, Any]:
    """Get one full stored session-analysis record by id."""
    from . import session_store

    return session_store.get_analysis(activity_id) or {
        "error": f"no stored analysis for {activity_id}"
    }


def main() -> None:
    """Console-script entry point.

    Usage:
        trackman-mcp                 run the MCP server (stdio)
        trackman-mcp login           open a browser to sign in and cache a token
        trackman-mcp login --headless  silently refresh using the saved session
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="trackman-mcp")
    sub = parser.add_subparsers(dest="command")
    login = sub.add_parser("login", help="Capture a Trackman token via a browser.")
    login.add_argument(
        "--headless", action="store_true",
        help="Refresh silently using the saved session (no window).",
    )
    args = parser.parse_args()

    if args.command == "login":
        raise SystemExit(asyncio.run(_login_cmd(args.headless)))
    if args.command is None:
        mcp.run()
        return
    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
