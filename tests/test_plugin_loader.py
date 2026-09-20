"""Real-PluginManager load test (quick 260919-jiz).

tests/test_plugin_imports.py uses plain importlib.import_module, which never
exercises the vendored yapsy loader. The loader used to exec plugin source
into a bare dict, so `from .scottecom import scottecom` failed with
KeyError "'__name__' not in globals". These tests drive the real loader.
"""

import configparser
import importlib
import logging
import pathlib

import pytest

from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.yapsy.PluginManager import PluginManager

PLUGINS_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "Pellmonsrv" / "plugins"

PLATFORM_UNAVAILABLE = {
    "grp",  # Unix-only stdlib, absent on Windows
    "pwd",  # Unix-only stdlib, absent on Windows
    "RPi",  # Raspberry Pi GPIO hardware library, not installable off-Pi
    "RPi.GPIO",  # submodule of the above
    "dbus",  # python3-dbus is a Linux system package
    "gi",  # PyGObject/GLib bindings, Linux system package
    "rrdtool",  # installed via apt on Linux only
    "pyownet",  # optional OWFS client used only by the owfs plugin
    "pyowm",  # optional OpenWeatherMap SDK used only by the openweathermap plugin
}

LOADER_ERROR = "Unable to execute the code in plugin"


def _descriptors():
    """Return {module: name} from every *.pellmon-plugin descriptor."""
    result = {}
    for descriptor in sorted(PLUGINS_DIR.glob("*.pellmon-plugin")):
        parser = configparser.ConfigParser()
        parser.read(descriptor, encoding="utf-8")
        result[parser["Core"]["Module"]] = parser["Core"]["Name"].strip()
    return result


DESCRIPTORS = _descriptors()


def _expected_loadable(name):
    try:
        importlib.import_module("Pellmonsrv.plugins." + name)
        return True, None
    except ModuleNotFoundError as exc:
        if exc.name in PLATFORM_UNAVAILABLE:
            return False, exc.name
        raise


def _new_manager():
    manager = PluginManager(categories_filter={"Protocols": protocols})
    manager.setPluginPlaces([str(PLUGINS_DIR)])
    return manager


@pytest.fixture
def loaded(caplog):
    caplog.set_level(logging.DEBUG, logger="pellMon")
    manager = _new_manager()
    manager.locatePlugins()
    manager.loadPlugins()
    return manager, caplog


def test_locate_plugins_finds_all_descriptors():
    """Guards against vacuous discovery: the real locatePlugins must find
    every descriptor, including scottecom and nbecom."""
    manager = _new_manager()
    assert manager.locatePlugins() >= 15
    found = {pathlib.Path(c[1]).parent.name for c in manager._candidates}
    assert set(DESCRIPTORS) <= found
    assert {"scottecom", "nbecom"} <= found


@pytest.mark.parametrize("module", sorted(DESCRIPTORS))
def test_every_available_plugin_loads(loaded, module):
    """Every plugin with importable deps must yield a live plugin object
    in the Protocols category through the real loader."""
    ok, missing = _expected_loadable(module)
    if not ok:
        pytest.skip("%s requires %s, unavailable on this platform" % (module, missing))
    manager, _ = loaded
    infos = [p for p in manager.getPluginsOfCategory("Protocols") if p.name == DESCRIPTORS[module]]
    assert infos, "plugin %s not collected" % module
    assert infos[0].plugin_object is not None
    assert isinstance(infos[0].plugin_object, protocols)


@pytest.mark.parametrize("module", sorted(DESCRIPTORS))
def test_no_loader_errors_for_available_plugins(loaded, module):
    """No loader error may be logged for a plugin whose deps are present."""
    ok, missing = _expected_loadable(module)
    if not ok:
        pytest.skip("%s requires %s, unavailable on this platform" % (module, missing))
    _, caplog = loaded
    segment = "%s%s__init__" % (module, __import__("os").sep)
    bad = [r for r in caplog.records
           if LOADER_ERROR in r.getMessage() and segment in r.getMessage()]
    assert not bad


def test_scottecom_relative_import_regression(loaded):
    """Regression: ScotteCom's PEP 328 relative import must resolve under
    the loader (was KeyError "'__name__' not in globals")."""
    manager, caplog = loaded
    infos = [p for p in manager.getPluginsOfCategory("Protocols") if p.name == DESCRIPTORS["scottecom"]]
    assert infos and infos[0].plugin_object is not None
    assert not [r for r in caplog.records if "'__name__' not in globals" in r.getMessage()
                or "'__name__' not in globals" in (r.exc_text or "")
                or (r.exc_info and "'__name__' not in globals" in str(r.exc_info[1]))]


def test_raise_on_error_propagates(tmp_path):
    """With raise_on_error set, a broken plugin must re-raise (debug mode);
    without it, the loop continues."""
    pdir = tmp_path / "bad"
    pdir.mkdir()
    (tmp_path / "bad.pellmon-plugin").write_text("[Core]\nName = Bad\nModule = bad\n")
    (pdir / "__init__.py").write_text("raise RuntimeError('boom')\n")
    manager = PluginManager(categories_filter={"Protocols": protocols})
    manager.setPluginPlaces([str(tmp_path)])
    manager.collectPlugins()
    assert manager.getPluginsOfCategory("Protocols") == []
    manager = PluginManager(categories_filter={"Protocols": protocols})
    manager.setPluginPlaces([str(tmp_path)])
    manager.raise_on_error = True
    with pytest.raises(RuntimeError):
        manager.collectPlugins()


def _broken_plugin_manager(tmp_path, raise_only_for):
    pdir = tmp_path / "bad"
    pdir.mkdir()
    (tmp_path / "bad.pellmon-plugin").write_text("[Core]\nName = Bad\nModule = bad\n")
    (pdir / "__init__.py").write_text("raise RuntimeError('boom')\n")
    manager = PluginManager(categories_filter={"Protocols": protocols})
    manager.setPluginPlaces([str(tmp_path)])
    manager.raise_on_error = True
    manager.raise_only_for = raise_only_for
    return manager


def test_raise_only_for_ignores_disabled_plugin_failures(tmp_path, caplog):
    """Debug mode must not abort because a plugin that is not enabled fails to load."""
    manager = _broken_plugin_manager(tmp_path, {"ScotteCom"})
    with caplog.at_level(logging.ERROR):
        manager.collectPlugins()
    assert manager.getPluginsOfCategory("Protocols") == []
    assert "Unable to execute the code in plugin" in caplog.text


def test_raise_only_for_raises_for_enabled_plugin(tmp_path):
    manager = _broken_plugin_manager(tmp_path, {"Bad"})
    with pytest.raises(RuntimeError):
        manager.collectPlugins()


def test_raise_only_for_default_raises_for_all(tmp_path):
    manager = _broken_plugin_manager(tmp_path, None)
    with pytest.raises(RuntimeError):
        manager.collectPlugins()


def test_platform_skip_allowlist_cannot_hide_defects():
    """Tripwire: the skip allowlist must never include real defect names."""
    assert PLATFORM_UNAVAILABLE.isdisjoint(
        {"protocol", "frames", "Scotteprotocol", "nbeprotocol", "datamap", "menus", "scottecom", "nbecom"}
    )
