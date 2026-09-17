---
phase: 02-exception-visibility-retrofit
plan: 04
subsystem: testing
tags: [logging, exception-visibility, caplog, pytest, python2-to-3-migration]

# Dependency graph
requires:
  - phase: 02-exception-visibility-retrofit
    provides: "before.xml JUnit outcome baseline, junit-outcome-diff.py, grp/pwd sys.modules stub technique (from plan 02-01)"
provides:
  - "Five logger.exception conversions in src/Pellmonsrv/plugins/calculate/__init__.py's Category A except blocks (activate x2, getItem, setItem, calcthread.run)"
  - "tests/Pellmonsrv/plugins/test_calculate_logging.py: caplog regression tests + a documented test-only string.maketrans shim"
affects: ["phase-4 (PROTO-02, PROTO-05 fixes to this same file)"]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Test-only string.maketrans = str.maketrans shim (undone in fixture teardown) to import an otherwise-Python-2-broken module purely for exception-visibility testing, documented in the test file's module docstring as NOT a production fix"
    - "logger.exception(msg) replacing logger.info(str(e))/logger.info(repr(e)) inside except blocks, preserving return values and re-raise control flow exactly"

key-files:
  created:
    - tests/Pellmonsrv/plugins/test_calculate_logging.py
  modified:
    - src/Pellmonsrv/plugins/calculate/__init__.py

key-decisions:
  - "Used '/' as the failing calc_prog test fixture (empty-stack pop raises IndexError -> Calc.run() converts to ValueError) rather than an arbitrary unknown token, since unknown tokens are pushed onto the stack as literals by the interpreter's catch-all and don't raise"
  - "Category B bare excepts (Calc interpreter control flow, missing calc_item fallbacks) left untouched -- confirmed via test_plain_item_access_produces_no_log_records asserting zero log records for plain-item access"

requirements-completed: [OBS-02]

# Metrics
duration: 25min
completed: 2026-09-17
---

# Phase 2 Plan 04: Calculate Plugin Exception Visibility Summary

Converted the five Category A `logger.info` calls in `plugins/calculate/__init__.py`'s except blocks to `logger.exception`, and added a caplog regression suite (using a test-only `string.maketrans` shim) proving the plugin's `NameError` from the Python-2-only `unicode()` call now produces a full traceback instead of a swallowed one-liner, while return values and Category B silence are unchanged.

## Performance

- **Duration:** 25 min
- **Tasks:** 2 completed
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `setItem()` on a calculated item still returns `'error'` but now logs an ERROR record with `exc_info[0] is NameError` (the OBS-02 smoking-gun case: `unicode(value)` at line 351)
- `getItem()` calc-run failures log a full traceback (calc_item name in the message) instead of a `repr()` one-liner
- `activate()`'s outer except still re-raises the original exception, now preceded by a `logger.exception` call
- Plain non-calculated item reads/writes (the dominant code path) still emit **zero** log records — pinned by a dedicated regression test
- The Phase 4 bugs (`from string import maketrans` line 28, `unicode(value)` line 351) are confirmed still present and still broken

## Task Commits

Each task was committed atomically:

1. **Task 1: Write caplog regression tests using the test-only maketrans shim** - `5077b52` (test)
2. **Task 2: Convert the five Category A log calls in calculate/__init__.py** - `545dae6` (feat)

_Note: This is a two-task plan where Task 1 establishes RED (assertion failures against the unmodified plugin) and Task 2 delivers GREEN — not a formal `tdd="true"` plan, but the same before/after discipline._

## Files Created/Modified
- `tests/Pellmonsrv/plugins/test_calculate_logging.py` - Four caplog tests (setItem NameError visibility, getItem calc-failure visibility, Category B silence guard, activate() re-raise preservation), plus a documented test-only grp/pwd + `string.maketrans` import shim
- `src/Pellmonsrv/plugins/calculate/__init__.py` - Five `except Exception as e: logger.info(...)` blocks converted to `except Exception: logger.exception(...)` (or, where the bound exception name is still needed for `raise e`, `except Exception as e: logger.exception(...)`); all five preserve their original return values and re-raise behavior exactly

