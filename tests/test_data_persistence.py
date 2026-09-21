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
