"""The login/refresh path must never write to stdout.

A stdio MCP server speaks JSON-RPC on stdout; any stray byte there can corrupt
the stream. `login.capture_token` is reachable at runtime (the `login` tool and
the silent-refresh retry on token expiry), so its diagnostics must go to stderr.
"""

from __future__ import annotations

import inspect
import re

from golf_coach import login


def test_log_writes_to_stderr_not_stdout(capsys):
    login._log("hello from login")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "hello from login" in captured.err


def test_no_bare_stdout_prints_in_login_module():
    src = inspect.getsource(login)
    # Every print(...) in this module must be directed to stderr.
    for m in re.finditer(r"\bprint\(", src):
        line = src[m.start():src.find("\n", m.start())]
        assert "stderr" in line, f"stdout print in login.py: {line!r}"


def test_token_capture_host_allowlist():
    assert login._is_trackman_host("https://api.trackmangolf.com/graphql")
    assert login._is_trackman_host("https://portal.trackmangolf.com/")
    # Look-alike / attacker hosts must not match.
    assert not login._is_trackman_host("https://nottrackmangolf.com/x")
    assert not login._is_trackman_host("https://trackmangolf.com.evil.com/x")
    assert not login._is_trackman_host("https://evil.com/?u=trackmangolf.com")
