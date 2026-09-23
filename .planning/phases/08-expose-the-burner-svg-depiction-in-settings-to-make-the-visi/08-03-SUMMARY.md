---
phase: 08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi
plan: 03
subsystem: web-settings
tags: [cherrypy, mako, settings, dbus]
requires: [08-01, 08-02]
provides: [settings-route, settings-page, per-request-systemimage]
key-files:
  created: [src/Pellmonweb/html/settings.html, tests/Pellmonweb/test_settings_page.py]
  modified: [src/Pellmonweb/pellmonweb.py, src/Pellmonweb/html/layout.html, src/Pellmonweb/media/css/pellmon.css]
decisions:
  - "systemimage resolves via effective_image per request with no-cache headers (D-04, RESEARCH A1)."
  - "Verified fact: no cherrypy caching tool is enabled in app_conf (only the module import exists); asserted by test_caching_tool_not_enabled_for_systemimage."
metrics:
  completed: 2026-09-21
---

# Phase 8 Plan 03: Settings page wiring Summary

Mounted /settings/, added Dbus_handler.get_setting/set_setting, made systemimage resolve the image per request with Cache-Control/Pragma no-cache, and built the JS-free radio-tile settings page with a navbar entry and .sysimg styles.

## Commits
- d7110b8: pellmonweb.py wiring (proxies, system_image_dir global, self.settings, systemimage)
- c3bcab8: settings.html, layout.html navbar entry, pellmon.css gallery styles
- bfbf3db: tests/Pellmonweb/test_settings_page.py (13 tests)

## Results
- Full suite (WSL venv): 388 passed, 15 skipped (baseline 376 / 14).
- test_settings_page.py with system python3 (dbus/gi): 13 passed, so the functional Dbus_handler test ran.

## Deviations from Plan
- Tasks 1 and 3 share one test file; all tests were written in a single commit (bfbf3db) after implementation rather than as separate RED/GREEN commits.
- The XSS test asserts the absence of the payload `<script>alert(1)</script>` rather than any `<script>`, because layout.html legitimately contains script tags.
- pellmonweb.py and pellmon.css were edited preserving CRLF; other new files are LF.

## Known Stubs
None.

## Self-Check: PASSED
