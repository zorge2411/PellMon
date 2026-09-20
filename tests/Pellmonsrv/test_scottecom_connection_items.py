"""burner_connection / burner_connection_reason items published by the
scottecom plugin. Plugin object is constructed directly; no D-Bus needed."""

import pytest

from Pellmonsrv.database import Database
from Pellmonsrv.plugins.scottecom.scottecom import scottecom


def _activate(conf):
    db = Database()
    plugin = scottecom()
    plugin.activate(conf, {}, db)
    return plugin, db


def test_demo_when_serialport_missing():
    plugin, db = _activate({"chipversion": "auto"})
    assert db.get_value("burner_connection") == "demo"
    assert "simulated" in db.get_value("burner_connection_reason")


def test_demo_when_serialport_blank():
    plugin, db = _activate({"serialport": "   ", "chipversion": "auto"})
    assert db.get_value("burner_connection") == "demo"


def test_unopenable_port_is_no_connection_and_serves_no_values():
    plugin, db = _activate({"serialport": "/nonexistent/ttyXYZ", "chipversion": "auto"})
    assert db.get_value("burner_connection") == "no_connection"
    assert "/nonexistent/ttyXYZ" in db.get_value("burner_connection_reason")
    with pytest.raises(IOError):
        db.get_value("power")


def test_transition_updates_items_in_place():
    plugin, db = _activate({"serialport": "/nonexistent/ttyXYZ", "chipversion": "auto"})
    plugin.protocol._set_connection_state("connected", "")
    assert db.get_value("burner_connection") == "connected"
    plugin.protocol._set_connection_state("no_connection", "burner not answering on X")
    assert db.get_value("burner_connection") == "no_connection"
    assert db.get_value("burner_connection_reason") == "burner not answering on X"


def test_items_are_in_db_keys_and_readonly():
    plugin, db = _activate({"chipversion": "auto"})
    for name in ("burner_connection", "burner_connection_reason"):
        assert name in list(db.keys())
        assert db.get_item(name).type == "R"
        assert isinstance(db.get_item(name).tags, list)


def test_items_survive_protocol_setup_failure(monkeypatch):
    """State items must exist even when the rest of activation blows up."""
    import sys
    mod = sys.modules["Pellmonsrv.plugins.scottecom.scottecom"]

    def boom(item):
        raise RuntimeError("menus broke")

    monkeypatch.setattr(mod.menus, "itemtags", boom)
    plugin, db = _activate({"serialport": "/nonexistent/ttyXYZ", "chipversion": "auto"})
    assert db.get_value("burner_connection") == "no_connection"
