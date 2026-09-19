---
phase: 02-exception-visibility-retrofit
plan: 03
subsystem: infra
tags: [logging, exception-visibility, pytest, caplog, threading]

requires:
  - phase: 02-exception-visibility-retrofit
    provides: "before.xml JUnit baseline, junit-outcome-diff.py, tests/Pellmonsrv/conftest.py::daemon_module fixture (plan 02-01)"
provides:
  - "Module-level `pellMon` logger in src/Pellmonsrv/pellmonsrv.py, usable before MyDaemon.run()/config.__init__ run"
  - "logger.exception (full traceback) on the daemon's plugin-activation loop, both Poller item-read failure branches, the whole-poll-iteration catch-all, and db_copy_thread's safety net"
  - "Zero print() calls in pellmonsrv.py"
  - "tests/Pellmonsrv/test_pellmonsrv_logging.py — 4 caplog/behavior regression tests"
affects: [02-05, 02-06]

tech-stack:
  added: []
  patterns:
    - "Module-level `logger = logging.getLogger('pellMon')` added alongside existing in-function `global logger` assignments -- behavior-identical since getLogger returns the same process-wide singleton, but makes daemon-side code importable/testable in isolation before any daemon bootstrap function has run"
    - "except Exception: / logger.exception(msg) replaces except Exception as e: / logger.info(str(e)) for Category A (failure-critical, non-credential) daemon paths -- full traceback at ERROR level instead of a one-line message"

key-files:
  created:
    - tests/Pellmonsrv/test_pellmonsrv_logging.py
    - .planning/phases/02-exception-visibility-retrofit/deferred-items.md
  modified:
    - src/Pellmonsrv/pellmonsrv.py

key-decisions:
  - "Module-level logger placed immediately after `import logging.handlers` (before `import sys`), matching the plan's approx. line 24-25 anchor"
  - "Category B config-default fallbacks in config.__init__/drop_privileges left untouched -- converting them would print 10-20 tracebacks on every normal daemon start with a minimal pellmon.conf"
  - "sendmail_thread's except Exception as e: (credential-adjacent str(e) from smtplib) left untouched per 02-RESEARCH.md's Security Domain note"
  - "Database(threading.Thread, _Database) unhashable-class bug (found while writing Task 1's tests) is out of this plan's scope and NOT fixed in src/ -- logged to deferred-items.md, worked around with a per-test __hash__ monkeypatch only"

requirements-completed: [OBS-01, OBS-02, OBS-03]

duration: 45min
completed: 2026-09-17
---

# Phase 2 Plan 03: Daemon Activation & Polling Exception Visibility Summary

