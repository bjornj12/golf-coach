"""Tests for training-target verification (deterministic)."""

from __future__ import annotations

from golf_coach import analysis


def _strokes(club: str, **metric_series):
    """Build strokes for one club; each kwarg is a list of metric values."""
    n = max(len(v) for v in metric_series.values())
    out = []
    for i in range(n):
        m = {k: v[i] for k, v in metric_series.items() if i < len(v)}
        out.append({"club": club, "measurement": m})
    return out


def test_evaluate_target_ops():
    assert analysis.evaluate_target(2.0, {"op": "<", "value": 3})["met"] is True
    assert analysis.evaluate_target(4.0, {"op": "<", "value": 3})["met"] is False
    assert analysis.evaluate_target(1.0, {"op": "between", "low": -1, "high": 2})["met"] is True
    assert analysis.evaluate_target(5.0, {"op": "between", "low": -1, "high": 2})["met"] is False
    assert analysis.evaluate_target(-2.5, {"op": "abs<", "value": 3})["met"] is True
    assert analysis.evaluate_target(-8.5, {"op": "abs<", "value": 3})["met"] is False


def test_evaluate_target_no_data():
    assert analysis.evaluate_target(None, {"op": "<", "value": 3})["met"] is None


def test_verify_targets_all_met():
    strokes = _strokes("DRIVER",
                       clubPath=[0.0, 1.0, 2.0],     # mean 1.0 -> in [-1,2]
                       spinAxis=[1.0, -1.0, 2.0])    # mean 0.67 -> |x|<3
    specs = [
        {"metric": "clubPath", "club": "DRIVER", "op": "between", "low": -1, "high": 2},
        {"metric": "spinAxis", "club": "DRIVER", "op": "abs<", "value": 3},
    ]
    out = analysis.verify_targets(strokes, specs)
    assert out["has_data"] is True
    assert out["all_met"] is True
    assert all(r["met"] for r in out["results"])


def test_verify_targets_not_met_reports_value():
    strokes = _strokes("DRIVER", clubPath=[-6.0, -4.0])  # mean -5.0, not in [-1,2]
    specs = [{"metric": "clubPath", "club": "DRIVER", "op": "between",
              "low": -1, "high": 2, "label": "club path"}]
    out = analysis.verify_targets(strokes, specs)
    r = out["results"][0]
    assert r["met"] is False
    assert r["value"] == -5.0
    assert r["n"] == 2
    assert out["all_met"] is False


def test_verify_targets_filters_by_club():
    strokes = _strokes("DRIVER", spinAxis=[8.0]) + _strokes("IRON7", spinAxis=[0.0])
    specs = [{"metric": "spinAxis", "club": "DRIVER", "op": "abs<", "value": 3}]
    out = analysis.verify_targets(strokes, specs)
    assert out["results"][0]["value"] == 8.0  # only the driver shot counted
    assert out["results"][0]["met"] is False


def test_verify_targets_no_data_for_club():
    strokes = _strokes("IRON7", spinAxis=[0.0])
    specs = [{"metric": "spinAxis", "club": "DRIVER", "op": "abs<", "value": 3}]
    out = analysis.verify_targets(strokes, specs)
    assert out["has_data"] is False
    assert out["results"][0]["value"] is None
    assert out["results"][0]["met"] is None
