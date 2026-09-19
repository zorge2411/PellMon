"""caplog regression tests for `Pellmonsrv.plugins.calculate` exception
visibility (Phase 2, OBS-02).

IMPORT PRECONDITIONS -- this module is unimportable today for two
independent reasons, both worked around HERE ONLY, never in `src/`:

1. `import os, grp, pwd` (calculate/__init__.py line 24) fails on Windows
   `venv-py3` -- `grp`/`pwd` stubs are injected into `sys.modules` before
   import, using the same technique as `tests/Pellmonsrv/conftest.py`'s
   `daemon_module` fixture.
2. `from string import maketrans` (calculate/__init__.py line 28) raises
   `ImportError` on every Python 3 interpreter, since `string.maketrans`
   was removed from the stdlib (moved to `str.maketrans`). This test file
   shims `string.maketrans = str.maketrans` before import.

Both shims exist SOLELY to make `Pellmonsrv.plugins.calculate` importable
for exception-visibility testing in this phase. This is not a production
fix -- the `from string import maketrans` line-28 bug is tracked as
PROTO-05 (Phase 4) and the `unicode(value)` line-351 bug is tracked as
PROTO-02 (Phase 4). Both bugs are still present and still broken in
`src/Pellmonsrv/plugins/calculate/__init__.py` after this test file lands;
only the log call inside the except blocks around them changed. Delete
this shim once Phase 4 / PROTO-05 fixes the import for real.
"""

import importlib
import logging
import string
import sys

import pytest


_STUBBED_MODULE_NAMES = ("grp", "pwd")


def _build_grp_stub():
    from unittest.mock import MagicMock

    stub = MagicMock(name="grp")
    stub.getgrall = MagicMock(name="grp.getgrall", return_value=[])
    stub.getgrnam = MagicMock(name="grp.getgrnam")
    stub.getgrgid = MagicMock(name="grp.getgrgid")
    return stub


def _build_pwd_stub():
    from unittest.mock import MagicMock

    stub = MagicMock(name="pwd")
    stub.getpwnam = MagicMock(name="pwd.getpwnam")
    return stub


_STUB_BUILDERS = {
    "grp": _build_grp_stub,
    "pwd": _build_pwd_stub,
}


@pytest.fixture(scope="module")
def calculate_module():
    """Import and yield `Pellmonsrv.plugins.calculate`, injecting sys.modules
    stubs for grp/pwd (Windows-only gap) and a test-only `string.maketrans`
    shim (Python-3-wide gap, PROTO-05) before import. Both are undone on
    teardown so `tests/test_plugin_imports.py` keeps producing its genuine,
    unshimmed outcomes.
    """
    injected_module_keys = []
    for name in _STUBBED_MODULE_NAMES:
        if name in sys.modules:
            continue
        try:
            importlib.import_module(name)
            continue
        except ImportError:
            pass
        sys.modules[name] = _STUB_BUILDERS[name]()
        injected_module_keys.append(name)

    calculate_keys_before = {
        k for k in sys.modules
        if k == "Pellmonsrv.plugins.calculate" or k.startswith("Pellmonsrv.plugins.calculate.")
    }

    try:
        module = importlib.import_module("Pellmonsrv.plugins.calculate")
        yield module
    finally:
        calculate_keys_after = {
            k for k in sys.modules
            if k == "Pellmonsrv.plugins.calculate" or k.startswith("Pellmonsrv.plugins.calculate.")
        }
        for key in calculate_keys_after - calculate_keys_before:
            sys.modules.pop(key, None)
        for key in injected_module_keys:
            sys.modules.pop(key, None)


@pytest.fixture
def plugin(calculate_module):
    """A `calculateplugin` instance with just enough state hand-populated
    (module-level `itemList` + instance `name2index`) to drive `getItem`/
    `setItem` without running the full `activate()` config-parsing path.
    """
    calculate_module.itemList.clear()
    calculate_module.itemTags.clear()
    calculate_module.itemValues.clear()

    obj = calculate_module.calculateplugin()
    obj.calc2index = {}
    obj.name2index = {}
    obj.tasks = {}
    obj.itemrefs = []
    obj.db = None
    yield obj
    calculate_module.itemList.clear()
    calculate_module.itemTags.clear()
    calculate_module.itemValues.clear()


