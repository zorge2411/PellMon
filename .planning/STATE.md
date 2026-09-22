---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_plan
stopped_at: Phase 7 complete (5/5) — ready to discuss Phase 08
last_updated: 2026-09-21T13:11:58.342Z
last_activity: 2026-09-21 -- Phase 07 planning complete
progress:
  total_phases: 8
  completed_phases: 5
  total_plans: 26
  completed_plans: 26
  percent: 63
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-17)

**Core value:** The daemon must actually talk to real burner hardware through its protocol plugins (Scotte, NBE) under Python 3 — a port where only the core modules import but the hardware plugins silently fail isn't done.
**Current focus:** Phase 08 — expose the burner svg depiction in settings to make the visi

## Current Position

Phase: 08
Plan: Not started
Status: Ready to plan
Last activity: 2026-09-21

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 26
- Average duration: - min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | - | - |
| 2 | 6 | - | - |
| 3 | 4 | - | - |
| 4 | 4 | - | - |
| 5 | 4 | - | - |
| 7 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Merged research's suggested Phase 5 (Security) and Phase 6 (CI/Deployment) into a single Phase 5 — both are independent of the protocol work and fit coarse granularity (3-5 phases) without breaking the required "security fixes after exception-visibility retrofit" ordering.
- Roadmap: Standard/horizontal phase structure used instead of MVP vertical slices — this is a bug-fix/hardening migration where phases are strictly dependency-ordered (test harness before fixes are trustworthy, import fixes before protocol code is reachable), not independently shippable user-facing feature slices.
- Phase 1 planning: Decision-coverage gate (`check.decision-coverage-plan`) reported D-01..D-05 as uncovered — this is a false negative. The mechanical grep only scans `must_haves`/`truths` XML fields, but the planner cited decisions inline in task `<action>` bodies instead (confirmed: `01-01-PLAN.md` lines 97, 138 cite D-02/D-01 verbatim). The independent gsd-plan-checker LLM review separately confirmed "Context Compliance: PASS — D-01 through D-05 each traced to an implementing task." Overridden and proceeded without re-planning.
- Phase 2 planning: Same decision-coverage gate false negative recurred for D-01..D-05 (same root cause — grep-based, only scans must_haves/truths). The independent gsd-plan-checker LLM review confirmed "Context compliance (D-01 through D-05): All five locked decisions are followed exactly as specified" with per-decision evidence (shared logger, 3-file scope, per-site Category A/B dispositions, print-sweep boundary, `logger.exception` idiom). Overridden and proceeded without re-planning. Plan-checker also found 1 blocker (RESEARCH.md Open Questions not marked resolved — fixed) and 2 warnings (02-05 touches 11 files, mitigated per checker's own note; REQUIREMENTS.md OBS-02/OBS-03 wording drift vs. locked CONTEXT.md decisions — fixed by syncing REQUIREMENTS.md to drop the Scotteprotocol mention and the `__name__`-logger wording).
- Research (Phase 2): Found a second, independent import-time bug in `plugins/calculate/__init__.py` — `from string import maketrans` at line 28 raises `ImportError` on Linux/WSL, distinct from the known `unicode()` bug at line 351. Tracked as new requirement `PROTO-05` (Phase 4). Also confirmed `Scotteprotocol/protocol.py` is unreachable via import today (fails in `Scotteprotocol/__init__.py:2` before reaching `protocol.py`'s own bug), so ROADMAP Phase 2 success criterion 3 and REQUIREMENTS.md OBS-02 were amended to exclude it — that file's exception-visibility work is deferred to Phase 3, bundled with IMPORT-01.

### Roadmap Evolution

- Phase 6 added: Enable Home Assistant MQTT device with settings on the web GUI (added 2026-09-20 after v1.0 closed; not yet planned)
- Phase 7 added: Persist RRD database and other relevant settings outside the Docker container (added 2026-09-21; not yet planned)
- Phase 8 added: Expose the burner SVG depiction in settings to make the visible representation more user friendly (added 2026-09-21; not yet planned)
- Phase 9 added: Add Docker Hub image publishing with semver versioning (added 2026-09-22; base reference doc copied in from an external project at docs/versioning-and-publish-reference.md — PowerShell-only, will need porting notes for this repo's Linux/CI environment; not yet planned)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 4 (Protocol Module Hardening): NBE's XTEA-encrypted UDP payloads and Scotte's checksum/byte-packing logic may need a short protocol-spec research pass during planning (per research/SUMMARY.md flag).
- Phase 5 (Security, CI & Deployment): D-Bus test infra (python-dbusmock) and systemd watchdog integration were only MEDIUM-confidence researched — worth a short research pass when planning this phase.
- All protocol-level fixes (Phase 4) are mocked-I/O verified only, never against physical hardware — must stay labeled "unit-verified, not hardware-verified" and not conflated with full verification.
- Phase 2 Wave 2 merge incident (self-corrected, no committed damage): the repo has a large pre-existing uncommitted WIP diff on `src/` from before this GSD session (user's own in-progress migration work, unrelated to any phase's scope). Merging Wave 2's 4 worktrees required stashing that WIP first; popping it back afterward produced one conflict in `pellmonsrv.py`, and my manual resolution + git's context-based auto-merge of the surrounding hunks accidentally orphaned the plugin-activation loop as dead code inside `Database.__eq__` (the WIP's own `__hash__`/`__eq__` addition — which incidentally fixes the exact unhashable-`Database` bug plan 02-03 flagged as a deferred item — landed between `__init__`'s last statement and the activation loop). Caught immediately by the post-merge test gate (2 unexpected failures beyond the known-red baseline), root-caused by inspection, and fixed by moving `__hash__`/`__eq__` after the activation loop. Full suite back to the exact expected baseline afterward. This fix lives only in the uncommitted WIP working tree, not in any Phase 2 commit — HEAD's committed `pellmonsrv.py` was never corrupted.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

### Quick Tasks Completed

| # | Description | Date | Commits | Directory |
|---|-------------|------|---------|-----------|
| 260919-atb | Review items 1-3: graph command injection (argv + validation), pellmonconf source/save allowlist, pellmoncli.in Python 3 port | 2026-09-19 | 6ca5c40, ee6d273, 02b748f | [260919-atb-fix-command-injection-in-graph-endpoint-](./quick/260919-atb-fix-command-injection-in-graph-endpoint-/) |
| 260919-bbw | Review items 4-8: shutil/subprocess in place of os.system, PBKDF2-only passwords (600k), web bind/cookie/CSRF hardening, .env ignored, NBE mock pincode check | 2026-09-19 | 124159d, 510e158, 67778a7 | [260919-bbw-fix-review-items-4-8-shell-calls-plainte](./quick/260919-bbw-fix-review-items-4-8-shell-calls-plainte/) |
| 260919-d5l | CI workflow fix: system python3 venv with --system-site-packages, drop setup-python and pip self-upgrade | 2026-09-19 | 6764a3e, 2f14310 | [260919-d5l-fix-ci-workflow-system-python-venv-drop-](./quick/260919-d5l-fix-ci-workflow-system-python-venv-drop-/) |
| 260919-gpe | Scotte burner emulator (tools/burner_sim.py, pty tests, README with 11 spec-vs-code discrepancies). Status incomplete: end-to-end run was blocked by the plugin loader bug (fixed in 260919-jiz) | 2026-09-19 | e614928, 7b236e6 | [260919-gpe-scotte-burner-emulator-for-integration-t](./quick/260919-gpe-scotte-burner-emulator-for-integration-t/) |
| 260919-jiz | Fix yapsy PluginManager to load plugins as real modules so relative imports work; ScotteCom now loads (all 15 plugins load in WSL except raspberrygpio, which needs RPi) | 2026-09-19 | a6b2cc1, 6caa694 | [260919-jiz-fix-yapsy-plugin-loading-so-relative-imp](./quick/260919-jiz-fix-yapsy-plugin-loading-so-relative-imp/) |
| 260919-olq | Fix Scotte CRLF retry frame duplication; `setItem` now returns 'OK' or raises ValueError/IOError instead of leaking raw bytes, so failed writes are no longer reported as OK to the web UI; failing-first tests in tests/test_scotte_protocol_bugs.py | 2026-09-19 | 03bc51e, 0d4aee0 | [260919-olq-fix-scotte-crlf-retry-duplication-and-se](./quick/260919-olq-fix-scotte-crlf-retry-duplication-and-se/) |

Full suite verified in WSL (Debian, Python 3.13): 246 passed, 5 skipped (platform guards). Plaintext web passwords are no longer accepted; `config/pellmon.conf` must hold a PBKDF2 hash.

Known open Scotte bugs (not yet fixed): `setDaemon` at `Scotteprotocol/protocol.py:77`, shared `Frame` singletons. (CRLF retry and `setItem` raw-bytes fixed in 260919-olq.)

## Session Continuity

Last session: 2026-09-18
Stopped at: Phase 5 verified & Milestone v1.0 complete
Resume file: None (Milestone complete)
