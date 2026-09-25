---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 08
subsystem: web-ui
tags: [javascript, progressive-enhancement, playwright, mobile]
requires: [06-04, 06-06]
provides:
  - homeassistant.js progressive enhancement for /homeassistant/
  - rendered UI-SPEC browser checks for /homeassistant/
affects: [06-09]
tech-stack:
  added: []
  patterns: [text-only DOM writes, held Playwright routes for busy-state assertions]
key-files:
  created:
    - src/Pellmonweb/media/js/homeassistant.js
    - tests/Pellmonweb/test_homeassistant_js.py
    - tests/browser/test_homeassistant_browser.py
  modified:
    - tests/browser/fake_dbus.py
    - tests/browser/test_mobile_overflow.py
    - tests/browser/test_browser_harness.py
key-decisions:
  - "Script focuses the validation summary (.alert[role=alert][tabindex=-1]) on load, since the template has no inline focus code but UI-SPEC and H-B9 require it"
  - "Status poll uses a cache-busting query and only rebuilds #mqtt-status when text, class or title differ from the DOM"
requirements-completed: [D-06, D-10, D-11, D-13]
duration: ~25 min
completed: 2026-09-25
---

# Phase 6 Plan 08: Home Assistant page script and rendered browser checks Summary

Text-only progressive enhancement for the Home Assistant page (5 s status poll, TLS/verify/marker/port sync, warnings, prefix mirror, Saving.../Testing... states, fetch-based Test with a 12 s abort) plus the UI-SPEC rendered checks in the browser suite.

## Tasks

| Task | Commit | Result |
|------|--------|--------|
| 1. homeassistant.js + source-scan test | f0dd549 | 4 passed (js scan + existing WR-07 scan) |
| 2. FakeDbus mqtt_* methods, PAGES entries, browser tests | 45a3c32 | Collected, all skipped on Windows (61 skipped) |

## Verification

- `tests/Pellmonweb/test_homeassistant_js.py` and `test_source_js_no_html_sink.py`: 4 passed.
- `pytest tests/browser -q -rs`: 61 skipped with the harness reason, no errors.
- Full suite `pytest tests -q`: 668 passed, 112 skipped, 3 failed. The 3 failures are the known baseline ones (test_backup_script conf.d override, test_plugin_loader consumption and silolevel).
- Acceptance greps: `enable_socket` count 0 in the new browser module; 5 `def mqtt_*` in fake_dbus.py; `/homeassistant/` present once in each PAGES list.

## Browser run pending (orchestrator action)

The executor cannot run wsl.exe. The orchestrator must run, immediately after wave 3 (06-07 and 06-08) and BEFORE 06-09 starts:

`PELLMON_BROWSER_TESTS=1 PYTHONPATH=src pytest tests/browser -v -rs --allow-unix-socket` in WSL

Failures go back to 06-08 (or the owning plan) before 06-09. The rendered tests were written against the templates and CSS by reading, never executed; expect possible selector or layout tuning (notably H-B4 menu link bounds, H-E3 navbar row, H-B9 focus, and same-origin acceptance of the Save POST in the stub).

## Deviations from Plan

**1. [Rule 2 - Missing critical functionality] Validation summary focus on load**
- **Found during:** Task 2 (H-B9)
- **Issue:** UI-SPEC says the validation alert is focused on load; homeassistant.html contains no focus code.
- **Fix:** homeassistant.js focuses `.mqtt-page > .alert[role="alert"][tabindex="-1"]` at start.
- **Files modified:** src/Pellmonweb/media/js/homeassistant.js
- **Commit:** 45a3c32

Otherwise the plan was executed as written.

## Known Stubs

None. The fake D-Bus values are test fixtures; no real identifier from the untracked export was used.

## Threat Flags

None. T-06-34/35/36 mitigations hold: no HTML sinks (scan-tested), the password field is never looked up (only submitted inside FormData of the whole form on Test), and the fetch is same-origin with the server check remaining authoritative.

## Self-Check: PASSED

Files exist, commits f0dd549 and 45a3c32 present, mqtt-*.json never staged, STATE.md and ROADMAP.md untouched.
