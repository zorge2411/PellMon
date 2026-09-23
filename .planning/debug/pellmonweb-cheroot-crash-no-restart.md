---
status: investigating
trigger: "During the same real-Pi Phase 8 checklist step 7 retest that confirmed the D-Bus reconnect fix (v2.0.4) working, a WebSocket upgrade request raced against pellmonsrv still being restarted, got a DbusNotConnected 500 from Dbus_handler.getdb(), and moments later cheroot (the CherryPy HTTP server) hit an unhandled AttributeError/OSError and the whole HTTP server thread died ('ENGINE Bus EXITED'). Unlike a normal crash, the pellmonweb container did NOT restart itself afterward -- docker-compose.yml sets `restart: unless-stopped` on pellmonweb, but no automatic recovery happened. Operator had to run `docker compose stop` (all 4 containers) then `docker compose up -d` to bring the stack back to healthy."
created: 2026-09-23T15:05:00Z
updated: 2026-09-23T15:05:00Z
---

## Current Focus
<!-- OVERWRITE on each update - always reflects NOW -->

hypothesis: The CherryPy/cheroot engine caught the fatal socket exception internally (logged "Bus STOPPING" / "Bus STOPPED" / "Bus EXITED" -- CherryPy's own graceful-shutdown sequence) but the container's PID 1 Python process did not actually terminate/exit afterward. If PID 1 never exits, `restart: unless-stopped` has nothing to react to -- Docker only restarts a container when its main process exits (any exit code), not based on the container being internally broken-but-still-running. This would explain both this incident AND the very first symptom observed at the start of this whole investigation (docker ps showing pellmonweb "Up 5 minutes (unhealthy)" without ever restarting on its own, before any of today's fixes).
test: Read cherrypy's engine.stop()/engine.exit() behavior in this codebase (search pellmonweb.py for any custom exception handling around the HTTP server or `cherrypy.engine`), and check whether pellmonweb.py or the Dockerfile/entrypoint has any wrapper that would keep the process alive after cherrypy's bus exits (e.g. a bare `main_loop.run()` GLib loop that doesn't itself exit when cherrypy's HTTP thread dies, matching the visible traceback's "Exception in thread HTTPServer Thread-3" -- the exception happened in a background thread, and an uncaught exception in a non-main Python thread does NOT terminate the process by default).
expecting: If pellmonweb's actual process-level entry point runs cherrypy's HTTP server in a background thread (as the traceback's "Thread-3 (_start_http_thread)" and "CP Server Thread-9" names suggest) while a separate main thread runs something else (a GLib main_loop per pellmonweb.py's D-Bus watcher, matching the architecture pattern already seen in pellmonsrv's own MyDaemon), then a fatal exception in the HTTP thread would only kill that thread, leaving the main process (and therefore the container) alive but permanently unable to serve HTTP -- confirming the hypothesis and pointing to a fix: either make the process exit hard on this class of engine failure (`os._exit()`/`sys.exit()` from an exception hook attached to the HTTP thread), or fix the underlying cheroot exception so the crash never happens, or both.
next_action: Read src/Pellmonweb/pellmonweb.py's run()/main entry point in full to find what runs in the main thread vs. the HTTP server thread, and how (if at all) a fatal HTTP-thread exception is supposed to propagate to process exit. Also grep for any existing SIGTERM/signal-based graceful-shutdown code from the OPS-02 phase 5 work (graceful lifecycle handling) that might interact with this.
reasoning_checkpoint: null
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

root_cause: []
fix: []
verification: []
files_changed: []
