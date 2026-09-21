import logging
import sqlite3

import pytest

from Pellmonsrv.database import Keyval_storage


def test_getval_absent_key_returns_empty_and_no_error_log(tmp_path, caplog):
    store = Keyval_storage(str(tmp_path / "test.db"))
    with caplog.at_level(logging.DEBUG, logger="pellMon"):
        assert store.getval("nosuchkey") == ""
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_getval_absent_key_custom_default(tmp_path):
    store = Keyval_storage(str(tmp_path / "test.db"))
    assert store.getval("nosuchkey", default="fallback") == "fallback"


def test_first_insert_roundtrip_and_confvalue_not_null(tmp_path):
    """Settles RESEARCH A2: first writeval without confval must not abort on NOT NULL."""
    dbfile = str(tmp_path / "test.db")
    store = Keyval_storage(dbfile)
    store.writeval("web.system_image", "system_nbe.svg")
    assert store.getval("web.system_image") == "system_nbe.svg"
    conn = sqlite3.connect(dbfile)
    (conf,) = conn.execute("SELECT confvalue FROM keyval WHERE id=?", ("web.system_image",)).fetchone()
    conn.close()
    assert conf is not None


def test_null_value_reads_as_default(tmp_path):
    dbfile = str(tmp_path / "test.db")
    store = Keyval_storage(dbfile)
    store.writeval("k", None)
    assert store.getval("k") == ""
    assert store.getval("k", "d") == "d"


@pytest.fixture
def svc(daemon_module, tmp_path):
    from Pellmonsrv.database import init_keyval_storage
    init_keyval_storage(str(tmp_path / "settings.db"))
    # Call unbound so no real bus is needed; dbus decorators are identity under test.
    cls = daemon_module.MyDBUSService
    yield cls
    Keyval_storage.keyval_storage = None


def test_get_unset_returns_empty(svc):
    assert svc.GetSetting(None, "web.system_image") == ""


def test_set_then_get(svc):
    assert svc.SetSetting(None, "web.system_image", "system_nbe.svg") is True
    assert svc.GetSetting(None, "web.system_image") == "system_nbe.svg"


def test_unknown_key_rejected(svc, caplog):
    with caplog.at_level(logging.WARNING, logger="pellMon"):
        assert svc.SetSetting(None, "some.other.key", "x") is False
    assert "some.other.key" in caplog.text
    assert Keyval_storage.keyval_storage.getval("some.other.key") == ""
    assert svc.GetSetting(None, "some.other.key") == ""


@pytest.mark.parametrize("bad", [
    "../../etc/passwd", "/etc/passwd", "system.svg/../../etc/passwd",
    "system.svg\x00", "SYSTEM.SVG", "", "systemsvg",
])
def test_bad_values_rejected_and_stored_unchanged(svc, bad):
    assert svc.SetSetting(None, "web.system_image", "system_nbe.svg") is True
    assert svc.SetSetting(None, "web.system_image", bad) is False
    assert svc.GetSetting(None, "web.system_image") == "system_nbe.svg"


def test_set_without_store_returns_false(svc):
    Keyval_storage.keyval_storage = None
    assert svc.SetSetting(None, "web.system_image", "system.svg") is False
    assert svc.GetSetting(None, "web.system_image") == ""
