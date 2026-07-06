"""In-process registry that data sources register into at import time."""

from __future__ import annotations

from .base import Source

_SOURCES: dict[str, Source] = {}


def register(source: Source) -> None:
    """Register a source instance under its .name (idempotent — last wins)."""
    _SOURCES[source.name] = source


def get_source(name: str) -> Source | None:
    return _SOURCES.get(name)


def available_sources() -> list[Source]:
    """All registered sources, sorted by name for determinism."""
    return [_SOURCES[k] for k in sorted(_SOURCES)]


def clear() -> None:
    """Test helper: empty the registry."""
    _SOURCES.clear()
