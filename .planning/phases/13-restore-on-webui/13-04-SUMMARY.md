---
phase: 13-restore-on-webui
plan: 04
subsystem: backup
tags: [backup, restore, plugin, threading]
requires: [13-02, 13-03]
provides:
  - backupplugin.preview_backup, start_restore, run_restore, ack_restore_result, restore block in status_dict
affects: [13-05]
key-files:
  modified:
    - src/Pellmonsrv/plugins/backup/__init__.py
    - tests/Pellmonsrv/plugins/test_backup_plugin.py
  created:
    - tests/Pellmonsrv/plugins/test_backup_restore_plugin.py
decisions:
  - start_restore validates the name against the folder listing (bounded by preview_timeout) before spawning the worker
  - ack_restore_result returns a failed in-memory restore state to idle
  - after a successful swap `restoring` stays True until the restart so no backup or second restore runs on stale state
metrics:
  tasks: 2
  completed: 2026-11-06
---

# Phase 13 Plan 04: Backup plugin restore glue Summary

The Backup plugin now runs a restore in its own daemon worker thread (single-flight, exclusive with backups), reports progress states 1..5, swaps under the daemon's `restore_lock` plus the settings store lock, sets `conf.restore_done`, and in Docker sends itself SIGTERM after a successful swap. Results persist in `.restore-result.json` until acknowledged; leftovers are cleaned at activation; the status lists every archive.

## Commits
- a43a940: restore worker, preview, exclusion, watchdog, self-restart (Task 1)
- 0f54fa1: result persistence/ack, startup cleanup, restore status block, uncapped archive list

## Plan-checker findings folded in
1. `ack_restore_result()` resets the in-memory restore state to idle when it is `failed` (test_restore_ack_resets_failed_state, test_restore_ack_keeps_non_failed_state).
2. `start_restore` checks the name via `core.validate_archive_name` against the listing before spawning a worker, so an unknown but well-formed name returns `REASON_ARCHIVE_NOT_FOUND` at once (test_restore_unknown_name_checked_against_listing, test_restore_invalid_name).

## Verification
WSL (venv-wsl): tests/Pellmonsrv/plugins, test_backup_dbus.py, test_backup_restore.py: 458 passed, 1 skipped.

## Deviations from Plan
- `_save_restore_result` was implemented in Task 1 (rather than Task 2) because the Task 1 success/failure tests read the result file.
- The test for test_status_lists_archives... was renamed to test_status_lists_all_archives_newest_first as planned.
- The name pre-check in start_restore runs through call_with_timeout so a hung NAS cannot block the D-Bus thread (REASON_TIMEOUT).

## Known Stubs
None.

## Self-Check: PASSED
