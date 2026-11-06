---
phase: 13-restore-on-webui
plan: 03
subsystem: daemon-core
tags: [restore, locking, dbus]
requires: []
provides: [restore_lock, conf.restore_done guard, PreviewBackup/StartRestore/AckRestoreResult D-Bus methods]
affects: [src/Pellmonsrv/pellmonsrv.py]
key-files:
  modified:
    - src/Pellmonsrv/pellmonsrv.py
    - tests/Pellmonsrv/test_db_copy.py
    - tests/Pellmonsrv/test_backup_dbus.py
decisions:
  - copy_db now returns True/False; SIGTERM handlers log "synced" only on True
metrics:
  tasks: 2
  completed: 2026-11-06
---

# Phase 13 Plan 03: Daemon restore safety Summary

Module-level `restore_lock` serialises the Poller's rrdtool update and copy_db's file copy against a restore swap. `conf.restore_done` makes `copy_db('store')` a no-op for the db_copy_thread and all three SIGTERM handlers. Three leak-free D-Bus methods delegate to the Backup plugin.

## Commits
- 6947a4f: restore_lock and restore_done guard (Task 1)
- b6f0f6e: PreviewBackup, StartRestore, AckRestoreResult D-Bus methods (Task 2)

## Deviations from Plan
None - plan executed as written.

## Deferred Issues
- tests/Pellmonsrv/test_db_copy.py::test_nbe_controller_* fail in this dev environment (module `xtea` not installed). Pre-existing and unrelated; the other 10 tests pass.

## Self-Check: PASSED
