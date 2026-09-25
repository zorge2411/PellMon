---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 02
subsystem: homeassistant-plugin
tags: [mqtt, home-assistant, settings, validation]
requires: []
provides:
  - entities.py (ENTITIES, CLEANUP_BUTTONS, topic helpers, discovery_messages)
  - settings.py (DEFAULTS, validate, validate_password, effective, load, save, public_view)
key-files:
  created:
    - src/Pellmonsrv/plugins/homeassistant/entities.py
    - src/Pellmonsrv/plugins/homeassistant/settings.py
    - tests/Pellmonsrv/plugins/test_homeassistant_entities.py
    - tests/Pellmonsrv/plugins/test_homeassistant_settings.py
decisions:
  - effective() defaults node_id and uid_prefix to device_id
  - D-18 policy isolated in _removed_when_commands_off() (one-line change)
metrics:
  tasks: 2
  files: 4
completed: 2026-09-25
---

# Phase 6 Plan 02: Entity table and settings model Summary

Pure, stdlib-only modules: a 21-entity Home Assistant table with discovery payload builder (D-18 removal payloads, datamap-bounded ranges) and a single authoritative settings validator with password-safe Keyval storage and a TLS-verify-downgrade-proof rule.

## Commits
- 7d5d0d4: entities.py + tests
- 0158e4e: settings.py + tests

## Tests
- `pytest tests/Pellmonsrv/plugins -k homeassistant`: 56 passed (17 entities, 39 settings)
- Full suite: 3 failed (known baseline: test_backup_script conf_d override, test_plugin_loader consumption and silolevel), 464 passed, 82 skipped

## Deviations from Plan
- TDD RED commits were not made separately: tests and implementation were written in the same task and committed together per task (tests were written first, run green after implementation).
- No `__init__.py` created in the homeassistant directory, as specified (06-07 owns it).
- datamap min/max are ints, not strings as the plan interface said; the cross-check uses `float()` so it works with either.

## Known Stubs
None.

## Self-Check: PASSED
