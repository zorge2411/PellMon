---
status: awaiting_human_verify
trigger: "During the same real-Pi Phase 8 checklist step 7 retest that confirmed the D-Bus reconnect fix (v2.0.4) working, a WebSocket upgrade request raced against pellmonsrv still being restarted, got a DbusNotConnected 500 from Dbus_handler.getdb(), and moments later cheroot (the CherryPy HTTP server) hit an unhandled AttributeError/OSError and the whole HTTP server thread died ('ENGINE Bus EXITED'). Unlike a normal crash, the pellmonweb container did NOT restart itself afterward -- docker-compose.yml sets `restart: unless-stopped` on pellmonweb, but no automatic recovery happened. Operator had to run `docker compose stop` (all 4 containers) then `docker compose up -d` to bring the stack back to healthy."
created: 2026-09-23T15:05:00Z
updated: 2026-09-23T15:05:00Z
---

## Current Focus
<!-- OVERWRITE on each update - always reflects NOW -->

hypothesis: CONFIRMED (two-part root cause, see Resolution).
test: n/a -- confirmed via direct source reading of cherrypy/process/servers.py,
  ws4py/server/cherrypyserver.py, ws4py/compat.py (vendored in venv-py3/wsl site-packages).
expecting: n/a
next_action: Fix implemented, tested (432 passed/3 skipped on real Linux+dbus+gi via WSL;
  381 passed/50 skipped/3 known-pre-existing-failed on required Windows venv-py3 run), and
  PR opened. Awaiting human verification on real Pi hardware at next deploy (cannot be
  live-retested this session -- see reasoning_checkpoint.blind_spots).
