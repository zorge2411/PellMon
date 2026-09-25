---
phase: 06
plan: 09
status: partial
---

# Phase 06 - Human UAT (real broker, Home Assistant, burner)

Not approved until the user replies. Do not push or open a PR before sign-off; merging publishes a release.

| # | Step | Requirement | Status |
|---|------|-------------|--------|
| 1 | Browser suite result from orchestrator is green: 61 passed in WSL after c91c2bf (accept) | UI | done (precondition, recorded) |
| 2 | On phone and desktop open /homeassistant/ from the menu: readable, no sideways scroll, password never shown, Test connection and Save messages clear | UI, D-12 | pending |
| 3 | Switch off the old publisher; enter broker, device identifier, device name, node id, unique-id prefix; save. Same device shows current values, history continues | D-01, D-02, D-03 | passed 2026-09-25 (v2.3.3): needed Discovery node ID `scotte_burner` and Unique ID prefix `scotte` from the old discovery payloads; with them empty HA created duplicate `pille_fyr_*` entities. After setting them, the 21 original entities update again and the duplicates were removed. Old silo_level/daily_consumption/total_consumption stay unavailable (not published by PellMon) |
| 4 | Burner ON/OFF gone or unavailable. Commands off: numbers and resets removed; `mosquitto_pub -t scotte_burner/boiler_temp_set/set -m 60` (use your topic prefix) does not change the burner and the log shows "commands are disabled". Commands on: they return. Note whether history survived the removal (A4) | D-06, D-07, D-18 | pending |
| 5 | Commands on: change one setpoint from Home Assistant while watching the burner display; burner changes and HA shows the read-back. Out-of-range value snaps back and the log has a rejected line | D-08, D-09 | pending |
| 6 | Unplug the burner serial link: entities unavailable, return on reconnect. Stop pellmonsrv container: device offline; kill hard: last will marks it offline | D-14, D-15 | pending |
| 7 | Restart Home Assistant: values reappear within seconds (birth message) | D-19 | pending |

## Outcome

UAT: partial. Step 3 (device takeover) passed on the real system; steps 2 and 4-7 open.
