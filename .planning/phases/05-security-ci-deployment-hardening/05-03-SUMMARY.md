---
phase: 05-security-ci-deployment-hardening
plan: 03
subsystem: signal-handling
tags: [signals, sigterm, sigint, graceful-shutdown, rrdtool, glib, cherrypy]
dependency-graph:
  requires: []
  provides:
    - Graceful SIGTERM and SIGINT handling in pellmonsrv flushing RRD data and quitting GLib main loop (OPS-02)
    - Graceful SIGTERM and SIGINT handling in pellmonweb exiting CherryPy engine and GLib loop (OPS-02)
    - Unit test suite verifying signal handling and graceful cleanup logic
  affects:
    - src/Pellmonsrv/pellmonsrv.py
    - src/Pellmonweb/pellmonweb.py
    - tests/Pellmonsrv/test_sigterm_handling.py
tech-stack:
  added: []
  patterns:
    - Signal handler registration with signal.SIGTERM and signal.SIGINT
    - Safe non-volatile RRD sync on termination via copy_db('store')
    - Poller thread cooperative termination with stop() method and Event unblocking
    - GLib MainLoop quit and CherryPy engine exit orchestration
key-files:
  created:
    - tests/Pellmonsrv/test_sigterm_handling.py
  modified:
    - src/Pellmonsrv/pellmonsrv.py
    - src/Pellmonweb/pellmonweb.py
decisions: [D-04]
metrics:
  completed: 2026-09-18
---

# Phase 5 Plan 03: Graceful SIGTERM & SIGINT Handling Summary

Implemented robust, graceful termination signal handling for both `pellmonsrv` and `pellmonweb` daemons (OPS-02) so that container stops, `docker compose down`, and system shutdowns safely flush RRD database writes to non-volatile storage, stop background polling threads, clean up pidfiles, and exit CherryPy/GLib main loops without corrupted state.

## What Was Built

### Task 1: Graceful SIGTERM and SIGINT handler in pellmonsrv.py (OPS-02)
- Added module-level `DBUSMAINLOOP = None`, `daemon_instance = None`, and `conf = None` declarations.
- Updated `Poller` with thread cooperative cancellation:
  - Added `self.running = True` and `def stop(self)` method which sets `self.running = False` and unblocks `self.ev.set()`.
  - Updated `Poller.run()` loop to check `getattr(self, 'running', True)`.
- Defined comprehensive `sigterm_handler`:
  - Logs reception of termination signal at INFO level with signal number.
  - Flushes RRD database to persistent storage (`copy_db('store')`) if `conf.polling` and `conf.nvdb != conf.db`.
  - Terminates the poller thread cooperatively via `self.poller.stop()`.
  - Quits the GLib main loop (`DBUSMAINLOOP.quit()`).
  - Removes the daemon pidfile via `self.delpid()`.
- Registered `sigterm_handler` for both `signal.SIGTERM` and `signal.SIGINT`.
- Exposed `sigterm_handler` on `MyDaemon` instance and module level for testing and runtime robustness.

### Task 2: Register SIGTERM in pellmonweb.py for clean shutdown (OPS-02)
- Defined module-level `main_loop = None` and `signal_handler(signal_num, frame=None)`.
- In `Pellmonweb.pellmonweb.run()`:
  - Updated inner `signal_handler` to take `signal_num, frame` and log graceful shutdown at INFO level.
  - Intercepted `signal.SIGTERM` in addition to `signal.SIGINT`.
  - Invoked `cherrypy.engine.exit()` and `main_loop.quit()` to cleanly terminate HTTP server and GLib loops.

### Task 3: Unit tests for graceful signal handling (tests/Pellmonsrv/test_sigterm_handling.py)
Created 8 unit tests covering signal handler behavior across server and web:
- `test_pellmonsrv_sigterm_handler_flushes_db_and_quits_loop`: Mocks `conf`, `copy_db`, and `DBUSMAINLOOP`. Asserts `copy_db('store')` and `DBUSMAINLOOP.quit()` are called upon SIGTERM.
- `test_pellmonsrv_sigterm_handler_skips_flush_when_same_db`: Asserts `copy_db` is skipped when `nvdb == db`, but loop still quits.
- `test_pellmonsrv_sigterm_handler_stops_poller_and_removes_pid`: Verifies poller thread stop and pidfile cleanup.
- `test_pellmonsrv_mydaemon_method_sigterm_handler`: Verifies `MyDaemon.sigterm_handler` method works on instance.
- `test_poller_stop_lifecycle`: Verifies `Poller.stop()` sets running state to `False` and wakes up event.
- `test_pellmonsrv_ast_signal_registration`: Verifies AST contains signal handler registrations for both SIGTERM and SIGINT.
- `test_pellmonweb_signal_handler_quits_engine_and_loop`: Mocks CherryPy engine and main loop, asserts clean exit on SIGTERM.
- `test_pellmonweb_ast_signal_registration`: Verifies AST of pellmonweb registers both SIGINT and SIGTERM handlers.

## Verification Results

1. Task 1 Verification:
```powershell
venv-py3/Scripts/python.exe -c "import ast; tree = ast.parse(open('src/Pellmonsrv/pellmonsrv.py', 'r', encoding='utf-8').read()); found = any(isinstance(n, ast.FunctionDef) and n.name == 'sigterm_handler' for n in ast.walk(tree)); assert found, 'sigterm_handler not found in pellmonsrv.py'"
# Exit 0
```

2. Task 2 Verification:
```powershell
venv-py3/Scripts/python.exe -c "content = open('src/Pellmonweb/pellmonweb.py', 'r', encoding='utf-8').read(); assert 'signal.signal(signal.SIGTERM, signal_handler)' in content"
# Exit 0
```

3. Task 3 Test Suite Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_sigterm_handling.py -v
# 8 passed in 0.34s
```

4. Full Test Suite Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/ -v
# 110 passed, 8 skipped, 2 warnings in 2.35s
```

## Deviations from Plan

None. Implementation strictly followed D-04 and plan specifications.

## Commits

- `0b9a1a7` feat(phase-5): implement graceful SIGTERM and SIGINT handler in pellmonsrv
- `c397cb6` feat(phase-5): register SIGTERM in pellmonweb for clean shutdown
- `bd2c132` test(phase-5): add unit tests for graceful signal handling