reasoning_checkpoint:
  hypothesis: "(1) WsHandler.ws() in pellmonweb.py calls dbus.getdb() with no try/except.
    ws4py's WebSocketTool.upgrade() hook (before_request_body) already commits the HTTP
    response to '101 Switching Protocols' + streaming BEFORE ws() runs. When getdb() raises
    DbusNotConnected (pellmonsrv mid-restart), the exception propagates out of the page
    handler after the protocol switch already started; cherrypy's normal error/finalize path
    then collides with the already-committed 101 response while ws4py's on_end_request hook
    (start_handler) still detaches the raw socket (BufferedReader.detach(), which sets
    fileobj.raw = None) and hands it to WebSocketManager regardless of the handler's outcome.
    This corrupts/double-owns the same socket between cheroot's connection object and
    WebSocketManager, producing the observed AttributeError('NoneType' has no attribute
    'read') then OSError(Bad file descriptor) ~5s later on the same connection. (2)
    cherrypy/process/servers.py _start_http_thread catches any Exception from
    httpserver.start(), calls self.bus.exit() (publishes the 'exit' bus channel, engine goes
    STOPPING/STOPPED/EXITING/EXITED), then re-raises -- inside a background
    threading.Thread, so nothing terminates the process. pellmonweb.py's run() runs
    GLib main_loop.run() on the main thread; the only tie between it and cherrypy's bus is a
    100ms publish() timeout that calls cherrypy.engine.publish('main') -- it never checks
    engine state or quits the loop. So the main thread blocks in main_loop.run() forever
    after the HTTP thread dies, the container stays 'Up' but unresponsive, and
    `restart: unless-stopped` never fires because PID 1 never exits."
  confirming_evidence:
    - "cherrypy/process/servers.py:214-237 _start_http_thread: except Exception: ...
      self.bus.log('Error in HTTP server: shutting down', ...); self.bus.exit(); raise --
      matches evidence's 'ENGINE Error in HTTP server: shutting down' + 'Exception in
      thread HTTPServer Thread-3' exactly."
    - "ws4py/server/cherrypyserver.py WebSocketTool._setup(): upgrade() attached at
      before_request_body (runs BEFORE the page handler), complete()/start_handler()
      attached at before_finalize/on_end_request (run AFTER, unconditionally once
      request.ws_handler exists) -- confirms the upgrade commits to 101 before WsHandler.ws()
      executes, and detach/handoff happens regardless of whether ws() raised."
    - "ws4py/compat.py: detach_connection(fileobj) calls fileobj.detach() (Python io
      BufferedReader.detach()), which is documented to sever/null the raw stream -- matches
      the observed 'NoneType has no attribute read' AttributeError on a later read of the
      same connection."
    - "pellmonweb.py WsHandler.ws() (line ~722): db=dbus.getdb() called with zero
      try/except, unlike every other dbus call site in PellMonWeb (getparam, parameters,
      index all catch DbusNotConnected)."
    - "pellmonweb.py run() (line ~1057): publish() callback only calls
      cherrypy.engine.publish('main'); no listener anywhere subscribes to cherrypy's 'exit'
      bus channel or checks cherrypy.engine.state to quit main_loop or exit the process."
  falsification_test: "If WsHandler.ws() already wrapped dbus.getdb() in try/except
    DbusNotConnected (it does not -- confirmed by direct read), or if pellmonweb.py already
    subscribed to the cherrypy 'exit' channel / exited the process after main_loop.run()
    returns (it does not -- confirmed by direct read, only KeyboardInterrupt is caught),
    this hypothesis would be false."
  fix_rationale: "Fix targets both the proximate trigger (ws() raising mid-upgrade, which
    corrupts the socket) and the structural gap (no path from 'HTTP thread died' to 'process
    exits'), per the investigation's own constraint that a structural fix making ANY future
    uncaught background-thread exception result in process exit is an acceptable and
    necessary bar, not just papering over this one trigger."
  blind_spots: "Cannot live-retest on the real Pi (no hardware access this session).
    Cannot fully prove the exact interleaving that produces the specific AttributeError vs.
    some other symptom of the same corrupted-detach condition -- treating 'ws() must never
    raise after the websocket upgrade already began' as the defensible root-cause-level
    fix regardless of the exact subsequent cheroot stack trace. Also not verifying whether
    ws4py's WebSocketManager itself would have gracefully reaped this half-broken connection
    given more time; the structural process-exit fix is the safety net regardless."
tdd_checkpoint: null

## Symptoms
<!-- Written during gathering, then immutable -->

expected: If pellmonweb's HTTP server (cheroot) hits a fatal, unrecoverable internal error, the container should either recover on its own or at minimum exit so Docker's `restart: unless-stopped` policy brings it back automatically -- per this project's own OPS-02 requirement (Phase 5: "Both pellmonsrv and pellmonweb handle SIGTERM gracefully... so docker compose down/restart doesn't leave locked resources") and its healthcheck/restart-policy infrastructure (OPS-03).
actual: The container stayed "Up" (process alive) but completely unresponsive on port 8081 after the crash. No automatic restart happened. Required a full manual `docker compose stop` (all 4 services) + `docker compose up -d` to recover -- not even a targeted `docker compose restart pellmonweb` was tried yet, so it's not yet confirmed whether restarting pellmonweb alone would have been sufficient (open question for next verification round).
errors: |
  Sequence (user-pasted docker logs pellmonweb, real Pi, 2026-09-23 ~14:52 local):
  1. 14:52:37 - GET /websocket/ws/?parameters=... (a websocket upgrade request, real
     browser client via the stoker.schoeler.pro reverse proxy, Sec-WebSocket-* headers
     present) -> 500. Traceback: Dbus_handler.getdb() (pellmonweb.py:220) ->
     DbusNotConnected("server not running") -- this occurred WHILE pellmonsrv was still
     mid-restart from the step 7 test, i.e. a legitimate transient state, not itself a bug.
  2. 14:52:39 and 14:52:41 - GET / -> 200 (twice). Main page recovered fine once
     pellmonsrv was back -- confirms the D-Bus reconnect fix (v2.0.4, resolved session
     pellmonweb-dbus-not-connected) IS working correctly for plain HTTP requests.
  3. 14:52:42 - ENGINE AttributeError("'NoneType' object has no attribute 'read'") inside
     cheroot's HTTP connection parsing (server.py read_request_line -> readline ->
     _pyio.py peek -> raw.read), immediately followed by OSError: [Errno 9] Bad file
     descriptor when cheroot tried to `shutdown(socket.SHUT_RDWR)` the same (already-dead)
     socket in conn.close(). This looks like the SAME underlying connection as the
     WebSocket request from step 1 -- its raw socket file object (self.raw) became None
     between the failed websocket handshake/500 response and a later attempt to read
     from or close that same connection, likely because the 500 response path for the
     websocket request didn't clean up the upgraded/hijacked connection state correctly.
  4. cherrypy's engine catches the OSError in _start_http_thread's serve() call, logs
     "ENGINE Error in HTTP server: shutting down", runs its Bus STOPPING/STOPPED/EXITING/
     EXITED sequence, removes the PID file -- but the exception traceback for
     "Exception in thread HTTPServer Thread-3" is UNCAUGHT at the Python threading level
     (default threading.excepthook just prints it), which does not terminate the process.
