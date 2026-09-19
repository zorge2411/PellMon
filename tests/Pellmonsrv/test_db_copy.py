"""Regression tests for copy_db locking, rrd create argv, and the NBE mock pincode check."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def conf_stub(daemon_module):
    daemon_module.conf = SimpleNamespace(db="/tmp/a.db", nvdb="/tmp/b.db")
    yield daemon_module.conf
    del daemon_module.conf


def test_no_os_system_in_daemon():
    import ast
    path = os.path.join(os.path.dirname(__file__), "..", "..", "src", "Pellmonsrv", "pellmonsrv.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "system" and getattr(node.value, "id", "") == "os":
            pytest.fail("os.system still used at line %d" % node.lineno)


def test_copy_store_and_restore(daemon_module, conf_stub, mocker):
    cp = mocker.patch.object(daemon_module.shutil, "copy")
    daemon_module.copy_db("store")
    cp.assert_called_once_with("/tmp/a.db", "/tmp/b.db")
    cp.reset_mock()
    daemon_module.copy_db("restore")
    cp.assert_called_once_with("/tmp/b.db", "/tmp/a.db")


def test_copy_failure_is_logged_and_lock_released(daemon_module, conf_stub, mocker, caplog):
    cp = mocker.patch.object(daemon_module.shutil, "copy", side_effect=OSError("boom"))
    daemon_module.logger = __import__("logging").getLogger("pellMon")
    with caplog.at_level("ERROR", logger="pellMon"):
        daemon_module.copy_db("store")
    assert "failed" in caplog.text
    assert not daemon_module._copy_lock.locked()
    cp.side_effect = None
    cp.reset_mock()
    daemon_module.copy_db("store")
    assert cp.call_count == 1


def test_reentrant_copy_is_skipped(daemon_module, conf_stub, mocker):
    calls = []

    def fake_copy(src, dst):
        calls.append((src, dst))
        assert daemon_module._copy_lock.locked()
        daemon_module.copy_db("store")  # must return immediately

    mocker.patch.object(daemon_module.shutil, "copy", side_effect=fake_copy)
    daemon_module.copy_db("store")
    assert len(calls) == 1


def test_rrd_create_command_is_argv_list(daemon_module, tmp_path):
    conffile = tmp_path / "p.conf"
    conffile.write_text(
        "[conf]\ndatabase = /tmp/x db.rrd\npersistent_db = /tmp/y db.rrd\npollinterval = 10\n"
        "[pollvalues]\nk1 = item1\nk2 = item2\n"
        "[rrd_ds_names]\nk1 = ds1\nk2 = ds2\n[rrd_ds_types]\n"
    )
    c = daemon_module.config(str(conffile))
    cmd = c.RrdCreateCommand
    assert isinstance(cmd, list)
    assert cmd[:3] == ["rrdtool", "create", "/tmp/y db.rrd"]
    assert sum(1 for e in cmd if e.startswith("DS:")) == 2
    assert sum(1 for e in cmd if e.startswith("RRA:AVERAGE:")) == 4
    assert all(" " not in e for e in cmd[3:])
    assert c.RrdCreateString == " ".join(cmd)


def _run_controller_once(request):
    pytest.importorskip("Crypto")
    from Pellmonsrv.plugins.nbecom.nbeprotocol import protocol

    sock = MagicMock()
    sock.recvfrom.side_effect = [(b"x", ("1.2.3.4", 1)), KeyboardInterrupt()]
    ctl = protocol.Controller.__new__(protocol.Controller)
    ctl.s = sock
    ctl.password = "0123456789"
    ctl.request = request
    ctl.response = MagicMock()
    ctl.response.encode.return_value = b"frame"
    with pytest.raises(KeyboardInterrupt):
        ctl.run()
    return ctl


def _request(pincode):
    req = MagicMock()
    req.function = 1
    req.pincode = pincode
    req.payload = b"boiler.temp"
    return req


def test_nbe_controller_rejects_wrong_pincode():
    ctl = _run_controller_once(_request("   wrongpin"))
    assert ctl.response.payload == "wrong password"
    assert ctl.response.status == 1


def test_nbe_controller_accepts_matching_padded_pincode():
    ctl = _run_controller_once(_request("0123456789"))
    assert ctl.response.payload != "wrong password"
    ctl = _run_controller_once(_request("  12345678"))  # mismatch
    assert ctl.response.payload == "wrong password"
