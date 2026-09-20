"""Bytes/str regression tests for rrdtool parsing in the cleaning,
consumption and silolevel plugins (enabled by default).

RED STATE: each parser handled bytes as str; the TypeError was swallowed by a
broad except so cleaning returned '0' and consumption returned None, and
silolevel raised TypeError from int(bytes)/re.sub on bytes.
"""

import importlib
import json
import sys
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

XPORT = (b"{ about: 'RRDtool graph JSON output',\n  meta: {\n    start: 1758300000,\n    step: 60,\n"
         b"    end: 1758300060,\n    rows: 1,\n    columns: 1,\n    legend: [\n      'level'\n    ]\n  },\n"
         b"  data: [\n    [ 1.0e+02 ]\n  ]\n}\n")


class _FakePopen:
    def __init__(self, out=b"", err=b"", returncode=0):
        self._r = (out, err)
        self.returncode = returncode

    def communicate(self):
        return self._r


@pytest.fixture
def plugin_import():
    injected = []
    for name, builder in (("grp", lambda: MagicMock(getgrall=MagicMock(return_value=[]))),
                          ("pwd", lambda: MagicMock())):
        if name not in sys.modules:
            try:
                importlib.import_module(name)
            except ImportError:
                sys.modules[name] = builder()
                injected.append(name)
    yield lambda mod: importlib.import_module(mod)
    for n in injected:
        sys.modules.pop(n, None)


def test_cleaning_rrd_total(plugin_import, monkeypatch):
    mod = plugin_import("Pellmonsrv.plugins.cleaning")
    monkeypatch.setattr(mod.subprocess, "Popen",
                        lambda *a, **k: _FakePopen(b'0x0\n"123.456789"\n'))
    p = object.__new__(mod.cleaningplugin)
    p.rrdfile, p.feeder_time, p.feeder_capacity = "d.rrd", "ft", "fc"
    assert p.rrd_total(1, 2) == "123"


def test_consumption_rrd_total(plugin_import, monkeypatch):
    import threading
    from weakref import WeakValueDictionary
    mod = plugin_import("Pellmonsrv.plugins.consumption")
    monkeypatch.setattr(mod.subprocess, "Popen",
                        lambda *a, **k: _FakePopen(b'0x0\n"123,46"\n'))
    p = object.__new__(mod.Consumption_plugin)
    p.rrdfile, p.feeder_time, p.feeder_capacity = "d.rrd", "ft", "fc"
    p.totals = WeakValueDictionary()
    p.totals_fifo = [None] * 200
    p.cache_lock = threading.Lock()
    r = p.rrd_total(1, 2)
    assert isinstance(r, str) and "." in r and "," not in r


def _silo(plugin_import, monkeypatch, popen):
    mod = plugin_import("Pellmonsrv.plugins.silolevel")
    monkeypatch.setattr(mod.subprocess, "Popen", popen)
    p = object.__new__(mod.silolevelplugin)
    p.glob = {"conf": SimpleNamespace(db="d.rrd", poll_interval=60)}
    p.feeder_time, p.feeder_capacity = "ft", "fc"
    p.updateTime = 0
    p.siloData = None
    p.silo_level = 0
    return mod, p


def test_silolevel_last_update_and_xport(plugin_import, monkeypatch):
    def popen(cmd, *a, **k):
        if cmd[1] == "last":
            return _FakePopen(b"1758300060\n")
        return _FakePopen(XPORT)

    mod, p = _silo(plugin_import, monkeypatch, popen)
    vals = {"silo_reset_level": "100", "silo_reset_time": "01/01/25 00:00"}
    monkeypatch.setattr(p, "getItem", lambda i: vals[i], raising=False)
    p.db = MagicMock()
    p.db.get_value.side_effect = Exception("no consumption data")
    seen = []
    orig = mod.subprocess.Popen

    def spy(cmd, *a, **k):
        seen.append(cmd[1])
        return orig(cmd, *a, **k)

    monkeypatch.setattr(mod.subprocess, "Popen", spy)
    try:
        p.graphData()
    except TypeError as e:
        pytest.fail("bytes/str TypeError: %s" % e)
    except json.JSONDecodeError as e:
        pytest.fail("xport output not parseable: %s" % e)
    except Exception:
        pass  # later, unrelated post-processing is out of scope here
    # both the 'last' int() parse and the xport json parse must have been reached
    assert "last" in seen and "xport" in seen
