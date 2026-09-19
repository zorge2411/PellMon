"""Unit tests for Daemon hardening (PROTO-03).

Verifies that daemon stderr redirection uses line-buffered text I/O (buffering=1)
instead of unbuffered text I/O (buffering=0), which raises ValueError under Python 3.
"""

import ast
import pathlib
import tempfile
import pytest

from Pellmonsrv.daemon import Daemon


def test_daemon_initialization_defaults():
    """Verify Daemon initializes with expected default file paths."""
    d = Daemon()
    assert d.stdin == "/dev/null"
    assert d.stdout == "/dev/null"
    assert d.stderr == "/dev/null"
    assert d.pidfile == ""


def test_daemon_initialization_custom():
    """Verify Daemon accepts custom paths for pid and descriptors."""
    d = Daemon(
        pidfile="/tmp/test.pid",
        stdin="/tmp/in",
        stdout="/tmp/out",
        stderr="/tmp/err",
    )
    assert d.pidfile == "/tmp/test.pid"
    assert d.stdin == "/tmp/in"
    assert d.stdout == "/tmp/out"
    assert d.stderr == "/tmp/err"


def test_daemon_stderr_buffering_avoids_valueerror():
    """Verify that opening stderr with 'a+' and buffering=1 succeeds in Python 3,
    whereas buffering=0 raises ValueError: can't have unbuffered text I/O.
    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        tmp_path = f.name

    try:
        # buffering=0 in text mode ('a+') MUST raise ValueError in Python 3
        with pytest.raises(ValueError, match="can't have unbuffered text I/O"):
            open(tmp_path, "a+", buffering=0)

        # buffering=1 (line-buffered) MUST succeed in Python 3
        with open(tmp_path, "a+", buffering=1) as se:
            se.write("daemon stderr message\n")
            assert not se.closed

        # Verify content was written
        with open(tmp_path, "r", encoding="utf-8") as check:
            content = check.read()
            assert "daemon stderr message\n" in content
    finally:
        pathlib.Path(tmp_path).unlink(missing_ok=True)


def test_daemon_source_ast_buffering():
    """Inspect daemon.py AST to verify line-buffered stderr redirection is used."""
    daemon_path = pathlib.Path("src/Pellmonsrv/daemon.py")
    source = daemon_path.read_text(encoding="utf-8")
    assert "buffering=0" not in source, "Found buffering=0 in daemon.py"
    assert "buffering=1" in source, "buffering=1 not found in daemon.py"
