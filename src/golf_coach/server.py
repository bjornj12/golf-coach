"""Trackman Golf MCP server (FastMCP).

Exposes the user's Trackman golf data as MCP tools, and serves the coaching
skills as MCP prompts. The server ONLY fetches/returns raw data and runs the
deterministic analytics — coaching *judgment* lives in the skills (now delivered
as prompts). See CLAUDE.md.

Run:  golf-coach           (stdio transport)
Auth: run `golf-coach login` (browser) or set TRACKMAN_TOKEN. See README.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastmcp import FastMCP

from . import queries
from .client import TrackmanAuthError, TrackmanClient
from .config import Config

mcp = FastMCP(
    name="golf-coach",
    instructions=(
        "Fetches the signed-in user's Trackman Golf statistics: profile and "
        "handicap, practice/course sessions, scorecards, shot-level launch "
        "metrics, and club gapping. Returns raw data only — interpret it with "
        "the coaching prompts this server provides. Call `auth` (action='status') "
        "first. If it reports the user isn't signed in or the session expired, "
        "call `auth` (action='login') — it opens a browser window for a one-time "
        "sign-in and returns immediately with `pending: true`; the window stays "
        "open until the user finishes. After they say they're done, call `auth` "
        "(action='status') to confirm, then retry. Never ask the user to paste a "
        "token or run terminal commands unless they ask how."
    ),
)

# Tool annotation presets (readOnly, idempotent, openWorld).
_RO_API = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": True}
_RO_LOCAL = {"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False}
_WRITE_API = {"readOnlyHint": False, "idempotentHint": False, "openWorldHint": True}
_WRITE_LOCAL = {"readOnlyHint": False, "idempotentHint": False, "openWorldHint": False}

# Seconds to wait for a silent refresh before giving up (dead session fails fast).
SILENT_REFRESH_TIMEOUT = 30.0

# The in-flight interactive browser login, if any. An interactive sign-in takes
# minutes (the human has to type credentials + Apple/Google 2FA), far longer than
# an MCP client's per-request timeout. If we awaited it inside the `auth` tool
# call, the client would cancel the request and the cancellation would tear the
# sign-in window down (see login.py's `finally: context.close()`). So we run it as
# a detached background task on the server's own event loop — it outlives the tool
# call. A module-level reference keeps it from being garbage-collected mid-flight.
_LOGIN_TASK: asyncio.Task[None] | None = None


def _login_in_progress() -> bool:
    """True while a background interactive login is still running."""
    return _LOGIN_TASK is not None and not _LOGIN_TASK.done()


def _has_saved_browser_session() -> bool:
    """True if a persisted browser profile from a prior login exists.

    Lets a first-time user skip the silent-refresh attempt so the sign-in window
    opens immediately instead of after `SILENT_REFRESH_TIMEOUT`. Constructs the
    path directly — `token_store.browser_profile_dir()` would *create* it.
    """
    try:
        from . import token_store

        profile = token_store.cache_dir() / "browser-profile"
        return profile.is_dir() and any(profile.iterdir())
    except Exception:
        return False


async def _background_login() -> None:
    """Capture a token off the tool-call clock: silent refresh, else a window.

    Runs detached from the `auth` request so the client's request timeout can't
    cancel it (and thus can't close the browser). Progress and errors go to
    stderr via login.py; the captured token lands in the local token store, which
    `auth(action='status')` then reads. Never raises — a failed sign-in just
    leaves no token, and status will report "not signed in".
    """
    from .login import capture_token

    # Returning user: refresh silently while the saved session is valid. Skip for
    # a first-time user (no saved profile) so the window isn't delayed for nothing.
    if _has_saved_browser_session():
        try:
            await capture_token(headless=True, timeout_seconds=SILENT_REFRESH_TIMEOUT)
            return
        except Exception:
            pass  # session expired — fall through to an interactive sign-in.
    try:
        # First run / expired session: open a window for an interactive login.
        await capture_token(headless=False)
    except Exception:
        pass  # already reported to stderr; status will show "not signed in".


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
    global _LOGIN_TASK
    from .login import capture_token

    # 1) Already signed in? Confirm instantly, no browser. (Fast, no long await.)
    config = Config.from_env()
    if config.has_token:
        try:
            async with TrackmanClient(config) as client:
                info = await client.whoami()
            return {
                "success": True,
                "name": info.get("name") or info.get("sub"),
                "message": "Already signed in. The MCP will use this automatically.",
            }
        except TrackmanAuthError:
            pass  # token expired — fall through to (re)authenticate.

    # 2) A sign-in window is already open — don't spawn a second one.
    if _login_in_progress():
        return {
            "success": None,
            "pending": True,
            "message": "A Trackman sign-in is already in progress. Finish signing "
                       "in the browser window that's open, then ask me to check "
                       "auth(action='status').",
        }

    # 3) Non-interactive caller: try a silent refresh only (no window).
    if not open_browser:
        try:
            await capture_token(headless=True, timeout_seconds=SILENT_REFRESH_TIMEOUT)
        except Exception:
            return {
                "success": False,
                "message": "Saved session expired and open_browser is false. "
                           "Call auth(action='login', open_browser=true), or run "
                           "`golf-coach login` in a terminal.",
            }
        return {"success": True,
                "message": "Refreshed the saved session. The MCP will use it."}

    # 4) Interactive sign-in: run it in a detached background task so the client's
    # request timeout can't cancel the request and close the browser. Return now;
    # the user signs in at their own pace and we confirm via auth(action='status').
    _LOGIN_TASK = asyncio.create_task(_background_login())
    return {
        "success": None,
        "pending": True,
        "message": "Opening a browser window to sign in to Trackman. Sign in there "
                   "(e.g. with Apple) — the window stays open for a few minutes and "
                   "won't close on its own. When you're done, tell me and I'll "
                   "confirm with auth(action='status').",
    }


@mcp.tool(annotations=_WRITE_API)
async def auth(
    action: Literal["status", "login"] = "status",
    open_browser: bool = True,
    source: str = "trackman",
) -> dict[str, Any]:
    """Check or (re)establish your Trackman sign-in.

    Actions:
    - `status` (default): report whether the current token works and who you're
      signed in as. Use this first; it never opens anything.
    - `login`: (re)authenticate. If already signed in, confirms instantly. If the
      saved session expired and `open_browser` is true, it opens a sign-in window
      and returns immediately with `pending: true` — the window stays open for a
      few minutes and the user signs in at their own pace (the browser is driven
      by a background task, so it won't close on its own). After the user says
      they've finished, call `auth(action='status')` to confirm. Do NOT re-call
      `login` while one is pending — it won't open a second window.

    `source` selects the data source to authenticate; only `trackman` needs auth
    (other sources, e.g. GameBook, are local). Never echoes the token.
    """
    if source != "trackman":
        return {"error": "auth is only needed for the 'trackman' source"}
    if action == "login":
        return await _auth_login(open_browser)
    return await _auth_status()


# --------------------------------------------------------------------------- #
# Trackman data reads (one `trackman(action, …)` tool over per-action helpers)
# --------------------------------------------------------------------------- #
#
# Each helper below carries the exact fetch/return behavior of a former discrete
# tool (profile, handicap, …, one per `trackman` action). They are plain async
# functions — no `@mcp.tool` — dispatched from the single `trackman` tool.
# Return shapes are unchanged from the discrete tools they replace.


async def _tm_profile() -> dict[str, Any]:
    """Player profile + current handicap (identity, `hcp.currentHcp`, record)."""
    data = await _run(queries.PROFILE)
    return data.get("me", {})


async def _tm_handicap(
    skip: int = 0, take: int = 20, only_in_avg: bool = False
) -> dict[str, Any]:
    """Handicap history: per-round differentials and how the index moved."""
    data = await _run(
        queries.HANDICAP_HISTORY,
        {"skip": skip, "take": take, "onlyInAvg": only_in_avg},
    )
    return data.get("me", {}).get("hcp", {})


async def _tm_sessions(
    skip: int = 0,
    take: int = 25,
    kinds: list[str] | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Activities (practice + course), totalCount + a page of item summaries."""
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


async def _tm_session(activity_id: str) -> dict[str, Any]:
    """One activity in full by id — shot-level launch metrics / scorecard."""
    data = await _run(queries.GET_SESSION, {"id": activity_id})
    node = data.get("node")
    if not node:
        raise ValueError(f"No activity found for id {activity_id!r}.")
    return node


async def _tm_rounds(
    skip: int = 0, take: int = 20, completed: bool | None = True
) -> dict[str, Any]:
    """Course rounds (scorecards): per-hole scores + round `stat` aggregates."""
    data = await _run(
        queries.COURSE_ROUNDS, {"skip": skip, "take": take, "completed": completed}
    )
    return {"scorecards": data.get("me", {}).get("scorecards", [])}


async def _tm_clubs(include_retired: bool = False) -> dict[str, Any]:
    """Per-club gapping and dispersion ("My Bag" / Find My Distance)."""
    data = await _run(queries.CLUB_STATS, {"includeRetired": include_retired})
    return data.get("me", {}).get("equipment", {})


async def _tm_summary(
    time_from: str | None = None,
    time_to: str | None = None,
    skip: int = 0,
    take: int = 50,
) -> dict[str, Any]:
    """Activity counts grouped by kind over an optional time window."""
    data = await _run(
        queries.ACTIVITY_SUMMARY,
        {"timeFrom": time_from, "timeTo": time_to, "skip": skip, "take": take},
    )
    return data.get("me", {}).get("activitySummary", {})


@mcp.tool(annotations=_RO_API)
async def trackman(
    action: Literal[
        "profile", "handicap", "sessions", "session", "rounds", "clubs", "summary"
    ],
    activity_id: str | None = None,
    skip: int = 0,
    take: int | None = None,
    only_in_avg: bool = False,
    kinds: list[str] | None = None,
    time_from: str | None = None,
    time_to: str | None = None,
    include_hidden: bool = False,
    include_retired: bool = False,
    completed: bool | None = True,
) -> dict[str, Any]:
    """Trackman data reads (controlled/flat-lie launch-monitor data). Raw only.

    Actions:
    - `profile`: identity + current handicap (`hcp.currentHcp`, latest record).
    - `handicap` (paging `skip`/`take` default 20, `only_in_avg`): handicap
      history — per-round differentials and how the index moved.
    - `sessions` (`skip`/`take` default 25, `kinds`, `time_from`/`time_to`,
      `include_hidden`): list activities (practice sessions and course rounds) —
      totalCount + a page of item summaries. Use `session` with an item's id for
      full detail.
    - `session` (needs `activity_id`): one activity in full, with shot-level launch
      metrics (RANGE_PRACTICE strokes) or the scorecard (COURSE_PLAY).
    - `rounds` (`skip`/`take` default 20, `completed`): course rounds (scorecards) —
      per-hole scores and round `stat` aggregates. `completed=None` returns all
      rounds regardless of completion state.
    - `clubs` (`include_retired`): per-club gapping and dispersion ("My Bag" /
      Find My Distance) — the source for gapping analysis.
    - `summary` (`time_from`/`time_to`, `skip`/`take` default 50): activity counts
      grouped by kind over an optional time window.

    `take` defaults to each action's own historical default (20 for `handicap`
    and `rounds`, 25 for `sessions`, 50 for `summary`) when omitted; pass it
    explicitly to override.
    """
    if action == "profile":
        return await _tm_profile()
    if action == "handicap":
        return await _tm_handicap(
            skip=skip, take=take if take is not None else 20, only_in_avg=only_in_avg
        )
    if action == "sessions":
        return await _tm_sessions(
            skip=skip, take=take if take is not None else 25, kinds=kinds,
            time_from=time_from, time_to=time_to, include_hidden=include_hidden,
        )
    if action == "session":
        if not activity_id:
            raise ValueError("trackman(action='session') needs an activity_id.")
        return await _tm_session(activity_id)
    if action == "rounds":
        return await _tm_rounds(
            skip=skip, take=take if take is not None else 20, completed=completed
        )
    if action == "clubs":
        return await _tm_clubs(include_retired=include_retired)
    return await _tm_summary(
        time_from=time_from, time_to=time_to, skip=skip,
        take=take if take is not None else 50,
    )


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
# Cross-source synthesis (aligns each source's findings; no verdict)
# --------------------------------------------------------------------------- #


@mcp.tool(annotations=_RO_LOCAL)
async def synthesize() -> dict[str, Any]:
    """Cross-source, context-aware view: runs each source's expert analyzer and aligns their findings by skill area (no verdicts — the coach interprets)."""
    from .synthesis import synthesize as _synth

    view = await _synth()
    return view.model_dump()


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
async def gamebook(
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
            raise ValueError("gamebook(action='save') needs a non-empty `round`.")
        return _gamebook_save(round)
    if action == "list":
        return _gamebook_list()
    if action == "get":
        if not round_id:
            raise ValueError("gamebook(action='get') needs a `round_id`.")
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
        golf-coach                 run the MCP server (stdio)
        golf-coach login           open a browser to sign in and cache a token
        golf-coach login --headless  silently refresh using the saved session
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="golf-coach")
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