## Decisions Made
- Test 2's calc program uses `'/'` (division with an empty stack) instead of an arbitrary "unknown token" string, because the `Calc` interpreter's catch-all branch (`else: self.stack.append(c)`) pushes unrecognized tokens as literal values rather than raising — `'/'` reliably triggers `IndexError` -> `ValueError` inside `Calc.run()`, which is what the plugin's `getItem` except block is designed to catch.
- Confirmed (via `store_setting`/`load_setting` inspection in `plugin_categories.py`) that a plain `'R'`-type item's `setItem()` falls through with an implicit `None` return (not `'error'`) when it hits the `except: if item['type'] == 'R/W': ...` fallback — this is pre-existing Category B control flow, left untouched; the test asserts the actual `None` behavior rather than an assumed `'error'`.

## Deviations from Plan

None - plan executed exactly as written. All five Category A edits match the plan's `<action>` specification verbatim (including EDIT 1's requirement to keep `except Exception as e:`/`raise e` at the inner `activate()` handler, and EDIT 4's requirement to preserve the `calc = Calc(prog, self.db)` line in `setItem`'s except block). No auto-fixes, no architectural changes, no auth gates.

## Issues Encountered

During Task 1's initial draft, two test assumptions were wrong and were corrected before commit (both are properties of the *existing, unmodified* plugin logic, not deviations from the plan's scope):
- The originally-chosen "unknown token" calc program for `getItem`'s failure test did not actually raise (the interpreter's catch-all pushes it as a literal) — replaced with `'/'` which reliably raises via empty-stack pop.
- The originally-assumed `setItem()` return value of `'error'` for a plain `'R'`-type item was wrong — the actual fallthrough return is `None` (Category B control flow, confirmed by reading `plugin_categories.py`'s `store_setting`). Test assertion corrected to match actual (unchanged) behavior.

Both corrections were made during Task 1's RED-phase authoring, before any `src/` edit, and did not require re-scoping.

## Verification Results

- `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_calculate_logging.py -v` — all four tests pass (GREEN, after Task 2)
- `grep -c "logger.exception" src/Pellmonsrv/plugins/calculate/__init__.py` → `5`
- `grep -c "logger.info" src/Pellmonsrv/plugins/calculate/__init__.py` → `0`
- `grep -n "from string import maketrans" src/Pellmonsrv/plugins/calculate/__init__.py` → still present (line 28, PROTO-05, Phase 4)
- `grep -n "unicode(value)" src/Pellmonsrv/plugins/calculate/__init__.py` → still present (line 351, PROTO-02, Phase 4)
- `git diff --numstat src/Pellmonsrv/plugins/calculate/__init__.py` (Task 2 commit) → `10 10` (exactly the expected 10 added / 10 removed)
- Bare `except:` count in the file unchanged at `8` before and after Task 2 (verified via `grep -vn "^\s*#" ... | grep -c "except:"`)
- `venv-py3/Scripts/python.exe -m pytest tests/ -q -m "not known_broken"` → `33 passed, 8 skipped, 2 deselected` (Phase 1 baseline was `29 passed, 8 skipped`; the +4 are this plan's new tests — identical pass/skip status for every pre-existing test ID)
- `venv-py3/Scripts/python.exe -m pytest tests/test_plugin_imports.py -v` (run immediately after the new test file, to check for shim leakage) → same 2 expected-red failures (`scottecom`, `nbecom` deferred-import), 12 passed, 8 skipped — confirms the grp/pwd/`maketrans` test-only shims do not leak into the real import checks

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `plugins/calculate/__init__.py`'s exception visibility is now complete for this phase's OBS-02 scope; Phase 4's PROTO-02 (`unicode()` fix) and PROTO-05 (`maketrans` import fix) can proceed against a file whose failure paths are already loud, making their fixes trivially verifiable via this plan's caplog test suite (which will need its test-only shim removed once PROTO-05 lands for real).
- No blockers for sibling Wave 2 plans (02-02, 02-03, 02-05) — this plan's file scope (`tests/Pellmonsrv/plugins/test_calculate_logging.py`, `src/Pellmonsrv/plugins/calculate/__init__.py`) has zero overlap with theirs.

---
*Phase: 02-exception-visibility-retrofit*
*Completed: 2026-09-17*