def test_setitem_calc_failure_visibility(calculate_module, plugin, caplog):
    """setItem() on a calculated item whose calc program raises still
    returns 'error', and the underlying calc execution failure reaches the
    log with a full traceback and the calc_item name in the message.
    """
    calculate_module.itemList.append({
        'name': 'calc_result', 'value': '', 'calc_item': 'calc_prog',
        'min': '', 'max': '', 'unit': '', 'type': 'R/W', 'description': '',
    })
    calculate_module.itemList.append({
        'name': 'calc_prog', 'value': '/', 'min': '', 'max': '',
        'unit': '', 'type': 'R', 'description': '',
    })
    plugin.name2index['calc_result'] = 0
    plugin.name2index['calc_prog'] = 1

    with caplog.at_level(logging.ERROR, logger='pellMon'):
        result = plugin.setItem('calc_result', '1')

    assert result == 'error'

    matching = [r for r in caplog.records if r.exc_info is not None]
    assert matching, "expected at least one ERROR record with exc_info attached"
    record = matching[0]
    assert record.levelno == logging.ERROR
    assert 'calc_prog' in record.getMessage()


def test_getitem_calc_failure_visibility(calculate_module, plugin, caplog):
    """getItem() on a calculated item whose calc program raises still
    returns 'error', but now logs a full traceback (with the calc_item
    name in the message) instead of a repr() one-liner.
    """
    calculate_module.itemList.append({
        'name': 'calc_result', 'value': '', 'calc_item': 'calc_prog',
        'min': '', 'max': '', 'unit': '', 'type': 'R', 'description': '',
    })
    calculate_module.itemList.append({
        # '/' with an empty stack raises IndexError inside Calc.execute(),
        # which Calc.run() converts to a ValueError and re-raises --
        # guaranteed to raise, unlike a bare unknown-token program (which
        # the interpreter just pushes onto the stack as a literal, per
        # the trailing `else: self.stack.append(c)` catch-all).
        'name': 'calc_prog', 'value': '/', 'min': '', 'max': '',
        'unit': '', 'type': 'R', 'description': '',
    })
    plugin.name2index['calc_result'] = 0
    plugin.name2index['calc_prog'] = 1

    with caplog.at_level(logging.ERROR, logger='pellMon'):
        result = plugin.getItem('calc_result')

    assert result == 'error'

    matching = [r for r in caplog.records if r.exc_info is not None]
    assert matching, "expected at least one ERROR record with exc_info attached"
    record = matching[0]
    assert record.levelno == logging.ERROR
    assert 'calc_prog' in record.getMessage()


def test_plain_item_access_produces_no_log_records(calculate_module, plugin, caplog):
    """getItem()/setItem() on a plain non-calculated item (no `calc_item`
    key -- hitting the Category B fallback lookups) must emit ZERO log
    records at any level. This is the regression guard that prevents a
    future contributor from converting those fallbacks into logged
    catches and flooding the log on every ordinary item access.
    """
    calculate_module.itemList.append({
        'name': 'plain_item', 'value': 'hello', 'min': '', 'max': '',
        'unit': '', 'type': 'R', 'description': '',
    })
    plugin.name2index['plain_item'] = 0

    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        read_result = plugin.getItem('plain_item')
        write_result = plugin.setItem('plain_item', 'new_value')

    assert read_result == 'hello'
    # A plain 'R'-type item's setItem falls through with no explicit return
    # (the Category B `except: if item['type'] == 'R/W': ...` branch is
    # only taken for writable items) -- that control flow is untouched by
    # this plan; the assertion that matters here is the log-silence one.
    assert write_result is None
    assert len(caplog.records) == 0


def test_activate_reraise_preserved(calculate_module, plugin, caplog):
    """The outer activate() except path still logs an ERROR record with a
    traceback AND still re-raises the original exception -- control flow
    is unchanged, only the log call is upgraded.
    """
    class _BrokenConf:
        def items(self):
            raise RuntimeError('boom - simulated config parse failure')

    with caplog.at_level(logging.ERROR, logger='pellMon'):
        with pytest.raises(RuntimeError, match='boom - simulated config parse failure'):
            plugin.activate(_BrokenConf(), None, None)

    matching = [r for r in caplog.records if r.exc_info is not None]
    assert matching, "expected at least one ERROR record with exc_info attached"
    assert matching[0].levelno == logging.ERROR
