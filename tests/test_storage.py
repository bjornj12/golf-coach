"""Tests for the shared secure-storage helpers (atomic, 0600, corruption-safe)."""

from __future__ import annotations

import json
import os
import stat

from golf_coach import storage


def test_write_secure_works_without_fchmod(tmp_path, monkeypatch):
    # Windows has no os.fchmod — write_secure must not crash there.
    monkeypatch.delattr(os, "fchmod", raising=False)
    p = tmp_path / "win.json"
    storage.write_secure(p, "ok")
    assert p.read_text() == "ok"


def test_write_secure_sets_user_only_mode(tmp_path):
    p = tmp_path / "secret.json"
    storage.write_secure(p, '{"a": 1}')
    mode = stat.S_IMODE(p.stat().st_mode)
    assert mode == 0o600


def test_write_secure_overwrites_atomically(tmp_path):
    p = tmp_path / "secret.json"
    storage.write_secure(p, "first")
    storage.write_secure(p, "second")
    assert p.read_text() == "second"
    # No temp/leftover files beside the target.
    leftovers = [f.name for f in tmp_path.iterdir() if f.name != "secret.json"]
    assert leftovers == []


def test_read_json_missing_returns_default(tmp_path):
    p = tmp_path / "absent.json"
    assert storage.read_json(p, default=[]) == []
    sentinel = {"x": 1}
    assert storage.read_json(p, default=sentinel) == sentinel


def test_read_json_parses_valid(tmp_path):
    p = tmp_path / "data.json"
    p.write_text(json.dumps([1, 2, 3]))
    assert storage.read_json(p, default=[]) == [1, 2, 3]


def test_read_json_corrupt_is_backed_up_not_silently_lost(tmp_path):
    p = tmp_path / "data.json"
    p.write_text("{ this is not valid json ]")
    result = storage.read_json(p, default=[])
    assert result == []
    # The unparseable content is preserved for forensics, not silently wiped.
    backup = p.with_suffix(p.suffix + ".corrupt")
    assert backup.exists()
    assert backup.read_text() == "{ this is not valid json ]"


def test_secure_dir_is_user_only(tmp_path):
    d = tmp_path / "nested" / "cache"
    storage.secure_dir(d)
    assert d.is_dir()
    mode = stat.S_IMODE(d.stat().st_mode)
    assert mode == 0o700
