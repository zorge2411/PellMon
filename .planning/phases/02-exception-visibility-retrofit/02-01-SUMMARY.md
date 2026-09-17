---
phase: 02-exception-visibility-retrofit
plan: 01
subsystem: test-infrastructure
tags: [testing, junit-xml, pytest-fixtures, dbus-stub]
dependency-graph:
  requires: []
  provides:
    - before.xml (pre-change JUnit outcome baseline)
    - junit-outcome-diff.py (outcome-only regression check)
    - tests/Pellmonsrv/conftest.py::daemon_module fixture
  affects:
    - "all subsequent Phase 2 plans (02-02..02-06), which edit source and must be
       verified against before.xml via junit-outcome-diff.py"
tech-stack:
  added: []
  patterns:
    - "sys.modules stub injection before importlib.import_module, torn down in a
       try/finally so stubs never leak into other tests"
key-files:
  created:
    - .planning/phases/02-exception-visibility-retrofit/before.xml
    - junit-outcome-diff.py
    - tests/Pellmonsrv/conftest.py
  modified: []
decisions: []
metrics:
  duration_minutes: 35
  completed: 2026-09-17
---

# Phase 2 Plan 01: Safety Net & Import-Stub Fixture Summary

Captured the Phase 2 pre-change JUnit outcome baseline, built a stdlib-only outcome-diff tool that proves ROADMAP Phase 2 success criterion 1, and added a `daemon_module` pytest fixture that stubs dbus/gi/pwd/grp so `Pellmonsrv.pellmonsrv` imports cleanly under test on the Windows `venv-py3` interpreter.

## What Was Built

### Task 1: Pre-change JUnit outcome baseline

Ran the full-truth suite on `venv-py3/Scripts/python.exe` (freshly created for this worktree — `py -3.14 -m venv venv-py3` + `pip install -r requirements.txt -r requirements-dev.txt`) before touching any `src/` file:

```
venv-py3/Scripts/python.exe -m pytest tests/ -v --junitxml=.planning/phases/02-exception-visibility-retrofit/before.xml
```

**Result: 2 failed, 29 passed, 8 skipped, 39 testcases total.**

The two expected-red failures are present exactly as documented:
- `tests/test_plugin_imports.py::test_plugin_module_imports[scottecom]` — `ModuleNotFoundError: No module named 'protocol'`
- `tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import` — `ModuleNotFoundError: No module named 'frames'`

`git status --porcelain src/` was confirmed empty both immediately before this run and after — zero `src/` edits were made in this task.

### Task 2: `junit-outcome-diff.py`

Root-level stdlib-only (`xml.etree.ElementTree`, `sys`, `pathlib`) script implementing the comparison semantics from `02-RESEARCH.md`'s "Exact before/after comparison mechanism", with the required BEFORE-keyed refinement:

- `outcomes(path)` classifies each `<testcase>` as `fail`/`error`/`skip`/`pass` based solely on `<failure>`/`<error>`/`<skipped>` child presence — captured stdout/stderr log text and `<properties>` are never read (verified: `grep -c "system-out\|system-err" junit-outcome-diff.py` returns 0).
- CHANGED = BEFORE test_id whose AFTER outcome differs.
- DISAPPEARED = BEFORE test_id missing from AFTER.
- ADDED = AFTER-only test_id, reported informationally, never causes a nonzero exit (Phase 2 plans 02/03/04/06 add new test files whose IDs only exist in AFTER).
- Exit 0 + literal `IDENTICAL pass/fail/skip status before and after` when CHANGED and DISAPPEARED are both empty; exit 1 naming each offending test_id and its `before -> after` pair otherwise.

Verified:
- Self-comparison (`before.xml` vs itself) exits 0 and prints the literal success line.
- A deliberately mutated copy (one passing `<testcase>` given an injected `<failure/>` child, written to the scratchpad) exits 1 and names `tests.Pellmonsrv.plugins.test_mocked_transport_smoke::test_loop_serial_roundtrip` with `pass -> fail`.
- `grep -n "^import\|^from" junit-outcome-diff.py` shows only `sys`, `xml.etree.ElementTree`, `pathlib`.

