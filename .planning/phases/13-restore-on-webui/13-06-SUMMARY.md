---
phase: 13-restore-on-webui
plan: 06
subsystem: docs
tags: [docs, restore, backup, deploy]
requires: [13-04, 13-05]
provides:
  - DEPLOY-PI.md web restore section, undo steps, recovery notes, failure rows
  - doc test test_deploy_guide_documents_web_restore
key-files:
  modified:
    - DEPLOY-PI.md
    - tests/test_backup_compose.py
    - .planning/phases/12-add-backup-of-rrd-database-and-settings-to-nas-or-other-med/12-CONTEXT.md
requirements-completed: [D-10, D-11, D-12, D-16]
completed: 2026-11-06
---

# Phase 13 Plan 06: Restore documentation Summary

Operator docs for the web restore (what is replaced, `.pre-restore` copies, config via host tool, Docker self-restart, manual undo, 11 new failure rows), enforced by doc tests. Task 2 (Pi UAT) is PENDING.

## Tasks
1. DEPLOY-PI.md, doc test, Phase 12 note. Commit 006deb7.
2. Restore on the real Pi (human-verify): **PENDING - not performed.** Assumptions A1 (Docker restarts the daemon) and A3 (rrdtool restore time on a Pi) remain unconfirmed. Steps are in 13-06-PLAN.md.

## Verification
WSL (venv-wsl) full suite: 1199 passed, 87 skipped, 25 failed. All 25 failures are in tests/test_pi_check.py (`bash -n tools/pi_check.sh` returns 2, likely CRLF line endings in the Windows checkout); unrelated to this plan. tests/test_backup_compose.py: 10 passed.

## Deviations from Plan
- Added two recovery notes requested by plan-checker findings: manual restart of pellmonsrv if Docker did not restart it; residual risk of other plugins writing stale settings in the ~2 s window between swap and restart.
- The Phase 12 note is inserted inline after "restore from the web GUI," in the Out-of-scope sentence.

## Known Stubs
None.

## Self-Check: PASSED
