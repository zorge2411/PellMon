---
phase: 3
slug: import-strategy-plugin-loading
status: draft
nyquist_compliant: true
created: 2026-09-18
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9.0,<10` |
| **Config file** | `pytest.ini` |
| **Interpreter** | `venv-py3/Scripts/python.exe` |
| **Plugin import test** | `venv-py3/Scripts/python.exe -m pytest tests/test_plugin_imports.py -v` |
| **Shim enforcement test** | `venv-py3/Scripts/python.exe -m pytest tests/test_no_sys_path_shims.py -v` |
| **Coexistence test** | `venv-py3/Scripts/python.exe -m pytest tests/test_protocol_coexistence.py -v` |
| **Full suite command** | `venv-py3/Scripts/python.exe -m pytest tests/ -v` |

---

## Sampling Rate

- **After every task commit:** quick run command (`pytest tests/test_plugin_imports.py -v`)
- **After every plan wave:** full suite command (`pytest tests/ -v`)
- **Before phase completion:** 100% green test run across all non-skipped tests (0 failures, 0 known_broken)

---

## Success Criteria Mapping

| Criterion | Requirement | Test / Verification Command |
|-----------|-------------|-----------------------------|
| 1. ScotteCom imports & activates | IMPORT-01 | `pytest tests/test_plugin_imports.py -k scottecom` passes |
| 2. NBEcom imports & activates | IMPORT-02 | `pytest tests/test_plugin_imports.py -k nbecom` passes |
| 3. No sys.path shims & PEP 328 | IMPORT-03 | `pytest tests/test_no_sys_path_shims.py -v` passes |
| 4. Coexistence without collisions | IMPORT-04 | `pytest tests/test_protocol_coexistence.py -v` passes |
| Inherited: Scotteprotocol exception sweep | OBS-02 / D-04 | `pytest tests/Pellmonsrv/test_scotteprotocol_logging.py -v` passes |

---

## Validation Sign-Off

- [x] Automated commands defined for every success criterion
- [x] Clear definition of green baseline (elimination of expected-red failures)
- [x] Coexistence test isolates namespaces
- [x] Sampling continuity: test run after every task
