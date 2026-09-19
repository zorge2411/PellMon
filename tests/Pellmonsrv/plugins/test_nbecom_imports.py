"""Unit tests for NBEcom and nbeprotocol imports and instantiation (IMPORT-02).

Verifies that:
- Pellmonsrv.plugins.nbecom imports and nbecomplugin instantiates cleanly.
- nbeprotocol.protocol imports and Proxy instantiates with expected attributes.
- nbeprotocol.frames imports and Request_frame instantiates.
- nbeprotocol.language and langmap are accessible.
"""

import threading
import pytest

import Pellmonsrv.plugins.nbecom as nbecom_mod
from Pellmonsrv.plugins.nbecom.nbeprotocol import protocol as protocol_mod
from Pellmonsrv.plugins.nbecom.nbeprotocol import frames as frames_mod
from Pellmonsrv.plugins.nbecom.nbeprotocol import language as language_mod


def test_nbecom_plugin_import_and_instantiation():
    """Verify Pellmonsrv.plugins.nbecom imports and nbecomplugin instantiates."""
    plugin = nbecom_mod.nbecomplugin()
    assert plugin is not None
    assert hasattr(plugin, "activate")
    assert hasattr(plugin, "getItem")
    assert hasattr(plugin, "setItem")


def test_nbeprotocol_proxy_import_and_instantiation(mocked_udp_socket, monkeypatch):
    """Verify nbeprotocol Proxy imports and instantiates with expected attributes."""
    # Prevent background discovery threads from launching during unit test
    monkeypatch.setattr(
        threading,
        "Thread",
        lambda target, **kw: type("MockThread", (), {"setDaemon": lambda self, d: None, "start": lambda self: None})(),
    )

    proxy = protocol_mod.Proxy("testpass")
    assert proxy is not None
    assert proxy.password == "testpass"
    assert proxy.controller_online is False
    assert proxy.connected is False
    assert proxy.discover_addr == (None, 1920)
    assert hasattr(proxy, "request")
    assert hasattr(proxy, "response")
    assert isinstance(proxy.request, frames_mod.Request_frame)
    assert isinstance(proxy.response, frames_mod.Response_frame)


def test_nbeprotocol_request_frame_instantiation():
    """Verify nbeprotocol Request_frame instantiates and has expected fields."""
    frame = frames_mod.Request_frame()
    assert frame is not None
    assert frame.REQUEST_HEADER_SIZE == 52
    assert frame.controllerid == "id"
    assert frame.encrypted is False
    assert frame.sequencenumber == 0
    assert frame.pincode == "0123456789"
    assert frame.payload == ""
    assert len(frame.appid) == 12


def test_nbeprotocol_response_frame_instantiation():
    """Verify nbeprotocol Response_frame instantiates with a Request_frame."""
    req = frames_mod.Request_frame()
    resp = frames_mod.Response_frame(req)
    assert resp is not None
    assert resp.request is req


def test_nbeprotocol_language_import_and_mappings():
    """Verify nbeprotocol language module loads language properties and mappings."""
    assert hasattr(language_mod, "lang_value_to_text")
    assert len(language_mod.lang_value_to_text) > 0
    assert hasattr(language_mod, "enumdicts")
