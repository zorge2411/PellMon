"""Bytes/str regression tests for pellmonsrv.py's rrdtool call sites.

`subprocess.check_output` / `Popen.communicate` return bytes under Python 3;
the daemon parsed them as str (`s.split('\n')`, `out.rstrip('\n')`), which
killed the daemon at startup in every default deployment.

RED STATE: `read_lastupdate(db_path)` (module-level helper extracted from
MyDaemon.run()) does not exist yet, so the lastupdate tests fail with
AttributeError; the Poller test fails with TypeError from bytes.rstrip(str).
The fix turns this file GREEN.
"""

import logging
import threading
from types import SimpleNamespace

import pytest

FRESH = b"feeder_time boiler_temp power\n\n1758300000: U U U\n"
POPULATED = b"feeder_time boiler_temp power\n\n1758300060: 12 73.5 30\n"


def test_read_lastupdate_fresh_db(daemon_module, monkeypatch):
    monkeypatch.setattr(daemon_module.subprocess, "check_output",
                        lambda *a, **k: FRESH)
    t, d = daemon_module.read_lastupdate("x.rrd")
    assert t == 1758300000
    assert d == {"feeder_time": "U", "boiler_temp": "U", "power": "U"}


def test_read_lastupdate_populated_db(daemon_module, monkeypatch):
    monkeypatch.setattr(daemon_module.subprocess, "check_output",
                        lambda *a, **k: POPULATED)
    t, d = daemon_module.read_lastupdate("x.rrd")
    assert t == 1758300060
    assert d["boiler_temp"] == "73.5"


@pytest.mark.parametrize("out", [b"", b"header\n"])
def test_read_lastupdate_short_output(daemon_module, monkeypatch, out):
    monkeypatch.setattr(daemon_module.subprocess, "check_output",
                        lambda *a, **k: out)
    t, d = daemon_module.read_lastupdate("x.rrd")
    assert isinstance(t, int) and t > 0
    assert d == {}


def test_poller_failed_update_logs_decoded_text(daemon_module, monkeypatch, mocker, caplog):
    class _Stop(Exception):
        pass

    class _DB(dict):
        def __getitem__(self, k):
            return SimpleNamespace(value="1.5")

    conf = SimpleNamespace(polling=True, pollData=[{"name": "a", "ds_type": "GAUGE"}],
                           database=_DB(), lastupdate_time=0, db="d.rrd",
                           lastupdate={})
    monkeypatch.setattr(daemon_module, "conf", conf, raising=False)
    popen = mocker.patch.object(daemon_module.subprocess, "Popen")
    popen.return_value.communicate.return_value = (b"", b"ERROR: bad update\n")
    popen.return_value.returncode = 1
    mocker.patch.object(daemon_module.time, "sleep", side_effect=_Stop)

    poller = object.__new__(daemon_module.Poller)
    poller.ev = threading.Event()
    poller.ev.set()
    poller.timesync_wait = 0

    with caplog.at_level(logging.DEBUG, logger="pellMon"):
        with pytest.raises(_Stop):
            poller.run()

    msgs = [r.getMessage() for r in caplog.records]
    assert any("ERROR: bad update" in m for m in msgs), msgs
    assert not any("error in polling" in m for m in msgs), msgs
