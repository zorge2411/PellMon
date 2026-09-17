"""Caplog regression tests for pellmonsrv.py's daemon-side failure paths.

Covers OBS-01 (daemon half: plugin-activation loop) and OBS-02 (RRD-polling
item-read failure path) -- see ROADMAP.md Phase 2 success criteria 2 and 3.
Phase 2 plan 02-03 converts the plugin-activation and Poller failure paths
from a one-line `logger.info(str(e))` message into a full `logger.exception`
traceback while leaving control flow (failed_plugins bookkeeping, debug-mode
re-raise, the RRD 'U' fallback value) unchanged.

RED STATE: every test in this file is expected to FAIL against the
unmodified `src/Pellmonsrv/pellmonsrv.py` -- either with an assertion error
(no ERROR-level/exc_info record present) or with `NameError: name 'logger'
is not defined` (pellmonsrv.py has no module-level logger before Task 2
lands, so the activation/poller failure branches cannot resolve the bare
name `logger`). Task 2 (module-level `logger = logging.getLogger('pellMon')`
plus the six `logger.exception(...)` conversions) turns this suite GREEN.
"""

import logging
import threading
from types import SimpleNamespace

import pytest


class _FailingPluginObject:
    """Stand-in plugin object whose activate() always raises."""

    def activate(self, *args, **kwargs):
        raise RuntimeError("deliberate activate failure")


class _StandInPlugin:
    def __init__(self, name):
        self.name = name
        self.plugin_object = _FailingPluginObject()


class _FakePluginManager:
    """Stands in for Pellmonsrv.yapsy.PluginManager.PluginManager -- avoids
    scanning real plugin directories and always yields one failing plugin."""

    def __init__(self, *args, **kwargs):
        self._plugins = [_StandInPlugin("failplugin")]

    def setPluginPlaces(self, dirs):
        pass

    def collectPlugins(self):
        pass

    def getPluginsOfCategory(self, category):
        return self._plugins


def _make_database_hashable(daemon_module, monkeypatch):
    """Pre-existing, out-of-scope bug worked around here for test purposes
    only (see deferred-items.md): `Database(threading.Thread, _Database)`
    inherits `__hash__ = None` from `_Database`'s `WeakValueDictionary` base
    (which defines `__eq__` without `__hash__`), so `threading.Thread.__init__`
    raises `TypeError: cannot use 'weakref.ReferenceType' as a set element`
    the instant a `Database()` is constructed, on every Python 3.4+ runtime --
    this is unrelated to Phase 2's exception-visibility scope and is NOT
    fixed in src/, only patched here so the activation-loop tests can run."""
    monkeypatch.setattr(daemon_module.Database, "__hash__", object.__hash__, raising=False)


def _build_conf(keyval_db):
    return SimpleNamespace(
        keyval_db=keyval_db,
        plugin_dirs=[],
        enabled_plugins=["failplugin"],
        plugin_conf={"failplugin": {}},
        command="start",
    )


def test_plugin_activation_failure_logs_traceback(daemon_module, tmp_path, monkeypatch, caplog):
    """OBS-01 (daemon half): a plugin whose activate() raises must produce a
    full traceback at ERROR level, naming the plugin, and the plugin must
    still land in the daemon's failed-plugins bookkeeping (proven via the
    'Failed to activate plugins' summary line the loop already emits)."""
    monkeypatch.setattr(daemon_module, "conf", _build_conf(str(tmp_path / "keyval.db")), raising=False)
    monkeypatch.setattr(daemon_module, "PluginManager", _FakePluginManager)
    _make_database_hashable(daemon_module, monkeypatch)

    with caplog.at_level(logging.DEBUG, logger="pellMon"):
        daemon_module.Database()

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected an ERROR-level record for the failed plugin activation"
    record = error_records[0]
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert "failplugin" in record.getMessage()

    summary_records = [
        r for r in caplog.records
        if "Failed to activate plugins" in r.getMessage() and "failplugin" in r.getMessage()
    ]
    assert summary_records, "failplugin must still appear in the failed-plugins summary line"


def test_plugin_activation_debug_mode_reraises(daemon_module, tmp_path, monkeypatch):
    """Guards the explicitly-untouched `if conf.command == 'debug': raise`
    branch against being collapsed during the Task 2 conversion."""
    conf = _build_conf(str(tmp_path / "keyval_debug.db"))
    conf.command = "debug"
    monkeypatch.setattr(daemon_module, "conf", conf, raising=False)
    monkeypatch.setattr(daemon_module, "PluginManager", _FakePluginManager)
    _make_database_hashable(daemon_module, monkeypatch)

    with pytest.raises(RuntimeError):
        daemon_module.Database()


def test_poller_item_read_failure_logs_traceback(daemon_module, monkeypatch, mocker, caplog):
    """OBS-02: a failed RRD item read during polling must log a traceback
    naming the item, and the poller must still write the 'U' fallback value
    for that item -- proving only the log changed, not the control flow."""

    class _FailingDB(dict):
        def __getitem__(self, key):
            raise RuntimeError("deliberate item read failure")

    class _StopLoop(Exception):
        """Sentinel used to break out of Poller.run()'s `while True` after
        exactly one iteration; raised from the mocked time.sleep(1) call
        which sits outside the per-iteration try/except in pellmonsrv.py."""

    conf = SimpleNamespace(
        polling=True,
        pollData=[{"name": "faildata", "ds_type": "GAUGE"}],
        database=_FailingDB(),
        lastupdate_time=0,
        db="dummy.rrd",
    )
    monkeypatch.setattr(daemon_module, "conf", conf, raising=False)

    popen_mock = mocker.patch.object(daemon_module.subprocess, "Popen")
    popen_mock.return_value.communicate.return_value = (b"", b"")
    popen_mock.return_value.returncode = 0
    mocker.patch.object(daemon_module.time, "sleep", side_effect=_StopLoop)

    poller = object.__new__(daemon_module.Poller)
    poller.ev = threading.Event()
    poller.ev.set()
    poller.timesync_wait = 0

    with caplog.at_level(logging.DEBUG, logger="pellMon"):
        with pytest.raises(_StopLoop):
            poller.run()

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_records, "expected an ERROR-level record for the failed item read"
    record = error_records[0]
    assert record.exc_info is not None
    assert "faildata" in record.getMessage()

    # The 'U' fallback for the failing item must still reach the RRD update command.
    rrd_command = popen_mock.call_args[0][0]
    assert rrd_command[3].endswith(":U")


def test_module_level_logger_available_before_daemon_run(daemon_module):
    """Pins the Task 2 requirement that makes the other three tests possible:
    a module-level `pellMon` logger must exist immediately after import,
    before MyDaemon.run() or config.__init__ ever runs."""
    assert hasattr(daemon_module, "logger")
