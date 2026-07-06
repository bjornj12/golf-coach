"""Tests for the self-contained HTML visualizer.

Covers the injection-safety contract (no HTML/JS breakout from data fields) and
the self-contained guarantee (no external network resources), neither of which
needs a browser to verify.
"""

from __future__ import annotations

import re

import pytest

from golf_coach.visualize import build_html


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
    from golf_coach import visualize
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


def test_fixit_section_replaces_flat_plan_list():
    html = build_html({"title": "ok"})
    assert 'id="fixit"' in html
    assert 'id="plan"' not in html          # the old flat list is gone
    assert "renderBlocks" in html
    # groups render only when they have items (no empty headers)
    assert "if(!items.length) return" in html


def test_hostile_link_label_and_url_cannot_break_out():
    html = build_html({
        "title": "ok",
        "blocks": [{"name": "Drill", "where": "home",
                    "links": [{"label": "</script><script>alert(1)</script>",
                               "url": "javascript:alert(1)"}]}],
    })
    # embedded JSON stays breakout-safe; only the template's own script closes
    assert html.count("</script>") == 1
    assert "<script>alert(1)" not in html


def test_side_view_hero_present_with_honest_guards():
    html = build_html({"shots": [{"carry": 200, "launchAngle": 12,
                                  "maxHeight": 25, "landingAngle": 35,
                                  "hangTime": 5.5}]})
    assert 'id="side"' in html and 'id="sideCard"' in html
    # reconstruction exists and estimates geometry only when unmeasured
    assert "sideCurve" in html and "apexMeasured" in html
    # the apex label renders only behind the measured guard
    assert "repSide.apexMeasured" in html
    # panel hides itself when no shot has usable height data
    assert "card.style.display='none'" in html
    # the embedded page JSON carries the shots with vertical fields intact
    assert '"maxHeight": 25' in html and '"hangTime": 5.5' in html


def test_animation_duration_scales_with_hangtime():
    html = build_html({"title": "ok"})
    # duration = 600ms x clamped hang seconds; default 4 when unmeasured
    assert "600*Math.min(7,Math.max(2.5" in html
    # one clock drives all panels in sync
    assert "drawSide(clockT);drawFlight(clockT);drawSwing(clockT)" in html


def test_topdown_draws_every_shot_as_its_own_tracer():
    html = build_html({"shots": [{"carry": 150, "launchDirection": -2,
                                  "totalSide": 10},
                                 {"carry": 160, "launchDirection": 1,
                                  "totalSide": -5}]})
    assert "shotCurve" in html
    # per-shot faint tracer color distinct from the bright animated mean
    assert "rgba(78,161,255,.22)" in html
    # tracers go through the handedness-aware sx() mapping (regression guard)
    assert "(RH? v: -v)" in html
