"""Regression test for pellmonweb-cheroot-crash-no-restart.

WsHandler.ws() used to call dbus.getdb() with no try/except. ws4py's
WebSocketTool.upgrade() hook (before_request_body) already commits the HTTP
response to '101 Switching Protocols' + streaming *before* this handler runs.
When getdb() raised DbusNotConnected (e.g. pellmonsrv mid-restart), the
exception propagated out of the handler after the protocol switch had already
started. cherrypy's normal error-response path then collided with the
already-committed 101 response, while ws4py's on_end_request hook still
unconditionally detached the raw socket and handed it to WebSocketManager --
corrupting the connection. Minutes later cheroot's HTTP server thread crashed
reading/closing that same corrupted connection (AttributeError, then OSError:
Bad file descriptor), taking the whole HTTP server down without exiting the
process (see the companion test in test_engine_exit_process_restart.py for
that half of the fix).

Needs the real Linux stack (cherrypy, dbus, gi); skipped where unavailable.

RED STATE (pre-fix): ws() re-raises DbusNotConnected straight out of the
handler once the websocket upgrade has already begun.
"""

import pytest

pytest.importorskip("cherrypy")
pytest.importorskip("dbus")
pytest.importorskip("gi")


class _DownDbus:
    """Stands in for Dbus_handler when pellmonsrv is not reachable."""

    def getdb(self):
        web = pytest.importorskip("Pellmonweb.pellmonweb")
        raise web.DbusNotConnected("server not running")


class _FakeRequest:
    def __init__(self, ws_handler):
        self.ws_handler = ws_handler


class _FakeWsHandler:
    def __init__(self):
        self.closed_with = None

    def close(self, reason=''):
        self.closed_with = reason


def test_ws_does_not_raise_when_dbus_down(monkeypatch):
    """The handler must not let DbusNotConnected propagate once the ws4py
    upgrade hook has already committed the HTTP response -- doing so is what
    corrupted the connection and crashed cheroot on real hardware."""
    web = pytest.importorskip("Pellmonweb.pellmonweb")
    monkeypatch.setattr(web, "dbus", _DownDbus(), raising=False)

    fake_ws_handler = _FakeWsHandler()
    monkeypatch.setattr(web.cherrypy, "request", _FakeRequest(fake_ws_handler), raising=False)

    handler = web.WsHandler()
    # Must not raise.
    handler.ws(parameters='foo,bar', events='no')

    # And it should close the already-upgraded connection instead of
    # leaving the client believing it has a live (but silently dead forever)
    # websocket.
    assert fake_ws_handler.closed_with is not None


def test_ws_registers_sensor_when_dbus_up(monkeypatch):
    """Sanity check: the happy path (dbus reachable) is unaffected by the fix."""
    web = pytest.importorskip("Pellmonweb.pellmonweb")

    class _UpDbus:
        def getdb(self):
            return {'foo': {}, 'bar': {}}

        def getItem(self, name):
            return 'x'

    # Sensor.__init__ schedules a Timer(0.1, ...) that reads the module-global
    # `dbus` after this test (and monkeypatch's teardown) may already have
    # finished -- set it directly instead of via monkeypatch so the timer
    # callback doesn't see a reverted/missing global from a torn-down fixture.
    original_dbus = getattr(web, "dbus", None)
    web.dbus = _UpDbus()
    fake_ws_handler = _FakeWsHandler()
    monkeypatch.setattr(web.cherrypy, "request", _FakeRequest(fake_ws_handler), raising=False)

    web.Sensor.sensorlist = []
    try:
        handler = web.WsHandler()
        handler.ws(parameters='foo,bar', events='no')

        assert len(web.Sensor.sensorlist) == 1
        assert fake_ws_handler.closed_with is None
    finally:
        web.Sensor.sensorlist = []
        import time
        time.sleep(0.15)  # let the Timer fire while `dbus` is still valid
        web.dbus = original_dbus
