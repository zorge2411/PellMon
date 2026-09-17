"""Import-stub fixture for `Pellmonsrv.pellmonsrv` (Phase 2 exception-
visibility testing).

Codebase-specific gotcha: `src/Pellmonsrv/pellmonsrv.py`'s module-level
import block requires `dbus`, `dbus.service`, `dbus.mainloop.glib.DBusGMainLoop`,
`gi.repository.GLib`/`GObject`, and `pwd`/`grp` -- all Linux-only and absent
on the documented `venv-py3` Windows dev interpreter. `pellmonsrv.py` also
evaluates `class MyDBUSService(dbus.service.Object)` and seven
`@dbus.service.method(...)`/`@dbus.service.signal(...)` decorators at class
*definition* time (import time), so a plain `MagicMock()` for `dbus.service`
is not sufficient -- the stub must supply a real subclassable `Object` and
decorator callables that return their wrapped function unchanged.

These stubs exist ONLY to make `Pellmonsrv.pellmonsrv` importable off-Linux
for exception-visibility testing (Phase 2, OBS-01/OBS-02). This is NOT a
production shim -- the daemon still requires real `python3-dbus`/`python3-gi`
system packages at runtime; nothing here is ever installed or imported
outside the pytest process.
"""

import importlib
import sys
from unittest.mock import MagicMock

import pytest

# Same module-name set `tests/test_plugin_imports.py`'s PLATFORM_UNAVAILABLE
# allowlist documents as Linux-only / not pip-installable on Windows.
_STUBBED_MODULE_NAMES = (
    "dbus",
    "dbus.service",
    "dbus.mainloop",
    "dbus.mainloop.glib",
    "gi",
    "gi.repository",
    "pwd",
    "grp",
)


class _IdentityDecoratorFactory:
    """Stands in for `dbus.service.method`/`dbus.service.signal`.

    `pellmonsrv.py` calls these as `@dbus.service.method('org.pellmon.int')`
    and `@dbus.service.method(dbus_interface=..., in_signature=..., out_signature=...)`
    at class-definition time -- accept any positional/keyword args and return
    an identity decorator so the wrapped method is left unchanged.
    """

    def __call__(self, *args, **kwargs):
        def identity_decorator(func):
            return func

        return identity_decorator


def _build_dbus_service_stub():
    stub = MagicMock(name="dbus.service")

    class Object:
        """Permissive stand-in for dbus.service.Object -- pellmonsrv.py
        subclasses this (`class MyDBUSService(dbus.service.Object)`)."""

        def __init__(self, *args, **kwargs):
            pass

    stub.Object = Object
    stub.method = _IdentityDecoratorFactory()
    stub.signal = _IdentityDecoratorFactory()
    stub.BusName = MagicMock(name="dbus.service.BusName")
    return stub


def _build_dbus_stub():
    stub = MagicMock(name="dbus")
    stub.service = _build_dbus_service_stub()
    stub.SessionBus = MagicMock(name="dbus.SessionBus")
    stub.SystemBus = MagicMock(name="dbus.SystemBus")
    return stub


def _build_dbus_mainloop_glib_stub():
    stub = MagicMock(name="dbus.mainloop.glib")
    stub.DBusGMainLoop = MagicMock(name="dbus.mainloop.glib.DBusGMainLoop")
    return stub


def _build_gi_repository_stub():
    stub = MagicMock(name="gi.repository")
    stub.GLib = MagicMock(name="gi.repository.GLib")
    stub.GObject = MagicMock(name="gi.repository.GObject")
    return stub


def _build_pwd_stub():
    stub = MagicMock(name="pwd")
    stub.getpwnam = MagicMock(name="pwd.getpwnam")
    return stub


def _build_grp_stub():
    stub = MagicMock(name="grp")
    stub.getgrall = MagicMock(name="grp.getgrall", return_value=[])
    stub.getgrnam = MagicMock(name="grp.getgrnam")
    stub.getgrgid = MagicMock(name="grp.getgrgid")
    return stub


_STUB_BUILDERS = {
    "dbus": _build_dbus_stub,
    "dbus.service": lambda: sys.modules["dbus"].service if "dbus" in sys.modules else _build_dbus_service_stub(),
    "dbus.mainloop": lambda: MagicMock(name="dbus.mainloop"),
    "dbus.mainloop.glib": _build_dbus_mainloop_glib_stub,
    "gi": lambda: MagicMock(name="gi"),
    "gi.repository": _build_gi_repository_stub,
    "pwd": _build_pwd_stub,
    "grp": _build_grp_stub,
}


@pytest.fixture
def daemon_module():
    """Import and yield `Pellmonsrv.pellmonsrv`, injecting sys.modules stubs
    for dbus/gi/pwd/grp only where those modules are not already importable
    (a no-op passthrough on real Linux/Docker where they ARE importable).

    Teardown removes every stub key this fixture injected, plus any
    `Pellmonsrv.pellmonsrv` / `Pellmonsrv.database` entries the import
    created, so the stubs can never leak into `tests/test_plugin_imports.py`'s
    real import checks (which must keep failing/skipping for genuine
    platform-unavailable reasons, not because a stub silently satisfied the
    import).
    """
    injected_keys = []

    for name in _STUBBED_MODULE_NAMES:
        if name in sys.modules:
            continue
        try:
            importlib.import_module(name)
            continue
        except ImportError:
            pass
        sys.modules[name] = _STUB_BUILDERS[name]()
        injected_keys.append(name)

    # dbus.service must be resolvable as an attribute of the dbus stub too,
    # in case dbus.service was injected before dbus itself picked it up.
    if "dbus" in sys.modules and not hasattr(sys.modules["dbus"], "service") and "dbus.service" in sys.modules:
        sys.modules["dbus"].service = sys.modules["dbus.service"]

    pellmonsrv_keys_before = {k for k in sys.modules if k == "Pellmonsrv" or k.startswith("Pellmonsrv.")}

    try:
        module = importlib.import_module("Pellmonsrv.pellmonsrv")
        yield module
    finally:
        pellmonsrv_keys_after = {k for k in sys.modules if k == "Pellmonsrv" or k.startswith("Pellmonsrv.")}
        for key in pellmonsrv_keys_after - pellmonsrv_keys_before:
            sys.modules.pop(key, None)
        for key in injected_keys:
            sys.modules.pop(key, None)
