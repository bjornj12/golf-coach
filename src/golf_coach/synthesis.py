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

import asyncio
from typing import Any

from .model import CrossSourceView, Finding

_GENERIC_SETTING_LABELS = {
    "controlled": "the controlled-setting source(s)",
    "on_course": "the on-course source(s)",
}


def _setting_label(findings: list[Finding], setting: str) -> str:
    """Human-readable label for the distinct sources that captured `findings`
    under `setting` (e.g. "controlled" or "on_course").

    Derived from the findings actually present rather than a hardcoded
    product name, so a future third source is described correctly too. Falls
    back to a generic phrase if (unexpectedly) no source matches.
    """
    names = sorted({f.source for f in findings if f.context.setting == setting})
    if not names:
        return _GENERIC_SETTING_LABELS.get(setting, f"the {setting} source(s)")
    return "/".join(name.capitalize() for name in names)


def _context_mix_note(findings: list[Finding]) -> str:
    controlled = _setting_label(findings, "controlled")
    on_course = _setting_label(findings, "on_course")
    return (
        f"{controlled} findings are clean-room (flat lie, no pressure); "
        f"{on_course} findings are on-course (variable lies, weather, pressure) — "
        "weigh them accordingly."
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
            delta_findings = list(first_by_source.values())
            controlled = _setting_label(delta_findings, "controlled")
            on_course = _setting_label(delta_findings, "on_course")
            delta["context_note"] = (
                f"{area}: {controlled} is controlled/flat-lie; {on_course} is on-course — "
                "a gap here points at lies/pressure/course-management, not pure mechanics."
            )
        cross_source_deltas.append(delta)

    context_notes: list[str] = []
    all_settings = {finding.context.setting for finding in findings}
    if "controlled" in all_settings and "on_course" in all_settings:
        context_notes.append(_context_mix_note(findings))

    return CrossSourceView(
        by_skill_area=by_skill_area,
        cross_source_deltas=cross_source_deltas,
        context_notes=context_notes,
        coverage_summary=coverage_summary,
    )


async def synthesize() -> CrossSourceView:
    """Run each registered source's own `analyze()` concurrently, then align.

    Importing this module's `.sources` registry runs `sources/__init__`, which
    registers the built-in sources — so `synthesize()` sees real data, not an
    empty registry. Polymorphic over whatever is registered: no source names
    are hardcoded here, so adding a new source is a one-module change (just
    implement `Source.analyze()`). When a source's `analyze()` raises (e.g.
    GameBook has no rounds saved yet, or Trackman's token expired) it records
    an observable `context_notes` entry instead of crashing the whole
    synthesis — one unavailable source never takes the view down. The note
    names only the exception type, never any secret.
    """
    from .sources import registry

    sources = registry.available_sources()
    failure_notes: list[str] = []

    async def _safe(source: Any) -> list[Finding]:
        try:
            return await source.analyze()
        except Exception as exc:  # one source failing must not sink the view
            failure_notes.append(f"{source.name} source unavailable: {type(exc).__name__}")
            return []

    results = await asyncio.gather(
        *(_safe(source) for source in sources), return_exceptions=False
    )
    findings: list[Finding] = [finding for result in results for finding in result]

    view = align(findings)
    if failure_notes:
        view.context_notes = [*view.context_notes, *failure_notes]
    return view
