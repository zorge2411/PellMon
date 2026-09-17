"""Caplog regression tests for yapsy plugin-load failure visibility (OBS-01).

ROADMAP Phase 2 success criterion 2: "a deliberately triggered plugin
import/activation failure produces a full traceback via
`logger.exception(...)` in the logs instead of being silently skipped by a
bare `except:` in the yapsy plugin manager."

These tests exercise `Pellmonsrv.yapsy.PluginManager` directly against
throwaway `tmp_path` plugin directories -- no `daemon_module` fixture is
needed here since `Pellmonsrv.yapsy.PluginManager` imports cleanly on
`venv-py3` today.

Expected to FAIL (assertion errors, not collection/import errors) until
Task 2 lands the corresponding edits in
`src/Pellmonsrv/yapsy/PluginManager.py`.
"""

import logging

from Pellmonsrv.yapsy.PluginManager import PluginManager


def _write_descriptor(directory, filename, name, module):
    descriptor_path = directory / filename
    descriptor_path.write_text(
        "[Core]\n"
        "Name = %s\n"
        "Module = %s\n"
        "\n"
        "[Documentation]\n"
        "Author = test\n"
        "Version = 0.1\n" % (name, module),
        encoding="utf-8",
    )
    return descriptor_path


def test_broken_plugin_exec_failure_logs_error_with_traceback(tmp_path, caplog):
    """A plugin module that raises at exec time must produce an ERROR-level
    log record carrying the real exception's traceback, not a swallowed
    one-line message."""
    _write_descriptor(tmp_path, "broken.pellmon-plugin", "Broken", "broken")
    (tmp_path / "broken.py").write_text(
        'raise RuntimeError("deliberate plugin load failure")\n',
        encoding="utf-8",
    )

    manager = PluginManager(
        categories_filter={},
        directories_list=[str(tmp_path)],
        plugin_info_ext="pellmon-plugin",
    )

    with caplog.at_level(logging.DEBUG):
        manager.locatePlugins()
        manager.loadPlugins()  # must not raise -- broken plugin still skipped

    matching = [
        record
        for record in caplog.records
        if record.levelno == logging.ERROR
        and record.exc_info is not None
        and "Unable to execute the code in plugin" in record.getMessage()
    ]
    assert matching, "expected an ERROR record with exc_info for the broken plugin exec failure"
    assert matching[0].exc_info[0] is RuntimeError


def test_malformed_descriptor_logs_debug_with_traceback(tmp_path, caplog):
    """A plugin descriptor configparser cannot parse still logs at DEBUG
    level (per D-03), but now carries the traceback via exc_info."""
    malformed = tmp_path / "malformed.pellmon-plugin"
    malformed.write_text("this is not a valid ini file\nkey without section\n", encoding="utf-8")

    manager = PluginManager(
        categories_filter={},
        directories_list=[str(tmp_path)],
        plugin_info_ext="pellmon-plugin",
    )

    with caplog.at_level(logging.DEBUG):
        manager.locatePlugins()

    matching = [
        record
        for record in caplog.records
        if record.levelno == logging.DEBUG
        and record.exc_info is not None
        and "Could not parse the plugin file" in record.getMessage()
    ]
    assert matching, "expected a DEBUG record with exc_info for the malformed descriptor"


def test_normal_plugin_scan_probe_stays_silent(tmp_path, caplog):
    """The per-symbol `issubclass` subclass probe in the category loop must
    emit no log output at all during a normal plugin scan -- this guards
    against a future contributor turning the narrow `except TypeError:`
    back into a logged broad catch."""
    _write_descriptor(tmp_path, "plain.pellmon-plugin", "Plain", "plain")
    (tmp_path / "plain.py").write_text(
        "VALUE_A = 1\n"
        "VALUE_B = 'text'\n"
        "VALUE_C = [1, 2, 3]\n"
        "def some_function():\n"
        "    pass\n",
        encoding="utf-8",
    )

    manager = PluginManager(
        categories_filter={},
        directories_list=[str(tmp_path)],
        plugin_info_ext="pellmon-plugin",
    )

    with caplog.at_level(logging.DEBUG):
        manager.locatePlugins()
        manager.loadPlugins()

    assert not any("issubclass" in record.getMessage() for record in caplog.records)
    assert not any(record.levelno == logging.ERROR for record in caplog.records)
