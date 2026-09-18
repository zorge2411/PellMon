"""Unit tests for NBE protocol frame round-trips and Proxy.get() string semantics.

Verifies:
- Proxy.__init__ accepts constructor-injectable transport and start_threads parameter (PROTO-04).
- Request_frame encode/decode formatting, header length, and sequence number handling.
- Response_frame encode/decode and parse_payload() key-value parsing into str.
- Proxy.get() returns str for single parameters without TypeError (PROTO-01).
- Proxy.get(group=True) returns list of str for parameter groups without TypeError (PROTO-01).
- End-to-end request/response round-trip through injected transport without real hardware.
"""

from unittest.mock import MagicMock
import pytest

from Pellmonsrv.plugins.nbecom.nbeprotocol.frames import (
    Request_frame,
    Response_frame,
    START,
    END,
)
from Pellmonsrv.plugins.nbecom.nbeprotocol.protocol import Proxy


def test_proxy_init_injectable_transport():
    """Verify Proxy accepts an injectable transport and start_threads=False (PROTO-04)."""
    mock_transport = MagicMock()
    proxy = Proxy("testpass", transport=mock_transport, start_threads=False)

    assert proxy.s is mock_transport
    assert proxy.password == "testpass"
    assert proxy.controller_online is False
    assert not hasattr(proxy, "t")


def test_request_frame_encode_decode():
    """Verify Request_frame encode structure and decode field extraction."""
    req = Request_frame()
    req.function = 1
    req.sequencenumber = 42
    req.payload = "boiler.temp"

    encoded = req.encode()
    assert isinstance(encoded, bytes)
    # Header format: 12 (appid) + 6 (controllerid) + 1 (enc) = 19 prefix bytes
    assert len(req.appid) == 12
    assert encoded[19:20] == START
    assert encoded[20:22] == b"01"  # function
    assert encoded[22:24] == b"42"  # sequence number
    assert encoded[48:51] == b"011"  # payload size (11)
    assert encoded[51:62] == b"boiler.temp"
    assert encoded[62:63] == END

    req2 = Request_frame()
    req2.decode(encoded)
    assert req2.function == 1
    assert req2.sequencenumber == 42
    assert req2.payload == b"boiler.temp"


def test_response_frame_encode_decode_and_parse_payload():
    """Verify Response_frame encode/decode and parse_payload() string dictionary parsing."""
    req = Request_frame()
    req.sequencenumber = 15
    resp = Response_frame(req)
    resp.function = 1
    resp.status = 0
    resp.payload = "boiler.temp=65.5;boiler.state=3"

    encoded = resp.encode()
    assert isinstance(encoded, bytes)

    resp2 = Response_frame(req)
    resp2.decode(encoded)
    assert resp2.function == 1
    assert resp2.status == 0
    assert resp2.sequencenumber == 15
    assert isinstance(resp2.payload, str)
    assert resp2.payload == "boiler.temp=65.5;boiler.state=3"

    parsed = resp2.parse_payload()
    assert parsed == {"boiler.temp": "65.5", "boiler.state": "3"}
    for k, v in parsed.items():
        assert isinstance(k, str)
        assert isinstance(v, str)


def test_proxy_get_single_parameter_returns_str(mocker):
    """Verify Proxy.get() returns str value for single item without TypeError (PROTO-01)."""
    mock_transport = MagicMock()
    proxy = Proxy("secret", transport=mock_transport, start_threads=False)
    proxy.controller_online = True

    mock_resp = Response_frame(proxy.request)
    mock_resp.status = 0
    mock_resp.payload = "boiler.temp=65.5"
    mocker.patch.object(proxy, "make_request", return_value=mock_resp)

    val = proxy.get(1, "boiler.temp", group=False)
    assert val == "65.5"
    assert isinstance(val, str)
    assert not isinstance(val, bytes)


def test_proxy_get_parameter_group_returns_list_of_str(mocker):
    """Verify Proxy.get(group=True) returns list of str without TypeError (PROTO-01)."""
    mock_transport = MagicMock()
    proxy = Proxy("secret", transport=mock_transport, start_threads=False)
    proxy.controller_online = True

    mock_resp = Response_frame(proxy.request)
    mock_resp.status = 0
    mock_resp.payload = "temp=65.5;state=3;power=10"
    mocker.patch.object(proxy, "make_request", return_value=mock_resp)

    items = proxy.get(4, "*", group=True)
    assert items == ["temp=65.5", "state=3", "power=10"]
    assert isinstance(items, list)
    for item in items:
        assert isinstance(item, str)
        assert not isinstance(item, bytes)


def test_proxy_roundtrip_with_injected_transport():
    """Verify end-to-end request/response round-trip through injected transport (PROTO-04)."""
    mock_transport = MagicMock()
    proxy = Proxy("secret", transport=mock_transport, start_threads=False)
    proxy.controller_online = True
    proxy.addr = ("127.0.0.1", 1920)

    # Configure transport to respond with a valid encoded Response_frame
    def fake_recvfrom(bufsize):
        resp = Response_frame(proxy.request)
        resp.function = proxy.request.function
        resp.status = 0
        resp.payload = "boiler.temp=68.2"
        return resp.encode(), proxy.addr

    mock_transport.recvfrom.side_effect = fake_recvfrom

    val = proxy.get(1, "boiler.temp")
    assert val == "68.2"
    assert isinstance(val, str)
    assert mock_transport.sendto.called
    sent_data, sent_addr = mock_transport.sendto.call_args[0]
    assert isinstance(sent_data, bytes)
    assert sent_addr == ("127.0.0.1", 1920)
