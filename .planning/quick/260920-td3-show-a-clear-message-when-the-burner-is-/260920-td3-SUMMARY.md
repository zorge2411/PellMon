---
phase: quick-260920-td3
plan: 01
status: complete
branch: feat/burner-connection-status
requirements: [BURNCONN-01, BURNCONN-02, BURNCONN-03, BURNCONN-04, BURNCONN-05, BURNCONN-06, BURNCONN-07]
key-files:
  modified:
    - src/Scotteprotocol/protocol.py
    - src/Pellmonsrv/plugins/scottecom/scottecom.py
    - src/Pellmonweb/pellmonweb.py
    - src/Pellmonweb/html/index.html
    - src/Pellmonweb/media/js/index.js
    - src/Pellmonweb/media/css/pellmon.css
    - DEPLOY-PI.md
    - HARDWARE-BRINGUP.md
    - tests/Pellmonsrv/test_scotteprotocol_logging.py
  created:
    - src/Pellmonweb/html/connectionbanner
    - tests/test_scotte_connection_state.py
    - tests/Pellmonsrv/test_scottecom_connection_items.py
    - tests/Pellmonweb/test_connection_banner.py
---

# Quick 260920-td3: Show a clear message when the burner is not connected

Replaced the Scotte plugin's silent dummy-data fallback with an explicit live
connection state (`burner_connection` / `burner_connection_reason` items) and a
main-page banner plus greyed-out widgets.

## Connection-state design

- Items (generic names, no scotte prefix, `Plainitem`, type `R`, tags `['All']`):
  `burner_connection` in {`connected`, `no_connection`, `demo`}, and
  `burner_connection_reason` (free text).
- Web-only extra state `server_down` (daemon unreachable), never an item.
- Initial: `demo` when `serialport` is missing/blank; `no_connection` when the port
  cannot be opened (reason `serial port <dev> cannot be opened: <OS error>`; no poll
  thread, every getItem/setItem raises IOError, item names still registered);
  `connected` otherwise, then driven by real polls.
- Transitions: 3 consecutive give-ups (`FAILURE_THRESHOLD`, each = attempt + retry)
  -> `no_connection` ("burner not answering on <dev>"); any successful real poll ->
  `connected`. Only real device polls count (frame-cache hits do not). A rejected write
  (device answered) counts as an answer; only "No answer" counts as failure.
- Callback `on_connection_change(state, reason)` fires once per transition, inside
  try/except.
- While `no_connection`, only one real poll per `PROBE_INTERVAL` (10 s) is attempted;
  other reads raise IOError immediately (see deviation 2).
- Items are registered before and outside the plugin's try/except.

## Commits

See `git log master..feat/burner-connection-status`: RED tests, protocol state
machine, plugin items, web banner, RED probe tests, probe fix, docs.

## Test numbers

- WSL full suite: baseline master 261 passed / 7 skipped; after 283 passed / 10 skipped
  (3 new skips are the resolver tests that need dbus/gi, which venv-wsl lacks).
- System python3 (dbus/gi present) `tests/Pellmonweb tests/Pellmonsrv`: 174 passed,
  0 skipped (includes the resolver tests).

## Dry runs (WSL Debian, private session bus, config under /tmp/dry3_*)

1. serialport=/nonexistent/ttyXYZ: burner_connection `no_connection`, reason names the
   port and OS error; GetItem boiler_temp/power fail with a D-Bus OSError (no 1234);
   served HTML has `data-state="no_connection"`, the no_connection alert visible, others
   `hidden`, `id="pellmon-widgets" class="pellmon-disconnected"`, reason escaped.
2. serialport=burner_sim pty: `connected`, boiler_temp 57.6, power 64, no banner.
   The simulator cannot re-publish the same pty path, so outage was simulated with
   SIGSTOP/SIGCONT on the simulator (pty stays open, it just stops answering).
   STOP -> `no_connection` after ~8 s ("burner not answering on /dev/pts/6"), HTML
   showed banner + greyed widgets; after a further 10 s outage CONT -> `connected`
   within one poll, boiler_temp 57.8, banner hidden, no daemon restart. A ws4py
   websocket client received `burner_connection=no_connection` (+reason) about 2 s after
   the flip and `connected` about 2 s after recovery (live propagation VERIFIED).
3. serialport line removed: `demo`, reason "no serialport is configured, values are
   simulated", boiler_temp/power `1234`, HTML `data-state="demo"` with demo alert visible,
   widgets not greyed.
pgrep clean after every run. Nothing was installed.

## Deviations from plan

1. [Rule 1] `tests/Pellmonsrv/test_scotteprotocol_logging.py` asserted the old behaviour
   (exception traceback logged, dummyDevice True); rewritten to the plan-mandated
   error-level log and `port_failed`/`no_connection`.
2. [Rule 1 - found in dry run] With a dead burner each read of a stale frame burned a full
   poll+retry (~2 s) and the daemon's Database loop visits every item, so the state change
   would have reached the UI minutes late. Added `PROBE_INTERVAL` fail-fast (tests first).
3. setItem: only "No answer" counts as a connectivity failure; a device rejection (answer)
   counts as connected, so 3 rejected writes cannot flip to no_connection.
4. The PowerShell tool was unavailable; WSL was driven from Git Bash with
   `MSYS_NO_PATHCONV=1` (same as quick 260920-rpd).
5. Banner reason line rendered with explicit `| h` (Mako has no default HTML escaping
   here); state items use tags `['All']` so they do not add a menu entry.

## Not verified / findings left unfixed

- Browser-level rendering and the JS (setConnectionState, onclose -> server_down, reload on
  reopen) were NOT exercised in a browser; only served HTML and websocket payloads were.
- Real burner hardware, a real Pi, and the NBE plugin were not covered.
- The web websocket stays open when only the daemon dies, so `server_down` shows live only
  if the socket itself closes; a plain page reload always shows it.
- While disconnected the Poller logs an ERROR with traceback per polled item every
  pollinterval (pre-existing pellmonsrv.py behaviour); noisy but unchanged.
- setupPolling() in index.js still has a pre-existing `var params` redeclaration and calls
  setupWebSocket on retry; untouched.
- ws4py/`websockets` path with `getparamlist` polling fallback was not run.

## Self-Check: PASSED
