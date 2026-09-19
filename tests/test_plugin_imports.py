"""Descriptor-driven, two-layer plugin import check (TEST-02).

Supersedes the ad hoc root `test-imports.py`, which only imports 4 core
modules and never exercises the plugin system. This file discovers every
plugin from its `.pellmon-plugin` descriptor and import-checks it, plus
probes NBEcom's deferred (activate-time) protocol import explicitly so it
cannot false-pass.

Two cases previously failed as the Phase 1 expected-red baseline:
  - test_plugin_module_imports[scottecom]     (IMPORT-01, resolved in Phase 3)
  - test_nbecom_deferred_protocol_import       (IMPORT-02, resolved in Phase 3)
Phase 3 fixed the underlying PEP 328 explicit relative imports and package
structure, so both tests now pass cleanly under Python 3 with 0 known_broken.
"""

import configparser
import importlib
import pathlib

import pytest

PLUGINS_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "Pellmonsrv" / "plugins"

# Modules whose absence means "this dev machine is not the Linux/Pi
# production target", NOT a migration defect. Every name here must be
# justified:
PLATFORM_UNAVAILABLE = {
    "grp",  # Unix-only stdlib; imported by Pellmonsrv.pellmonsrv (pwd/grp for privilege drop), absent on Windows
    "pwd",  # Unix-only stdlib; same privilege-drop import path as grp, absent on Windows
    "RPi",  # Raspberry Pi GPIO hardware library, not installable off-Pi
    "RPi.GPIO",  # submodule of the above
    "dbus",  # python3-dbus is a Linux system package, not pip-installable on Windows
    "gi",  # PyGObject/GLib bindings, Linux system package, not pip-installable on Windows
    "rrdtool",  # round-robin database bindings, installed via apt on Linux only
}

# Plugin modules with a confirmed, still-unfixed Python 3 import defect.
# Resolved in Phase 3 (IMPORT-01, IMPORT-02) -- empty baseline.
KNOWN_BROKEN_MODULES = set()


def discover_plugin_modules():
    """Return the sorted list of `[Core] Module` values from every
    `*.pellmon-plugin` descriptor in the plugins directory.

    Descriptor-driven, not hardcoded -- a new plugin dropped into
    src/Pellmonsrv/plugins/ is picked up automatically the next time this
    test module is collected.
    """
    modules = []
    for descriptor in sorted(PLUGINS_DIR.glob("*.pellmon-plugin")):
        parser = configparser.ConfigParser()
        parser.read(descriptor, encoding="utf-8")
        modules.append(parser["Core"]["Module"])
    return sorted(modules)


def test_plugin_discovery_is_not_vacuous():
    """Guard against a silently-empty glob making this whole file vacuously
    green -- discovery must find at least the 15 plugins known today,
    including both hardware protocol plugins."""
    discovered = discover_plugin_modules()
    assert len(discovered) >= 15
    assert "scottecom" in discovered
    assert "nbecom" in discovered


def _plugin_param_list():
    params = []
    for name in discover_plugin_modules():
        if name in KNOWN_BROKEN_MODULES:
            params.append(pytest.param(name, marks=pytest.mark.known_broken))
        else:
            params.append(pytest.param(name))
    return params


@pytest.mark.parametrize("module_name", _plugin_param_list())
def test_plugin_module_imports(module_name):
    """Layer 1: every descriptor-listed plugin module must import cleanly
    under Python 3, or skip with a named platform-unavailable reason.

    Any other failure (in particular a broken relative import left over
    from the Python 2 port) is a real migration defect and must FAIL loudly
    -- no bare except, no blanket skip on ModuleNotFoundError.
    """
    try:
        importlib.import_module("Pellmonsrv.plugins." + module_name)
    except ModuleNotFoundError as exc:
        if exc.name in PLATFORM_UNAVAILABLE:
            pytest.skip(
                "%s requires %s, unavailable on this platform (Linux/Pi-only); "
                "covered on the Linux CI runner" % (module_name, exc.name)
            )
        raise


def test_nbecom_deferred_protocol_import():
    """Layer 2: NBEcom's protocol import is deferred.

    `nbecom` passes Layer 1 because `from .nbeprotocol.protocol import Proxy`
    lives inside `nbecomplugin.activate()`
    (src/Pellmonsrv/plugins/nbecom/__init__.py), not at module level, so
    a naive per-module import loop would give it a false pass. This probe
    imports the deferred target directly. Previously failed under Python 2
    relative import syntax; now cleanly resolved in Phase 3 (IMPORT-02).
    """
    importlib.import_module("Pellmonsrv.plugins.nbecom.nbeprotocol.protocol")


def test_skip_allowlist_cannot_hide_migration_defects():
    """Tripwire: if a future contributor tries to quiet the red baseline by
    widening PLATFORM_UNAVAILABLE to include one of the actual broken
    migration-defect module names, this test fails."""
    assert PLATFORM_UNAVAILABLE.isdisjoint(
        {"protocol", "frames", "Scotteprotocol", "nbeprotocol", "datamap", "menus"}
    )


CORE_MODULES = [
    "Pellmonsrv.pellmonsrv",
    "Pellmonsrv.database",
    "Pellmonweb.pellmonweb",
    "Pellmonweb.pellmonconf",
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_modules_import(module_name):
    """Core-module parity with the legacy root `test-imports.py`: the four
    modules it covers must still import cleanly (or skip with a named
    platform-unavailable reason), making this suite a strict superset."""
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name in PLATFORM_UNAVAILABLE:
            pytest.skip(
                "%s requires %s, unavailable on this platform (Linux/Pi-only); "
                "covered on the Linux CI runner" % (module_name, exc.name)
            )
        raise
