---
phase: 13-restore-on-webui
plan: 02
subsystem: backup
tags: [backup, restore, rrdtool, sqlite, swap]
requires: [13-01]
provides:
  - build_rrd, rrd_layout, rrd_last, check_layout, carry_over_settings, keep_pre_restore, swap_in, write_result, read_result, restore_archive in backup_core
affects: [13-04]
key-files:
  modified: [src/Pellmonsrv/backup_core.py, tests/Pellmonsrv/test_backup_restore.py]
decisions:
  - Swap failure rolls back already replaced targets from .pre-restore inside the locks and raises REASON_SWAP
  - should_continue False before the swap raises REASON_ARCHIVE_DAMAGED (per plan) with live files untouched
metrics:
  tasks: 2
  completed: 2026-11-06
---

# Phase 13 Plan 02: Restore engine swap Summary

`restore_archive` rebuilds the archive RRD with `rrdtool restore` into `<db>.restore-new`, checks layout (step and ordered DS names against the live RRD, or `poll_ds_names`) and a one-day future-clock limit, stages the settings DB with the Backup page's own `backup.config`/`backup.state` rows carried over, then swaps everything under the caller's locks with 0600 `.pre-restore` copies and rollback. Results persist in a sanitised 0600 `.restore-result.json`.

## Commit
- (single commit for both tasks, see deviations) feat(13-02): restore engine RRD rebuild, layout checks, locked swap with rollback, result file

## Verification
- Windows host: test_backup_restore.py 45 passed, 22 skipped (POSIX-only / real-rrdtool tests).
- WSL Debian (venv-wsl, real rrdtool present): test_backup_restore.py + test_backup_core.py 114 passed (including test_roundtrip with real rrdtool); tests/test_backup_script.py 25 passed.
- On the Windows host the shell-script fake rrdtool tests in test_backup_core.py and test_backup_script.py fail as before (pre-existing, not caused by this plan); they pass under WSL.

## Deviations from Plan
- Tasks 1 and 2 were implemented and committed together in one commit (the helpers and orchestration were written in one pass).
- Test module additions were made via file append; no behavior changes to the plan's contract.

## Known Stubs
None.

## Self-Check: PASSED
