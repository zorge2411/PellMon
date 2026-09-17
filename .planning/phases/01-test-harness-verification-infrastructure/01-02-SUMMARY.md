---
phase: 01-test-harness-verification-infrastructure
plan: 02
subsystem: testing
tags: [pytest, sqlite, cherrypy, auth, keyval-storage]

# Dependency graph
requires: ["01-01"]
provides:
  - "TEST-03 coverage of Pellmonsrv/database.py Keyval_storage (init happy path + OperationalError fallback, writeval/readval roundtrip, non-str coercion, missing-key contract, confval upsert)"
  - "TEST-03 coverage of Pellmonweb/auth.py AuthController (credential check success/two failure modes, login/logout session flow) with no live CherryPy server"
  - "Fixed cherrypy_request_ctx fixture (tests/conftest.py) — cherrypy.session patch now uses create=True"
affects: [phase-2-exception-visibility-retrofit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real temp-file SQLite via tmp_path fixture as the test double for Keyval_storage — no mocking of sqlite3"
    - "mocker.patch.object(cherrypy, attr, ..., create=True) required for cherrypy.session since it's not a real module attribute outside a live request context"

key-files:
  created:
    - tests/Pellmonsrv/test_database.py
    - tests/Pellmonweb/test_auth.py
  modified:
    - tests/conftest.py

key-decisions:
  - "Fixed a latent bug in the cherrypy_request_ctx fixture (missing create=True on the cherrypy.session patch) discovered while writing AuthController tests — Rule 3 blocking-issue fix, not scope creep, since the fixture as originally written could not support any test that touches cherrypy.session"

requirements-completed: [TEST-03]

# Metrics
duration: 25min
completed: 2026-09-17
---

# Phase 1 Plan 2: Database and Auth Regression Coverage Summary

**Locked in Keyval_storage's SQLite behavior (both init paths, coercion, the crude 'error'-string-on-missing-key contract) and AuthController's credential/session flow against real temp-file SQLite and mocked CherryPy thread-locals, with zero assertions on the SEC-01 password-logging defect.**

## Performance

- **Duration:** ~25 min
- **Started:** (worktree setup + task execution)
- **Completed:** 2026-09-17
- **Tasks:** 2
- **Files modified:** 2 created, 1 modified

## Accomplishments
- `tests/Pellmonsrv/test_database.py` — 6 tests covering `Keyval_storage.__init__` (happy path and the `sqlite3.OperationalError` fallback `CREATE TABLE` branch, verified via a pre-seeded unrelated-schema DB file), `writeval`/`readval` roundtrip, non-`str` value coercion, the missing-key `'error'`-string contract (not an exception), and the `confval` upsert path through the nested bare `except:`.
- `tests/Pellmonweb/test_auth.py` — 6 tests covering `AuthController.check_credentials` (success, wrong password, unknown user), `login()` success (session set + `HTTPRedirect`) and failure (loginform rendered, no session, no redirect), and `logout()` (`HTTPRedirect` + session key set to `None`, not deleted). No CherryPy server started, no port bound.
- Both files respect the SEC-01 scope guard: assertions only on return values and session state, never on `cherrypy.log` call content, with a module-level comment recording the constraint.
- Nothing under `src/` modified — plan's additive-only scope guard held.

## Task Commits

Each task was committed atomically:

1. **Task 1: Test Keyval_storage against real temp-file SQLite** - `fec14b1` (test)
2. **Task 2: Test AuthController with mocked CherryPy thread-locals** - `22320db` (test, includes the `tests/conftest.py` fixture fix required to make it pass)

_Plan metadata commit and STATE.md/ROADMAP.md updates are owned by the orchestrator after this wave completes (parallel-worktree execution mode)._

## Files Created/Modified
- `tests/Pellmonsrv/test_database.py` - 6 `Keyval_storage` tests, real temp-file SQLite, no mocking
- `tests/Pellmonweb/test_auth.py` - 6 `AuthController` tests, mocked CherryPy thread-locals via `cherrypy_request_ctx`
- `tests/conftest.py` - fixed `cherrypy_request_ctx` fixture: `mocker.patch.object(cherrypy, "session", {}, create=True)`

## Decisions Made
- **Rule 3 (blocking issue) — fixed `cherrypy_request_ctx` fixture:** Running Task 2's first test raised `AttributeError: <module 'cherrypy'> does not have the attribute 'session'` from inside the fixture itself, before any `AuthController` test body ran. `cherrypy.session` is only a genuine module attribute once CherryPy's `SessionTool` has set it up for a live request; outside a live request it does not exist, so `mock.patch.object` needs `create=True` or it refuses to patch a nonexistent attribute. This was a pre-existing defect in the fixture as written in plan 01-01 (never exercised there, since 01-01's smoke test only used `loop_serial`/`mocked_udp_socket`). Fixed by adding `create=True` to the `cherrypy.session` patch call — one-line change, no change to the fixture's documented contract or return value.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed `cherrypy_request_ctx` fixture missing `create=True`**
- **Found during:** Task 2 (AuthController tests)
- **Issue:** `mocker.patch.object(cherrypy, "session", {})` raised `AttributeError` because `cherrypy.session` does not exist as a module attribute outside a live request/session context. This blocked every test in `tests/Pellmonweb/test_auth.py`.
- **Fix:** Added `create=True` to that one `mocker.patch.object` call in `tests/conftest.py`.
- **Files modified:** `tests/conftest.py`
- **Verification:** All 6 `test_auth.py` tests pass; full suite (`pytest tests/ -q`) still green at 14 passed (12 new + 2 from plan 01-01's smoke test).
- **Commit:** `22320db`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to execute Task 2; no scope creep — fix is a one-line correction to a fixture contract that was already documented as "must be applied to every AuthController test," it just didn't actually work yet.

## Issues Encountered
None beyond the fixture fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `tests/Pellmonsrv/test_database.py` and `tests/Pellmonweb/test_auth.py` give Phase 2 (exception visibility retrofit) a regression baseline for `Keyval_storage` and `AuthController` — Phase 2 claims to change only logging in these modules, and these 12 tests are how that claim gets proven (any behavior change beyond log level fails them).
- `cherrypy_request_ctx` fixture is now correct and stable for any future CherryPy-thread-local test (e.g. Phase 5 SEC-01 rewrite of `check_credentials`).
- No blockers.

---
*Phase: 01-test-harness-verification-infrastructure*
*Completed: 2026-09-17*
