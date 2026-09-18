# Roadmap: PellMon Python 3 Migration

## Overview

The Python 2→3 port was declared "complete" on the strength of a shallow import-smoke-test that never touched the hardware protocol plugins — ScotteCom and NBEcom are confirmed broken. This roadmap finishes the migration and gets it production-ready through a dependency-driven safe order: first build a hardware-free test harness so every later fix has a real pass/fail signal, then make failures loud (exception visibility) as its own behavior-preserving step so regressions stay bisectable, then fix the import breakage that's actually blocking the two hardware plugins, then fix the protocol-level bytes/str bugs those imports were hiding, and finally close out security gaps and CI/deployment hardening now that there's a trustworthy codebase and test suite to enforce against.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Test Harness & Verification Infrastructure** - Build a hardware-free pytest suite (mocked serial/UDP) and a broadened import-check so every later phase has a real pass/fail signal instead of "it imports." (completed 2026-09-17)
- [ ] **Phase 2: Exception Visibility Retrofit** - Replace bare `except:` with logged, traceback-visible failures in plugin loading and protocol/database paths, behavior-preserving, verified against Phase 1's harness.
- [ ] **Phase 3: Import Strategy & Plugin Loading Fixes** - Fix the broken implicit relative imports so ScotteCom and NBEcom actually load and activate under Python 3.
- [ ] **Phase 4: Protocol Module Hardening (Bytes/Str Semantics)** - Fix the confirmed bytes/str `TypeError` and related protocol bugs, add constructor-injectable transports, verify with round-trip tests.
- [ ] **Phase 5: Security, CI & Deployment Hardening** - Close credential/logging/shell-injection security gaps and lock in a CI pipeline plus graceful shutdown, healthchecks, pinned deps, and cleanup.

## Phase Details

### Phase 1: Test Harness & Verification Infrastructure

**Goal**: Developer has a real, automated pass/fail signal for protocol and plugin code, without needing physical burner hardware.
**Depends on**: Nothing (first phase)
**Requirements**: TEST-01, TEST-02, TEST-03
**Success Criteria** (what must be TRUE):

  1. Developer can run `pytest` locally and it exercises protocol encode/decode logic via mocked serial (`loop://`) and mocked UDP sockets, with no real hardware I/O required.
  2. Running the broadened import-check imports every plugin package (including `scottecom` and `nbecom`, not just the 4 core modules `test-imports.py` covers today) and fails with a nonzero exit when any plugin's import is broken.
  3. Developer can run a `pytest` suite covering `database.py` (SQLite keyval get/set/init, including the fallback table-creation path) and `Pellmonweb/auth.py` (credential check, session login flow), and it passes against current behavior.
  4. A real (unmocked) socket call made accidentally during a test run causes that test to fail loudly instead of hanging or silently succeeding.

