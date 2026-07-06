"""__version__ must track the installed distribution (no hand-bumped constant)."""

from __future__ import annotations

from importlib.metadata import version

import golf_coach


def test_version_matches_distribution_metadata():
    assert golf_coach.__version__ == version("golf-coach")
