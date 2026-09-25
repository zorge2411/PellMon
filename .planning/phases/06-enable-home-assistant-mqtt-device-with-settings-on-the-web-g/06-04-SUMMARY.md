---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 04
subsystem: web-ui
tags: [mako, css, mqtt, home-assistant, bootstrap3]
requires: []
provides:
  - homeassistant.html page (template context contract in 06-04-PLAN interfaces)
  - Home Assistant navbar entry
  - Phase 6 .mqtt-* CSS block
affects: [06-06 controller, 06-08 JS]
tech-stack:
  added: []
  patterns: [Mako render tests without controller]
key-files:
  created:
    - src/Pellmonweb/html/homeassistant.html
    - tests/Pellmonweb/test_homeassistant_ui.py
  modified:
    - src/Pellmonweb/html/layout.html
    - src/Pellmonweb/media/css/pellmon.css
decisions:
  - "Phase 6 CSS inserted immediately before the Phase 10 header so Phase 10 CSS tests keep working"
metrics:
  tasks: 2
  files: 4
completed: 2026-09-25
---

# Phase 6 Plan 04: Home Assistant / MQTT page Summary

Server-rendered "Home Assistant / MQTT" page (five panels, one form, status line, Save/Test buttons), navbar entry and Phase 6 CSS block per 06-UI-SPEC, verified by Mako-render structural tests.

## Commits
- 18962dc: template, layout navbar entry, structural tests
- 147b914: Phase 6 CSS block

## Deviations from Plan
None functionally. Note: the CSS acceptance tests live in the same test file that Task 1 created, so at commit 18962dc the three CSS tests fail until commit 147b914 lands (both commits are consecutive).

Deliberate UI-SPEC extension (planner-added, D-19/C2): the Device panel has two extra optional fields, Discovery node ID (`node_id`) and Unique ID prefix (`uid_prefix`), for taking over an existing device. The hidden `tls_verify_field` marker is disabled together with the Verify checkbox.

## Test results
- tests/Pellmonweb/test_homeassistant_ui.py, test_settings_page.py, test_mobile_forms.py, test_mobile_css.py: all pass.
- Full suite: 434 passed, 82 skipped, 3 failed (the known baseline failures: test_backup_script conf_d override, test_plugin_loader consumption and silolevel).
- Browser layout checks (UI-SPEC H-*) not run here; left to the orchestrator/06-08.

## Known Stubs
None. The template reads only the documented context keys; `homeassistant.js` (referenced via `scripts`) is delivered by another plan (06-08), so the page 404s that script until then.

## Threat Flags
None beyond the plan's threat model (T-06-12 to T-06-14b mitigated: no password value/key read, all dynamic values escaped, commands off by default, marker disabled with checkbox).

## Self-Check: PASSED
Files and commits 18962dc, 147b914 exist.
