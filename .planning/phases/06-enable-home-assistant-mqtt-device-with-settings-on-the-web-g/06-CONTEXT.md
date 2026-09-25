# Phase 6: Enable Home Assistant MQTT device with settings on the web GUI - Context

**Gathered:** 2026-09-20
**Status:** Ready for planning

<domain>
## Phase Boundary

PellMon publishes the burner to Home Assistant as an MQTT device (with MQTT discovery), and the
MQTT connection settings are edited on a dedicated page in the pellmonweb GUI. Home Assistant can
read the burner's values and, when explicitly allowed, change a fixed set of burner settings.

In scope: the MQTT client and topic/discovery layout, the settings page and its storage, command
handling from Home Assistant, availability/offline behaviour, tests, docs.

Out of scope (new capabilities, other phases): NBE burner support over MQTT, multiple burners,
Home Assistant custom integration/HACS component, MQTT-based control of anything beyond the fixed
entity list, a general-purpose MQTT bridge for arbitrary plugins.

</domain>

<decisions>
## Implementation Decisions

### Matching the existing Home Assistant device
- **D-01:** Keep the existing topic layout so current Home Assistant dashboards and automations keep
  working: `<prefix>/<item>/state` for values, `<prefix>/<item>/set` for commands, and
  `<prefix>/status` as the availability topic. The prefix is configurable and defaults to `scotte`.
- **D-02:** Expose the same 23 entities as the existing "Scotte Pellet Burner" device, with the same
  names, units, device classes, state classes and min/max/step for numbers:
  - 9 sensors: Power (%), Power kW, Boiler Temperature, Chute Temperature, Smoke Temperature, Oxygen
    Level, Light (LDR), Feeder Time, Burner Mode.
  - 10 numbers (settable): Boiler Temp Setpoint (40-85), Boiler Temp Minimum (10-70), Boiler Diff
    Down (0-20), Boiler Diff Up (0-15), Chimney Draught (0-10), Cleaning Interval (1-120 min),
    Cleaning Time (0-60 s), Feeder Capacity (400-8000 g/h), Min Power (10-100), Max Power (10-100).
  - 4 buttons: Burner ON, Burner OFF, Reset Alarm, Reset Ignition (see D-06 for which are exposed).
  - Numeric ranges advertised in discovery must never be wider than what the PellMon/Scotte datamap
    allows for that item; where they differ, use the narrower range.
- **D-03:** PellMon takes over the same Home Assistant device rather than creating a second one: reuse
  the same device identifiers and per-entity unique IDs so entities, history and dashboards continue.
  The device identifier and device name must be **settings** (web GUI / settings store), never
  hard-coded in the repository. The old publisher must be switched off first; document this.
- **D-04:** Use MQTT discovery, published automatically and retained, under a configurable discovery
  prefix (default `homeassistant`).
- **D-05 (mapping, verified against the datamap):** Home Assistant entity to PellMon item:
  `power`, `power_kW`, `boiler_temp`, `chute_temp`, `smoke_temp`, `oxygen`, `light`, `feeder_time`,
  `mode`; settings `boiler_temp_set`, `boiler_temp_min`, `boiler_temp_diff_down`,
  `boiler_temp_diff_up`, `chimney_draught`, `cleaning_interval`, `cleaning_time`, `feeder_capacity`,
  `min_power`, `max_power`; commands `burner_on`, `burner_off`, `reset_alarm`, `reset_ignition`.
  Some items exist only for certain chip versions (datamap keys are version tuples, e.g.
  `boiler_temp_diff_down` from 4.00, `boiler_temp_diff_up` from 4.99): publish discovery only for
  items that exist in the connected burner's database.

### Commands from Home Assistant
- **D-06:** Commands are OFF by default. A clearly labelled "Allow commands from Home Assistant"
  switch on the settings page enables them. When off, number and button entities are not published
  as controllable (or are removed from discovery) and any message on a `/set` topic is ignored and
  logged.
