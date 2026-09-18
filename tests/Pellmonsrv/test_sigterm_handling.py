"""Unit tests for graceful SIGTERM and SIGINT handling (OPS-02).

Verifies that:
- pellmonsrv handles SIGTERM and SIGINT by flushing RRD data to disk when
  using a non-volatile copy, stopping the poller thread, quitting the GLib
  main loop, and removing its pidfile.
- pellmonweb registers SIGTERM alongside SIGINT and triggers CherryPy engine
  exit and GLib main loop quit cleanly.
"""

import ast
import importlib
import logging
import signal
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def web_module():
    """Import and yield `Pellmonweb.pellmonweb`, injecting sys.modules stubs
    for gi/dbus/pwd/grp if not already present on non-Linux environments.
    """
    stubs = {}
    stub_names = (
        "gi",
        "gi.repository",
        "dbus",
        "dbus.mainloop",
        "dbus.mainloop.glib",
        "pwd",
        "grp",
    )
    for name in stub_names:
        if name not in sys.modules:
            stubs[name] = MagicMock(name=name)
            sys.modules[name] = stubs[name]

    pellmonweb_keys_before = {
        k for k in sys.modules if k == "Pellmonweb" or k.startswith("Pellmonweb.")
    }
    try:
        mod = importlib.import_module("Pellmonweb.pellmonweb")
        yield mod
    finally:
        pellmonweb_keys_after = {
            k for k in sys.modules if k == "Pellmonweb" or k.startswith("Pellmonweb.")
        }
        for key in pellmonweb_keys_after - pellmonweb_keys_before:
            sys.modules.pop(key, None)
        for key in stubs:
            sys.modules.pop(key, None)


def test_pellmonsrv_sigterm_handler_flushes_db_and_quits_loop(daemon_module, monkeypatch, caplog):
    """Mocks conf, copy_db, and DBUSMAINLOOP.
    Simulates signal dispatch to sigterm_handler.
    Asserts copy_db('store') is invoked when conf.nvdb != conf.db.
    Asserts DBUSMAINLOOP.quit() is called.
    """
    mock_conf = SimpleNamespace(
        polling=True,
        nvdb="/var/lib/pellmon/rrd.db",
        db="/tmp/pellmon/rrd.db",
    )
    monkeypatch.setattr(daemon_module, "conf", mock_conf, raising=False)

    mock_copy_db = MagicMock()
    monkeypatch.setattr(daemon_module, "copy_db", mock_copy_db, raising=False)

    mock_mainloop = MagicMock()
    monkeypatch.setattr(daemon_module, "DBUSMAINLOOP", mock_mainloop, raising=False)

    with caplog.at_level(logging.INFO, logger="pellMon"):
        daemon_module.sigterm_handler(signal.SIGTERM, None)

    mock_copy_db.assert_called_once_with("store")
    mock_mainloop.quit.assert_called_once()
    assert any("Signal 15 received" in r.getMessage() for r in caplog.records)


def test_pellmonsrv_sigterm_handler_skips_flush_when_same_db(daemon_module, monkeypatch):
    """When conf.nvdb == conf.db, copy_db must not be called, but main loop still quits."""
    mock_conf = SimpleNamespace(
        polling=True,
        nvdb="/var/lib/pellmon/rrd.db",
        db="/var/lib/pellmon/rrd.db",
    )
    monkeypatch.setattr(daemon_module, "conf", mock_conf, raising=False)

    mock_copy_db = MagicMock()
    monkeypatch.setattr(daemon_module, "copy_db", mock_copy_db, raising=False)

    mock_mainloop = MagicMock()
    monkeypatch.setattr(daemon_module, "DBUSMAINLOOP", mock_mainloop, raising=False)

    daemon_module.sigterm_handler(signal.SIGINT, None)

    mock_copy_db.assert_not_called()
    mock_mainloop.quit.assert_called_once()


