---
phase: 02-exception-visibility-retrofit
plan: 06
subsystem: testing
tags: [ast, static-analysis, print-enforcement, junit-xml, regression-check, roadmap-alignment]
dependency-graph:
  requires:
    - "02-01 (before.xml baseline, junit-outcome-diff.py tool)"
    - "02-02 (PluginManager logging + caplog tests)"
    - "02-03 (pellmonsrv.py logging + caplog tests)"
    - "02-04 (calculate plugin logging + caplog tests)"
    - "02-05 (39-print sweep across 11 files)"
  provides:
    - "tests/test_no_ad_hoc_print.py (executable OBS-03 enforcement gate)"
    - ".planning/phases/02-exception-visibility-retrofit/after.xml (post-phase JUnit outcome record)"
    - "Verified outcome parity against before.xml (0 changed, 0 disappeared)"
    - "Amended ROADMAP Phase 2 criterion 4 (aligned with D-01) and Phase 3 inherited scope"
  affects:
    - "Phase 3 (inherits Scotteprotocol/protocol.py exception sweep alongside IMPORT-01)"
tech-stack:
  added: []
  patterns:
    - "AST NodeVisitor for static print() detection scoped to runtime code"
    - "Path-and-string-fragment keyed allowlist for CLI startup banners"
key-files:
  created:
    - tests/test_no_ad_hoc_print.py
    - .planning/phases/02-exception-visibility-retrofit/after.xml
  modified:
    - .planning/ROADMAP.md
decisions:
  - "D-01 alignment: ROADMAP Phase 2 criterion 4 references shared logging.getLogger('pellMon') instead of getLogger(__name__)"
  - "Scotteprotocol deferral: Recorded in Phase 3 detail block as inherited work alongside IMPORT-01"
metrics:
  duration_minutes: 30
  completed: 2026-09-18
---

# Phase 2 Plan 06: Phase Gate & Regression Verification Summary

Enforced OBS-03 via an AST-based pytest gate (`tests/test_no_ad_hoc_print.py`), captured the post-retrofit JUnit XML test outcome record (`after.xml`), proved exact outcome parity against `before.xml` using `junit-outcome-diff.py`, and aligned `.planning/ROADMAP.md` Phase 2 and Phase 3 specifications with locked architectural decisions.

## What Was Built

### Task 1: OBS-03 Print-Enforcement Test (`tests/test_no_ad_hoc_print.py`)

Implemented an AST-driven test that scans all `.py` files under `src/Pellmonsrv/` and `src/Pellmonweb/` (excluding `.py2bak` backups):
- Discovers all `ast.Call` nodes invoking `print`.
- Enforces that no ad hoc `print()` calls exist in runtime code.
- Exempts only the three sanctioned CLI startup banner lines in `src/Pellmonweb/pellmonconf.py` (D-04), keyed by path and literal argument string fragment (`Open http://<ip>:%u`, `Run as root to be able to save changes`, `Quit with CTRL-C`), not by fragile line numbers.
- Includes a non-vacuousness test (`test_print_allowlist_is_not_vacuous`) asserting all three allowlisted sites exist in source.
- Verified Tripwire / Negative Test: Temporarily injected `print('scratch')` into `src/Pellmonsrv/database.py:23`. The test failed with:
  ```
  AssertionError: Found 1 disallowed print() call(s) in runtime code:
    - src/Pellmonsrv/database.py:23 (arg preview: 'scratch')
  ```
  Reverting the injected line restored 100% test pass (`2 passed in 0.20s`).

### Task 2: Post-Change Outcome Record & Parity Diff (`after.xml`)

Captured `after.xml` using `venv-py3/Scripts/python.exe` on Windows, matching the environment and interpreter from `02-01-SUMMARY.md`:

```
venv-py3/Scripts/python.exe -m pytest tests/ -v --junitxml=.planning/phases/02-exception-visibility-retrofit/after.xml
```

#### Test Suite Tallies
- **Before-run tally (`02-01-SUMMARY.md`)**:
  `2 failed, 29 passed, 8 skipped, 39 testcases total`
- **After-run tally (`after.xml`)**:
  `2 failed, 42 passed, 8 skipped, 2 warnings in 1.83s, 52 testcases total`

