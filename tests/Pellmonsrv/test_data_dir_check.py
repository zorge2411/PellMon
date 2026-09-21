"""Startup guard and settings-path derivation tests (Phase 7, D-07)."""

import os
import sys
from types import SimpleNamespace

import pytest

posix_user = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs a non-root POSIX user",
)


def _conf(tmp_path, logfile=True):
    d = tmp_path / "data"
    return SimpleNamespace(
        db=str(d / "rrd.db"),
        keyval_db=str(d / "pellmon_settings.db"),
        logfile=str(tmp_path / "logs" / "pellmon.log") if logfile else None,
        polling=True,
    )


def test_writable_dirs_ok_and_created(daemon_module, tmp_path, monkeypatch):
    monkeypatch.setenv("PELLMON_REQUIRE_DATADIR", "1")
    c = _conf(tmp_path)
    assert daemon_module.check_data_dirs(c) is True
    assert os.path.isdir(os.path.dirname(c.db))
    assert os.path.isdir(os.path.dirname(c.logfile))


@posix_user
def test_unwritable_dir_exits_when_required(daemon_module, tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("PELLMON_REQUIRE_DATADIR", "1")
    c = _conf(tmp_path)
    d = os.path.dirname(c.db)
    os.makedirs(d)
    os.chmod(d, 0o500)
    try:
        with caplog.at_level("ERROR", logger="pellMon"):
            with pytest.raises(SystemExit) as ei:
                daemon_module.check_data_dirs(c)
    finally:
        os.chmod(d, 0o700)
    assert ei.value.code == 1
    assert d in caplog.text


@posix_user
def test_unwritable_dir_warns_when_not_required(daemon_module, tmp_path, monkeypatch, caplog):
    monkeypatch.delenv("PELLMON_REQUIRE_DATADIR", raising=False)
    c = _conf(tmp_path)
    d = os.path.dirname(c.db)
    os.makedirs(d)
    os.chmod(d, 0o500)
    try:
        with caplog.at_level("WARNING", logger="pellMon"):
            assert daemon_module.check_data_dirs(c) is False
    finally:
        os.chmod(d, 0o700)
    assert d in caplog.text


@posix_user
def test_unwritable_rrd_file(daemon_module, tmp_path, monkeypatch, caplog):
    c = _conf(tmp_path)
    os.makedirs(os.path.dirname(c.db))
    with open(c.db, "w") as f:
        f.write("x")
    os.chmod(c.db, 0o400)
    try:
        monkeypatch.setenv("PELLMON_REQUIRE_DATADIR", "1")
        with pytest.raises(SystemExit) as ei:
            daemon_module.check_data_dirs(c)
        assert ei.value.code == 1
        monkeypatch.delenv("PELLMON_REQUIRE_DATADIR")
        with caplog.at_level("WARNING", logger="pellMon"):
            assert daemon_module.check_data_dirs(c) is False
        assert c.db in caplog.text
    finally:
        os.chmod(c.db, 0o600)


def test_settings_db_next_to_rrd_when_polling_off(daemon_module, tmp_path):
    conffile = tmp_path / "p.conf"
    conffile.write_text("[conf]\ndatabase = %s\n" % (tmp_path / "rrd.db"))
    c = daemon_module.config(str(conffile))
    assert c.polling is False
    assert c.keyval_db == os.path.join(str(tmp_path), "pellmon_settings.db")
    assert "/tmp" not in c.keyval_db
