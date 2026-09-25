---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 01
subsystem: mqtt-dependency-and-test-seam
tags: [paho-mqtt, docker, tls, test-doubles]
requires: []
provides: [paho-mqtt pin, ca-certificates in image, FakeMqttClient/FakeClientFactory/FakeDb test fakes]
affects: [06-02, 06-03, 06-04, 06-05]
tech-stack:
  added: [paho-mqtt==2.1.0]
  patterns: [in-memory client factory seam]
key-files:
  created:
    - tests/Pellmonsrv/plugins/fake_mqtt.py
    - tests/Pellmonsrv/plugins/conftest.py
    - tests/Pellmonsrv/plugins/test_fake_mqtt.py
  modified:
    - requirements.txt
    - requirements-wsl.txt
    - Dockerfile
    - tests/test_ci_docker_config.py
key-decisions:
  - "paho-mqtt pinned ==2.1.0 in requirements.txt, >=2.1.0 in requirements-wsl.txt (VERSION2 callback API)"
requirements-completed: [D-11, D-13]
duration: short
completed: 2026-09-25
---

# Phase 6 Plan 01: paho-mqtt pin, CA store, MQTT test fakes Summary

paho-mqtt 2.1.0 pinned after human package verification, the image gains ca-certificates for TLS verification, and socket-free fakes (client, factory, burner db) are in place for later MQTT tests.

## Task 1 (checkpoint)
Human verification of paho-mqtt==2.1.0 was APPROVED by the user in chat before execution (relayed by the orchestrator; exact approval text not available to this agent).

## Commits
- Task 2: 19bf648 (pin, ca-certificates, guard tests)
- Task 3: 02cd38a (in-memory fakes and self-tests)

## Results
- New guard tests (2) pass; fake self-tests (16) pass.
- Full suite: 3 failed, 426 passed, 82 skipped. The 3 failures are the known baseline (test_backup_script::test_conf_d_overrides_pellmon_conf, test_plugin_loader[consumption], [silolevel]).
- paho-mqtt 2.1.0 installed in the main checkout's venv-py3.

## Deviations from Plan
None. Note: FakeDb.make_scotte_db follows the plan's explicit item list (9 sensors, 10 numbers, 4 commands, burner_connection = 20 items, not the "21" in the behaviour prose).

## Known Stubs
None.

## Self-Check: PASSED
