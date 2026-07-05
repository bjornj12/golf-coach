"""Trackman Golf MCP server (FastMCP).

Exposes the user's Trackman golf data as MCP tools, and serves the coaching
skills as MCP prompts. The server ONLY fetches/returns raw data and runs the
deterministic analytics — coaching *judgment* lives in the skills (now delivered
as prompts). See CLAUDE.md.

Run:  trackman-mcp           (stdio transport)
Auth: run `trackman-mcp login` (browser) or set TRACKMAN_TOKEN. See README.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

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
        "the coaching prompts this server provides. Call `auth` (action='status') "
        "first. If it reports the user isn't signed in or the session expired, "
        "call `auth` (action='login') — it opens a browser window for a one-time "
        "sign-in (no terminal or token needed) — then retry. Never ask the user "
        "to paste a token or run terminal commands unless they ask how."
    ),
)

# Tool annotation presets (readOnly, idempotent, openWorld).
_RO_API = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
_RO_LOCAL = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}
_WRITE_API = {"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True}
_WRITE_LOCAL = {"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False}

# Seconds to wait for a silent refresh before giving up (dead session fails fast).
SILENT_REFRESH_TIMEOUT = 30.0


async def _try_silent_refresh() -> bool:
    """Try to refresh the token headlessly using the persisted browser session.

    Returns True if a fresh token was captured (the saved portal session is still
    valid), False otherwise (session expired, or Playwright not installed).
    """
    try:
        from .login import capture_token

        await capture_token(headless=True, timeout_seconds=SILENT_REFRESH_TIMEOUT)
        return True
    except Exception:
        return False


async def _run(
    query: str, variables: dict[str, Any] | None = None, _allow_refresh: bool = True
) -> dict[str, Any]:
    """Execute a GraphQL query with a fresh authenticated client.

    On an auth failure, transparently try a one-time silent token refresh (using
    the saved browser session) and retry. If that fails too, the auth error
    propagates with guidance to re-login.
    """
    config = Config.from_env()
    try:
        async with TrackmanClient(config) as client:
            return await client.execute(query, variables)
    except TrackmanAuthError:
        if _allow_refresh and await _try_silent_refresh():
            return await _run(query, variables, _allow_refresh=False)
        raise


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #


async def _auth_status() -> dict[str, Any]:
    config = Config.from_env()
    if not config.has_token:
        return {
            "authenticated": False,
            "reason": "Not signed in to Trackman yet.",
            "how_to_fix": "Call auth(action='login') — a browser window opens for a "
                          "one-time sign-in (no terminal or token needed).",
        }
    try:
        async with TrackmanClient(config) as client:
            info = await client.whoami()
    except TrackmanAuthError:
        return {
            "authenticated": False,
            "reason": "Your Trackman session has expired.",
            "how_to_fix": "Call auth(action='login') — a browser window opens to "
                          "sign in again (no terminal needed).",
        }
    # Identity claims only; never echo the token.
    return {
        "authenticated": True,
        "subject": info.get("sub"),
        "name": info.get("name"),
        "email": info.get("email"),
    }


async def _auth_login(open_browser: bool) -> dict[str, Any]:
    from .login import TrackmanLoginError, capture_token

    # 1) Silent refresh (fast; works while the saved session is valid).
    try:
        await capture_token(headless=True, timeout_seconds=SILENT_REFRESH_TIMEOUT)
    except Exception:
        # 2) Session likely expired — open a window for an interactive sign-in.
        if not open_browser:
            return {
                "success": False,
                "message": "Saved session expired and open_browser is false. "
                           "Call auth(action='login', open_browser=true), or run "
                           "`trackman-mcp login` in a terminal.",
            }
        try:
            await capture_token(headless=False)
        except TrackmanLoginError as exc:
            return {"success": False, "message": f"Login didn't complete: {exc}"}

    config = Config.from_env()
    try:
        async with TrackmanClient(config) as client:
            info = await client.whoami()
    except TrackmanAuthError:
        return {"success": False,
                "message": "Captured a token but it was rejected — try again."}
    return {"success": True, "name": info.get("name") or info.get("subject"),
            "message": "Signed in. The MCP will use this automatically."}


@mcp.tool(annotations=_WRITE_API)
async def auth(
    action: Literal["status", "login"] = "status",
    open_browser: bool = True,
) -> dict[str, Any]:
    """Check or (re)establish your Trackman sign-in.

    Actions:
    - `status` (default): report whether the current token works and who you're
      signed in as. Use this first; it never opens anything.
    - `login`: (re)authenticate. Tries a silent refresh of the saved browser
      session first; if that's expired and `open_browser` is true, opens a window
      to sign in once. Use when `status` says expired/not signed in.

    Never echoes the token.
    """
    if action == "login":
        return await _auth_login(open_browser)
    return await _auth_status()


# --------------------------------------------------------------------------- #
# Data reads (discrete, read-only)
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=_RO_API)
async def get_profile() -> dict[str, Any]:
    """Get the player's profile and current handicap.

    Returns identity (name, email, nationality, dexterity, category) and the
    current handicap (`hcp.currentHcp`, plus the most recent handicap record).
    """
    data = await _run(queries.PROFILE)
    return data.get("me", {})


@mcp.tool(annotations=_RO_API)
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


@mcp.tool(annotations=_RO_API)
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


@mcp.tool(annotations=_RO_API)
async def get_session(activity_id: str) -> dict[str, Any]:
    """Get one activity in full by its id — including shot-level launch metrics.

    For RANGE_PRACTICE: every stroke with its measurement (ball/club speed,
    smash, launch, spin, carry, side, curve, landing angle, …).
    For COURSE_PLAY: the scorecard with per-hole scores and per-shot metrics.
    """
    data = await _run(queries.GET_SESSION, {"id": activity_id})
    node = data.get("node")
    if not node:
        raise ValueError(f"No activity found for id {activity_id!r}.")
    return node


@mcp.tool(annotations=_RO_API)
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


@mcp.tool(annotations=_RO_API)
async def get_club_stats(include_retired: bool = False) -> dict[str, Any]:
    """Get per-club gapping and dispersion ("My Bag" / Find My Distance).

    For each club: average carry and total, carry/total standard deviation, and
    the dispersion ellipse. This is the source for gapping analysis.
    """
    data = await _run(queries.CLUB_STATS, {"includeRetired": include_retired})
    return data.get("me", {}).get("equipment", {})


@mcp.tool(annotations=_RO_API)
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


# --------------------------------------------------------------------------- #
# Session analysis (local store, deterministic analytics)
# --------------------------------------------------------------------------- #


async def _analysis_analyze(activity_id: str) -> dict[str, Any]:
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


def _analysis_list() -> dict[str, Any]:
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


@mcp.tool(annotations=_WRITE_API)
async def session_analysis(
    action: Literal["analyze", "get", "list"],
    activity_id: str | None = None,
) -> dict[str, Any]:
    """Per-session analysis (deterministic classification + metrics, stored locally).

    Actions:
    - `analyze` (needs `activity_id`): fetch a session, classify it (warm-up vs
      serious practice vs game), compute metrics, normalize vs prior stored
      sessions, store the record (last 30 kept), and return it.
    - `get` (needs `activity_id`): return one stored analysis record.
    - `list`: return the index of stored analyses (most recent first).

    Drive this with the `trackman-session-analyzer` prompt.
    """
    if action == "analyze":
        if not activity_id:
            raise ValueError("session_analysis(action='analyze') needs an activity_id.")
        return await _analysis_analyze(activity_id)
    if action == "get":
        if not activity_id:
            raise ValueError("session_analysis(action='get') needs an activity_id.")
        from . import session_store
        return session_store.get_analysis(activity_id) or {
            "error": f"no stored analysis for {activity_id}"
        }
    return _analysis_list()


# --------------------------------------------------------------------------- #
# Training plans (the coach's memory)
# --------------------------------------------------------------------------- #


async def _training_verify(plan_id: str, activity_id: str | None) -> dict[str, Any]:
    from . import analysis, training_store

    plan = training_store.get_plan(plan_id)
    if not plan:
        return {"error": f"no training plan with id {plan_id}"}
    specs = plan.get("target_specs")
    if not specs:
        return {"error": "this plan has no machine-readable target_specs to verify",
                "plan_id": plan_id}

    target_clubs = {analysis.canonical_club(s.get("club")) for s in specs if s.get("club")}

    async def _strokes_for(aid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        node = (await _run(queries.SESSION_MEASUREMENTS, {"id": aid})).get("node") or {}
        return node, (node.get("strokes") or [])

    scan_window = 20
    chosen_id = activity_id
    node: dict[str, Any] = {}
    strokes: list[dict[str, Any]] = []
    if chosen_id:
        node, strokes = await _strokes_for(chosen_id)
    else:
        # Newest first: first session that has shots for a target club.
        acts = (await _run(queries.LIST_SESSIONS, {
            "skip": 0, "take": scan_window, "kinds": None,
            "timeFrom": None, "timeTo": None, "includeHidden": False,
        })).get("me", {}).get("activities", {}).get("items", [])
        for it in acts:
            aid = it.get("id")
            if not aid:
                continue
            # Pre-filter: if the list already names this session's clubs and none
            # match a target club, skip the per-session measurement fetch.
            if target_clubs and it.get("clubs") is not None:
                listed = {analysis.canonical_club(c) for c in it["clubs"]}
                if not (listed & target_clubs):
                    continue
            n, s = await _strokes_for(aid)
            has_target_club = any(
                analysis.canonical_club(st.get("club")) in target_clubs for st in s
            ) if target_clubs else bool(s)
            if has_target_club:
                chosen_id, node, strokes = aid, n, s
                break

    if not strokes:
        scope = "the session you gave" if activity_id else \
            f"the last {scan_window} activities"
        return {"plan_id": plan_id, "checked_session": chosen_id,
                "has_data": False,
                "message": f"No shots for this plan's target club(s) in {scope}."}

    verdict = analysis.verify_targets(strokes, specs)
    return {
        "plan_id": plan_id,
        "plan_title": plan.get("title"),
        "checked_session": chosen_id,
        "session_time": node.get("time"),
        "session_kind": node.get("kind"),
        "results": verdict["results"],
        "all_met": verdict["all_met"],
        "has_data": verdict["has_data"],
        "recommendation": (
            "All targets met — call training_plan(action='done') to graduate it."
            if verdict["all_met"] else
            "Not all targets met yet — keep this as the current focus."
        ),
    }


@mcp.tool(annotations=_WRITE_API)
async def training_plan(
    action: Literal["save", "next", "list", "done", "verify"],
    plan: dict[str, Any] | None = None,
    plan_id: str | None = None,
    status: Literal["pending", "done"] | None = None,
    activity_id: str | None = None,
    result_session_id: str | None = None,
) -> dict[str, Any]:
    """The coach's memory: save prescribed practice plans and recall/grade them.

    Actions:
    - `save` (needs `plan`): persist a prescribed plan to the pending queue. The
      `plan` is a structured dict — title, focus, diagnosis, blocks
      [{name, club, reps, detail, link, goal}], and optional `target_specs`
      (machine-readable targets, e.g. {metric:'clubPath', club:'DRIVER',
      op:'between', low:-1, high:2}) used by `verify`. Returns the stored plan
      (with id). Capped at the most recent 50.
    - `next`: return the next pending plan — the answer to "what's today's training?".
    - `list` (optional `status`='pending'|'done'): list plans, oldest→newest.
    - `done` (needs `plan_id`, optional `result_session_id`): mark a plan complete.
    - `verify` (needs `plan_id`, optional `activity_id`): grade a recent session's
      real shot metrics against the plan's `target_specs`; returns per-target
      session-mean vs target, `all_met`, and a recommendation.
    """
    from . import training_store

    if action == "save":
        if not isinstance(plan, dict) or not plan:
            raise ValueError("training_plan(action='save') needs a non-empty `plan` object.")
        return training_store.save_plan(plan)

    if action == "next":
        nxt = training_store.next_pending()
        if not nxt:
            return {"has_plan": False,
                    "message": "No pending training plan. Ask the coach for one."}
        pending = training_store.list_plans(status="pending")
        return {"has_plan": True, "plan": nxt, "pending_count": len(pending)}

    if action == "list":
        plans = training_store.list_plans(status=status)
        return {"count": len(plans), "plans": plans}

    if action == "done":
        if not plan_id:
            raise ValueError("training_plan(action='done') needs a `plan_id`.")
        updated = training_store.mark_done(plan_id, result_session_id=result_session_id)
        return updated or {"error": f"no training plan with id {plan_id}"}

    # verify
    if not plan_id:
        raise ValueError("training_plan(action='verify') needs a `plan_id`.")
    return await _training_verify(plan_id, activity_id)


# --------------------------------------------------------------------------- #
# Visualization
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=_RO_LOCAL)
async def build_visualization(data: dict[str, Any]) -> dict[str, Any]:
    """Render a coaching diagnosis into a self-contained animated HTML page.

    Returns `{html}` — one standalone document (inline canvas/JS, no network, no
    external resources) ready to drop straight into a Claude **HTML artifact**.

    `data` shape (all optional; the viz adapts): {title, subtitle, diagnosis,
    handedness "RH"|"LH", shots:[{launchDirection,launchAngle,carry,total,
    totalSide,curve,maxHeight,landingAngle,hangTime}],
    swing:{clubPath,faceAngle,faceToPath}, targets:[{label,value,target,low,
    high,met}], blocks:[{name,detail,goal,where "range"|"home",
    links:[{label,url}]}]}. Renders the measured flight (side view + top-down,
    animated) and drills grouped range/home. See the trackman-visualizer prompt.
    """
    from .visualize import build_html

    html = build_html(data)
    return {"html": html, "bytes": len(html.encode()),
            "render_as": "text/html artifact"}


@mcp.tool(annotations=_RO_LOCAL)
async def setup() -> dict[str, Any]:
    """One-call onboarding for the Trackman golf coach.

    Returns everything needed to set the coach up in your client:
    - `system_prompt`: paste into a Claude/ChatGPT **Project's** custom
      instructions so every chat in it is the coach (with this MCP connected);
    - `skills`: upload-ready `SKILL.md` files (Settings → Capabilities → Skills)
      for always-on auto-activation;
    - `instructions`: per-client steps (Claude Projects, Desktop Skills, ChatGPT,
      Claude Code).

    An MCP server can't create the Project or enable Skills itself — this hands
    you the content + steps. In Claude Code, the assistant can write the files
    for you directly from this kit. (Pairs with the `setup` prompt.)
    """
    from .onboarding import build_setup_kit

    return build_setup_kit()


# --------------------------------------------------------------------------- #
# GameBook rounds (on-course data ingested from screenshots)
# --------------------------------------------------------------------------- #


def _gamebook_save(record: dict[str, Any]) -> dict[str, Any]:
    from . import gamebook_analysis as ga
    from . import gamebook_store

    record = dict(record)
    problems = ga.self_check(record)
    if problems:
        return {"saved": False, "problems": problems,
                "message": "Read failed self-check — re-check these holes before saving."}

    record["scoring"] = ga.scoring_from_holes(record.get("holes") or [])
    record.setdefault("source", "golf-gamebook")

    # Derive id from date, suffixing on same-day collisions with a different round.
    base = record.get("id") or record.get("date") or "round"
    rid, n = base, 1
    while True:
        existing = gamebook_store.get_round(rid)
        same_round = existing is not None and \
            existing.get("result", {}).get("gross") == record.get("result", {}).get("gross")
        if existing is None or same_round:
            break
        n += 1
        rid = f"{base}-{n}"
    record["id"] = rid

    saved = gamebook_store.save_round(record)
    return {"saved": True, "round": saved,
            "stored_count": len(gamebook_store.list_rounds())}


def _gamebook_list() -> dict[str, Any]:
    from . import gamebook_store

    rounds = gamebook_store.list_rounds()
    items = [
        {"id": r.get("id"), "date": r.get("date"),
         "course_par": (r.get("course") or {}).get("par"),
         "gross": (r.get("result") or {}).get("gross"),
         "net": (r.get("result") or {}).get("net"),
         "to_par": (r.get("scoring") or {}).get("to_par"),
         "coverage": r.get("coverage")}
        for r in rounds
    ]
    return {"count": len(items),
            "latest_id": items[0]["id"] if items else None, "items": items}


def _gamebook_compare(round_id: str | None) -> dict[str, Any]:
    from . import gamebook_analysis as ga
    from . import gamebook_store

    latest = gamebook_store.get_round(round_id) if round_id else gamebook_store.latest_round()
    if latest is None:
        return {"error": "no stored rounds to compare"}
    priors = gamebook_store.priors_of(latest["id"])
    if not priors:
        return {"round_id": latest["id"], "n_priors": 0,
                "message": "First stored round — nothing earlier to compare against yet."}
    return ga.compare_rounds(latest, priors)


@mcp.tool(annotations=_WRITE_LOCAL)
async def gamebook_round(
    action: Literal["save", "list", "get", "compare"],
    round: dict[str, Any] | None = None,
    round_id: str | None = None,
) -> dict[str, Any]:
    """On-course rounds ingested from Golf GameBook screenshots (local, last 5).

    The `gamebook-screenshot-analysis` skill extracts a round from screenshots
    and saves it here. Only score-per-hole is trusted; every other dimension
    carries a `coverage` flag (`full`|`partial`|`none`) and analysis respects it.

    Actions:
    - `save` (needs `round`): a coverage-aware record — {date, course:{par,cr,slope},
      result:{gross,net,to_par,position}, holes:[{hole,par,score,putts?,fairway?,
      gir?,bunkers?,chips?,penalties?}], coverage:{...}, dimensions:{...}}. Runs a
      self-check (hole sums vs gross/par); refuses inconsistent reads. Computes the
      `scoring` block, stores it (last 5), returns the stored record.
    - `list`: index of stored rounds (id, date, gross, net, to_par, coverage), newest first.
    - `get` (needs `round_id`): one full stored round.
    - `compare` (optional `round_id`, default latest): deterministic deltas vs the
      rounds before it — scoring always, other dimensions only where both tracked
      them. Returns measurement; the coach narrates progress from it.
    """
    from . import gamebook_store

    if action == "save":
        if not isinstance(round, dict) or not round:
            raise ValueError("gamebook_round(action='save') needs a non-empty `round`.")
        return _gamebook_save(round)
    if action == "list":
        return _gamebook_list()
    if action == "get":
        if not round_id:
            raise ValueError("gamebook_round(action='get') needs a `round_id`.")
        return gamebook_store.get_round(round_id) or {"error": f"no round {round_id}"}
    return _gamebook_compare(round_id)


# --------------------------------------------------------------------------- #
# Skill prompts
# --------------------------------------------------------------------------- #

from .prompts import register_skill_prompts  # noqa: E402

register_skill_prompts(mcp)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


async def _login_cmd(headless: bool) -> int:
    """Run the browser login, cache the token, and confirm identity."""
    import sys

    from .login import TrackmanLoginError, capture_token

    mode = "headless" if headless else "a browser window"
    print(f"Opening Trackman login ({mode})… sign in if prompted.", file=sys.stderr)
    try:
        await capture_token(headless=headless)
    except TrackmanLoginError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1

    config = Config.from_env()
    async with TrackmanClient(config) as client:
        info = await client.whoami()
    print(f"✓ Logged in as {info.get('name') or info.get('sub')}. "
          "Token cached — the MCP will use it automatically.", file=sys.stderr)
    return 0


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
