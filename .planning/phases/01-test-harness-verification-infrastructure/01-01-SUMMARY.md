---
phase: 01-test-harness-verification-infrastructure
plan: 01
subsystem: testing
tags: [pytest, pytest-mock, pytest-socket, pytest-cov, pyserial, cherrypy]

# Dependency graph
requires: []
provides:
  - "requirements-dev.txt with pinned pytest/pytest-mock/pytest-socket/pytest-cov, separate from production requirements.txt"
  - "Root pytest.ini: pythonpath=src, testpaths=tests, --disable-socket suite-wide guardrail, known_broken marker"
  - "tests/ tree mirroring src/ (tests/Pellmonsrv/, tests/Pellmonsrv/plugins/, tests/Pellmonweb/)"
  - "tests/conftest.py with loop_serial, mocked_udp_socket, cherrypy_request_ctx fixtures"
  - "TEST-01 smoke test proving both hardware-mock fixtures work with zero physical hardware"
affects: [01-02, 01-03, phase-4-protocol-module-hardening]

# Tech tracking
tech-stack:
  added: [pytest>=9.0, pytest-mock>=3.15, pytest-socket>=0.8, pytest-cov>=7.1]
  patterns:
    - "pythonpath=src ini option replaces sys.path.insert hacks in test files"
    - "loop:// pyserial URL handler for hardware-free serial fixture"
    - "mocker.patch('socket.socket') for hardware-free UDP fixture, applied after pytest-socket's global block"
    - "CherryPy thread-local monkeypatching (cherrypy.request/session/log) for auth tests without a live server"

key-files:
  created:
    - requirements-dev.txt
    - pytest.ini
    - tests/conftest.py
    - tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py
  modified: []

key-decisions:
  - "venv-py3 did not exist in this worktree (gitignored, not present in main checkout either) -- created it fresh with py -3.14 and installed requirements.txt + requirements-dev.txt into it, per plan's environment_facts describing venv-py3 as the intended interpreter"

patterns-established:
  - "Fixture 1: loop_serial -> yields serial.serial_for_url('loop://', timeout=1), closed on teardown"
  - "Fixture 2: mocked_udp_socket -> mocker.patch('socket.socket').return_value, pre-configured with recvfrom.return_value = (b'', ('0.0.0.0', 0))"
  - "Fixture 3: cherrypy_request_ctx -> patches cherrypy.request/session/log; every AuthController test must request this fixture due to auth.py's bare except: calling cherrypy.log with cherrypy.request.headers"

requirements-completed: [TEST-01]

# Metrics
duration: 20min
completed: 2026-09-17
---

# Phase 1 Plan 1: Test Harness Foundation Summary

**pytest harness stood up from scratch (pytest.ini, tests/ tree, three shared fixtures) with a self-contained smoke test proving hardware-free serial and UDP mocking both work under a suite-wide real-socket block.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-17T05:05:00Z (approx)
- **Completed:** 2026-09-17T05:25:38Z
- **Tasks:** 3
- **Files modified:** 4 created

## Accomplishments
- `requirements-dev.txt` added at repo root with pinned dev/test dependencies, `requirements.txt` left untouched
- `pytest.ini` centralizes `sys.path` setup (`pythonpath = src`) and enables `--disable-socket` as a suite-wide guardrail against accidental real network I/O
- Three reusable fixtures (`loop_serial`, `mocked_udp_socket`, `cherrypy_request_ctx`) now available to every future test file in `tests/`
- TEST-01 demonstrated: a real `Serial`-compatible round-trip via `loop://` and a fully mocked UDP `sendto`/`recvfrom` cycle, both green with zero physical hardware and zero real sockets

## Task Commits

Each task was committed atomically:

1. **Task 1: Create requirements-dev.txt and verify the venv-py3 environment** - `11fc472` (feat)
2. **Task 2: Create pytest.ini and the tests/ tree with shared fixtures** - `67f57a5` (feat)
3. **Task 3: Write the mocked-transport smoke test (TEST-01)** - `ea0cb46` (test)

_Plan metadata commit and STATE.md/ROADMAP.md updates are owned by the orchestrator after this wave completes (parallel-worktree execution mode)._

## Files Created/Modified
- `requirements-dev.txt` - dev-only pytest/pytest-mock/pytest-socket/pytest-cov pins
- `pytest.ini` - pythonpath, testpaths, --disable-socket addopts, known_broken marker
- `tests/conftest.py` - loop_serial, mocked_udp_socket, cherrypy_request_ctx fixtures
- `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py` - TEST-01 smoke test (2 tests)

## Decisions Made
- **venv-py3 setup (Rule 3 - blocking issue):** The plan's `<environment_facts>` describe `venv-py3/Scripts/python.exe` as an already-existing interpreter with `cherrypy` and `pyserial` installed. In this worktree, `venv-py3/` does not exist (it's gitignored and worktrees only carry tracked files; it was also absent from the main checkout root). Created it fresh with `py -3.14 -m venv venv-py3`, installed `requirements.txt` then `requirements-dev.txt` into it. This matches the plan's intent exactly (same interpreter version, same package set) and unblocked every verification step in the plan without requiring any plan changes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created missing venv-py3 dev environment**
- **Found during:** Task 1 (environment verification)
- **Issue:** `venv-py3/Scripts/python.exe`, the interpreter the plan's environment_facts and all three tasks' verify/acceptance steps depend on, did not exist in this worktree checkout.
- **Fix:** `py -3.14 -m venv venv-py3`, then `pip install -r requirements.txt` and `pip install -r requirements-dev.txt` into it.
- **Files modified:** None tracked (venv-py3/ is gitignored, matches existing `.gitignore` entry `venv-py3/`)
- **Verification:** `venv-py3/Scripts/python.exe -m pytest --version` prints `pytest 9.1.1`; the Open-Question-1 spike (`import Pellmonsrv.database, Pellmonsrv.plugins.testplugin, Pellmonweb.auth`) prints `spike ok` with no `directories.py` stub present, matching the plan's expected outcome exactly.

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to execute any part of this plan; no scope creep, no changes to plan intent or fixture contracts.

## Issues Encountered
- `pytest --collect-only -q` returns exit code 5 ("no tests collected") after Task 2 completes but before Task 3 adds a test file — this is standard pytest behavior for zero collected items, not a collection error. Confirmed resolved (exit 0, 2 items collected) once Task 3's test file exists; the plan's overall `<verification>` section (run after all tasks) passes cleanly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `loop_serial`, `mocked_udp_socket`, `cherrypy_request_ctx` fixture contracts are stable and match the `<interfaces>` block plans 01-02 and 01-03 depend on
- Plan 01-02/01-03 can now add `tests/Pellmonsrv/test_database.py`, `tests/Pellmonweb/test_auth.py`, and `tests/test_plugin_imports.py` on top of this harness with no further scaffolding needed
- Phase 4 (PROTO-04) has a proven mechanism (`loop_serial`/`mocked_udp_socket`) ready to wire into `Scotteprotocol.Protocol`/`nbeprotocol.Proxy` once those packages' import breakage is fixed in Phase 3
- No blockers

---
*Phase: 01-test-harness-verification-infrastructure*
*Completed: 2026-09-17*
