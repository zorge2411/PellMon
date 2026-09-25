---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 03
subsystem: daemon
tags: [mqtt, dbus, home-assistant]
requires: []
provides:
  - Database.add_change_listener / _notify / snapshot
  - five MQTT JSON D-Bus methods and _ha_plugin()
affects: [06-07, web settings page]
key-files:
  modified: [src/Pellmonsrv/pellmonsrv.py]
  created: [tests/Pellmonsrv/test_homeassistant_dbus.py, tests/Pellmonsrv/test_database_change_listener.py]
key-decisions:
  - "Password never leaves the daemon: output stripped, ALLOWED_SETTINGS untouched, logs carry method and exception type only"
requirements-completed: [D-12, D-13, D-16, D-19]
duration: short
completed: 2026-09-25
---

# Phase 6 Plan 03: Daemon listener hook and MQTT D-Bus API Summary

Change-listener hook on the pellmonsrv Database thread plus five JSON D-Bus methods (settings get/set, status, start-and-poll connection test) with a write-only MQTT password.

## Commits
- 6af4afb: Database change-listener hook and snapshot
- ab549fe: five MQTT D-Bus methods

## Tests
- Targeted: 31 passed (new dbus and listener tests, settings store).
- Full suite: 3 failed (known baseline: test_conf_d_overrides_pellmon_conf, test_every_available_plugin_loads[consumption], [silolevel]), 424 passed, 82 skipped.

## Deviations from Plan
None. Listener init written as `self.listeners = []` (with spaces) so the plan's source-order check matches literally.

## Known Stubs
None. The methods depend on the plugin-object contract implemented by 06-07; until then they return `available: false`.

## Self-Check: PASSED
