---
phase: 2
slug: exception-visibility-retrofit
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-17
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9.0,<10` (already installed, Phase 1 deliverable) |
| **Config file** | `pytest.ini` (repo root, from Phase 1) |
| **Interpreter** | `venv-py3/Scripts/python.exe` (matches Phase 1's established interpreter choice — has cherrypy + pyserial) |
| **Quick run command** | `venv-py3/Scripts/python.exe -m pytest tests/ -x -q -m "not known_broken"` |
| **Full suite command** | `venv-py3/Scripts/python.exe -m pytest tests/ -v` |
| **Estimated runtime** | ~10-20 seconds (unchanged from Phase 1 — no hardware I/O) |

---

## Sampling Rate

- **After every task commit:** quick run command
- **After every plan wave:** full suite command + the before/after JUnit-XML outcome diff (see below)
- **Before `/gsd:verify-work`:** full suite must exactly match Phase 1's documented 2-failure red baseline; before/after outcome diff must be empty
- **Max feedback latency:** 20 seconds

---

## Before/After Regression Check (Phase success criterion 1)

Do NOT diff raw pytest console text — the `.info`/`print()` → `.exception()` log-verbosity change would falsely register as a "regression" if console output is compared directly. Compare structured per-test **outcomes only** via JUnit XML:

```bash
# BEFORE any Phase 2 edits (captured once, first task of Wave 0):
venv-py3/Scripts/python.exe -m pytest tests/ -v --junitxml=.planning/phases/02-exception-visibility-retrofit/before.xml

# ... Phase 2 changes applied across waves ...

# AFTER all Phase 2 edits (final task, before phase verification):
venv-py3/Scripts/python.exe -m pytest tests/ -v --junitxml=.planning/phases/02-exception-visibility-retrofit/after.xml
```

Then diff pass/fail/error/skip per test ID only (ignore captured log/stdout content) — see `02-RESEARCH.md` § "Exact before/after comparison mechanism" for the exact Python diff script. Expected result: empty diff, with the two Expected-Red-Baseline failures (`test_plugin_module_imports[scottecom]`, `test_nbecom_deferred_protocol_import`) still failing with the identical failure type.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | — | — | N/A | infra | `test -f .planning/phases/02-exception-visibility-retrofit/before.xml` | ✅ created by task | ⬜ pending |
| 02-01-02 | 01 | 1 | OBS-01 | — | N/A | unit | `pytest tests/Pellmonsrv/test_plugin_manager_logging.py -v` | ✅ | ⬜ pending |
| 02-01-03 | 01 | 1 | OBS-01 | — | N/A | unit | `pytest tests/Pellmonsrv/test_pellmonsrv_logging.py -v` (plugin-activation loop coverage) | ✅ | ⬜ pending |
| 02-02-01 | 02 | 1 | OBS-02 | — | N/A | unit | `pytest tests/Pellmonsrv/plugins/test_calculate_logging.py -v` (test-only `maketrans` shim) | ✅ | ⬜ pending |
| 02-02-02 | 02 | 1 | OBS-02 | — | N/A | unit | `pytest tests/Pellmonsrv/test_pellmonsrv_logging.py -v` (Poller.run failure coverage, same file as 02-01-03) | ✅ | ⬜ pending |
| 02-03-01 | 03 | 2 | OBS-03 | — | N/A | enforcement | `grep -rn "print(" src/Pellmonsrv src/Pellmonweb --include="*.py" \| grep -v "\.py2bak"` — assert output is exactly 3 lines, all `pellmonconf.py` (the one confirmed intentional CLI banner) | ✅ | ⬜ pending |
| 02-03-02 | 03 | 2 | Phase SC-1 | — | N/A | integration | before/after JUnit-XML outcome diff — assert empty diff | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: this phase has no threat model beyond "don't change behavior" — it's a pure observability retrofit touching only logging/print calls, not security-relevant logic. Threat Ref is N/A throughout.*

---

## Wave 0 Requirements

- [ ] `.planning/phases/02-exception-visibility-retrofit/before.xml` — captured via `pytest tests/ -v --junitxml=...` BEFORE any Phase 2 source edits
- [ ] `tests/Pellmonsrv/test_plugin_manager_logging.py` — `caplog`-based test asserting `PluginManager.py`'s plugin-load exec failure path emits a `logging.exception`-level record with `record.exc_info is not None`
- [ ] `tests/Pellmonsrv/test_pellmonsrv_logging.py` — covers both the plugin-activation loop and `Poller.run`'s failure paths via `caplog`
- [ ] `tests/Pellmonsrv/plugins/test_calculate_logging.py` — includes the test-only `string.maketrans` shim (per 02-RESEARCH.md Pitfall 3) before importing the module, then asserts `setItem()` still returns `'error'` (logic unchanged) AND a `logger.exception` record with a `NameError` traceback was emitted

---

## Manual-Only Verifications

*None — all phase behaviors (logging conversions, print-statement removal, before/after parity) have automated verification via pytest + caplog + the JUnit-XML diff script.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (the 3 new caplog-based test files, plus the before.xml capture)
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
