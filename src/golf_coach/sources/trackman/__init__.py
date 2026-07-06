"""The Trackman data source: GraphQL -> the normalized golf-coach model.

Importing this package registers a module-level `TrackmanSource()` instance
into the shared source registry (see `..registry`).
"""

from __future__ import annotations

from .source import TrackmanSource

__all__ = ["TrackmanSource"]
