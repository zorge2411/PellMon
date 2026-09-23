---
phase: 08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi
plan: 04
status: complete
requirements: [D-04, D-05]
key-files:
  modified:
    - tests/test_backup_script.py
    - src/conf.d/webinterface.conf.in
    - DEPLOY-PI.md
---

# Phase 8 Plan 04: Backup proof, docs, phase gate Summary

Status: all 4 tasks complete. Task 4's live Docker verification passed on real hardware, including two real bugs found and fixed along the way (see below).

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

## Task 4 (live Docker verification) — complete, all steps approved

Steps 1-4 approved on the real Pi deployment (2026-09-23).

**Step 5 failed on first attempt, then failed again after an apparent fix, then passed on the
real fix** — two real bugs were found and shipped as separate hotfix releases during this
verification, outside this plan's original scope but directly blocking it from passing:

1. **`v2.0.1`** (unrelated, found earlier in Phase 9 verification): published Docker image was
   missing the `linux/arm/v7` platform, so the operator's Pi (32-bit ARM) couldn't even pull the
   image this plan needed to test against.
2. **`v2.0.2`** (`fix/systemimage-stale-rand`, PR #18): the main page's system-image `<object>`
   embed used a `rand` cache-buster fixed once per web-process lifetime instead of per request,
   so a browser never re-fetched it after a Settings save. Real fix, but not sufficient on its
   own -- operator still saw the old image after this shipped.
3. **`v2.0.3`** (`fix/systemimage-unbound-get-setting`, PR #19): the actual root cause.
   `pellmonweb.py`'s `systemimage()` handler passed `dbus.get_setting` to `effective_image()`
   **unbound** (missing the required `key` argument); `effective_image()`'s own bare
   `except Exception: return config_path` silently swallowed the resulting `TypeError` on every
   single request and always served the config-file default image. The Settings-saved choice
   was never read at all -- this was present since Plan 08-03 shipped the feature, not a
   regression from `v2.0.2`. Confirmed against the real `effective_image()` function that the
   old call site always returns the default regardless of the stored setting.

Operator confirmed on `v2.0.3`: **"finally fixed! image changes now tried them all!"** -- all
six gallery images switch and persist visibly on the main page. Step 5 now passes for real.

Steps 6-8 approved by the operator (2026-09-23): persistence across `docker compose down -v`,
the daemon-down graceful message on save with `pellmonsrv` stopped, and the `/settings/` auth
redirect when logged out. Step 9 (no-JS) not separately confirmed but not required for sign-off
per the plan's acceptance criteria ("step 9 optional").

**All 9 how-to-verify steps (1-8 required, 9 optional-and-skipped) are approved.** Phase 8's
Task 4 blocking checkpoint is resolved.
