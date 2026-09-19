"""Regression tests for two Scotte protocol bugs.

1. CRLF-mode GET retry must write the same singly-terminated frame as the
   first attempt (previously sent CRLF CRLF on the retry).
2. Protocol.setItem must return 'OK' on success and raise (ValueError for
   local validation, IOError for device rejection / no answer) instead of
   returning raw device reply text.
"""

import concurrent.futures
import importlib.util
import os
import queue
import sys
import threading
import time
from pathlib import Path

import pytest

from Scotteprotocol import Protocol

_SIM_PATH = Path(__file__).resolve().parents[1] / "tools" / "burner_sim.py"
_spec = importlib.util.spec_from_file_location("burner_sim_bugs", _SIM_PATH)
burner_sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(burner_sim)

needs_pty = pytest.mark.skipif(
    not hasattr(os, "openpty") or sys.platform == "win32",
    reason="pty unavailable on Windows",
)

CALL_TIMEOUT = 30


def bounded(fn, *args, timeout=CALL_TIMEOUT, **kwargs):
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        pytest.fail("call did not return within %s s (hang)" % timeout)
    finally:
        ex.shutdown(wait=False)


def _reset_shared_frames():
    from Scotteprotocol import frames
    for fid in burner_sim.FRAME_LAYOUT:
        f = getattr(frames, "Frame" + fid)
        f.readtime = 0.0
        f.indexWriteTime = [0.0] * len(f.dataDef)


@pytest.fixture(autouse=True)
def reset_frames():
    _reset_shared_frames()
    yield
    _reset_shared_frames()


class RecordingTransport:
    """Fake serial transport that records writes and never answers."""

    def __init__(self):
        self.writes = []
        self.lock = threading.Lock()

    def write(self, data):
        with self.lock:
            self.writes.append(bytes(data))

    def read(self, n=1):
        time.sleep(0.01)
        return b""

    def flushInput(self):
        pass

    def close(self):
        pass


# ---------------------------------------------------------------- bug 1

def test_crlf_get_retry_is_terminated_exactly_once():
    from Scotteprotocol import frames
    transport = RecordingTransport()
    protocol = Protocol(None, "6.99", transport=transport, start_thread=True)
    protocol.frame_term_crlf = True
    responses = queue.Queue(3)
    protocol.q.put(("FORCE_GET", frames.FrameZ00, responses))
    result = responses.get(True, 10)   # bounded: run() puts False after retry
    assert result is False
    assert len(transport.writes) == 2
    assert transport.writes[0] == transport.writes[1]
    for w in transport.writes:
        assert w.endswith(b"\r\n")
        assert w.count(b"\r\n") == 1
        assert b"\r\n\r\n" not in w


# ---------------------------------------------------------------- bug 2

@pytest.fixture
def sim_factory():
    sims = []
    protocols = []

    def make(**opts):
        opts.setdefault("seed", 1)
        opts.setdefault("freeze", True)
        sim = burner_sim.BurnerSim(**opts)
        path = sim.start()
        sims.append(sim)
        p = bounded(Protocol, path, "6.99")
        protocols.append(p)
        return sim, p

    yield make
    for p in protocols:
        try:
            p.ser.close()
        except Exception:
            pass
    for s in sims:
        s.stop()


@needs_pty
def test_setitem_success_returns_ok(sim_factory):
    sim, p = sim_factory()
    assert bounded(p.setItem, "boiler_temp_set", "65") == "OK"
    assert sim.table["Z00"][10] == 65


@needs_pty
def test_setitem_read_only_rejection_raises(sim_factory):
    sim, p = sim_factory(read_only=True)
    with pytest.raises(IOError) as ei:
        bounded(p.setItem, "boiler_temp_set", "65")
    assert "E1" not in str(ei.value) and "E0" not in str(ei.value)
    assert sim.table["Z00"][10] == 60


@needs_pty
def test_setitem_corrupt_checksum_reply_raises(sim_factory):
    sim, p = sim_factory()
    sim.corrupt_checksum_rate = 1.0
    with pytest.raises(IOError):
        bounded(p.setItem, "boiler_temp_set", "65")


@needs_pty
def test_setitem_no_answer_raises(sim_factory):
    sim, p = sim_factory()
    sim.offline_after = sim.command_count
    with pytest.raises(IOError) as ei:
        bounded(p.setItem, "boiler_temp_set", "65")
    assert "No answer" not in str(ei.value)


def test_setitem_local_validation_raises_valueerror():
    p = Protocol(None, "6.99", transport=RecordingTransport(), start_thread=False)
    with pytest.raises(ValueError):
        p.setItem("boiler_temp_set", "abc")
    with pytest.raises(ValueError):
        p.setItem("boiler_temp_set", "100000")
    with pytest.raises(ValueError):
        p.setItem("boiler_temp", "1")   # read-only, no address
