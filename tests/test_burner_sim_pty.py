"""pty-based integration tests: Scotteprotocol.Protocol against tools/burner_sim.py.

Unlike the loop:// tests, these exercise the real serial code path
(Protocol.__init__ with a device name, the poll thread, Frame.parse, setItem).
Tests that need a pty skip on Windows; the pure in-process ones still run.
"""

import concurrent.futures
import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

from Scotteprotocol import Protocol
from Scotteprotocol.datamap import dataBaseMap, param
from Scotteprotocol.enumerations import dataEnumerations

_SIM_PATH = Path(__file__).resolve().parents[1] / "tools" / "burner_sim.py"
_spec = importlib.util.spec_from_file_location("burner_sim", _SIM_PATH)
burner_sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(burner_sim)

needs_pty = pytest.mark.skipif(
    not hasattr(os, "openpty") or sys.platform == "win32",
    reason="pty unavailable on Windows",
)

# generous hard bounds so a hang fails the test instead of blocking the suite
CALL_TIMEOUT = 30


def bounded(fn, *args, timeout=CALL_TIMEOUT, **kwargs):
    """Run fn on a worker thread; a hang surfaces as a test failure."""
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        pytest.fail("call did not return within %s s (hang)" % timeout)
    finally:
        ex.shutdown(wait=False)


def _reset_shared_frames():
    """Frame objects in Scotteprotocol.frames are module-level singletons, so
    readtime/indexWriteTime leak between Protocol instances (and tests)."""
    from Scotteprotocol import frames
    for fid in burner_sim.FRAME_LAYOUT:
        f = getattr(frames, "Frame" + fid)
        f.readtime = 0.0
        f.indexWriteTime = [0.0] * len(f.dataDef)


@pytest.fixture
def burner_sim_factory():
    _reset_shared_frames()
    sims = []
    protocols = []

    def make(version="6.99", connect=True, **opts):
        opts.setdefault("seed", 1)
        opts.setdefault("freeze", True)
        sim = burner_sim.BurnerSim(**opts)
        path = sim.start()
        sims.append(sim)
        protocol = None
        if connect:
            protocol = bounded(Protocol, path, version)
            protocols.append(protocol)
        return sim, path, protocol

    yield make
    for p in protocols:
        try:
            p.ser.close()
        except Exception:
            pass
    for s in sims:
        s.stop()
    _reset_shared_frames()


# ------------------------------------------------------------ pure (no pty)

def test_sim_tables_match_scotteprotocol_datamap():
    """The simulator's write map must agree with src/Scotteprotocol/datamap.py."""
    seen = set()
    for name, mappings in dataBaseMap.items():
        for versions, m in mappings.items():
            if not isinstance(m, param):
                continue
            if not (versions[0] <= "6.99" < versions[1]):
                continue
            addr = m.address
            seen.add(addr)
            assert addr in burner_sim.WRITE_MAP, "sim lacks address %s (%s)" % (addr, name)
            fid, idx, dec = burner_sim.WRITE_MAP[addr][:3]
            assert (fid, idx, dec) == (m.frame.pollFrame[:3], m.index, m.decimals), name
    assert seen <= set(burner_sim.WRITE_MAP)


def test_sim_frame_layouts_match_scotteprotocol():
    from Scotteprotocol import frames
    for fid, widths in burner_sim.FRAME_LAYOUT.items():
        assert widths == getattr(frames, "Frame" + fid).dataDef


def test_sim_error_responses_in_process():
    sim = burner_sim.BurnerSim(seed=1, freeze=True)
    ok_cmd = burner_sim.add_checksum("B010060").encode("latin-1")
    bad_cmd = ok_cmd[:-1] + bytes([ok_cmd[-1] ^ 1])
    assert sim.handle_command(bad_cmd) == burner_sim.add_checksum("E0").encode("latin-1")
    unknown_write = burner_sim.add_checksum("Q990010").encode("latin-1")
    assert sim.handle_command(unknown_write) == burner_sim.add_checksum("E1").encode("latin-1")
    unknown_frame = burner_sim.add_checksum("Z990000").encode("latin-1")
    assert sim.handle_command(unknown_frame) == burner_sim.add_checksum("E1").encode("latin-1")
    assert sim.handle_command(ok_cmd) == burner_sim.add_checksum("OK").encode("latin-1")
    assert sim.table["Z00"][10] == 60


