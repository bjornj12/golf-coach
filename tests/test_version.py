"""__version__ must track the installed distribution (no hand-bumped constant)."""

from __future__ import annotations

from importlib.metadata import version

import trackman_mcp


def test_version_matches_distribution_metadata():
    assert trackman_mcp.__version__ == version("trackman-mcp")
