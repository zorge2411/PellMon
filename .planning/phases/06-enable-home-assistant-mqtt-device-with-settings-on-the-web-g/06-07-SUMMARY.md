---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 07
subsystem: daemon-plugin
tags: [mqtt, home-assistant, yapsy, autotools]
requires: ["06-03", "06-05"]
provides:
  - homeassistant(protocols) plugin with the five-method D-Bus contract
  - HomeAssistant yapsy descriptor, autotools entries, p15 enabled by default
affects: [06-09]
key-files:
  created:
    - src/Pellmonsrv/plugins/homeassistant/__init__.py
    - src/Pellmonsrv/plugins/homeassistant/Makefile.am
    - src/Pellmonsrv/plugins/homeassistant.pellmon-plugin
    - tests/Pellmonsrv/plugins/test_homeassistant_plugin.py
  modified:
    - src/Pellmonsrv/plugins/Makefile.am
    - configure.ac
    - src/conf.d/enabled_plugins.conf
decisions:
  - "apply_settings/start_test validate with current = stored settings, so tls_verify is kept unless TLS is on and the marker is sent"
  - "With paho missing or the bridge unbuildable, valid settings are still stored and the result carries available:false"
requirements-completed: [D-03, D-06, D-12, D-13, D-15, D-16]
completed: 2026-09-25
---

# Phase 6 Plan 07: HomeAssistant plugin Summary

The HomeAssistant plugin is a protocols subclass that builds a Bridge, registers it as a Database change listener, publishes offline via atexit, stays inert until enabled, and applies saved settings live (password write-only, never logged).

## Commits
- 7e1c37c: plugin class and 13 plugin tests
- 815c1ce: descriptor, plugin Makefile.am, plugins/Makefile.am, configure.ac, enabled_plugins.conf (p15)

## Deviations from Plan
**1. [Rule 3 - Blocking] Stale worktree base.** Fast-forwarded to feat/phase-6-homeassistant-mqtt before starting.

**2. Test detail.** `Keyval_storage.keyval_storage` is only set at runtime by `init_keyval_storage` (the class is shadowed in database.py), so tests monkeypatch it with `raising=False`.

## Test results
- test_homeassistant_plugin.py: 13 passed.
- Full suite: 681 passed, 83 skipped, 3 failed = the known baseline failures (test_backup_script conf_d override, test_plugin_loader consumption and silolevel). The new descriptor passes the import and loader tests.
- `config/conf.d` (untracked user copy) and `mqtt-*.json` untouched.

## Known Stubs
None.

## Threat Flags
None beyond the plan's threat model (T-06-30..T-06-32 mitigated as tested).

## Self-Check: PASSED
Commits 7e1c37c and 815c1ce exist; listed files present.
