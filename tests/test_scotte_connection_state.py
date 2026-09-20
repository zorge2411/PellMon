"""Connection state machine of Scotteprotocol.Protocol (states: connected,
no_connection, demo). Replaces the old silent dummy-data fallback."""

import importlib.util
import os
import sys
import time
from pathlib import Path

import pytest

from Scotteprotocol import Protocol
import Scotteprotocol.protocol as protocol_module

_SIM_PATH = Path(__file__).resolve().parents[1] / "tools" / "burner_sim.py"
_spec = importlib.util.spec_from_file_location("burner_sim", _SIM_PATH)
burner_sim = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(burner_sim)

from test_burner_sim_pty import bounded, _reset_shared_frames, needs_pty, burner_sim_factory  # noqa: E402,F401


class SilentTransport:
    """Transport that never answers."""

    def flushInput(self):
        pass

    def write(self, data):
        return len(data)

    def read(self, n=1):
        time.sleep(0.01)
        return b""

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fresh_frames():
    _reset_shared_frames()
    yield
    _reset_shared_frames()


def test_threshold_constant_is_three():
    assert protocol_module.FAILURE_THRESHOLD == 3


def test_nonexistent_port_serves_nothing():
    p = bounded(Protocol, "/nonexistent/ttyXYZ", "auto")
    assert p.connection_state == "no_connection"
    assert "/nonexistent/ttyXYZ" in p.connection_reason
    assert not p.is_alive()          # no poll thread
    with pytest.raises(IOError):
        p.getItem("power")
    with pytest.raises(IOError):
        p.setItem("boiler_temp_set", "65")
    assert "power" in p.getDataBase()  # item names still registered


def test_demo_mode_is_explicit():
    p = Protocol(None, "")
    assert p.connection_state == "demo"
    assert "simulated" in p.connection_reason
    assert p.getItem("power") == "1234"


def test_silent_transport_flips_after_three_giveups():
    p = Protocol(None, "6.99", transport=SilentTransport())
    assert p.connection_state == "connected"
    seen = []
    p.on_connection_change = lambda s, r: seen.append((s, r))
    # three distinct frames so each getItem does a real poll
    for i, name in enumerate(["boiler_temp_min", "power", "boiler_temp_set"]):
        assert p.connection_state == "connected", "flipped too early at %d" % i
        with pytest.raises(IOError):
            bounded(p.getItem, name)
    assert p.connection_state == "no_connection"
    assert "burner not answering" in p.connection_reason
    assert len(seen) == 1 and seen[0][0] == "no_connection"


@needs_pty
def test_full_cycle_connected_lost_recovered(burner_sim_factory):
    sim, path, p = burner_sim_factory()
    changes = []
    p.on_connection_change = lambda s, r: changes.append(s)
    assert bounded(p.getItem, "power") == "64"
    assert p.connection_state == "connected"

    sim.offline_after = sim.command_count
    for _ in range(protocol_module.FAILURE_THRESHOLD + 2):
        if p.connection_state == "no_connection":
            break
        with pytest.raises(IOError):
            bounded(p.getItem, "boiler_temp_min")
    assert p.connection_state == "no_connection"

    sim.offline_after = None
    assert bounded(p.getItem, "boiler_temp_min") == "30"
    assert p.connection_state == "connected"
    # exactly one callback per transition, not one per poll
    assert changes == ["no_connection", "connected"]


def test_callback_exception_does_not_break_state():
    p = Protocol(None, "6.99", transport=SilentTransport())

    def boom(s, r):
        raise RuntimeError("consumer bug")

    p.on_connection_change = boom
    p._set_connection_state("no_connection", "x")
    assert p.connection_state == "no_connection"


def test_callback_fires_once_per_transition():
    p = Protocol(None, "6.99", transport=SilentTransport())
    seen = []
    p.on_connection_change = lambda s, r: seen.append(s)
    for _ in range(5):
        p._set_connection_state("no_connection", "x")
    p._set_connection_state("connected", "")
    p._set_connection_state("connected", "")
    assert seen == ["no_connection", "connected"]