def test_pellmonsrv_sigterm_handler_stops_poller_and_removes_pid(daemon_module, monkeypatch):
    """Verifies that sigterm_handler stops the poller thread and cleans up the pidfile."""
    mock_conf = SimpleNamespace(
        polling=False,
        nvdb="/tmp/db",
        db="/tmp/db",
    )
    monkeypatch.setattr(daemon_module, "conf", mock_conf, raising=False)

    mock_poller = MagicMock()
    mock_daemon = MagicMock()
    mock_daemon.poller = mock_poller

    monkeypatch.setattr(daemon_module, "daemon_instance", mock_daemon, raising=False)

    mock_mainloop = MagicMock()
    monkeypatch.setattr(daemon_module, "DBUSMAINLOOP", mock_mainloop, raising=False)

    daemon_module.sigterm_handler(signal.SIGTERM, None)

    mock_poller.stop.assert_called_once()
    mock_daemon.delpid.assert_called_once()
    mock_mainloop.quit.assert_called_once()


def test_pellmonsrv_mydaemon_method_sigterm_handler(daemon_module, monkeypatch):
    """Verifies MyDaemon.sigterm_handler method works directly on daemon instance."""
    mock_conf = SimpleNamespace(
        polling=True,
        nvdb="/nvram/rrd.db",
        db="/ramdisk/rrd.db",
    )
    monkeypatch.setattr(daemon_module, "conf", mock_conf, raising=False)

    mock_copy_db = MagicMock()
    monkeypatch.setattr(daemon_module, "copy_db", mock_copy_db, raising=False)

    mock_mainloop = MagicMock()
    monkeypatch.setattr(daemon_module, "DBUSMAINLOOP", mock_mainloop, raising=False)

    daemon = daemon_module.MyDaemon("/tmp/test.pid")
    mock_poller = MagicMock()
    daemon.poller = mock_poller
    daemon.delpid = MagicMock()

    daemon.sigterm_handler(signal.SIGTERM, None)

    mock_copy_db.assert_called_once_with("store")
    mock_poller.stop.assert_called_once()
    daemon.delpid.assert_called_once()
    mock_mainloop.quit.assert_called_once()


def test_poller_stop_lifecycle(daemon_module):
    """Verifies Poller.stop() sets running to False and wakes up event."""
    mock_ev = MagicMock()
    poller = object.__new__(daemon_module.Poller)
    poller.ev = mock_ev
    poller.running = True

    poller.stop()

    assert poller.running is False
    mock_ev.set.assert_called_once()


def test_pellmonsrv_ast_signal_registration():
    """Verify pellmonsrv.py registers both SIGTERM and SIGINT handlers."""
    content = open("src/Pellmonsrv/pellmonsrv.py", "r", encoding="utf-8").read()
    tree = ast.parse(content)

    registered_signals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "signal":
                if len(node.args) >= 2 and isinstance(node.args[0], ast.Attribute):
                    registered_signals.append(node.args[0].attr)

    assert "SIGTERM" in registered_signals, "SIGTERM not registered in pellmonsrv.py"
    assert "SIGINT" in registered_signals, "SIGINT not registered in pellmonsrv.py"


def test_pellmonweb_signal_handler_quits_engine_and_loop(web_module, monkeypatch, caplog):
    """Mocks cherrypy.engine and main_loop.
    Simulates signal dispatch to signal_handler.
    Asserts cherrypy.engine.exit() and main_loop.quit() are called.
    """
    mock_engine = MagicMock()
    monkeypatch.setattr(web_module.cherrypy, "engine", mock_engine)

    mock_loop = MagicMock()
    monkeypatch.setattr(web_module, "main_loop", mock_loop)

    with caplog.at_level(logging.INFO, logger="pellMon"):
        web_module.signal_handler(signal.SIGTERM, None)

    mock_engine.exit.assert_called_once()
    mock_loop.quit.assert_called_once()
    assert any("Signal 15 received" in r.getMessage() for r in caplog.records)


def test_pellmonweb_ast_signal_registration():
    """Verify pellmonweb.py registers both SIGINT and SIGTERM handlers."""
    content = open("src/Pellmonweb/pellmonweb.py", "r", encoding="utf-8").read()
    assert "signal.signal(signal.SIGINT, signal_handler)" in content
    assert "signal.signal(signal.SIGTERM, signal_handler)" in content
