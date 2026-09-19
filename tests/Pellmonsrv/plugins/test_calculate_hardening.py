"""Unit tests for Calculate plugin hardening (PROTO-02 and PROTO-05).

Verifies:
1. `calculate` does not import `maketrans` from `string` (PROTO-05).
2. `Calc` execution handles string and numeric values without `NameError: unicode`.
3. `setItem` uses `str(value)` and executes successfully on calculated items (PROTO-02).
"""

import ast
import importlib
import logging
import pathlib
import sys
from unittest.mock import MagicMock
import pytest


_STUBBED_MODULE_NAMES = ("grp", "pwd")


def _build_grp_stub():
    stub = MagicMock(name="grp")
    stub.getgrall = MagicMock(name="grp.getgrall", return_value=[])
    stub.getgrnam = MagicMock(name="grp.getgrnam")
    stub.getgrgid = MagicMock(name="grp.getgrgid")
    return stub


def _build_pwd_stub():
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
    stubs for grp/pwd (Windows-only gap). Crucially, NO string.maketrans shim
    is applied, proving calculate/__init__.py is importable natively under Python 3.
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
    """A clean `calculateplugin` instance with isolated item state."""
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


def test_calculate_does_not_import_maketrans():
    """Verify PROTO-05: calculate/__init__.py has no 'maketrans' import."""
    init_path = pathlib.Path("src/Pellmonsrv/plugins/calculate/__init__.py")
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported_names = [alias.name for alias in node.names]
            assert "maketrans" not in imported_names, (
                "Found 'from %s import maketrans' in %s" % (node.module, init_path)
            )
        elif isinstance(node, ast.Import):
            imported_names = [alias.name for alias in node.names]
            assert "maketrans" not in imported_names


def test_calculate_has_no_unicode_references():
    """Verify PROTO-02: calculate/__init__.py has no references to unicode()."""
    init_path = pathlib.Path("src/Pellmonsrv/plugins/calculate/__init__.py")
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "unicode":
            pytest.fail("Found 'unicode' identifier at line %d in %s" % (node.lineno, init_path))


def test_calc_execution_with_string_values(calculate_module):
    """Test that Calc arithmetic and logic evaluate cleanly with string representation."""
    Calc = calculate_module.Calc

    # Addition
    c1 = Calc("1 2 +", db=None)
    assert c1.run() == "3.0"

    # Multiplication and division
    c2 = Calc("6 2 /", db=None)
    assert c2.run() == "3.0"

    # Comparison
    c3 = Calc("5 3 >", db=None)
    assert c3.run() == "1"

    # Variable storage and recall (value var sto var rcl)
    c4 = Calc("10 x sto x rcl", db=None)
    assert c4.run() == "10"


def test_setitem_uses_str_and_returns_ok(calculate_module, plugin):
    """Test PROTO-02: setItem on a calculated item converts value using str() and succeeds."""
    calculate_module.itemList.append({
        'name': 'calc_result', 'value': '', 'calc_item': 'calc_prog',
        'min': '', 'max': '', 'unit': '', 'type': 'R/W', 'description': '',
    })
    calculate_module.itemList.append({
        'name': 'calc_prog', 'value': '1 +', 'min': '', 'max': '',
        'unit': '', 'type': 'R', 'description': '',
    })
    plugin.name2index['calc_result'] = 0
    plugin.name2index['calc_prog'] = 1

    # Pass integer value; setItem should do str(value) -> stack=['10'] -> '10 1 +' -> '11.0'
    res = plugin.setItem('calc_result', 10)
    assert res == 'OK'


def test_setitem_calc_failure_logs_exception(calculate_module, plugin, caplog):
    """Test setItem error logging when the calculation fails at runtime."""
    calculate_module.itemList.append({
        'name': 'calc_result', 'value': '', 'calc_item': 'calc_prog',
        'min': '', 'max': '', 'unit': '', 'type': 'R/W', 'description': '',
    })
    calculate_module.itemList.append({
        # '/' with empty stack causes Calc to raise
        'name': 'calc_prog', 'value': '/', 'min': '', 'max': '',
        'unit': '', 'type': 'R', 'description': '',
    })
    plugin.name2index['calc_result'] = 0
    plugin.name2index['calc_prog'] = 1

    with caplog.at_level(logging.ERROR, logger='pellMon'):
        res = plugin.setItem('calc_result', 'invalid')

    assert res == 'error'
    matching = [r for r in caplog.records if r.exc_info is not None]
    assert matching, "expected at least one ERROR record with exc_info attached"
    assert matching[0].levelno == logging.ERROR
    assert 'calc_prog error' in matching[0].getMessage()
