---
phase: 08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi
plan: 04
status: awaiting-human-verification
requirements: [D-04, D-05]
key-files:
  modified:
    - tests/test_backup_script.py
    - src/conf.d/webinterface.conf.in
    - DEPLOY-PI.md
---

# Phase 8 Plan 04: Backup proof, docs, phase gate Summary

Status: tasks 1-3 complete; Task 4 (live Docker verification) is awaiting human verification and has not been run.

## Completed tasks

1. Added `test_system_image_setting_round_trip` to `tests/test_backup_script.py`. A `web.system_image` row survives backup, deletion and restore, and a never-stored key still returns the default. `tools/pellmon_backup.py` is unchanged, which confirms the RESEARCH prediction that no tool change is needed.
2. `webinterface.conf.in` now says `system_image` is the fallback and that the Settings page overrides it. The absolute-path option stays config-only. The default value is unchanged. `DEPLOY-PI.md` documents in both the data and backup sections that the choice lives in `pellmon_settings.db` and is included in backups.
3. Full-suite gate:
   - venv-wsl: 389 passed, 15 skipped (baseline was 388 passed, so +1 is the new test).
   - system python3 with venv-wsl site-packages: 401 passed, 3 skipped.
   - Skips in the venv-wsl run are platform guards only: dbus/gi not importable in the venv (test_export_bytes, test_connection_banner, test_settings_page, test_config_interpolation, test_log_level, test_plugin_imports) and the RPi guards (test_plugin_imports, test_plugin_loader). Those dbus/gi modules run under system python3.
   - The 3 skips under system python3 are all RPi guards.
   - No ad-hoc-print or sys.path-shim gate failures.

## Deviations from Plan

None.

## Awaiting: Task 4 (blocking human-verify)

Steps 1-9 in 08-04-PLAN.md must be run on a live Docker stack. Record any deviation verbatim, with its step number, here once the operator responds.
