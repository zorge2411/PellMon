---
phase: 01-test-harness-verification-infrastructure
plan: 03
subsystem: testing
tags: [pytest, configparser, importlib, pytest-socket, plugin-discovery]

# Dependency graph
requires: ["01-01"]
provides:
  - "tests/test_plugin_imports.py: descriptor-driven, two-layer plugin import check covering all 15 .pellmon-plugin modules plus 4 legacy core modules (TEST-02)"
  - "tests/test_socket_guardrail.py: in-suite, non-vacuity-proven evidence that --disable-socket blocks real socket construction while the mocked_udp_socket fixture still works"
  - "tests/README.md: expected-red baseline documentation for Phases 2-5"
affects: [phase-3-import-hardening, phase-4-protocol-module-hardening]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Descriptor-driven test discovery: configparser scan of *.pellmon-plugin [Core] Module keys, resolved via pathlib.Path(__file__).resolve().parents[1], never hardcoded and never CWD-relative"
    - "Two-layer import check: Layer 1 (module-level import) catches most breakage; Layer 2 (explicit deferred-import probe) catches imports hidden inside activate() that would otherwise false-pass"
    - "known_broken marker used to keep confirmed migration defects visible as real FAILs (never xfail/skip) while still filterable out of the green baseline gate"

key-files:
  created:
    - tests/test_plugin_imports.py
    - tests/test_socket_guardrail.py
    - tests/README.md
  modified: []

key-decisions:
  - "venv-py3 did not exist in this worktree (gitignored, worktrees only carry tracked files) -- recreated with py -3.14 -m venv venv-py3 then pip install -r requirements.txt -r requirements-dev.txt, per the environment note in the executor prompt"

patterns-established:
  - "PLATFORM_UNAVAILABLE set with a per-entry justification comment, tripwired by test_skip_allowlist_cannot_hide_migration_defects() against ever including a real migration-defect module name"
  - "KNOWN_BROKEN_MODULES set drives pytest.param(..., marks=pytest.mark.known_broken) construction in the parametrize list, rather than per-test marker application"

requirements-completed: [TEST-02]

# Metrics
duration: 25min
completed: 2026-09-17
---

# Phase 1 Plan 3: Plugin Import Check & Socket Guardrail Summary

**Descriptor-driven pytest import check replaces the 4-module ad hoc `test-imports.py`, covers all 15 plugins via a two-layer (module-level + deferred-activate-time) check, and is proven to correctly FAIL exactly on ScotteCom (IMPORT-01) and NBEcom's deferred protocol import (IMPORT-02) — the two confirmed Python 3 migration defects Phase 3 will fix.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-09-17 (worktree reset to base `1585e1b`, venv-py3 rebuilt)
- **Completed:** 2026-09-17
- **Tasks:** 3
- **Files modified:** 3 created

## Accomplishments
- `tests/test_plugin_imports.py`: `discover_plugin_modules()` globs `*.pellmon-plugin` descriptors and parses `[Core] Module` via `configparser` — no hardcoded plugin list, resolved from the test file's own path (not process CWD)
- Layer 1 parametrizes all 15 discovered plugins plus the 4 core modules the legacy script covered; platform-unavailable failures (`grp`, `pwd`, `RPi`, `dbus`, `gi`) skip with a named reason, everything else propagates as a real FAIL
- Layer 2 (`test_nbecom_deferred_protocol_import`) imports `Pellmonsrv.plugins.nbecom.nbeprotocol.protocol` directly, exposing the protocol import that NBEcom defers inside `activate()` and that a naive per-module loop would false-pass
- Tripwire test (`test_skip_allowlist_cannot_hide_migration_defects`) asserts `PLATFORM_UNAVAILABLE` never overlaps with real broken-import module names
- `tests/test_socket_guardrail.py`: proves `--disable-socket` blocks real UDP and TCP `socket.socket()` construction with `SocketBlockedError`, and that the sanctioned `mocked_udp_socket` fixture still works under the block; non-vacuity independently confirmed via `--force-enable-socket` (see Verification below)
- `tests/README.md`: run commands, the exact two-case expected-red table with owning requirement IDs, the platform-skip list, invariants later phases must not break, and the Phase 4 hardware-mock hook pointer

## Task Commits

Each task was committed atomically:

1. **Task 1: Descriptor-driven two-layer plugin import check** - `4a2bbbc` (test)
2. **Task 2: In-suite proof the socket guardrail is enforcing** - `9e75397` (test)
3. **Task 3: Expected-red baseline documentation** - `4c4b2e1` (docs)

_Plan metadata commit and STATE.md/ROADMAP.md updates are owned by the orchestrator after this wave completes (parallel-worktree execution mode)._

## Files Created/Modified
- `tests/test_plugin_imports.py` - 22 collected test cases (15 plugin params + 4 core-module params + 3 standalone: discovery guard, deferred probe, tripwire)
- `tests/test_socket_guardrail.py` - 3 tests proving the socket guardrail blocks real sockets and doesn't block the mocked fixture
- `tests/README.md` - expected-red baseline and invariant documentation

## Verification Results

**Green baseline gate** (`pytest tests/ -m "not known_broken" -q`):
```
17 passed, 8 skipped, 2 deselected, 2 warnings in 1.38s
```
Exit 0.

**Full-truth run** (`pytest tests/ -v`):
```
2 failed, 17 passed, 8 skipped, 2 warnings in 1.47s
```
Failures: `test_plugin_module_imports[scottecom]` (`No module named 'protocol'`) and `test_nbecom_deferred_protocol_import` (`No module named 'frames'`) — matches `01-VALIDATION.md`'s Expected Red Baseline exactly.

**Socket-guardrail non-vacuity** (`pytest tests/test_socket_guardrail.py --force-enable-socket -v`):
```
FAILED tests/test_socket_guardrail.py::test_real_socket_construction_is_blocked
FAILED tests/test_socket_guardrail.py::test_real_tcp_socket_construction_is_blocked
2 failed, 1 passed in 0.06s
```
Confirms the two block-assertions are non-vacuous (they only pass because the block is real) while the mocked-fixture test remains unaffected.

**`git status --short src/ test-imports.py requirements.txt`:** empty — no production code, legacy script, or dependency manifest touched.

## Decisions Made
- **venv-py3 setup (Rule 3 - blocking issue):** Same situation as plan 01-01 — this worktree's `venv-py3/` did not exist (gitignored, worktrees only carry git-tracked content). Rebuilt with `py -3.14 -m venv venv-py3` then `pip install -r requirements.txt -r requirements-dev.txt`. Matches the environment note in this plan's execution prompt exactly.

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria (grep checks, collect-only counts, exact failure message substrings, `git status` emptiness) verified to pass as specified in 01-03-PLAN.md.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `tests/test_plugin_imports.py` is the instrument Phase 3 (IMPORT-01/IMPORT-02) will be measured against: once those imports are fixed, `scottecom` and `test_nbecom_deferred_protocol_import` should flip to PASS and the `known_broken` marker can be removed from them
- `tests/README.md` gives Phase 2/3 executors the exact expected-red baseline so a regression (a new unexpected failure) is immediately distinguishable from the known baseline
- No blockers

---
*Phase: 01-test-harness-verification-infrastructure*
*Completed: 2026-09-17*

## Self-Check: PASSED

All created files verified present: `tests/test_plugin_imports.py`, `tests/test_socket_guardrail.py`, `tests/README.md`, `.planning/phases/01-test-harness-verification-infrastructure/01-03-SUMMARY.md`.
All commit hashes verified present in `git log`: `4a2bbbc`, `9e75397`, `4c4b2e1`, `1e97bcb`.
