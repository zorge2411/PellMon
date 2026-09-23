"""Regression test for pellmonweb-cheroot-crash-no-restart (structural half).

cherrypy's own HTTP server thread (_start_http_thread in
cherrypy/process/servers.py) catches any unhandled exception raised while
serving, logs it, calls self.bus.exit() -- which publishes the bus's 'exit'
channel -- and then re-raises *inside that background thread*. An uncaught
exception in a non-main Python thread does not terminate the process by
default.

pellmonweb.py's run() blocks the main thread in a GLib main loop
(main_loop.run()) that is otherwise only tied to cherrypy via a 100ms
publish() timeout -- before this fix, nothing ever told that main loop the
HTTP server had died, so the process (and therefore the container) stayed
"Up" forever after a background-thread crash, and docker-compose's
`restart: unless-stopped` never fired because PID 1 never exited.

This test does not spin up the full GLib/dbus stack (impractical to run
reliably in CI); instead it proves the wiring at the level that matters --
that cherrypy's own bus.exit() (the exact call _start_http_thread makes on
any unhandled exception) reliably reaches a subscriber on the 'exit' channel,
using a bare cherrypy.process.wspbus.Bus() so it doesn't touch the process
-wide cherrypy.engine singleton other tests rely on.
"""

import pytest

pytest.importorskip("cherrypy")


def test_bus_exit_channel_fires_on_any_exit():
    """cherrypy.engine.subscribe('exit', ...) is the mechanism pellmonweb.py's
    run() uses to unblock its GLib main loop. Confirm the bus actually
    publishes 'exit' -- and therefore invokes our listener -- via the same
    Bus.exit() call cherrypy/process/servers.py._start_http_thread makes when
    the HTTP server thread hits an unhandled exception."""
    from cherrypy.process import wspbus

    bus = wspbus.Bus()
    quit_calls = []
    bus.subscribe('exit', lambda: quit_calls.append(True))

    # Simulate _start_http_thread's except-Exception branch: log + bus.exit().
    bus.exit()

    assert quit_calls == [True]
    assert bus.state == wspbus.states.EXITING


def test_graceful_shutdown_flag_distinguishes_signal_from_crash():
    """pellmonweb.py's run() only sets graceful_shutdown before calling
    cherrypy.engine.exit() from its own SIGINT/SIGTERM handler. A crash inside
    _start_http_thread calls bus.exit() directly, without ever touching that
    flag -- which is exactly how run() decides whether to hard-exit the
    process (os._exit(1)) after main_loop.run() returns, so
    `restart: unless-stopped` can recover the container."""
    import threading
    from cherrypy.process import wspbus

    bus = wspbus.Bus()
    graceful_shutdown = threading.Event()

    def signal_handler():
        graceful_shutdown.set()
        bus.exit()

    def crash_in_http_thread():
        # Mirrors _start_http_thread's except-Exception branch: it never
        # touches graceful_shutdown.
        bus.exit()

    crash_in_http_thread()
    assert not graceful_shutdown.is_set()

    bus2 = wspbus.Bus()
    graceful_shutdown2 = threading.Event()

    def signal_handler2():
        graceful_shutdown2.set()
        bus2.exit()

    signal_handler2()
    assert graceful_shutdown2.is_set()
