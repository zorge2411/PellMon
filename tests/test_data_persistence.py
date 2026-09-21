"""Settings database file mode (Phase 7, D-09: file will hold the MQTT password)."""

import os
import stat
import sys

import pytest

from Pellmonsrv.database import Keyval_storage


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_settings_db_mode_is_0600(tmp_path):
    dbfile = str(tmp_path / "s.db")
    Keyval_storage(dbfile)
    assert stat.S_IMODE(os.stat(dbfile).st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_settings_db_is_never_group_or_world_readable_while_created(tmp_path, monkeypatch):
    """WR-05: the file must already be 0600 when sqlite first opens it (no umask-0644 window)."""
    import sqlite3
    dbfile = str(tmp_path / "s.db")
    seen = []
    real_connect = sqlite3.connect

    def spy(path, *a, **kw):
        if path == dbfile:
            seen.append(stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else None)
        return real_connect(path, *a, **kw)

    monkeypatch.setattr(sqlite3, "connect", spy)
    old = os.umask(0o022)
    try:
        Keyval_storage(dbfile)
    finally:
        os.umask(old)
    assert seen and seen[0] == 0o600
