"""Grade a live GameBook extraction against the 9-June golden fixture.

Vision extraction runs live (the gamebook-screenshot-analysis skill reads the
images in tests/fixtures/gamebook/2026-06-09/); this script measures that
extraction so the skill can be iterated objectively:

  1. Have the skill extract the fixture images to a JSON round record.
  2. python scripts/gamebook_eval.py path/to/extracted.json
  3. Read the score + mismatches, sharpen skills/gamebook-screenshot-analysis, repeat.

Exit code is nonzero when the score is below PASS_THRESHOLD.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from golf_coach import gamebook_analysis as ga

GOLDEN = Path(__file__).resolve().parent.parent / "tests/fixtures/gamebook/2026-06-09.json"
PASS_THRESHOLD = 95.0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: gamebook_eval.py <extracted-round.json>", file=sys.stderr)
        return 2
    extracted = json.loads(Path(argv[1]).read_text())
    golden = json.loads(GOLDEN.read_text())
    r = ga.grade_extraction(extracted, golden)
    print(f"score: {r['score']}/100  holes {r['holes_correct']}/{r['holes_total']}  "
          f"scoring_ok={r['scoring_ok']}  coverage_ok={r['coverage_ok']}")
    for m in r["mismatches"]:
        print(f"  - {m}")
    return 0 if r["score"] >= PASS_THRESHOLD else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
