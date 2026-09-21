import logging

import pytest
import serial


@pytest.fixture
def loop_serial():
    """Yield a real, in-process serial.Serial-compatible object backed by
    pyserial's loop:// URL handler -- no physical serial device required.

    Bytes written are immediately available to read back, making this
    suitable for exercising protocol encode/decode logic (Scotte/NBE frame
    round-trips, Phase 4) without any hardware attached.
    """
    ser = serial.serial_for_url("loop://", timeout=1)
    yield ser
    ser.close()


@pytest.fixture
def mocked_udp_socket(mocker):
    """Return a MagicMock standing in for socket.socket, pre-configured with
    a default recvfrom() response.

    mocker.patch("socket.socket") is applied *after* pytest-socket's own
    --disable-socket patch, so it takes precedence for the duration of the
    test -- this fixture is the only sanctioned way for a test to touch
    socket.socket while the suite-wide real-socket guardrail stays active.
    """
    mock_socket_cls = mocker.patch("socket.socket")
    mock_sock = mock_socket_cls.return_value
    mock_sock.recvfrom.return_value = (b"", ("0.0.0.0", 0))
    return mock_sock


@pytest.fixture
def cherrypy_request_ctx(mocker):
    """Patch cherrypy.request, cherrypy.session, and cherrypy.log with
    fakes, and return the fake request object.

    Codebase-specific gotcha: AuthController.check_credentials()
    (src/Pellmonweb/auth.py:149-151) has a bare `except:` whose own recovery
    code calls cherrypy.log(...cherrypy.request.headers["Remote-Addr"]...).
    Without this fixture, calling it raises a second, uncaught exception
    instead of returning the expected error string. Every test that calls
    an AuthController method must request this fixture.
    """
    import cherrypy

    fake_request = mocker.MagicMock()
    fake_request.headers = {"Remote-Addr": "127.0.0.1"}
    fake_request.script_name = ""
    mocker.patch.object(cherrypy, "request", fake_request)
    # cherrypy.session is only a real module attribute once a request/session
    # context is active (it's set dynamically by the SessionTool) -- outside
    # a live request it doesn't exist yet, so mock.patch needs create=True or
    # it raises AttributeError before the test body even runs.
    mocker.patch.object(cherrypy, "session", {}, create=True)
    mocker.patch.object(cherrypy, "log")
    return fake_request


@pytest.fixture(autouse=True)
def _restore_pellmon_logger():
    """Give every test the shared 'pellMon' logger it found.

    Building the daemon config (Pellmonsrv.pellmonsrv.config) sets the level and adds file
    handlers on this process-wide logger. Without this, one test's level leaks into the next
    (the default used to be DEBUG, which made unrelated tests pass by accident)."""
    logger = logging.getLogger('pellMon')
    level = logger.level
    handlers = list(logger.handlers)
    yield
    logger.setLevel(level)
    for handler in list(logger.handlers):
        if handler not in handlers:
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass
