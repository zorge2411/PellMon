# Phase 6: Enable Home Assistant MQTT device with settings on the web GUI - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-20
**Phase:** 6-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
**Areas discussed:** Matching the existing HA device, Commands from Home Assistant, The web GUI settings page, When the burner is offline

---

## Matching the existing HA device

| Question | Options | Selected |
|----------|---------|----------|
| Topic layout | Same layout, configurable prefix / Exactly scotte/... fixed / New PellMon layout | Same layout, configurable prefix |
| Entities | The same 23 as today / Same 23 plus extras / Sensors only | The same 23 as today |
| Relation to existing device | Take over the same device / New separate PellMon device / You decide | Take over the same device |
| Discovery | MQTT discovery, automatic / Discovery with an on/off switch | MQTT discovery, automatic |

**Notes:** Reference was the existing Home Assistant MQTT diagnostics export (23 entities: 9 sensors, 10 numbers, 4 buttons; `scotte/...` topics). Device identifiers must be a setting, not hard-coded.

---

## Commands from Home Assistant

| Question | Options | Selected |
|----------|---------|----------|
| Writes and default | Off by default with GUI switch / On when MQTT enabled / Read-only | Off by default, GUI switch |
| Buttons | Reset alarm and reset ignition only / All four as today / None | Reset alarm and reset ignition only |
| Failed commands | Re-read and republish real value / Also raise a visible error in HA / Log only | Re-read and republish the real value |

**Notes:** Burner ON/OFF are deliberately not exposed to Home Assistant (differs from the existing device).

---

## The web GUI settings page

| Question | Options | Selected |
|----------|---------|----------|
| Placement | New 'Home Assistant / MQTT' page / Section in existing config editor | New page |
| Password | Settings database, masked / Environment variable or Docker secret only / Either | Settings database, masked in the GUI |
| Fields | Basic + TLS toggle / Basic only / Advanced (client certs, custom CA) | Basic + TLS toggle |
| Apply | Save and reconnect live, with status and Test button / Save and restart the daemon | Save and reconnect live |

**Notes:** Password must be stored readable to connect; the volume must be protected (documented).

---

## When the burner is offline

| Question | Options | Selected |
|----------|---------|----------|
| Burner disconnected | Entities become unavailable / Keep last values plus connection sensor / Unavailable plus a connection sensor | Entities become unavailable |
| PellMon or broker lost | Last-will marks everything offline / No last-will | Last-will marks everything offline |
| Publishing cadence | On change plus periodic refresh / Fixed interval only / On change only | On change plus periodic refresh (default 60 s) |
| Retain | Discovery retained, states not / Retain everything | Discovery retained, states not |

---

## Claude's Discretion

- MQTT library and pinned version; where the client runs (likely a daemon-side plugin); threading and reconnect strategy; demo-mode publishing; extra safety limits and rate limiting; test strategy.

## Deferred Ideas

- Client-certificate/custom CA TLS options; Burner ON/OFF from Home Assistant behind extra confirmation; last-command-error and connection-status entities; extra PellMon items; multiple/NBE burners; password via environment variable or Docker secret.