Added a module-level `pellMon` logger to `pellmonsrv.py` and converted six Category-A daemon-side failure paths (plugin activation, both Poller item-read branches, the whole-poll-iteration catch-all, and `db_copy_thread`'s bare-except) from one-line `.info`/`.debug` messages into full `logger.exception` tracebacks, removing the two remaining `print()` calls in the file.

## Performance

- **Duration:** ~45 min
- **Tasks:** 2/2 completed
- **Files modified:** 2 (1 test file created, 1 source file edited)

## Accomplishments

- `tests/Pellmonsrv/test_pellmonsrv_logging.py`: 4 caplog/behavior tests covering OBS-01 (daemon-side plugin activation), OBS-02 (Poller item-read failure), the debug-mode re-raise guard, and module-level logger availability. Confirmed RED against the unmodified source (3 of 4 failed with `NameError`/`AssertionError`, not a collection error), then GREEN after Task 2.
- `src/Pellmonsrv/pellmonsrv.py`: module-level `logger = logging.getLogger('pellMon')` added; 6 `logger.exception(...)` call sites now cover the daemon's Category A failure paths; both stray `print()` calls removed; Category B config-fallback section (config.__init__, drop_privileges) and the credential-adjacent `sendmail_thread` block left untouched exactly as the plan specified.
- `git diff --numstat src/Pellmonsrv/pellmonsrv.py`: 16 lines changed, 16 lines removed (well under the plan's <25-line budget).
- `junit-outcome-diff.py` against Wave 1's `before.xml`: **IDENTICAL pass/fail/skip status** -- 0 changed, 0 disappeared, 4 added (this plan's own new tests, informational only).

## Task Commits

Each task was committed atomically:

1. **Task 1: Write caplog regression tests for the activation loop and Poller failure paths** - `56f84da` (test)
2. **Task 2: Add a module-level logger and convert the Category A failure paths in pellmonsrv.py** - `6501292` (feat)

## Files Created/Modified

- `tests/Pellmonsrv/test_pellmonsrv_logging.py` - 4 caplog/behavior tests for the daemon's plugin-activation loop and Poller item-read failure path, all using the `daemon_module` fixture from plan 02-01
- `src/Pellmonsrv/pellmonsrv.py` - module-level `pellMon` logger; 6 `logger.exception` conversions; 2 `print()` calls removed
- `.planning/phases/02-exception-visibility-retrofit/deferred-items.md` - new file, records the out-of-scope `Database` unhashable-class bug found during Task 1

## Decisions Made

- Module-level `logger = logging.getLogger('pellMon')` is placed directly after `import logging.handlers`, immediately before `import sys` -- matches the plan's line-24-25 anchor and is verified behavior-identical to the two existing in-function `global logger; logger = logging.getLogger('pellMon')` assignments (`MyDaemon.run()`, `config.__init__`), since `logging.getLogger('pellMon')` always returns the same cached process-wide `Logger` singleton regardless of which scope calls it. This addition only changes *when* the name `logger` first resolves inside the module (at import time instead of after daemon bootstrap), not *what* it resolves to.
- Category B (config-default `try: <read one optional value> except: <hardcoded default>` blocks) and the credential-adjacent `sendmail_thread` exception handler were left completely untouched, per the plan's explicit disposition and 02-RESEARCH.md's Security Domain note.

## Deviations from Plan

### Auto-fixed Issues

None required fixing in the plan's own scope -- Task 2's five edits were applied exactly as specified in the plan's per-site table.

### Out-of-Scope Discovery (documented, not fixed)

**1. `Database(threading.Thread, _Database)` is unhashable, crashes on construction**
- **Found during:** Task 1 (writing the plugin-activation-loop caplog test)
- **Issue:** `_Database` (from `Pellmonsrv.database.Database`) subclasses `weakref.WeakValueDictionary`, which defines `__eq__` without `__hash__`, so Python auto-sets `__hash__ = None`. `Database` inherits this. `threading.Thread.__init__` registers every new thread in a `WeakSet` (`_dangling`), which requires the object to be hashable -- so `Database()` raises `TypeError: cannot use 'weakref.ReferenceType' as a set element (unhashable type: 'Database')` immediately on construction, on every CPython 3.4+ runtime. This is the exact class instantiated in `MyDaemon.run()` (`conf.database = Database()`), so the crash path is reachable in production, not just under test.
- **Why not fixed:** Out of this plan's declared scope (`files_modified`: the test file and pellmonsrv.py's Category-A conversions only) and the deviation rules' scope boundary explicitly excludes pre-existing issues not caused by this task's own changes.
- **Workaround:** `tests/Pellmonsrv/test_pellmonsrv_logging.py` monkeypatches `daemon_module.Database.__hash__ = object.__hash__` for the duration of the two tests that construct a real `Database()`; `src/Pellmonsrv/pellmonsrv.py` itself is unchanged.
- **Documented in:** `.planning/phases/02-exception-visibility-retrofit/deferred-items.md` with a suggested fix (explicit `__hash__ = object.__hash__` on the `Database` class) for a future phase.

---

**Total deviations:** 0 auto-fixed, 1 out-of-scope discovery deferred (not fixed).
**Impact on plan:** None -- the deferred discovery was worked around entirely within the test file; `pellmonsrv.py`'s diff matches the plan's per-site table exactly.

## Issues Encountered

None beyond the deferred `Database` hashability discovery above, which was resolved via test-only workaround rather than requiring a plan change.

## Known Stubs

None -- no hardcoded empty values, placeholder UI text, or unwired data sources were introduced by this plan.

## Threat Flags

None -- this plan only changes what gets logged (message content and level) on already-existing exception paths; no new network endpoints, auth paths, file-access patterns, or schema changes were introduced. All six converted messages interpolate only plugin names, item names, and a fixed literal string -- no credential-bearing values, matching the plan's `<threat_model>` audit.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- `pellmonsrv.py`'s daemon-side plugin-activation and RRD-polling failures now produce full tracebacks instead of silent one-line messages, satisfying ROADMAP Phase 2 success criteria 2 and 3 for this file.
- The `daemon_module` fixture (plan 02-01) is now proven to support real `Database()`/`Poller` construction under test (with the documented hashability workaround), which future Phase 2/3 plans touching `pellmonsrv.py` can reuse.
- `deferred-items.md`'s `Database` hashability bug should be picked up by a future daemon-hardening phase (candidate: Phase 3) -- it is a genuine production-reachable crash, independent of this phase's exception-visibility scope.

---
*Phase: 02-exception-visibility-retrofit*
*Completed: 2026-09-17*

## Self-Check: PASSED

- `tests/Pellmonsrv/test_pellmonsrv_logging.py` — FOUND
- `src/Pellmonsrv/pellmonsrv.py` — FOUND
- `.planning/phases/02-exception-visibility-retrofit/deferred-items.md` — FOUND
- Commit `56f84da` (Task 1 — failing caplog tests) — FOUND in `git log --oneline --all`
- Commit `6501292` (Task 2 — logger + Category A conversions) — FOUND in `git log --oneline --all`
