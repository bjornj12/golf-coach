"""Shared secure local-storage helpers for the token + JSON caches.

Every file the MCP writes locally may contain sensitive material (the bearer
token, or personal golf data). These helpers make those writes:

- **user-only readable** (mode 0600), with the restrictive mode applied at
  creation time so there is no world-readable window;
- **atomic** (write to a temp file in the same directory, then `os.replace`),
  so an interrupted or concurrent write can never leave a truncated file; and
- **corruption-safe on read** — an unparseable file is backed up to a
  `.corrupt` sibling and reported to stderr rather than being silently treated
  as empty (which would wipe the user's history without a trace).

Directories are created mode 0700. No secrets are logged.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def secure_dir(path: Path) -> Path:
    """Create `path` (and parents) as a user-only directory (0700) and return it."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # mkdir's mode is subject to umask and is a no-op if the dir already exists,
    # so enforce 0700 explicitly. Best-effort: Windows ignores POSIX modes.
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def write_secure(path: Path, text: str) -> None:
    """Atomically write `text` to `path` with user-only (0600) permissions.

    Writes to a temp file in the same directory created with mode 0600, then
    atomically renames it over the target. The 0600 mode is set at creation, so
    the contents are never briefly world-readable.
    """
    directory = path.parent
    # mkstemp already creates the file owner-only (0600) on POSIX.
    fd, tmp_name = tempfile.mkstemp(dir=str(directory), prefix=".tmp-", suffix=path.suffix)
    try:
        # Tighten explicitly where supported; os.fchmod is Unix-only (Windows
        # uses ACLs and has no POSIX modes — the file is still user-scoped there).
        if hasattr(os, "fchmod"):
            try:
                os.fchmod(fd, 0o600)
            except OSError:
                pass
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        # Don't leave the temp file behind on any failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_json(path: Path, default: Any) -> Any:
    """Load JSON from `path`, returning `default` if absent or unparseable.

    A file that exists but doesn't parse is preserved as `<path>.corrupt` and a
    one-line warning is written to stderr, so a single bad byte never silently
    erases the user's stored history.
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except (ValueError, OSError) as exc:
        backup = path.with_suffix(path.suffix + ".corrupt")
        try:
            os.replace(path, backup)
            note = f" (backed up to {backup.name})"
        except OSError:
            note = ""
        print(
            f"trackman-mcp: could not parse {path.name}: {exc}{note}",
            file=sys.stderr,
        )
        return default
