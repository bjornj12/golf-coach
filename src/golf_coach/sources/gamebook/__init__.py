"""The GameBook data source: stored rounds -> the normalized golf-coach model.

Importing this package registers a module-level `GameBookSource()` instance
into the shared source registry (see `..registry`).
"""

from __future__ import annotations

from .source import GameBookSource

__all__ = ["GameBookSource"]