reproduction: |
  1. Have the stack mid-restart from Phase 8 checklist step 7 (pellmonsrv stopped/starting
     back up), so a brief D-Bus-not-ready window exists.
  2. Have a real browser client attempt a WebSocket upgrade to /websocket/ws/ during that
     window (this happened via the stoker.schoeler.pro reverse-proxied browser tab that
     was already open, auto-reconnecting).
  3. The websocket request 500s cleanly (expected, matches D-Bus-down graceful-ish
     behavior), but something about how that specific connection is torn down leaves its
     socket in a bad state, and a subsequent read/close on it crashes cheroot's serving
     thread -- taking down the whole HTTP server without taking down the container process.
  Not yet reproduced deliberately / minimally -- only observed once, in the wild, during
  today's Pi verification. Needs a controlled repro (e.g. open a websocket connection,
  kill pellmonsrv mid-handshake, see if the crash reproduces reliably) before a fix can be
  verified with confidence.
started: Today (2026-09-23), same live Phase 8 Task 4 / D-Bus-reconnect verification
  session on the real Pi deployment, immediately after confirming the pellmon-dbus fix
  (v2.0.4) resolved the original main-page-500 bug.

## Eliminated
<!-- APPEND only - prevents re-investigating after /clear -->

## Evidence
<!-- APPEND only - facts discovered during investigation -->

- timestamp: 2026-09-23T15:05:00Z
  checked: user-pasted docker logs pellmonweb, full sequence around the crash
  found: The crash follows a failed WebSocket upgrade request that itself 500'd cleanly
    (a normal, non-fatal DbusNotConnected during the pellmonsrv restart window). The fatal
    AttributeError/OSError happened ~5 seconds later, on a different log line, appearing
    to involve the same/an adjacent raw socket object going bad, not a fresh request.
  implication: The bug is most likely in cleanup/teardown of a WebSocket-upgraded
    connection after its handler raises mid-handshake, not in the D-Bus reconnect path
    itself (which is confirmed working -- two plain GET / requests succeeded in between).

