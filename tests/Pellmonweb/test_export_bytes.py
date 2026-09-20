"""Bytes/str regression test for pellmonweb.PellMonWeb.export().

rrdtool xport output is bytes under Python 3; the endpoint ran str-pattern
re.sub on it (TypeError). Needs the real Linux stack (cherrypy, dbus, gi);
skipped where unavailable.

RED STATE: export() raises TypeError until the output is decoded.
"""

import json

import pytest

pytest.importorskip("cherrypy")
pytest.importorskip("dbus")
pytest.importorskip("gi")

XPORT = (b"{ about: 'RRDtool graph JSON output',\n  meta: {\n    start: 1758300000,\n    step: 60,\n"
         b"    end: 1758300060,\n    rows: 1,\n    columns: 1,\n    legend: [\n      'level'\n    ]\n  },\n"
         b"  data: [\n    [ 1.0e+02 ]\n  ]\n}\n")


class _FakePopen:
    returncode = 0

    def __init__(self, *a, **k):
        pass

    def communicate(self):
        return XPORT, b""


def test_export_parses_bytes_output(monkeypatch):
    web = pytest.importorskip("Pellmonweb.pellmonweb")
    monkeypatch.setattr(web, "polling", True, raising=False)
    monkeypatch.setattr(web, "colorsDict", {"x": "#ff0000"}, raising=False)
    monkeypatch.setattr(web, "graph_lines",
                        [{"name": "level", "color": "#ff0000", "ds_name": "ds"}], raising=False)
    monkeypatch.setattr(web, "logtick", None, raising=False)
    monkeypatch.setattr(web, "db", "d.rrd", raising=False)
    monkeypatch.setattr(web.subprocess, "Popen", _FakePopen)
    root = object.__new__(web.PellMonWeb)
    out = root.export(timespan="3600")
    data = json.loads(out)
    assert data[0]["label"] == "level"
    assert data[0]["data"][0][1] == 100.0
