---
phase: 13-restore-on-webui
plan: 05
subsystem: web
tags: [cherrypy, mako, restore, backup, dbus]
requires: [13-02, 13-03]
provides:
  - Backup page restore flow (links, confirm page, guarded POST, status JSON, polling script, one-time result banner)
affects: [src/Pellmonweb/backup.py, src/Pellmonweb/pellmonweb.py]
key-files:
  created:
    - src/Pellmonweb/html/backup_restore.html
    - src/Pellmonweb/media/js/backup.js
    - tests/Pellmonweb/test_backup_js.py
  modified:
    - src/Pellmonweb/backup.py
    - src/Pellmonweb/pellmonweb.py
    - src/Pellmonweb/html/backup.html
    - tests/Pellmonweb/test_backup_page.py
requirements-completed: [D-02, D-03, D-13, D-14, D-15, D-16]
duration: ~25 min
completed: 2026-11-06
---

# Phase 13 Plan 05: Web restore flow Summary

Authenticated, same-origin, typed-RESTORE restore flow on the Backup page, with fixed-text JSON progress polled by a textContent-only script across the daemon restart.

## Tasks
1. D-Bus client methods (backup_preview, backup_restore, backup_restore_ack) and routes restore, restore_run, restore_status, restore_view, one-time banner ack, run() mapping REASON_RESTORE_BUSY. Commit 34b4c7e.
2. Restore links per archive row, progress panel, confirm page backup_restore.html, backup.js, template and JS tests. Commit a18ce04.

## Verification
`venv-wsl/bin/python -m pytest tests/Pellmonweb/ -q` under WSL: 353 passed, 9 skipped. (Windows Python lacks cherrypy.)

## Deviations from Plan
- The confirm page always shows the `--with-config` host command pointer (D-02), with an extra sentence when the archive contains config, instead of only when has_config.
- The ack flag is stored on `cherrypy.request` (per-request) rather than controller state, since the controller is shared across threads.
- backup.html uses CRLF line endings; edits preserved them.

## Known Stubs
None.

## Self-Check: PASSED
