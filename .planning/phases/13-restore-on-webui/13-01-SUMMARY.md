---
phase: 13-restore-on-webui
plan: 01
subsystem: backup
tags: [backup, restore, tarfile, sqlite]
requires: []
provides:
  - restore reasons, validate_archive_name, open_archive/close_archive, check_archive, preview_archive, safe_extract, verify_sqlite, check_restore_space, clean_restore_leftovers, prepare_staging in backup_core
affects: [13-02, 13-04, 13-05]
key-files:
  modified: [src/Pellmonsrv/backup_core.py]
  created: [tests/Pellmonsrv/test_backup_restore.py]
decisions:
  - open_archive keeps the raw fd file object in tar.pellmon_raw; callers use close_archive(tar)
metrics:
  completed: 2026-11-06
---

# Phase 13 Plan 01: Restore engine archive checks Summary

Daemon-side port of the host tool's hardened extractor plus archive validation, manifest preview, SQLite verification, 0700 staging and free-space pre-check, all in stdlib-only `backup_core.py`.

## Tasks
1. Reasons, name allow-list, check/preview, safe_extract, verify_sqlite - commit 652e7f1
2. Staging, leftovers cleanup, space check - commit 652e7f1 (implemented together with task 1; one commit)

## Verification
`tests/Pellmonsrv/test_backup_restore.py`: 37 passed, 4 skipped (POSIX-mode tests on Windows). Parity test covers 7 malicious archive kinds against both the tool and core extractor. `tools/pellmon_backup.py` unchanged.

## Deviations from Plan
- Both tasks went into a single commit because the staging code sat in the same file edit as task 1.
- Test ids for the oversized-manifest case are explicit (`ids=`) because a 64 KiB parametrize id overflowed the Windows environment-variable limit.

## Known pre-existing failures (out of scope)
On this Windows dev host, `tests/Pellmonsrv/test_backup_core.py` (shell-script fake rrdtool) and `tests/test_backup_script.py::test_conf_d_overrides_pellmon_conf` (path separators) fail; they are Linux-only assumptions unrelated to this plan.

## Self-Check: PASSED