### Task 3: `tests/Pellmonsrv/conftest.py` — `daemon_module` fixture

Provides a `daemon_module` fixture that imports `Pellmonsrv.pellmonsrv` on any interpreter, including `venv-py3` on Windows (no `dbus`, `gi`, `pwd`, or `grp`):

- Injects `sys.modules` stubs for `dbus`, `dbus.service`, `dbus.mainloop`, `dbus.mainloop.glib`, `gi`, `gi.repository`, `pwd`, `grp` — only for names not already importable (no-op passthrough on real Linux/Docker).
- The `dbus.service` stub supplies a real subclassable `Object` (permissive `__init__`) and identity-decorator `method`/`signal` callables, satisfying `pellmonsrv.py`'s class-definition-time `class MyDBUSService(dbus.service.Object)` and seven `@dbus.service.method(...)`/`@dbus.service.signal(...)` decorators.
- `dbus.mainloop.glib` stub exposes a callable `DBusGMainLoop`; `gi.repository` stub exposes `GLib`/`GObject` MagicMocks; `pwd`/`grp` stubs expose `getpwnam`/`getgrall`/`getgrnam`/`getgrgid` MagicMocks (used by `pellmonsrv.getgroups`/`drop_privileges`, never called by the caplog tests this fixture unblocks).
- Teardown (in a `try/finally`) removes every injected stub key plus any `Pellmonsrv.pellmonsrv`/`Pellmonsrv.database`-prefixed `sys.modules` entries the import created, so stubs cannot leak into `tests/test_plugin_imports.py`'s real import checks.
- Docstring explicitly states "This is NOT a production shim" per the plan's requirement.

Verified via a throwaway scratch test (written, run, then deleted — not part of the committed deliverable):
- `daemon_module.__name__ == "Pellmonsrv.pellmonsrv"`, `hasattr(daemon_module, "Poller")`, `hasattr(daemon_module, "MyDBUSService")` all passed.
- Full suite after using the fixture: `venv-py3/Scripts/python.exe -m pytest tests/ -q -m "not known_broken"` → `29 passed, 8 skipped` (matches baseline exactly), exit 0.
- Full-truth run captured to a temp JUnit XML and diffed against `before.xml` via `junit-outcome-diff.py`: 0 changed, 0 disappeared, 1 added (the throwaway scratch test itself, informational only) → `IDENTICAL pass/fail/skip status before and after`. Confirmed `test_plugin_module_imports[scottecom]` still fails and grp/pwd-dependent plugin imports still skip, proving no stub leakage.

## Environment Note

`venv-py3` is gitignored and was not present in this worktree checkout. Created fresh: `py -3.14 -m venv venv-py3` then `venv-py3/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt`. Installed versions: pytest 9.1.1, CherryPy 18.10.0, Mako 1.4.1, pyserial 3.5, pytest-cov 7.1.0, pytest-mock 3.15.1, pytest-socket 0.8.1.

## Deviations from Plan

None — plan executed exactly as written. No auto-fixes, no architectural changes, no auth gates.

## Known Stubs

None applicable — `daemon_module`'s dbus/gi/pwd/grp stubs are the plan's explicit, documented deliverable (a test-only import shim), not an undocumented stub masking missing functionality. The fixture's docstring makes this explicit ("NOT a production shim").

## Threat Flags

None — this plan adds test infrastructure only (a baseline capture, a comparison script, and a pytest fixture); no runtime source file under `src/` was edited, matching the plan's `<threat_model>` of N/A.

## Self-Check: PASSED

- `.planning/phases/02-exception-visibility-retrofit/before.xml` — FOUND
- `junit-outcome-diff.py` — FOUND
- `tests/Pellmonsrv/conftest.py` — FOUND
- Commit `9306d84` (before.xml capture) — FOUND in `git log --oneline --all`
- Commit `d398200` (junit-outcome-diff.py) — FOUND in `git log --oneline --all`
- Commit `ba6d545` (daemon_module fixture) — FOUND in `git log --oneline --all`
