"""Tests for the self-contained HTML visualizer.

Covers the injection-safety contract (no HTML/JS breakout from data fields) and
the self-contained guarantee (no external network resources), neither of which
needs a browser to verify.
"""

from __future__ import annotations

import re

import pytest

from trackman_mcp.visualize import build_html


def test_build_html_is_self_contained_and_nonempty():
    html = build_html({"title": "Coach", "shots": [{"carry": 200}]})
    assert html.lstrip().lower().startswith("<!doctype html>")
    # Exactly one script block (the inline app), no external src/href to the net.
    assert re.search(r'<script[^>]+src=', html) is None
    assert re.search(r'<link[^>]+href=', html) is None
    assert "http://" not in html and "https://" not in html


def test_title_subtitle_diagnosis_are_html_escaped():
    html = build_html({
        "title": "<img src=x onerror=alert(1)>",
        "subtitle": "<b>sub</b>",
        "diagnosis": "1 < 2 & 3 > 0",
    })
    # The raw markup must not appear; escaped entities must.
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<b>sub</b>" not in html
    assert "&amp;" in html  # the "&" in the diagnosis got escaped


def test_data_cannot_break_out_of_the_script_block():
    # A data field containing </script> must not close the inline script.
    html = build_html({
        "title": "ok",
        "blocks": [{"name": "</script><script>alert(1)</script>", "detail": "x"}],
    })
    # Only the template's own closing </script> tag may remain.
    assert html.count("</script>") == 1
    # And no attacker-supplied opening <script> survived.
    assert "<script>alert(1)" not in html


def test_client_js_renders_data_without_unsafe_interpolation():
    html = build_html({"title": "ok"})
    # The block/target data must not be templated into innerHTML strings.
    assert "${b.name}" not in html
    assert "${b.link}" not in html
    assert "${t.label}" not in html
    # Links go through a scheme whitelist before being attached.
    assert "safeHref" in html


def test_swing_path_not_mirrored_for_right_handers():
    # Regression lock for the mirrored-swing-path bug: the in-to-out angle must
    # use (RH?a:-a) so a +path leans right for RH (matching the ball-flight
    # panel), not the old (RH?-a:a) which flipped it left-for-right.
    html = build_html({"title": "ok", "handedness": "RH"})
    assert "(RH?a:-a)" in html
    assert "(RH?-a:a)" not in html
    # And the dead handedness ternary on the launch control point is gone.
    assert "(RH?launchDx:launchDx)" not in html


def test_demo_data_renders():
    from trackman_mcp import visualize
    html = build_html(visualize._DEMO)
    assert "<canvas" in html


def test_unknown_where_is_a_loud_error():
    with pytest.raises(ValueError, match="where.*'gym'.*home, range"):
        build_html({"blocks": [{"name": "x", "where": "gym"}]})


def test_malformed_links_entry_is_a_loud_error():
    # a bare string instead of {label, url} must be rejected, not skipped
    with pytest.raises(ValueError, match=r"blocks\[0\]\.links\[0\]"):
        build_html({"blocks": [{"name": "x", "links": ["https://y"]}]})


def test_links_must_be_a_list():
    with pytest.raises(ValueError, match=r"blocks\[0\]\.links must be a list"):
        build_html({"blocks": [{"name": "x", "links": "https://y"}]})


def test_valid_blocks_with_links_and_legacy_link_pass():
    html = build_html({"blocks": [
        {"name": "a", "where": "home",
         "links": [{"label": "video", "url": "https://example.com/v"}]},
        {"name": "b", "link": "https://example.com/w"},   # legacy single link
    ]})
    assert html.lstrip().lower().startswith("<!doctype html>")
