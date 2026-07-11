"""End-to-end integration test for the REAL source registry + `synthesize()`.

Unlike `test_synthesis.py` (which registers hand-built fakes), this exercises
the production wiring: importing the sources package registers the built-in
Trackman + GameBook sources (C1), and `synthesize()` runs their real adapters
and analyzers. GameBook data is seeded on disk under an isolated cache dir.

Trackman has no token here, so its fetch fails auth: after the source's own
silent-refresh retry fails (no saved browser session), the `TrackmanAuthError`
surfaces LOUDLY rather than degrading to an empty, successful-looking view — an
expired/absent token must not read as "you have no data". A genuinely-partial
(non-auth) source failure still degrades gracefully to a `context_note`.
"""

from __future__ import annotations

import importlib

import pytest

import golf_coach.sources  # noqa: F401  — import-time registration of built-ins
from golf_coach import gamebook_store
from golf_coach.client import TrackmanAuthError
from golf_coach.model import CrossSourceView
from golf_coach.sources import registry
from golf_coach.sources.gamebook import source as gamebook_source_mod
from golf_coach.sources.trackman import source as trackman_source_mod
from golf_coach.synthesis import synthesize


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Isolate the on-disk cache and guarantee no Trackman token is available."""
    monkeypatch.setenv("GOLF_COACH_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("TRACKMAN_TOKEN", raising=False)


@pytest.fixture
def registered_sources():
    """Re-run the import-time `registry.register(...)` side effect, resilient to
    other test modules having cleared the shared global registry. Reloading the
    leaf source modules exercises the exact registration code C1 relies on."""
    registry.clear()
    importlib.reload(trackman_source_mod)  # runs registry.register(TrackmanSource())
    importlib.reload(gamebook_source_mod)  # runs registry.register(GameBookSource())
    yield
    registry.clear()


def _gamebook_record() -> dict:
    return {
        "id": "round-2026-07-01",
        "date": "2026-07-01",
        "course": {"par": 72, "name": "Test Links"},
        "result": {"gross": 85, "net": 85, "to_par": 13},
        "holes": [],
        "scoring": {
            "to_par": 13,
            "distribution": {"par": 5, "bogey": 11, "double": 2},
            "by_par_type": {"par3": 1.0, "par4": 0.7, "par5": 0.5},
        },
        "dimensions": {"putts": {"value": 32, "coverage": "full"}},
        "coverage": {"scoring": "full", "putts": "full"},
        "notes": [],
    }


@pytest.fixture
def gamebook_only():
    """Register ONLY the GameBook source (no Trackman) so the GameBook pipeline
    can be exercised without a Trackman auth failure taking the view down."""
    registry.clear()
    importlib.reload(gamebook_source_mod)  # runs registry.register(GameBookSource())
    yield
    registry.clear()


def test_sources_register_on_import(registered_sources):
    names = {s.name for s in registry.available_sources()}
    assert "trackman" in names
    assert "gamebook" in names


async def test_synthesize_raises_loudly_when_trackman_token_absent(registered_sources):
    """With Trackman registered but no token, its silent-refresh retry fails (no
    saved browser session) and the auth error surfaces LOUDLY — it must NOT be
    swallowed into an empty, successful-looking view."""
    gamebook_store.save_round(_gamebook_record())

    with pytest.raises(TrackmanAuthError) as excinfo:
        await synthesize()

    # The loud error tells the caller exactly how to recover.
    assert "auth(action='login')" in str(excinfo.value)


async def test_synthesize_gamebook_only_produces_scoring(gamebook_only):
    """With only GameBook registered (no Trackman), the GameBook pipeline runs
    end-to-end and produces a real scoring finding — no auth involved."""
    gamebook_store.save_round(_gamebook_record())

    view = await synthesize()

    assert isinstance(view, CrossSourceView)
    scoring = view.by_skill_area.get("scoring") or []
    assert any(
        f.source == "gamebook" and f.metric == "to_par" and f.value == 13.0
        for f in scoring
    ), "expected a gamebook scoring finding"
