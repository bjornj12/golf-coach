"""CLI wrapper around golf_coach.visualize (kept for `uv run python scripts/visualize.py`).

    uv run python scripts/visualize.py <data.json> <out.html>
    uv run python scripts/visualize.py --demo out.html
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from golf_coach.visualize import build_html, main  # noqa: E402,F401

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
