"""In-suite proof that the global socket guardrail is actually enforcing
(ROADMAP Phase 1 success criterion 4: "a real, unmocked socket call inside
a test fails loudly with SocketBlockedError rather than hanging or
silently succeeding").

`--disable-socket` lives in `pytest.ini` `addopts`, so it applies to the
entire suite with no per-test opt-in required -- every test in tests/ gets
this protection automatically, including future Phase 4 protocol tests.

Non-vacuity is proven separately (not in this file) by re-running with
`--force-enable-socket`, which must flip the two block-assertion tests to
failing -- see tests/README.md for the recorded output.
"""

import socket

import pytest
from pytest_socket import SocketBlockedError


def test_real_socket_construction_is_blocked():
    """A real UDP socket.socket() call, unmocked, must raise
    SocketBlockedError under the suite-wide --disable-socket guardrail."""
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def test_real_tcp_socket_construction_is_blocked():
    """Same assertion for TCP, covering the transport the NBE protocol
    also uses."""
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_mocked_udp_socket_fixture_bypasses_the_block(mocked_udp_socket):
    """The guardrail is a floor, not a wall: the sanctioned mocked_udp_socket
    fixture (tests/conftest.py) still works under --disable-socket."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(b"x", ("127.0.0.1", 1))
    mocked_udp_socket.sendto.assert_called_once_with(b"x", ("127.0.0.1", 1))