**Plans**: 3 plans (2 waves)

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Harness foundation: `requirements-dev.txt`, `pytest.ini`, `tests/` tree, shared fixtures, mocked-transport smoke test (TEST-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Unit coverage for `database.py` `Keyval_storage` and `Pellmonweb/auth.py` `AuthController` (TEST-03)
- [x] 01-03-PLAN.md — Descriptor-driven two-layer plugin import-check, socket-guardrail enforcement test, expected-red baseline doc (TEST-02)

### Phase 2: Exception Visibility Retrofit

**Goal**: Plugin, protocol, and database failures are logged with full tracebacks instead of being silently swallowed — a purely observability change, with no logic altered.
**Depends on**: Phase 1
**Requirements**: OBS-01, OBS-02, OBS-03
**Success Criteria** (what must be TRUE):

  1. Re-running Phase 1's test suite and import-check before and after this phase produces identical pass/fail and plugin-activation results — only log output changes.
  2. A deliberately triggered plugin import/activation failure produces a full traceback via `logger.exception(...)` in the logs instead of being silently skipped by a bare `except:` in the yapsy plugin manager.
  3. A deliberately triggered protocol-parsing or database-write failure in `pellmonsrv.py` or `plugins/calculate/__init__.py` logs a full traceback instead of being swallowed. (`Scotteprotocol/protocol.py` is excluded here — confirmed unreachable via import today, since `Scotteprotocol/__init__.py:2`'s broken import fails before `protocol.py` is ever loaded; its exception-visibility work is deferred to Phase 3, after the import fix lands.)
  4. A repo-wide search finds no remaining ad hoc `print()` calls in `src/` outside of intentional CLI output; runtime code uses the shared `logging.getLogger('pellMon')` logger at appropriate levels, per CONTEXT D-01.

**Plans**: 6 plans (3 waves)

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Pre-change outcome baseline (`before.xml`), JUnit outcome-diff tool, daemon-import stub fixture (OBS-01, OBS-02)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — OBS-01: yapsy `PluginManager.py` plugin-load/descriptor/probe dispositions + caplog test
- [x] 02-03-PLAN.md — OBS-01/OBS-02: `pellmonsrv.py` module logger, activation-loop + Poller Category A conversions, 2 prints removed + caplog tests
- [x] 02-04-PLAN.md — OBS-02: `plugins/calculate/__init__.py` 5 Category A conversions + caplog tests via test-only `maketrans` shim
- [x] 02-05-PLAN.md — OBS-03: 39-print sweep across 11 files, shared `pellMon` logger added to 5 logger-less modules

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 02-06-PLAN.md — Phase gate: AST-based print-enforcement test, `after.xml` capture + outcome-parity diff, ROADMAP alignment

### Phase 3: Import Strategy & Plugin Loading Fixes

**Goal**: ScotteCom and NBEcom actually load and activate under Python 3, and import style is consistent across the codebase.
**Depends on**: Phase 2
**Requirements**: IMPORT-01, IMPORT-02, IMPORT-03, IMPORT-04
Phase 3 inherits the exception-visibility sweep of `src/Scotteprotocol/protocol.py`'s 19 bare/broad excepts alongside IMPORT-01, because the module cannot be imported under Python 3 today (verified: `Scotteprotocol/__init__.py:2`'s `from protocol import Protocol` raises `ModuleNotFoundError` before `protocol.py` is loaded) and exception-visibility work in an unimportable module cannot be verified.
**Success Criteria** (what must be TRUE):

  1. The ScotteCom plugin imports and activates successfully under Python 3 — Phase 1's broadened import-check passes for it with no `ModuleNotFoundError`.
  2. The NBEcom plugin imports and activates successfully under Python 3 — Phase 1's broadened import-check passes for it with no `ModuleNotFoundError`.
  3. A repo-wide search finds no remaining `sys.path.append` shims in `src/`; intra-package imports use explicit relative imports (PEP 328), with absolute imports used only at the yapsy `exec()`-loaded plugin `__init__.py` boundary.
  4. `Scotteprotocol` and `nbecom/nbeprotocol` load together (both plugins active in the same daemon process) with no duplicate-module-name collision.

**Plans**: TBD

### Phase 4: Protocol Module Hardening (Bytes/Str Semantics)

**Goal**: Scotte and NBE protocol modules correctly separate bytes and str at I/O boundaries and are independently testable without hardware.
**Depends on**: Phase 3
**Requirements**: PROTO-01, PROTO-02, PROTO-03, PROTO-04, PROTO-05
**Success Criteria** (what must be TRUE):

  1. NBEcom `Proxy.get()` splits response payloads correctly without raising `TypeError`, verified by a mocked-UDP round-trip test.
  2. Calculate plugin's `setItem()` no longer raises `NameError` from the leftover Python 2 `unicode()` call.
  3. The daemon can redirect stderr to a log file in daemonized mode without raising `ValueError: can't have unbuffered text I/O`.
  4. `Scotteprotocol.Protocol` and `nbeprotocol.Proxy` accept a constructor-injectable `transport` parameter, and per-frame-type encode/decode round-trip tests pass against it via the Phase 1 harness.

**Plans**: TBD

### Phase 5: Security, CI & Deployment Hardening

**Goal**: The production deployment is secure, enforced by CI on every change, and operationally robust for restart/redeploy.
**Depends on**: Phase 4
**Requirements**: SEC-01, SEC-02, SEC-03, OPS-01, OPS-02, OPS-03, OPS-04, OPS-05, OPS-06
**Success Criteria** (what must be TRUE):

  1. A failed web login no longer writes the submitted plaintext password to logs, and stored/compared web-auth credentials are hashed, with a documented one-time migration path for existing plaintext passwords in `config/pellmon.conf`.
  2. The Exec plugin's readscript path runs with `shell=False` and an explicit argument list, matching the writescript path's existing safe pattern.
  3. A GitHub Actions CI pipeline (Linux runner) runs the pytest suite and the broadened import-check on every pull request to `master`/`python3-migration` and blocks merge on failure.
  4. Sending SIGTERM to `pellmonsrv` or `pellmonweb` closes serial ports, releases D-Bus names, and flushes RRD writes cleanly, and `docker-compose.yml` defines a healthcheck for both services reflecting actual readiness.
  5. Dependency versions in `requirements.txt` are pinned (not `>=` floors), all `.py2bak` files have been removed from `src/`, and the README documents that production deployment is Linux-only.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Test Harness & Verification Infrastructure | 3/3 | Complete    | 2026-09-17 |
| 2. Exception Visibility Retrofit | 5/6 | In Progress|  |
| 3. Import Strategy & Plugin Loading Fixes | 0/TBD | Not started | - |
| 4. Protocol Module Hardening | 0/TBD | Not started | - |
| 5. Security, CI & Deployment Hardening | 0/TBD | Not started | - |
