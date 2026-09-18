---
phase: 04-protocol-module-hardening
plan: 01
subsystem: calculate-plugin & daemon
tags: [python3, calculate, maketrans, unicode, daemon, stderr-buffering, pytest]
dependency-graph:
  requires: []
  provides:
    - Fixed Calculate plugin maketrans and unicode() calls (PROTO-02, PROTO-05)
    - Fixed daemon.py line-buffered text I/O for stderr redirection (PROTO-03)
    - Unit tests in tests/Pellmonsrv/plugins/test_calculate_hardening.py
    - Unit tests in tests/Pellmonsrv/test_daemon_hardening.py
  affects:
    - Pellmonsrv.plugins.calculate
    - Pellmonsrv.daemon
tech-stack:
  added: []
  patterns:
    - Line-buffered text I/O (buffering=1) for daemon stderr
    - Explicit str() string conversions replacing Python 2 unicode()
key-files:
  created:
    - tests/Pellmonsrv/plugins/test_calculate_hardening.py
    - tests/Pellmonsrv/test_daemon_hardening.py
  modified:
    - src/Pellmonsrv/plugins/calculate/__init__.py
    - src/Pellmonsrv/daemon.py
    - tests/Pellmonsrv/plugins/test_calculate_logging.py
decisions: [D-02, D-03]
metrics:
  completed: 2026-09-18
---

# Phase 4 Plan 01: Calculate Plugin & Daemon Hardening Summary

Eliminated Python 3 runtime crashes in the Calculate plugin and Daemonizer: removed the obsolete Python 2 `from string import maketrans` import (PROTO-05), replaced `unicode(value)` with `str(value)` in Calculate `setItem` (PROTO-02), and updated `daemon.py` stderr redirection from unbuffered (`buffering=0`) to line-buffered (`buffering=1`) text I/O (PROTO-03).

## What Was Built

### Task 1: Fix Calculate plugin maketrans and unicode() calls
- In `src/Pellmonsrv/plugins/calculate/__init__.py`:
  - Removed obsolete line `from string import maketrans` (PROTO-05).
  - Replaced `stack = [unicode(value)]` with `stack = [str(value)]` in `setItem` (PROTO-02).
- Verification:
  - AST parse confirmed absence of `maketrans` and `unicode()` calls.

### Task 2: Fix daemon.py stderr redirection buffering
- In `src/Pellmonsrv/daemon.py`:
  - Updated line 72 from `se = open(self.stderr, 'a+', buffering=0)` to `se = open(self.stderr, 'a+', buffering=1)` (PROTO-03).
- Verification:
  - Confirmed Python 3 text I/O opens stderr with line-buffering without raising `ValueError: can't have unbuffered text I/O`.

### Task 3: Add unit tests for Calculate hardening and daemon stderr buffering
- Created `tests/Pellmonsrv/plugins/test_calculate_hardening.py`:
  - `test_calculate_does_not_import_maketrans`: AST check confirming no `maketrans` import.
  - `test_calculate_has_no_unicode_references`: AST check confirming no `unicode` identifiers.
  - `test_calc_execution_with_string_values`: Unit tests for `Calc` arithmetic, logic, and variable store/recall.
  - `test_setitem_uses_str_and_returns_ok`: Confirmed `setItem` converts arguments using `str()` and executes cleanly.
  - `test_setitem_calc_failure_logs_exception`: Confirmed error logging when calculation raises at runtime.
- Created `tests/Pellmonsrv/test_daemon_hardening.py`:
  - `test_daemon_initialization_defaults` & `test_daemon_initialization_custom`: Validated `Daemon` class constructor paths.
  - `test_daemon_stderr_buffering_avoids_valueerror`: Tested that `buffering=0` in text mode raises `ValueError` in Python 3 while `buffering=1` succeeds and writes text.
  - `test_daemon_source_ast_buffering`: Static AST check asserting `buffering=1` is present and `buffering=0` is absent.
- Updated `tests/Pellmonsrv/plugins/test_calculate_logging.py`:
  - Removed temporary Phase 2 `string.maketrans` fixture shim now that PROTO-05 is resolved in production code.
  - Updated `test_setitem_calc_failure_visibility` to test calc execution failure visibility with an error program, reflecting that `setItem` no longer raises `NameError`.

## Verification Results

1. Task 1 Verification:
```bash
venv-py3/Scripts/python.exe -c "import ast; tree = ast.parse(open('src/Pellmonsrv/plugins/calculate/__init__.py', 'rb').read()); assert 'maketrans' not in open('src/Pellmonsrv/plugins/calculate/__init__.py').read(); assert 'unicode(' not in open('src/Pellmonsrv/plugins/calculate/__init__.py').read()"
# Exited 0
```

2. Task 2 Verification:
```bash
venv-py3/Scripts/python.exe -c "import tempfile, os; f = tempfile.NamedTemporaryFile(delete=False); f.close(); se = open(f.name, 'a+', buffering=1); se.write('test\n'); se.close(); os.unlink(f.name)"
# Exited 0
```

3. Task 3 Verification:
```bash
venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_calculate_hardening.py tests/Pellmonsrv/test_daemon_hardening.py -v
# 9 passed in 0.06s
```

4. Full Test Suite Verification:
```bash
venv-py3/Scripts/python.exe -m pytest
# 67 passed, 8 skipped, 2 warnings in 1.89s
```

## Deviations from Plan

- `tests/Pellmonsrv/plugins/test_calculate_logging.py` was updated to remove the temporary Phase 2 `string.maketrans` test shim and update `test_setitem_namerror_visibility` to `test_setitem_calc_failure_visibility`. The Phase 2 test had specifically documented: *"Delete this shim once Phase 4 / PROTO-05 fixes the import for real"* and asserted `NameError` from `unicode(value)` which PROTO-02 resolved. Updating the test kept the exception-visibility regression suite green.

## Commits

- `2eeffff` fix(phase-4): fix Calculate plugin maketrans and unicode() calls
- `e11b77f` fix(phase-4): fix daemon.py stderr redirection buffering
- `2565f78` test(phase-4): add unit tests for calculate hardening and daemon stderr buffering