#### Documented Expected-Red Failures (Unchanged)
The two expected-red failures from Phase 1 remain failing with identical error types:
1. `tests/test_plugin_imports.py::test_plugin_module_imports[scottecom]`
   `ModuleNotFoundError: No module named 'protocol'` (raised from `src/Scotteprotocol/__init__.py:2`)
2. `tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import`
   `ModuleNotFoundError: No module named 'frames'` (raised from `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:27`)

#### Outcome Diff (`junit-outcome-diff.py`)
```
BEFORE test count: 39
AFTER test count:  52
CHANGED:     0
DISAPPEARED: 0
ADDED:       13 (informational only, not a failure)

ADDED (present only in AFTER, informational):
  tests.Pellmonsrv.plugins.test_calculate_logging::test_activate_reraise_preserved -> pass
  tests.Pellmonsrv.plugins.test_calculate_logging::test_getitem_calc_failure_visibility -> pass
  tests.Pellmonsrv.plugins.test_calculate_logging::test_plain_item_access_produces_no_log_records -> pass
  tests.Pellmonsrv.plugins.test_calculate_logging::test_setitem_namerror_visibility -> pass
  tests.Pellmonsrv.test_pellmonsrv_logging::test_module_level_logger_available_before_daemon_run -> pass
  tests.Pellmonsrv.test_pellmonsrv_logging::test_plugin_activation_debug_mode_reraises -> pass
  tests.Pellmonsrv.test_pellmonsrv_logging::test_plugin_activation_failure_logs_traceback -> pass
  tests.Pellmonsrv.test_pellmonsrv_logging::test_poller_item_read_failure_logs_traceback -> pass
  tests.Pellmonsrv.test_plugin_manager_logging::test_broken_plugin_exec_failure_logs_error_with_traceback -> pass
  tests.Pellmonsrv.test_plugin_manager_logging::test_malformed_descriptor_logs_debug_with_traceback -> pass
  tests.Pellmonsrv.test_plugin_manager_logging::test_normal_plugin_scan_probe_stays_silent -> pass
  tests.test_no_ad_hoc_print::test_no_ad_hoc_print_calls_in_runtime_code -> pass
  tests.test_no_ad_hoc_print::test_print_allowlist_is_not_vacuous -> pass

IDENTICAL pass/fail/skip status before and after
```
**Diff Tool Exit Code**: `0`

#### Green Baseline Check
```
venv-py3/Scripts/python.exe -m pytest tests/ -q -m "not known_broken"
42 passed, 8 skipped, 2 deselected, 2 warnings in 1.68s
```
**Green Baseline Exit Code**: `0`

### Task 3: ROADMAP Alignment (`.planning/ROADMAP.md`)

- **Alignment 1 (Scotteprotocol ownership)**: Added inherited scope statement to Phase 3 detail block:
  `Phase 3 inherits the exception-visibility sweep of src/Scotteprotocol/protocol.py's 19 bare/broad excepts alongside IMPORT-01, because the module cannot be imported under Python 3 today (verified: Scotteprotocol/__init__.py:2's from protocol import Protocol raises ModuleNotFoundError before protocol.py is loaded) and exception-visibility work in an unimportable module cannot be verified.`
- **Alignment 2 (D-01 logger convention)**: Updated Phase 2 criterion 4 to specify `the shared logging.getLogger('pellMon') logger at appropriate levels, per CONTEXT D-01` instead of `logging.getLogger(__name__)`.
- Verified structure: 5 Phase blocks intact, Phase 2 criteria numbered 1-4.

## Deviations from Plan

None — all deliverables completed and verified against their acceptance criteria.

## Threat Flags

None — this plan introduced test verification gates, captured JUnit XML test results, and updated documentation. No runtime code modifications or third-party dependencies added.

## Self-Check: PASSED

- `tests/test_no_ad_hoc_print.py` — FOUND, 2 tests passing
- `.planning/phases/02-exception-visibility-retrofit/after.xml` — FOUND, 52 testcases
- `.planning/ROADMAP.md` — FOUND, Phase 2 and 3 aligned
- Commit `5a5935a` (Task 1: tests/test_no_ad_hoc_print.py) — FOUND in `git log`
- Commit `d3fa539` (Task 2: after.xml) — FOUND in `git log`
- Commit `28a5428` (Task 3: ROADMAP.md) — FOUND in `git log`
- Pre-existing WIP files intact and uncommitted per constraints