- timestamp: 2026-09-23T15:05:00Z
  checked: docker ps after the crash (user-provided) vs. after a full manual `docker
    compose stop && up -d`
  found: Before manual intervention, pellmonweb did not recover on its own despite
    `restart: unless-stopped`. After a full stack stop+up, all three services report
    healthy again.
  implication: `restart: unless-stopped` is not firing on this failure mode, meaning the
    container's PID 1 process is very likely NOT exiting when cherrypy's HTTP thread dies
    -- consistent with a background-thread-only crash that never reaches the main thread /
    process exit path.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: |
  Two-part, confirmed by direct source reading of the vendored cherrypy/ws4py stack (not
  just inference):
  1) Proximate trigger: WsHandler.ws() (src/Pellmonweb/pellmonweb.py) called
     dbus.getdb() with no try/except. ws4py's WebSocketTool.upgrade() hook runs at
     before_request_body -- BEFORE this page handler -- and already commits the HTTP
     response to '101 Switching Protocols' + streaming. When getdb() raised
     DbusNotConnected (pellmonsrv mid-restart, a legitimate transient state), the exception
     propagated out of the handler after the protocol switch had already begun. cherrypy's
     normal error-response path then collided with the already-committed 101 response,
     while ws4py's on_end_request hook (start_handler) still unconditionally detached the
     raw socket (BufferedReader.detach(), which nulls fileobj.raw) and handed it to
     WebSocketManager regardless of the handler's outcome -- corrupting/double-owning the
     connection.
  2) Structural gap: cherrypy/process/servers.py _start_http_thread catches any Exception
     from httpserver.start(), logs 'Error in HTTP server: shutting down', calls
     self.bus.exit() (publishes the engine's 'exit' channel), then re-raises -- inside a
     background threading.Thread, so nothing terminates the process. pellmonweb.py's run()
     blocks the main thread in a GLib main_loop.run() that was only tied to cherrypy via a
     100ms publish() timeout (cherrypy.engine.publish('main')), which never checked engine
     state. So when the HTTP thread died, the process stayed alive but permanently unable to
     serve HTTP, and docker-compose's `restart: unless-stopped` never fired because PID 1
     never exited -- this is what made the incident unrecoverable without a manual
     stop/up of the whole stack.
fix: |
  1) src/Pellmonweb/pellmonweb.py WsHandler.ws(): wrap dbus.getdb()/Sensor creation in
     try/except DbusNotConnected; on failure, log and gracefully close the
     already-upgraded ws_handler instead of letting the exception propagate mid-handshake.
  2) src/Pellmonweb/pellmonweb.py run(): subscribe a listener to cherrypy.engine's 'exit'
     bus channel that always calls main_loop.quit() -- covering any path that ends the
     engine, planned (our own SIGINT/SIGTERM handler) or not (a background-thread crash).
     Track whether shutdown was self-initiated via a graceful_shutdown threading.Event; if
     main_loop.run() returns without that event set, hard-exit the process
     (os._exit(1)) so `restart: unless-stopped` can recover the container. This is a
     structural fix: it makes ANY future uncaught background-thread exception in the
     cherrypy engine result in process exit, not just this specific websocket trigger.
verification: |
  - Full test suite run in a real Linux environment with genuine dbus/gi available (WSL
    Debian, system python3-dbus/python3-gi layered onto venv-wsl's site-packages via
    PYTHONPATH, since Pellmonweb.pellmonweb cannot import without them):
    432 passed, 3 skipped, 0 failed (up from 428 passed/3 skipped pre-fix; the 4 new tests
    in tests/Pellmonweb/test_websocket_dbus_down.py and
    tests/Pellmonweb/test_engine_exit_process_restart.py all pass).
  - Required Windows run (PYTHONPATH=src venv-py3/Scripts/python.exe -m pytest tests/ -v):
    381 passed, 50 skipped, 3 failed -- the exact same pre-existing 3 failures
    (test_backup_script.py::test_conf_d_overrides_pellmon_conf,
    test_plugin_loader.py::test_every_available_plugin_loads[consumption/silolevel]),
    confirmed unrelated Windows-platform gaps (they pass under the real Linux run above).
    No new failures.
  - test_websocket_dbus_down.py::test_ws_does_not_raise_when_dbus_down directly reproduces
    the proximate trigger (WsHandler.ws() with a DbusNotConnected-raising dbus handler after
    the ws4py upgrade already began) and proves it no longer raises and gracefully closes
    the connection instead.
  - test_engine_exit_process_restart.py proves cherrypy's own bus.exit() (the exact call
    _start_http_thread makes on any unhandled exception) reliably reaches a subscriber on
    the 'exit' channel, and that the graceful_shutdown flag correctly distinguishes a
    self-initiated signal-based shutdown from an engine exit triggered elsewhere (a crash) --
    the two conditions run()'s exit-code decision depends on.
  - NOT verified: live retest on the real Pi (no hardware access this session, per
    investigation constraints). This is a defensible code-level fix backed by direct
    reading of the exact vendored library code paths involved (cherrypy 18.10.0,
    ws4py 0.6.0) plus targeted regression tests, not a live-Pi confirmation. Flagged for
    human verification at next real-hardware deploy.
files_changed:
  - src/Pellmonweb/pellmonweb.py
  - tests/Pellmonweb/test_websocket_dbus_down.py
  - tests/Pellmonweb/test_engine_exit_process_restart.py
