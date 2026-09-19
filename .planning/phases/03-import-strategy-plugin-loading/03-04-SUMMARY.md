---
phase: 03-import-strategy-plugin-loading
plan: 04
subsystem: protocol-coexistence & test-baseline
tags: [python3, coexistence, scotteprotocol, nbeprotocol, pytest, test-baseline, pep-328]
dependency-graph:
  requires:
    - 03-01 (Scotteprotocol top-level package & exception visibility)
    - 03-02 (NBEcom & nbeprotocol explicit relative imports)
    - 03-03 (Yapsy relative imports & AST enforcement gates)
  provides:
    - Automated coexistence test tests/test_protocol_coexistence.py verifying collision-free execution
    - Cleared KNOWN_BROKEN_MODULES baseline in tests/test_plugin_imports.py
    - 0-failure green test suite baseline documented in tests/README.md
  affects:
    - CI / pytest test suite baseline
tech-stack:
  added: []
  patterns:
    - Namespace isolation between independent protocol stacks
    - Zero expected-red test baseline
key-files:
  created:
    - tests/test_protocol_coexistence.py
  modified:
    - tests/test_plugin_imports.py
    - tests/README.md
decisions: [D-05, D-06]
metrics:
  completed: 2026-09-18
---

# Phase 3 Plan 04: Protocol Coexistence & Test Baseline Green Closeout Summary

Verified simultaneous collision-free loading of `Scotteprotocol` and `nbeprotocol` in the same interpreter session (IMPORT-04), cleared the `known_broken` marks from `tests/test_plugin_imports.py` (D-05), updated `tests/README.md` to declare a 0-failure green baseline, and confirmed all 58 non-skipped tests in the suite pass.

## What Was Built

### Task 1: Add automated protocol coexistence test
- Created `tests/test_protocol_coexistence.py` (66 lines):
  - Imports both `Scotteprotocol.protocol`, `Scotteprotocol.frames` and `Pellmonsrv.plugins.nbecom.nbeprotocol.protocol`, `Pellmonsrv.plugins.nbecom.nbeprotocol.frames`.
  - Asserts `sys.modules['Scotteprotocol.protocol']` and `sys.modules['Pellmonsrv.plugins.nbecom.nbeprotocol.protocol']` are distinct module objects with correct respective `__name__` attributes.
  - Asserts `sys.modules['Scotteprotocol.frames']` and `sys.modules['Pellmonsrv.plugins.nbecom.nbeprotocol.frames']` are distinct module objects with package-specific attributes (`FrameZ00` vs `Request_frame`).
  - Instantiates `Scotteprotocol.Protocol(None, '6.99')` and `nbeprotocol.Proxy('testpass')` in the same test case, confirming neither interferes with the other's operation, database, or attributes.

### Task 2: Clear known_broken marks and update tests/README.md
- `tests/test_plugin_imports.py`:
  - Emptied `KNOWN_BROKEN_MODULES = set()`.
  - Removed `@pytest.mark.known_broken` from `test_nbecom_deferred_protocol_import()`.
  - Updated docstrings noting Phase 3 resolution of both previously-failing import paths (`scottecom` and `nbeprotocol`).
- `tests/README.md`:
  - Updated "Expected-red baseline" section to declare 0 expected-red failures and document the Phase 3 resolutions.
- Full suite verification:
  - Ran `venv-py3/Scripts/python.exe -m pytest tests/ -v`, yielding 58 passed, 8 skipped (Windows platform dependencies), 0 failed, 0 known_broken.

## Verification Results

1. Protocol coexistence test:
```bash
venv-py3/Scripts/python.exe -m pytest tests/test_protocol_coexistence.py -v
# 1 passed in 0.06s
```

2. Plugin imports test:
```bash
venv-py3/Scripts/python.exe -m pytest tests/test_plugin_imports.py -v
# 14 passed, 8 skipped in 0.37s
```

3. Full suite execution:
```bash
venv-py3/Scripts/python.exe -m pytest tests/ -v
# 58 passed, 8 skipped, 2 warnings in 1.93s
```

## Deviations from Plan

None.

## Commits

- `1c3de5b` test(phase-3): add automated protocol coexistence test
- `e3ec6b2` test(phase-3): clear known_broken marks and update test baseline to 0-failure green
