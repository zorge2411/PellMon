"""Demonstrates the two hardware-mock fixtures (loop_serial, mocked_udp_socket)
work end to end with zero physical hardware attached.

These fixtures are the hardware-mock boundary that Phase 4 (PROTO-04) will
wire Protocol/Proxy into. This file deliberately stays self-contained until
then -- it must NOT import Scotteprotocol or Pellmonsrv.plugins.nbecom.nbeprotocol,
both of which are import-broken today (IMPORT-01/IMPORT-02, Phase 3) and
neither has a constructor-injectable transport yet (that seam is PROTO-04,
Phase 4). This test proves the mechanism is ready for Phase 4 to plug into.
"""

import socket


def test_loop_serial_roundtrip(loop_serial):
    loop_serial.write(b"\x02TEST\x03")
    loop_serial.flush()
    assert loop_serial.read(7) == b"\x02TEST\x03"


def test_udp_send_uses_mock_not_real_network(mocked_udp_socket):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"ping", ("127.0.0.1", 1920))
    mocked_udp_socket.sendto.assert_called_once_with(b"ping", ("127.0.0.1", 1920))
    assert mocked_udp_socket.recvfrom() == (b"", ("0.0.0.0", 0))
