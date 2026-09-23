---
phase: 08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi
plan: 01
subsystem: daemon-settings
tags: [dbus, sqlite, settings, whitelist]
requires: []
provides: [Keyval_storage.getval, ALLOWED_SETTINGS, GetSetting, SetSetting]
key-files:
  modified: [src/Pellmonsrv/database.py, src/Pellmonsrv/pellmonsrv.py]
  created: [tests/Pellmonsrv/test_settings_store.py]
decisions:
  - "Namespaced whitelist dict ALLOWED_SETTINGS (key -> validator); web.system_image validated by anchored ^system[a-z0-9_]*\.svg$"
metrics:
  completed: 2026-09-21
---

# Phase 8 Plan 01: Daemon settings API Summary

Validated persistent GetSetting/SetSetting over D-Bus backed by pellmon_settings.db, with an exception-free Keyval_storage.getval.

## Commits
- a8f79ea: Keyval_storage.getval
- 62f5f82: ALLOWED_SETTINGS, GetSetting/SetSetting, tests

## Results
- RESEARCH A2 settled: first-insert writeval succeeds and confvalue is non-NULL (real sqlite test).
- Baseline gate (Pellmonsrv + print + sys.path gates, WSL Debian): 106 passed, 0 skipped.
- Full suite (WSL): 348 passed, 14 skipped.

## Deviations from Plan
None. Tasks 1 and 2 shared one test file, so the test file was committed with Task 2. Task 3 required no fixes.

## Self-Check: PASSED
