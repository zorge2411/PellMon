---
phase: 08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi
plan: 02
subsystem: web-settings
tags: [cherrypy, csrf, whitelist, settings]
requires: [08-01]
provides: [check_same_origin, SYSTEM_IMAGES, IMAGE_NAMES, available_images, effective_image, Settings, SETTING_KEY]
key-files:
  created: [src/Pellmonweb/security.py, src/Pellmonweb/settings.py, tests/Pellmonweb/test_settings_image.py]
  modified: [src/Pellmonweb/pellmonconf.py, src/Pellmonweb/__init__.py]
decisions:
  - "Settings.save returns rendered HTML (not JSON) so the form works with JavaScript disabled (UI-SPEC)."
  - "Daemon-down or falsy set_setting never falls back to a local file write (RESEARCH Open Question 2)."
metrics:
  completed: 2026-09-21
---

# Phase 8 Plan 02: Web-side system image logic Summary

Dbus-free web module: shared same-origin helper, six-file whitelist, effective-image resolver with one-warning config fallback, and an auth- and CSRF-gated Settings controller.

## Commits
- 19d0ab2: extract check_same_origin into security.py (pellmonconf aliases it)
- 838cdf4: settings.py whitelist, resolver, Settings controller
- c35654c: controller tests

## Results
- tests/Pellmonweb/test_settings_image.py: 28 passed; existing CSRF tests untouched and passing.
- Full suite (WSL): 376 passed, 14 skipped (baseline 348 / 14).

## Deviations from Plan
- Save returns rendered HTML rather than pellmonconf-style JSON (deliberate, per plan).
- Tasks 1-2 test/source grouping: settings.py was written with the controller included, so the Task 2 commit contains the controller code; Task 3 commit adds its tests only.
- CRLF preserved in pellmonconf.py and __init__.py; new files are LF in working copy (git autocrlf warns).

## Self-Check: PASSED
