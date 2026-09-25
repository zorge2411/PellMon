---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 09
subsystem: docs-validation
tags: [docs, home-assistant, mqtt, validation]
requires: ["06-07", "06-08"]
provides:
  - Home Assistant / MQTT deployment and bring-up documentation with a doc guard test
  - Final automated gate recorded in 06-VALIDATION.md
affects: [DEPLOY-PI.md, HARDWARE-BRINGUP.md]
key-files:
  created: [tests/test_homeassistant_docs.py, 06-HUMAN-UAT.md]
  modified: [DEPLOY-PI.md, HARDWARE-BRINGUP.md, 06-VALIDATION.md]
requirements-completed: []
duration: n/a
completed: 2026-09-25
---

# Phase 6 Plan 09: Docs, final gate and UAT hand-over Summary

Tasks 1 and 2 done; Task 3 (blocking-human real-system UAT) deliberately not executed.

**UAT: pending** - open steps are listed in `06-HUMAN-UAT.md`. The phase is not complete until the user approves.

## Precondition

Browser suite (WSL, `PELLMON_BROWSER_TESTS=1 ... tests/browser`) run by the orchestrator after commit c91c2bf: 61 passed.

## Tasks

1. Docs (commit 735435e): DEPLOY-PI.md "Home Assistant / MQTT" section (p15 = HomeAssistant, IP address / extra_hosts, old publisher off, takeover values, Burner ON/OFF removal, command-gated entities, availability, password in settings DB and backups, dedicated broker user with ACL) plus a backup-archive note; HARDWARE-BRINGUP.md supervised checklist and Not-verified entries; `tests/test_homeassistant_docs.py` (5 tests, RED confirmed before edit, includes no-32-hex-identifier guard).
2. Final gate: full suite 689 passed, 112 skipped, 3 failed = exactly the known baseline (test_backup_script::test_conf_d_overrides_pellmon_conf, test_plugin_loader[consumption], [silolevel]). No `enable_socket` in tests/, `--disable-socket` still in pytest.ini. 06-VALIDATION.md updated (executed, wave_0_complete, statuses). Committed separately.

## Home Assistant history on D-18 removal

Unknown until UAT step 4.

## Deviations from Plan

None. Note: in this worktree the untracked mqtt-*.json, DOCKER.md and config/conf.d/ are not present; none were staged. STATE.md and ROADMAP.md untouched by instruction.

## Self-Check: PASSED
