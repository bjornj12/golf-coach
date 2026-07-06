"""Stage-2 cross-source normalizer: per-source `Finding`s -> one aligned view.

Each source (Trackman, GameBook, ...) has its own expert analyzer that turns
its already-normalized model objects into `Finding`s (see
`sources/*/analyzer.py`). This module is what comes after: it pulls those
Findings together, groups them by skill area, and — where two or more sources
have something to say about the same skill area — surfaces the delta between
them, tagged with the context (controlled-range vs. on-course) each side was
captured under.

This module renders **no verdict**. It does not decide who's "right", does
not recommend anything, and does not say a gap is good or bad — it only
aligns data and states the *conditions* each side's data was captured under
(a fact, not an opinion). Interpretation stays in the coaching skills (see
CLAUDE.md's core boundary).
"""

from __future__ import annotations

from typing import Any

from .model import CrossSourceView, Finding

_CONTEXT_MIX_NOTE = (
    "Trackman findings are clean-room (flat lie, no pressure); GameBook findings "
    "are on-course (variable lies, weather, pressure) — weigh them accordingly."
)


def align(findings: list[Finding]) -> CrossSourceView:
    """Group Findings by skill area and compute cross-source deltas/coverage.

    Deterministic: grouping preserves input order within each skill area, and
    "first finding per source" (used for deltas/coverage) is the first one
    encountered per source, in input order.
    """
    if not findings:
        return CrossSourceView()

    by_skill_area: dict[str, list[Finding]] = {}
    for finding in findings:
        by_skill_area.setdefault(finding.skill_area, []).append(finding)

    cross_source_deltas: list[dict[str, Any]] = []
    coverage_summary: dict[str, Any] = {}

    for area, area_findings in by_skill_area.items():
        first_by_source: dict[str, Finding] = {}
        for finding in area_findings:
            first_by_source.setdefault(finding.source, finding)

        coverage_summary[area] = {
            source: finding.coverage for source, finding in first_by_source.items()
        }

        if len(first_by_source) < 2:
            continue

        delta: dict[str, Any] = {
            "skill_area": area,
            "sources": {
                source: {
                    "metric": finding.metric,
                    "value": finding.value,
                    "coverage": finding.coverage,
                    "setting": finding.context.setting,
                }
                for source, finding in first_by_source.items()
            },
        }
        settings = {finding.context.setting for finding in first_by_source.values()}
        if "controlled" in settings and "on_course" in settings:
            delta["context_note"] = (
                f"{area}: Trackman is controlled/flat-lie; GameBook is on-course — "
                "a gap here points at lies/pressure/course-management, not pure mechanics."
            )
        cross_source_deltas.append(delta)

    context_notes: list[str] = []
    all_settings = {finding.context.setting for finding in findings}
    if "controlled" in all_settings and "on_course" in all_settings:
        context_notes.append(_CONTEXT_MIX_NOTE)

    return CrossSourceView(
        by_skill_area=by_skill_area,
        cross_source_deltas=cross_source_deltas,
        context_notes=context_notes,
        coverage_summary=coverage_summary,
    )


async def synthesize() -> CrossSourceView:
    """Run each registered source's expert analyzer over its data, then align.

    Importing this module's `.sources` registry runs `sources/__init__`, which
    registers the built-in sources — so `synthesize()` sees real data, not an
    empty registry. Skips a source that isn't registered, and when a source's
    fetch raises (e.g. GameBook has no rounds saved yet, or Trackman's token
    expired) it records an observable `context_notes` entry instead of
    crashing the whole synthesis — one unavailable source never takes the view
    down. The note names only the exception type, never any secret. Analyzers
    are imported lazily here to avoid import cycles with the sources package.
    """
    from .sources import registry

    findings: list[Finding] = []
    failure_notes: list[str] = []

    gamebook_source = registry.get_source("gamebook")
    if gamebook_source is not None:
        try:
            from .sources.gamebook import analyzer as gamebook_analyzer

            rounds = await gamebook_source.rounds()
            findings.extend(gamebook_analyzer.analyze(rounds))
        except Exception as exc:  # one source failing must not sink the view
            failure_notes.append(f"gamebook source unavailable: {type(exc).__name__}")

    trackman_source = registry.get_source("trackman")
    if trackman_source is not None:
        try:
            from .sources.trackman import analyzer as trackman_analyzer

            sessions = await trackman_source.sessions()
            gapping = await trackman_source.club_gapping()
            findings.extend(trackman_analyzer.analyze(sessions, club_gapping=gapping))
        except Exception as exc:
            failure_notes.append(f"trackman source unavailable: {type(exc).__name__}")

    view = align(findings)
    if failure_notes:
        view.context_notes = [*view.context_notes, *failure_notes]
    return view