- **D-07:** Only two buttons exist in Home Assistant: **Reset Alarm** and **Reset Ignition**. Burner
  ON and Burner OFF are NOT exposed to Home Assistant (they stay in PellMon's own UI). This is a
  deliberate difference from the existing device; the old ON/OFF entities will show as unavailable
  or must be removed in Home Assistant. Document it.
- **D-08:** After every command from Home Assistant, PellMon reads the value back from the burner and
  republishes the actual value on the state topic, so Home Assistant snaps back if a write failed.
  A rejected or unanswered write logs a warning. Use the existing `setItem` contract (returns 'OK'
  or raises ValueError/IOError, see Phase 4 follow-up work) and the datamap min/max validation.
- **D-09:** Every accepted or rejected command received over MQTT is logged (topic, item, value,
  result). No secrets in logs.

### The web GUI settings page
- **D-10:** A new dedicated "Home Assistant / MQTT" page reachable from the main menu, with a normal
  form (not the raw-text config editor). It follows the existing login requirement and the same
  same-origin/CSRF protection used by the config editor's save.
- **D-11:** Fields: enable switch, broker host, port, username, password, TLS on/off with certificate
  verification, topic prefix, discovery prefix, Home Assistant device identifier and name,
  "Allow commands" switch, refresh interval. No client-certificate or custom-CA options in this
  phase (deferred).
- **D-12:** The MQTT password is stored in the existing SQLite settings store (on the data volume) and
  is never sent back to the browser: the form shows "set" and leaving the field blank keeps the
  current value. Document that the volume must be protected. Non-secret settings use the same store.
- **D-13:** Saving reconnects to the broker live, with no daemon restart. The page shows a status line
  (Connected / Disconnected with the reason, last publish time) and a "Test connection" button that
  checks host/port/credentials/TLS without saving them.

### When the burner or PellMon is offline
- **D-14:** When `burner_connection` (added by the "burner not connected" work, PR #11) is
  `no_connection`, the availability topic `<prefix>/status` goes `offline` so Home Assistant marks all
  entities unavailable instead of showing stale numbers; it returns to `online` automatically when
  the burner answers again. In `demo` mode the status is also not `online` for real entities unless
  explicitly decided in planning (see Claude's Discretion).
- **D-15:** PellMon registers an MQTT last-will on the availability topic so the broker publishes
  `offline` if PellMon dies or loses the network; PellMon publishes `online` after (re)connecting.
- **D-16:** Publish on change, plus a periodic refresh of all values (default 60 s, configurable in
  the GUI).
- **D-17:** Discovery messages are retained; state messages are not retained (so Home Assistant never
  shows a stale value from an earlier session). The availability/status message follows the
  last-will convention (retained online/offline), which is the standard pattern.

### Added after research (2026-09-25)
- **D-18 (clarifies D-06):** While "Allow commands from Home Assistant" is OFF, the 10 number
  entities and the 2 reset buttons are **removed from MQTT discovery** (an empty retained config
  payload), so nothing appears controllable that is not. They are published again when commands are
  enabled. Home Assistant may keep registry entries or history for removed entities; verifying that
  on the user's real instance is a manual UAT item. Not chosen: keeping them published with writes
  ignored, or adding parallel read-only sensors.
  (Plan-review note, implementation of D-06 "ignored and logged": the explicit per-entity `/set`
  topics stay subscribed while commands are OFF; every message on them is logged and dropped
  without a burner write. No wildcard subscriptions; Burner ON/OFF topics are never subscribed.)
- **D-19:** The research's corrections C1 (topic segments for `power_percent`, `power_kw`,
  `boiler_diff_down`, `boiler_diff_up` differ from PellMon item names; keep a separate object-id
  column), C2 (takeover needs device identifier, discovery `node_id` and unique-id prefix as
  settings), C5 (publish `offline` on clean shutdown via `atexit`, since a clean disconnect
  suppresses the last will), C6 (subscribe to Home Assistant's birth message and republish state)
  and C7 (Test connection is start-and-poll) are adopted as implementation decisions. See
  `06-RESEARCH.md` section "Corrections/Conflicts with CONTEXT".

### Claude's Discretion
- MQTT client library (likely paho-mqtt) and the version to pin; it must run on Python 3.11 in the
  Debian container on a Raspberry Pi 3A+ (512 MB RAM), so keep memory and thread use small.
- Where the client runs: most likely a new pellmonsrv Protocols-style plugin (it already has the
  item database, the settings store and the change signal), with pellmonweb only providing the
  settings page over D-Bus. Confirm during research.
- Threading and reconnect/back-off strategy, message ordering on connect, and how the plugin
  subscribes to `/set` topics safely.
- Whether `demo` mode publishes as online (labelled) or stays offline; default to NOT publishing
  simulated values as real (offline) unless a setting says otherwise.
- Safety limits beyond the datamap min/max, rate limiting of commands, and de-duplication of repeated
  identical commands.
- Test strategy (fake broker or in-process mock; no real network in CI) and documentation layout.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and prior decisions
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md` - constraints (Linux-only production, Python 3.11 in Debian bookworm-slim, Raspberry Pi target).
- `.planning/phases/05-security-ci-deployment-hardening/05-CONTEXT.md` - web auth (PBKDF2), CI and Docker decisions this phase must keep working with.
- `.planning/quick/260920-td3-show-a-clear-message-when-the-burner-is-/260920-td3-SUMMARY.md` - the `burner_connection` / `burner_connection_reason` items and their transition rules (D-14 depends on them). Implemented on PR #11.
- `.planning/quick/260919-olq-fix-scotte-crlf-retry-duplication-and-se/260919-olq-SUMMARY.md` - the `setItem` contract for writes.

### Burner data model
- `src/Scotteprotocol/datamap.py` - authoritative item names, frames, and min/max for settable parameters (version-dependent).
- `src/Pellmonsrv/plugins/scottecom/scottecom.py`, `src/Pellmonsrv/plugin_categories.py` - how plugins register items and use `load_setting`/`store_setting`.
- `src/Pellmonsrv/database.py` - `Keyval_storage` (SQLite settings store), `Item`/`Getsetitem`/`Plainitem`.
- `src/Pellmonsrv/pellmonsrv.py` - the Database thread's change detection and `changed_parameters` D-Bus signal.

### Web GUI
- `src/Pellmonweb/pellmonweb.py`, `src/Pellmonweb/pellmonconf.py`, `src/Pellmonweb/auth.py`, `src/Pellmonweb/html/layout.html` - page controllers, login, same-origin check, and the menu.

### Home Assistant reference (sensitive, do not commit)
- The untracked Home Assistant MQTT diagnostics export in the repo root (`mqtt-*.json`). It describes the existing "Scotte Pellet Burner" device (entity names, units, ranges, topic layout) and is the reference for D-01 to D-05. **It contains device identifiers: read it for structure only, never copy identifiers or serials into any committed file, never stage it.**

No other external specs. Home Assistant's MQTT discovery documentation should be consulted by research for current payload fields.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Plugin framework: Protocols-category plugins register items and receive `db`; the daemon's Database thread already detects item changes every 2 s and emits `changed_parameters`.
- `Keyval_storage` via `load_setting`/`store_setting`: persistent settings without touching `pellmon.conf`.
- Web login and same-origin check from the config editor's `save()`; the `Sensor`/websocket path for live status.
- `burner_connection` and `burner_connection_reason` items (PR #11) to drive availability.
- `tools/burner_sim.py` and the pty tests: an emulated burner for end-to-end checks.

### Established Patterns
- Plugins follow the closest existing plugin's style (lowercase class names subclassing `protocols`); `%`-formatting and the shared `pellMon` logger; new files carry the GPL header.
- Config values may contain `%`, so app config parsers use `interpolation=None`.
- Failing-first tests; tests must run in WSL/CI with mocked I/O and no real network.
- Docker: non-root `pellmon` user, config from `config/conf.d`, settings volume `pellmon-data`.

### Integration Points
- New daemon-side plugin (MQTT client) + D-Bus methods or items for the settings page; new pellmonweb page and menu entry; new dependency in `requirements.txt` and the Docker image (pinned); docs in `DEPLOY-PI.md` and `HARDWARE-BRINGUP.md`.

</code_context>

<specifics>
## Specific Ideas

- Match today's Home Assistant device so nothing in the user's dashboards needs to change, except the deliberate removal of the Burner ON/OFF buttons (D-07).
- Numbers and ranges as listed in D-02, taken from the existing device's discovery data.

</specifics>

<deferred>
## Deferred Ideas

- Client-certificate / custom CA options for MQTT TLS.
- Burner ON/OFF (and other high-impact commands) from Home Assistant, possibly behind an extra confirmation or separate switch.
- A "last command error" entity and a "Burner connection" status entity in Home Assistant (possible follow-up; the connection state is already available to expose).
- Publishing extra PellMon items (silo level, days left, consumption).
- Multiple burners / NBE burners over MQTT.
- Password storage via environment variable or Docker secret.

</deferred>

---

*Phase: 6-Enable Home Assistant MQTT device with settings on the web GUI*
*Context gathered: 2026-09-20*
