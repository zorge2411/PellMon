# -*- coding: utf-8 -*-
"""Automated protocol coexistence test (IMPORT-04).

Verifies that:
- Scotteprotocol and Pellmonsrv.plugins.nbecom.nbeprotocol coexist in the same
  process without module collision or namespace shadowing.
- sys.modules entries for 'protocol' and 'frames' under both packages remain
  strictly distinct module objects.
- Scotteprotocol.Protocol and nbeprotocol.Proxy can be instantiated in the same
  test without interfering with each other's operation or attributes.
"""

import sys
import threading
import pytest

import Scotteprotocol.protocol
import Scotteprotocol.frames
import Pellmonsrv.plugins.nbecom.nbeprotocol.protocol
import Pellmonsrv.plugins.nbecom.nbeprotocol.frames


def test_protocol_coexistence(mocked_udp_socket, monkeypatch):
    """Verify that Scotteprotocol and nbeprotocol coexist in the same process
    with zero namespace collision (IMPORT-04)."""
    # 1. Assert sys.modules['Scotteprotocol.protocol'] and
    # sys.modules['Pellmonsrv.plugins.nbecom.nbeprotocol.protocol'] are distinct.
    scotte_proto_mod = sys.modules["Scotteprotocol.protocol"]
    nbe_proto_mod = sys.modules["Pellmonsrv.plugins.nbecom.nbeprotocol.protocol"]
    assert scotte_proto_mod is not nbe_proto_mod
    assert scotte_proto_mod.__name__ == "Scotteprotocol.protocol"
    assert nbe_proto_mod.__name__ == "Pellmonsrv.plugins.nbecom.nbeprotocol.protocol"

    # 2. Assert sys.modules['Scotteprotocol.frames'] and
    # sys.modules['Pellmonsrv.plugins.nbecom.nbeprotocol.frames'] are distinct.
    scotte_frames_mod = sys.modules["Scotteprotocol.frames"]
    nbe_frames_mod = sys.modules["Pellmonsrv.plugins.nbecom.nbeprotocol.frames"]
    assert scotte_frames_mod is not nbe_frames_mod
    assert scotte_frames_mod.__name__ == "Scotteprotocol.frames"
    assert nbe_frames_mod.__name__ == "Pellmonsrv.plugins.nbecom.nbeprotocol.frames"

    # Distinct attributes check
    assert hasattr(scotte_frames_mod, "FrameZ00")
    assert hasattr(nbe_frames_mod, "Request_frame")
    assert not hasattr(scotte_frames_mod, "Request_frame")
    assert not hasattr(nbe_frames_mod, "FrameZ00")

    # 3. Instantiate Scotteprotocol.Protocol(None, '6.99') and nbeprotocol.Proxy('testpass')
    # Prevent background discovery threads from launching in nbeprotocol.Proxy
    monkeypatch.setattr(
        threading,
        "Thread",
        lambda target, **kw: type("MockThread", (), {"setDaemon": lambda self, d: None, "start": lambda self: None})(),
    )

    scotte_proto = Scotteprotocol.protocol.Protocol(None, "6.99")
    nbe_proxy = Pellmonsrv.plugins.nbecom.nbeprotocol.protocol.Proxy("testpass")

    # Confirm neither interferes with the other's operation or attributes
    assert scotte_proto is not None
    assert scotte_proto.dummyDevice is True
    assert scotte_proto.checksum is True
    assert isinstance(scotte_proto.dataBase, dict)
    assert "power" in scotte_proto.dataBase
    assert "boiler_temp" in scotte_proto.dataBase

    assert nbe_proxy is not None
    assert nbe_proxy.password == "testpass"
    assert nbe_proxy.controller_online is False
    assert nbe_proxy.connected is False
    assert hasattr(nbe_proxy, "request")
    assert hasattr(nbe_proxy, "response")
    assert isinstance(nbe_proxy.request, Pellmonsrv.plugins.nbecom.nbeprotocol.frames.Request_frame)
    assert isinstance(nbe_proxy.response, Pellmonsrv.plugins.nbecom.nbeprotocol.frames.Response_frame)