def test_sim_drift_is_seed_deterministic_and_bounded():
    a = burner_sim.BurnerSim(seed=7)
    b = burner_sim.BurnerSim(seed=7)
    start = a.table["Z02"][0]
    for _ in range(50):
        a.tick(3.0)
        b.tick(3.0)
    assert a.table == b.table
    assert 500 <= a.table["Z00"][2] <= 800
    assert a.table["Z02"][0] > start


# ------------------------------------------------------------------ pty tests

@needs_pty
def test_read_roundtrip(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    assert bounded(p.getItem, "power") == "64"
    assert bounded(p.getItem, "boiler_temp") == "58.2"
    mode = bounded(p.getItem, "mode")
    assert mode == dataEnumerations["mode"][sim.table["Z00"][16]] == "Running"
    assert bounded(p.getItem, "version").lstrip() == "6.99"
    assert any(c.startswith(b"Z000000") for c in sim.received_commands)


@needs_pty
def test_auto_version_detection(burner_sim_factory):
    sim, path, p = burner_sim_factory(version="auto")
    assert p.checksum is True and p.frame_term_crlf is False
    assert "chimney_draught" not in p.getDataBase()  # 6.99 >= 6.85
    assert bounded(p.getItem, "boiler_temp") == "58.2"


@needs_pty
def test_write_roundtrip(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    assert bounded(p.setItem, "boiler_temp_set", "65") == "OK"
    assert burner_sim.add_checksum("B010065").encode("latin-1") in sim.received_commands
    assert sim.table["Z00"][10] == 65
    # getItem re-polls for ~4 s after a write
    assert bounded(p.getItem, "boiler_temp_set") == "65"


@needs_pty
def test_command_write_changes_mode(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    assert bounded(p.setItem, "burner_off", "0") == "OK"
    assert sim.table["Z00"][16] == burner_sim.MODE_STOPPED


@needs_pty
def test_dropped_frames_do_not_hang(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    sim.drop_rate = 1.0
    t0 = time.time()
    with pytest.raises(IOError):
        bounded(p.getItem, "boiler_temp_min")   # Z01 not yet read -> real poll
    assert time.time() - t0 < 15
    assert sim.received_commands[-1].startswith(b"Z010000")


@needs_pty
def test_corrupt_checksum_handled(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    sim.corrupt_checksum_rate = 1.0
    t0 = time.time()
    with pytest.raises(IOError):
        bounded(p.getItem, "boiler_temp_min")
    assert time.time() - t0 < 15
    polls = [c for c in sim.received_commands if c.startswith(b"Z010000")]
    assert len(polls) == 2   # first attempt + one retry, then give up


@needs_pty
def test_delay_slows_but_succeeds(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    sim.delay = 0.3
    t0 = time.time()
    assert bounded(p.getItem, "boiler_temp_min") == "30"
    assert time.time() - t0 >= 0.3


@needs_pty
def test_offline_after_stops_answering(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    sim.offline_after = sim.command_count
    with pytest.raises(IOError):
        bounded(p.getItem, "boiler_temp_min")


@needs_pty
def test_read_only_mode_rejects_writes(burner_sim_factory):
    sim, path, p = burner_sim_factory(read_only=True)
    result = bounded(p.setItem, "boiler_temp_set", "65")
    assert result != "OK"
    assert sim.table["Z00"][10] == 60


@needs_pty
def test_pytest_socket_guardrail_not_triggered(burner_sim_factory):
    """ptys are file descriptors, so --disable-socket must not interfere."""
    import socket
    import pytest_socket
    sim, path, p = burner_sim_factory()
    assert bounded(p.getItem, "power") == "64"
    with pytest.raises(pytest_socket.SocketBlockedError):
        socket.socket()
