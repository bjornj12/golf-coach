"""Trackman Golf MCP — fetches a user's golf stats from Trackman's GraphQL API.

The server only fetches and returns raw data. All coaching/analysis lives in the
Claude skills under skills/. See CLAUDE.md and docs/trackman-api.md.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the installed distribution's version (pyproject).
    __version__ = version("golf-coach")
except PackageNotFoundError:  # pragma: no cover - source tree without an install
    __version__ = "0+unknown"
