---
phase: 04-protocol-module-hardening
plan: 04
subsystem: database
tags: [python3, database, sqlite, keyval, upsert, pytest]
dependency-graph:
  requires: ["04-01", "04-02", "04-03"]
  provides:
    - Correct parameter binding in Keyval_storage.writeval preserving existing value (D-05)
    - Strengthened database test asserting both value and confval columns after writeval update
    - Full test suite verification gate closing Phase 4
  affects:
    - Pellmonsrv.database
tech-stack:
  added: []
  patterns:
    - Preserving existing column data during SQLite INSERT OR REPLACE upserts
key-files:
  created: []
  modified:
    - src/Pellmonsrv/database.py
    - tests/Pellmonsrv/test_database.py
decisions: [D-05]
metrics:
  completed: 2026-09-18
---

# Phase 4 Plan 04: Database Keyval Upsert Fix & Phase Verification Gate Summary

Resolved the `Keyval_storage.writeval()` confval-upsert data corruption bug in `src/Pellmonsrv/database.py:199` (D-05), strengthened `tests/Pellmonsrv/test_database.py` to assert value preservation, and executed the full test suite as a phase-closeout verification gate.

## What Was Built

### Task 1: Fix Keyval_storage.writeval confval-upsert parameter binding and strengthen tests
- In `src/Pellmonsrv/database.py` line 199:
  - Changed parameter binding from `(item, confval, confval)` to `(item, value, confval)`.
  - When `writeval(item, confval=...)` updates a configuration value on an existing key, the existing `value` column is now preserved rather than being overwritten with the new `confval`.
- In `tests/Pellmonsrv/test_database.py`:
  - Strengthened `test_writeval_with_confval_sets_both_columns` to write an initial value (`writeval("test_item", "initial_value")`), subsequently update only the configuration value (`writeval("test_item", confval="new_conf")`), and query both columns directly from SQLite to assert that `value == "initial_value"` and `confvalue == "new_conf"`.

### Task 2: Full Phase 4 test suite gate
- Executed the full pytest test suite across the repository (`tests/`).
- Verified that all 83 non-skipped unit and round-trip tests pass with 0 failures and 0 regressions.
- The 8 skipped tests are platform-dependent (Linux/D-Bus system services) tracked on the test allowlist.
- Verified all new Phase 4 tests pass:
  - `tests/Pellmonsrv/plugins/test_calculate_hardening.py` (8 tests)
  - `tests/Pellmonsrv/test_daemon_hardening.py` (4 tests)
  - `tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py` (5 tests)
  - `tests/test_scotte_protocol_roundtrip.py` (9 tests)
  - `tests/Pellmonsrv/test_database.py` (6 tests)

## Verification Results

1. Database tests verification:
```bash
venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_database.py -v
# 6 passed in 0.11s
```

2. Full test suite verification:
```bash
venv-py3/Scripts/python.exe -m pytest tests/ -v
# 83 passed, 8 skipped, 2 warnings in 2.02s
```

3. Full test suite quiet run:
```bash
venv-py3/Scripts/python.exe -m pytest tests/ -q
# 83 passed, 8 skipped, 2 warnings in 1.96s
```

## Deviations from Plan

None. Implementation strictly followed D-05 and plan instructions.

## Commits

- `8fb0b8c` fix(phase-4): fix Keyval_storage.writeval confval-upsert parameter binding and strengthen tests
