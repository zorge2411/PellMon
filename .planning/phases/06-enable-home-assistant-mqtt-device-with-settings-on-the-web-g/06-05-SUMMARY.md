---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 05
subsystem: mqtt-bridge
tags: [mqtt, paho, home-assistant, threading]
requires: [06-01, 06-02]
provides:
  - Bridge (queue-driven MQTT worker), default_paho_factory, paho_available
  - tester module (REASONS, map_reason, ConnectionTester, CONNECT_TIMEOUT, TEST_TOTAL_SECONDS)
affects: [06-07 plugin wiring, 06-06 web controller]
key-files:
  created:
    - src/Pellmonsrv/plugins/homeassistant/bridge.py
    - src/Pellmonsrv/plugins/homeassistant/tester.py
    - tests/Pellmonsrv/plugins/test_homeassistant_bridge.py
    - tests/Pellmonsrv/plugins/test_homeassistant_tester.py
    - tests/Pellmonsrv/plugins/test_homeassistant_paho_factory.py
decisions:
  - "Disabling the feature only publishes retained offline; stale-config cleanup runs only when the new settings stay enabled (avoids deleting HA entities on a mere disable)"
  - "State values on change events use the changed-item value; full/refresh publishes use the snapshot"
  - "Number payloads must match [+-]digits(.0+)? so 1e2, nan, inf are rejected before any float()"
metrics:
  tasks: 3
  tests_added: 145
completed: 2026-09-25
---

# Phase 6 Plan 05: MQTT bridge Summary

Single-worker MQTT bridge with retained QoS1 discovery/availability, QoS0 states, gated and rate-limited Home Assistant commands with snap-back readback, live reconfigure and an isolated 8 s connection test, all driven by injectable factory and clocks.

## Commits
- 667f9cf: lifecycle, availability, discovery, state publishing; tester.py; paho factory guard
- c37e92a: commands (gate, validation, rate limits, readback, logging)
- 13adb1b: reconfigure cleanup, tester and delegation tests

## Test results
- tests/Pellmonsrv/plugins: 192 passed.
- Full suite: 611 passed, 82 skipped, 3 failed (known baseline: test_backup_script conf_d override, test_plugin_loader consumption and silolevel).
- No socket opened (--disable-socket on).

## Deviations from Plan
1. [Rule 3 - Blocking] The worktree base did not contain wave 1; fast-forwarded the worktree branch to feat/phase-6-homeassistant-mqtt (no conflicts, ancestor check passed) before starting.
2. ConnectionTester was written in Task 1 (bridge.py imports it at module level, so the module would not import without it); its tests are in the Task 3 commit as planned.
3. paho's own tls_set() calls tls_insecure_set(False) internally, so the factory test asserts no tls_insecure_set(True) call rather than no call.

## Known Stubs
None.

## Threat Flags
None beyond the plan threat model. Password never enters logs or status_dict (sentinel tests).

## Self-Check: PASSED
