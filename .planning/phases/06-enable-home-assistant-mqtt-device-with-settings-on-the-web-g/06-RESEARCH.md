# Phase 6: Enable Home Assistant MQTT device with settings on the web GUI - Research

**Researched:** 2026-09-25
**Domain:** MQTT client (paho-mqtt) inside the pellmonsrv daemon, Home Assistant MQTT discovery, D-Bus settings API, CherryPy settings page
**Confidence:** MEDIUM-HIGH (code facts and paho API verified locally; HA discovery facts cited from official docs; a few HA registry behaviours are `[ASSUMED]` and flagged)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Matching the existing Home Assistant device**
- **D-01:** Keep the existing topic layout so current Home Assistant dashboards and automations keep working: `<prefix>/<item>/state` for values, `<prefix>/<item>/set` for commands, and `<prefix>/status` as the availability topic. The prefix is configurable and defaults to `scotte`.
- **D-02:** Expose the same 23 entities as the existing "Scotte Pellet Burner" device, with the same names, units, device classes, state classes and min/max/step for numbers:
  - 9 sensors: Power (%), Power kW, Boiler Temperature, Chute Temperature, Smoke Temperature, Oxygen Level, Light (LDR), Feeder Time, Burner Mode.
  - 10 numbers (settable): Boiler Temp Setpoint (40-85), Boiler Temp Minimum (10-70), Boiler Diff Down (0-20), Boiler Diff Up (0-15), Chimney Draught (0-10), Cleaning Interval (1-120 min), Cleaning Time (0-60 s), Feeder Capacity (400-8000 g/h), Min Power (10-100), Max Power (10-100).
  - 4 buttons: Burner ON, Burner OFF, Reset Alarm, Reset Ignition (see D-06 for which are exposed).
  - Numeric ranges advertised in discovery must never be wider than what the PellMon/Scotte datamap allows for that item; where they differ, use the narrower range.
- **D-03:** PellMon takes over the same Home Assistant device rather than creating a second one: reuse the same device identifiers and per-entity unique IDs so entities, history and dashboards continue. The device identifier and device name must be **settings** (web GUI / settings store), never hard-coded in the repository. The old publisher must be switched off first; document this.
- **D-04:** Use MQTT discovery, published automatically and retained, under a configurable discovery prefix (default `homeassistant`).
- **D-05 (mapping, verified against the datamap):** Home Assistant entity to PellMon item: `power`, `power_kW`, `boiler_temp`, `chute_temp`, `smoke_temp`, `oxygen`, `light`, `feeder_time`, `mode`; settings `boiler_temp_set`, `boiler_temp_min`, `boiler_temp_diff_down`, `boiler_temp_diff_up`, `chimney_draught`, `cleaning_interval`, `cleaning_time`, `feeder_capacity`, `min_power`, `max_power`; commands `burner_on`, `burner_off`, `reset_alarm`, `reset_ignition`. Some items exist only for certain chip versions (datamap keys are version tuples, e.g. `boiler_temp_diff_down` from 4.00, `boiler_temp_diff_up` from 4.99): publish discovery only for items that exist in the connected burner's database.

**Commands from Home Assistant**
- **D-06:** Commands are OFF by default. A clearly labelled "Allow commands from Home Assistant" switch on the settings page enables them. When off, number and button entities are not published as controllable (or are removed from discovery) and any message on a `/set` topic is ignored and logged.
- **D-07:** Only two buttons exist in Home Assistant: **Reset Alarm** and **Reset Ignition**. Burner ON and Burner OFF are NOT exposed to Home Assistant (they stay in PellMon's own UI). This is a deliberate difference from the existing device; the old ON/OFF entities will show as unavailable or must be removed in Home Assistant. Document it.
- **D-08:** After every command from Home Assistant, PellMon reads the value back from the burner and republishes the actual value on the state topic, so Home Assistant snaps back if a write failed. A rejected or unanswered write logs a warning. Use the existing `setItem` contract (returns 'OK' or raises ValueError/IOError, see Phase 4 follow-up work) and the datamap min/max validation.
- **D-09:** Every accepted or rejected command received over MQTT is logged (topic, item, value, result). No secrets in logs.

**The web GUI settings page**
- **D-10:** A new dedicated "Home Assistant / MQTT" page reachable from the main menu, with a normal form (not the raw-text config editor). It follows the existing login requirement and the same same-origin/CSRF protection used by the config editor's save.
- **D-11:** Fields: enable switch, broker host, port, username, password, TLS on/off with certificate verification, topic prefix, discovery prefix, Home Assistant device identifier and name, "Allow commands" switch, refresh interval. No client-certificate or custom-CA options in this phase (deferred).
- **D-12:** The MQTT password is stored in the existing SQLite settings store (on the data volume) and is never sent back to the browser: the form shows "set" and leaving the field blank keeps the current value. Document that the volume must be protected. Non-secret settings use the same store.
- **D-13:** Saving reconnects to the broker live, with no daemon restart. The page shows a status line (Connected / Disconnected with the reason, last publish time) and a "Test connection" button that checks host/port/credentials/TLS without saving them.

**When the burner or PellMon is offline**
- **D-14:** When `burner_connection` (added by the "burner not connected" work, PR #11) is `no_connection`, the availability topic `<prefix>/status` goes `offline` so Home Assistant marks all entities unavailable instead of showing stale numbers; it returns to `online` automatically when the burner answers again. In `demo` mode the status is also not `online` for real entities unless explicitly decided in planning (see Claude's Discretion).
- **D-15:** PellMon registers an MQTT last-will on the availability topic so the broker publishes `offline` if PellMon dies or loses the network; PellMon publishes `online` after (re)connecting.
- **D-16:** Publish on change, plus a periodic refresh of all values (default 60 s, configurable in the GUI).
- **D-17:** Discovery messages are retained; state messages are not retained (so Home Assistant never shows a stale value from an earlier session). The availability/status message follows the last-will convention (retained online/offline), which is the standard pattern.

### Claude's Discretion
- MQTT client library (likely paho-mqtt) and the version to pin; it must run on Python 3.11 in the Debian container on a Raspberry Pi 3A+ (512 MB RAM), so keep memory and thread use small.
- Where the client runs: most likely a new pellmonsrv Protocols-style plugin (it already has the item database, the settings store and the change signal), with pellmonweb only providing the settings page over D-Bus. Confirm during research.
- Threading and reconnect/back-off strategy, message ordering on connect, and how the plugin subscribes to `/set` topics safely.
- Whether `demo` mode publishes as online (labelled) or stays offline; default to NOT publishing simulated values as real (offline) unless a setting says otherwise.
- Safety limits beyond the datamap min/max, rate limiting of commands, and de-duplication of repeated identical commands.
- Test strategy (fake broker or in-process mock; no real network in CI) and documentation layout.

### Deferred Ideas (OUT OF SCOPE)
- Client-certificate / custom CA options for MQTT TLS.
- Burner ON/OFF (and other high-impact commands) from Home Assistant, possibly behind an extra confirmation or separate switch.
- A "last command error" entity and a "Burner connection" status entity in Home Assistant (possible follow-up; the connection state is already available to expose).
- Publishing extra PellMon items (silo level, days left, consumption).
- Multiple burners / NBE burners over MQTT.
- Password storage via environment variable or Docker secret.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01 | Existing topic layout, configurable prefix default `scotte` | Object-id table (4 topic names differ from PellMon item names, see Corrections C1); state/set/status topic shape confirmed from export structure |
| D-02 | Same entities, names, units, classes, ranges | Entity table below (verified against export structure and datamap; all 10 HA ranges equal the datamap ranges) |
| D-03 | Take over the same HA device via settings | Three identifiers are involved, not one (C2); old retained discovery topics must be overwritten, not duplicated |
| D-04 | Retained discovery under configurable prefix | HA discovery topic/payload docs; publish policy in Architecture |
| D-05 | Item mapping, only items present in the db | Read `db` keys at (re)connect; chimney_draught only exists for chips below 6.85 |
| D-06 | Commands off by default | Discovery variant without number/button entities; `/set` gate in worker (C3) |
| D-07 | Only Reset Alarm / Reset Ignition buttons | Publish empty retained config for old ON/OFF topics (optional, recommended) |
| D-08 | Readback after every command | `db.get_text()` forces a re-read within 4 s of a write (Protocol.getItem FORCE_GET) |
| D-09 | Log every command, no secrets | Log format and no-secret test |
| D-10 | Dedicated login-protected page, same-origin check | `HomeAssistant` controller mirroring `Settings` in settings.py |
| D-11 | Field list | Validators table; extra takeover fields (C2) |
| D-12 | Password never returned to browser | Dedicated D-Bus methods, `mqtt.password` not in `ALLOWED_SETTINGS`, `has_password` flag |
| D-13 | Live reconnect, status line, Test connection | Worker `reconfigure` event; async start/poll test method (blocking D-Bus call rejected) |
| D-14 | Availability follows `burner_connection` | Cheap 1 s tick reading the Plainitem; demo = offline |
| D-15 | Last-will + online after connect | `will_set` before connect; explicit `offline` on graceful shutdown (C5) |
| D-16 | Publish on change plus periodic refresh | Database-thread change listener + refresh from the Database `values` snapshot |
| D-17 | Discovery retained, state not retained, status retained | qos/retain matrix below; HA birth message resubscribe |
</phase_requirements>

## Summary

The whole feature fits cleanly into existing infrastructure. A new Protocols-style plugin (`homeassistant`) runs inside pellmonsrv, gets change notifications from a small listener hook added to `pellmonsrv.Database.run()` (the 2 s value-diff loop that already exists), reads/writes items through the shared `db`, and owns two threads (paho's network thread plus one worker thread that serialises all publishing and command handling). pellmonweb never touches MQTT or the settings DB: it gets a new `HomeAssistant` controller (login + same-origin protected, mirroring `Settings`) that talks to five new D-Bus methods on `MyDBUSService`. Phase 8's `ALLOWED_SETTINGS` whitelist is left untouched, which is what keeps the password unreadable: `mqtt.password` is simply not whitelisted, and the new methods never return it.

paho-mqtt 2.1.0 (pure Python, `py3-none-any` wheel, 67 KB, requires Python >= 3.7, latest release 2024-04-29) is the right client. It compiles nothing on arm/v7 under QEMU, adds one thread, and needs the v2 callback API (`CallbackAPIVersion.VERSION2`). Two empirically verified constraints shape the design: (1) under `pytest --disable-socket` a real `paho.Client` can be constructed and configured but `loop_start()` raises `SocketBlockedError` (it creates a socketpair), so the plugin must take an injectable client factory and tests use an in-memory fake; (2) QoS 0 publishes while disconnected are dropped by paho, but QoS 1 publishes queue without bound by default, so publish only while connected and cap the queue.

Research found four points where CONTEXT cannot be implemented literally (see "Corrections/Conflicts with CONTEXT"): four MQTT topic names differ from the PellMon item names, the takeover needs three identifiers instead of one, `Database.terminate()` (needed for a graceful `offline`) is never called today, and D-06's "not controllable" needs a concrete discovery strategy that has a user-visible cost.

**Primary recommendation:** Build a `homeassistant` plugin with an injectable paho client factory, a single worker thread and a Database change-listener hook; expose non-secret settings plus `has_password` through new dedicated D-Bus methods (never through `GetSetting`); pin `paho-mqtt==2.1.0`; test everything against an in-memory fake client.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MQTT connection, LWT, discovery, state publishing | pellmonsrv plugin (daemon) | - | Daemon owns the item db, the burner link and the 2 s change loop; the web process must stay stateless |
| Command handling from HA (`/set`) | pellmonsrv plugin (worker thread) | Scotte protocol `setItem` | Validation next to the datamap min/max; must not run on paho's network thread |
| Settings + password persistence | pellmonsrv (`Keyval_storage`, 0600 file) | - | Web container mounts data read-only and never opens the DB (Phase 7 D-04) |
| Settings validation | pellmonsrv (single validator module) | Browser HTML5 attributes (UX only) | One authoritative validator, reused by the test-connection path |
| Settings page (form, status line, test button) | pellmonweb (CherryPy + Mako) | D-Bus JSON methods | Same pattern as Phase 8 `Settings` |
| AuthN/CSRF for the page | pellmonweb (`require()`, `check_same_origin`) | - | Existing pattern |
| Status line data | pellmonsrv plugin (`GetMqttStatus`) | pellmonweb polls via AJAX | Daemon knows connection state and last publish time |
| Availability semantics | pellmonsrv plugin | broker LWT | LWT covers crash/network loss, plugin covers burner loss and graceful stop |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| paho-mqtt | ==2.1.0 | MQTT 3.1.1 client (threaded `loop_start`) | Eclipse Foundation reference Python client; the only pure-Python, dependency-free client with built-in reconnect back-off, will, TLS. Requires `CallbackAPIVersion.VERSION2`. `[VERIFIED: PyPI JSON, pip index versions]` version and wheel type; package-name provenance see audit. |

### Supporting
None. Everything else is stdlib (`ssl`, `threading`, `queue`, `json`, `re`, `time`) plus what is already in the repo.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| paho-mqtt | `aiomqtt`, `gmqtt`, `amqtt` | asyncio-based; pellmonsrv is thread + GLib based, so an event loop would be a second concurrency model. Not needed. |
| pip paho 2.1.0 | Debian `python3-paho-mqtt` (bookworm ships 1.6.1) | 1.6.1 has no `CallbackAPIVersion` and different callback signatures. Do not use; guard with `hasattr(mqtt, "CallbackAPIVersion")` and log a clear error. `[ASSUMED]` bookworm version, from training data. |

**Installation:**
```bash
# requirements.txt (this project pins with ==)
paho-mqtt==2.1.0
```

**Version verification:** `pip index versions paho-mqtt` (run 2026-09-25) lists 2.1.0 as the newest release; PyPI JSON: released 2024-04-29, license `EPL-2.0 OR BSD-3-Clause`, wheel `paho_mqtt-2.1.0-py3-none-any.whl` 67,219 bytes, sdist 148,848 bytes. `[VERIFIED: PyPI]` No 2.x release since April 2024 (stable/quiet, not abandoned; Eclipse Paho org repository). Licence is compatible with a GPL application using it as a dependency (dual EPL-2.0 / BSD-3-Clause). `[ASSUMED]` legal reading, no legal review.

**Python 3.11 / bookworm-slim / arm:** py3-none-any wheel means no compilation and no build tools on linux/amd64, arm64 and arm/v7; the QEMU multi-arch CI build only downloads and unpacks it. Runtime cost is one extra thread (paho network loop) plus one plugin worker thread; memory is a few MB. `[VERIFIED: wheel tag]`, memory `[ASSUMED]` (not measured on a Pi).

## Package Legitimacy Audit

slopcheck could not be installed in this session (`pip install slopcheck` produced no usable command), so per protocol the package is tagged `[ASSUMED]` and the planner must gate the install behind a `checkpoint:human-verify` task (this project requires that for every new pip package anyway).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| paho-mqtt | PyPI | 10+ yrs (1.x series since 2013, 2.0.0 Feb 2024) | not measured (widely used, Home Assistant ecosystem client) | github.com/eclipse-paho/paho.mqtt.python | unavailable | `[ASSUMED]` - Approved pending human-verify. Evidence for the checkpoint: Eclipse Foundation project, PyPI metadata author Roger Light, no install scripts (pure-Python wheel, nothing runs at install), `pip index versions` works against the correct registry (PyPI) |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none (slopcheck unavailable; human-verify checkpoint required)

The human-verify checkpoint should confirm: name is exactly `paho-mqtt` (not `paho`, `paho-mqtt-client`), source repo is `eclipse-paho/paho.mqtt.python`, version is 2.1.0.

## Architecture Patterns

### System Architecture Diagram

```
                       Browser (login session)
                              |  GET/POST /homeassistant/...  (require() + check_same_origin on POST)
                              v
                  +-------------------------+
                  | pellmonweb              |  HomeAssistant controller (Mako page, AJAX status/test)
                  | Dbus_handler.mqtt_*     |  JSON strings only, password only on save/test
                  +------------+------------+
                               | D-Bus  GetMqttSettings / SetMqttSettings / GetMqttStatus /
                               |        StartMqttTest / GetMqttTestResult
                               v
 +-----------------------------------------------------------------------------+
 | pellmonsrv                                                                  |
 |  MyDBUSService --> homeassistant plugin (found via conf.database.protocols) |
 |                        |  settings: Keyval_storage (mqtt.config, mqtt.password, 0600)
 |  Database thread  --2 s diff--> change listener ---> event queue ---+       |
 |  (values snapshot)                                                  v       |
 |  burner_connection Plainitem --1 s tick------------------> WORKER THREAD    |
 |                                                            | publish (retain/qos matrix)
 |  Scotte protocol  <-- db.set_value / db.get_text ----------+ command handler|
 |                                                            |                |
 |                          paho network thread (loop_start) <-+  on_message ->queue
 +----------------------------------|------------------------------------------+
                                    | TCP 1883 / TLS 8883
                                    v
                               MQTT broker  <----->  Home Assistant
                       (LWT: <prefix>/status = offline, retained)
```

Data flow for a state change: burner value changes -> Database thread notices (<= 2 s) -> listener enqueues -> worker publishes `<prefix>/<obj>/state` (QoS 0, not retained) if it differs from the last published payload. Data flow for a command: HA publishes `<prefix>/<obj>/set` -> paho thread `on_message` only enqueues -> worker validates, rate-limits, calls `db.set_value`, logs, reads back with `db.get_text`, publishes actual state.

### Recommended Project Structure
```
src/Pellmonsrv/plugins/
├── homeassistant.pellmon-plugin        # [Core] Name = HomeAssistant, Module = homeassistant
└── homeassistant/
    ├── __init__.py                     # plugin class (protocols subclass), lazy paho import
    ├── entities.py                     # entity table + discovery payload builder (pure)
    ├── settings.py                     # defaults, validators, load/save, secret handling (pure)
    ├── bridge.py                       # worker thread, connect/reconnect, publish policy, commands
    └── Makefile.am                     # legacy autotools, mirror scottecom/Makefile.am
src/Pellmonweb/homeassistant.py         # HomeAssistant controller (like settings.py)
src/Pellmonweb/html/homeassistant.html  # Mako page
src/Pellmonweb/media/js/homeassistant.js# status poll + test button (.text() only, no .html())
tests/Pellmonsrv/plugins/test_homeassistant_*.py
tests/Pellmonweb/test_homeassistant_page.py
tests/browser/{fake_dbus.py, test_mobile_overflow.py, test_browser_harness.py}   # extend
```
Directory name follows the plugin convention (lowercase, no separators). Keep paho imports lazy (inside `bridge`/`activate`) so `tests/test_plugin_imports.py` (descriptor-driven, requires >= 15 plugins, will now find 16) imports the module on machines without paho or dbus.

### Pattern 1: Injectable client factory (test seam)
**What:** `Bridge(settings, db, client_factory=default_paho_factory, clock=time.monotonic)`. The default factory builds and fully configures a real paho client but does not connect. Tests pass a `FakeMqttClient`.
**When to use:** always; `pytest.ini` has `--disable-socket` and `tests/README.md` forbids removing it or adding `enable_socket`.
```python
# Source: paho 2.1.0 API, inspected from the installed package (client.py) and
# https://raw.githubusercontent.com/eclipse-paho/paho.mqtt.python/master/docs/migrations.rst
import ssl
import paho.mqtt.client as mqtt

def default_paho_factory(cfg, password, client_id, will_topic, on_connect, on_disconnect, on_message):
    if not hasattr(mqtt, 'CallbackAPIVersion'):
        raise RuntimeError('paho-mqtt >= 2.0 required')
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
    if cfg['username']:
        c.username_pw_set(cfg['username'], password or None)
    if cfg['tls']:
        if cfg['tls_verify']:
            c.tls_set(cert_reqs=ssl.CERT_REQUIRED)      # system CA store, hostname checked
        else:
            c.tls_set(cert_reqs=ssl.CERT_NONE)
            c.tls_insecure_set(True)                    # must come after tls_set
    c.will_set(will_topic, 'offline', qos=1, retain=True)
    c.reconnect_delay_set(min_delay=1, max_delay=60)
    c.max_queued_messages_set(200)
    c.on_connect = on_connect          # (client, userdata, flags, reason_code, properties)
    c.on_disconnect = on_disconnect    # (client, userdata, flags, reason_code, properties)
    c.on_message = on_message          # (client, userdata, message)
    return c
```
Verified by test on this machine (paho 2.1.0, Python 3.14, `--disable-socket`): construct + `will_set` + `username_pw_set` + `tls_set` + `reconnect_delay_set` pass; `loop_start()` fails with `SocketBlockedError`.

### Pattern 2: One worker thread, callbacks only enqueue
paho runs `on_message` on its network thread. `db.set_value` blocks on the Scotte serial queue (up to several seconds), which would stall keepalive pings. So `on_connect`/`on_disconnect`/`on_message` only `queue.put_nowait(...)`; the worker does `queue.get(timeout=1.0)` and on every timeout also runs the 1 s tick (availability from `burner_connection`, refresh interval, discovery settle timer). No `threading.Timer` chains (existing plugins create a new Timer thread every 30 s; do not copy that).

### Pattern 3: Database change listener (small change to existing code)
Add to `pellmonsrv.Database`: `self.listeners = []` set before plugin activation (plugins activate inside `__init__` before `self.start()`), `add_change_listener(cb)`, a `_notify(changed_params)` call in `run()` after `changed_params` is built (each callback in try/except so a plugin cannot kill the Database thread), and `snapshot()` returning `dict(self.values)`. The plugin uses `getattr(db, 'add_change_listener', None)`; when absent (plain `database.Database` in unit tests) it does nothing and tests drive `bridge.on_changes()` directly. The listener must only enqueue. `values` holds display text (`item.get_text(item.value)`, falling back to `item.value`), which for Scotte items is the same string style the old publisher sent (`64`, `6.8`, `56.9`, `Running`). Refresh (D-16) publishes from `snapshot()`, so it causes zero extra serial reads.

### Pattern 4: Settings storage and the password (D-12)
- Non-secret settings: one JSON blob under key `mqtt.config` (atomic single-row write, easy to version) via `Keyval_storage.keyval_storage.writeval`. Password: separate key `mqtt.password`.
- Read with `getval(key, default)` (exception-free, returns default for missing keys), NOT `protocols.load_setting()`: that calls `readval`, which logs `logger.exception` and returns the string `'error'` for a missing key.
- `ALLOWED_SETTINGS` and `GetSetting`/`SetSetting` stay exactly as Phase 8 built them. Neither `mqtt.config` nor `mqtt.password` is added. Result: `GetSetting('mqtt.password')` returns `''` and logs a warning (rejected unknown key), `SetSetting` returns False. Add a regression test asserting this and asserting no `mqtt.` key ever appears in `ALLOWED_SETTINGS`.
- New D-Bus methods (all `in/out_signature='s'` JSON strings, avoiding `a{sv}` variants):

| Method | Direction | Contents |
|--------|-----------|----------|
| `GetMqttSettings() -> s` | daemon -> web | all non-secret fields + `has_password: bool` + `available: bool` (plugin loaded, paho importable). Never a `password` key. |
| `SetMqttSettings(s) -> s` | web -> daemon | JSON incl. optional `password` (str) and `clear_password` (bool). Returns `{"ok": bool, "errors": {field: msg}}`. Blank/absent password = keep. Validates everything, stores atomically, triggers ONE reconfigure. |
| `GetMqttStatus() -> s` | daemon -> web | `{state, reason, last_publish (epoch or null), last_connect, entities, commands_enabled, availability}` |
| `StartMqttTest(s) -> b` | web -> daemon | candidate settings JSON (blank password = use stored); starts a background test, returns immediately |
| `GetMqttTestResult() -> s` | daemon -> web | `{state: idle|running|ok|error, message}` |

  `MyDBUSService` finds the plugin the way `getPlugins` does (`for p in conf.database.protocols: if p.name == 'HomeAssistant'`); when absent the methods return `{"available": false}` and the page shows "plugin not loaded, add `p15 = HomeAssistant` to enabled_plugins.conf".
- Why the test is start/poll and not one blocking call: `MyDBUSService` methods run in the GLib main loop; a 5-10 s blocking test would freeze every other D-Bus call (web UI GetItem) and `Dbus_handler` holds `self.lock` during each call. `[VERIFIED: pellmonsrv.py and pellmonweb.py]`
- The password crosses the private D-Bus once per save/test (session bus socket on the shared `pellmon-run` volume). Same trust boundary as `SetItem`. Never log D-Bus arguments or the settings dict.
- `readback of password`: none. The form shows "Password is set" (from `has_password`) and a "Remove stored password" checkbox; blank field = keep.

### Pattern 5: Publish policy (qos/retain matrix, ordering)
| Message | Topic | QoS | Retain |
|---------|-------|-----|--------|
| Discovery config | `<disc>/<component>/<node>/<obj>/config` | 1 | yes (D-04/D-17) |
| Availability (birth + LWT) | `<prefix>/status` payload `online`/`offline` | 1 | yes |
| State | `<prefix>/<obj>/state` | 0 | no (D-17) |
| Old Burner ON/OFF cleanup (empty payload) | `<disc>/button/<node>/burner_{on,off}/config` | 1 | yes |
QoS 0 for state matches what the existing device uses (observed in export). Connect sequence in the worker, after `on_connect` success: (1) subscribe to `<disc>/status` (HA birth) and, only if commands enabled, each explicit `<prefix>/<obj>/set` topic (no wildcard); (2) publish availability (`online` only if burner ok, else `offline`); (3) publish discovery; (4) after a 2 s settle delay publish all state (HA subscribes to state topics only after processing discovery, and state is not retained, so states published in the same instant can be missed on first creation); (5) periodic refresh thereafter. On HA birth message `online` on `<disc>/status`: republish discovery and all states after a short delay (HA restart loses non-retained state otherwise, and D-17 forbids retaining it). Publish only while connected; QoS 0 publishes while disconnected are dropped by paho, QoS 1 would queue unbounded (default `max_queued_messages` is 0 = unlimited), hence `max_queued_messages_set(200)` and the connected gate.

### Pattern 6: Command handling (D-06, D-08, D-09)
Worker steps for `<prefix>/<obj>/set`: ignore and log if `commands_enabled` is false (D-06) -> ignore messages with `retain=True` (a retained message on a `/set` topic would replay a stale command on every reconnect) -> payload <= 32 bytes, utf-8 decode -> map obj to item, must be one of the whitelisted items present in `db` -> buttons: payload must equal `PRESS`, then `db.set_value(item, '0')` (the web UI sends `'0'` for commands; `setItem` requires a numeric string) -> numbers: `float()`, finite, integral (all 10 settings have `decimals=0`), inside `[max(ha_min, item.min), min(ha_max, item.max)]` (item `.min/.max` are strings set by scottecom from the datamap) -> optional cross-check `min_power <= max_power` `[ASSUMED]` useful, not required by datamap -> rate limit -> `db.set_value` (raises ValueError/IOError) -> log `accepted`/`rejected` with topic, item, value, result -> readback `db.get_text(item)` and publish actual value (also on failure, D-08). Suggested limits `[ASSUMED]`, tune in planning: same item+value repeated within 2 s dropped, same item at most once per 5 s, global at most 10 writes per minute, command queue bounded to 20 (drop with a warning). These protect burner memory/EEPROM from a looping automation; the numbers themselves are not sourced from documentation.

### Anti-Patterns to Avoid
- **Doing serial I/O in paho callbacks:** stalls keepalive, causes spurious disconnects.
- **Reading item values in the plugin for every publish:** each read may hit the serial port. Use the Database `values` snapshot and change events; only force reads for readback.
- **Using the same MQTT client id for the test-connection client:** the broker would kick the live client (session takeover) every time the user presses Test. Use `pellmon-test-<random>`.
- **Adding `mqtt.*` keys to `ALLOWED_SETTINGS`:** would make the password readable via `GetSetting`.
- **`protocols.load_setting` for optional keys:** logs an exception traceback per missing key.
- **`enable_logger()` on paho:** noisy on an SD card; leave it off.
- **Retained `/set` handling:** always ignore retained command messages.
- **Deriving the HA device identity from the hostname or hard-coding it:** must be settings (D-03).

## Home Assistant discovery (D-02, D-04, D-05, D-17)

Discovery topic: `<discovery_prefix>/<component>/[<node_id>/]<object_id>/config`, payload JSON, published retained; empty payload removes the entity. `node_id`/`object_id` allow `[a-zA-Z0-9_-]`. `[CITED: https://www.home-assistant.io/integrations/mqtt/]` Availability by `availability_topic` with defaults `online`/`offline`; HA publishes a birth message on `homeassistant/status`. `[CITED: same page]` Number: `command_topic` required, `state_topic`, `min`/`max`/`step`/`mode`, `optimistic` defaults to false when a `state_topic` exists (so HA snaps back to the state topic value; that is exactly D-08's behaviour). `[CITED: https://www.home-assistant.io/integrations/number.mqtt/]` Button: `command_topic` required, `payload_press` default `PRESS`. `[CITED: https://www.home-assistant.io/integrations/button.mqtt/]`

The existing device (structure read from the export, no identifiers copied) uses, for every entity: `name`, `unique_id`, `device{identifiers[1], manufacturer, model, sw_version, name}`, `availability_topic`, `payload_available: online`, `payload_not_available: offline`; sensors add `state_topic` (+ `unit_of_measurement`, `device_class`, `state_class` where listed); numbers add `command_topic`, `state_topic`, `min`, `max`, `step: 1`, `mode: box`, `unit_of_measurement`; buttons add `command_topic` and `payload_press: PRESS`. Keep exactly this shape (legacy single `availability_topic` still supported per the docs); optionally add `origin` (HA recommends it). Device block: manufacturer `Bio Comfort`, model `Scotte` are structural constants (safe to commit); `identifiers` and `name` come from settings; `sw_version` can be PellMon's `__version__` (available as `glob['__version__']`).

### Entity table (topic object id -> PellMon item)

| Entity name | Component | Object id (topic segment and unique_id suffix) | PellMon item | Unit | device_class | state_class | min / max / step |
|-------------|-----------|-----------------------------------------------|--------------|------|--------------|-------------|------------------|
| Power | sensor | `power_percent` | `power` | % | power_factor | measurement | |
| Power kW | sensor | `power_kw` | `power_kW` | kW | power | measurement | |
| Boiler Temperature | sensor | `boiler_temp` | `boiler_temp` | °C | temperature | measurement | |
| Chute Temperature | sensor | `chute_temp` | `chute_temp` | °C | temperature | measurement | |
| Smoke Temperature | sensor | `smoke_temp` | `smoke_temp` | °C | temperature | measurement | |
| Oxygen Level | sensor | `oxygen` | `oxygen` | % | - | - | |
| Light (LDR) | sensor | `light` | `light` | - | - | - | |
| Feeder Time | sensor | `feeder_time` | `feeder_time` | s | duration | measurement | |
| Burner Mode | sensor | `mode` | `mode` | - | - | - | |
| Boiler Temp Setpoint | number | `boiler_temp_set` | `boiler_temp_set` | °C | | | 40 / 85 / 1 |
| Boiler Temp Minimum | number | `boiler_temp_min` | `boiler_temp_min` | °C | | | 10 / 70 / 1 |
| Boiler Diff Down | number | `boiler_diff_down` | `boiler_temp_diff_down` | °C | | | 0 / 20 / 1 |
| Boiler Diff Up | number | `boiler_diff_up` | `boiler_temp_diff_up` | °C | | | 0 / 15 / 1 |
| Chimney Draught | number | `chimney_draught` | `chimney_draught` | - | | | 0 / 10 / 1 |
| Cleaning Interval | number | `cleaning_interval` | `cleaning_interval` | min | | | 1 / 120 / 1 |
| Cleaning Time | number | `cleaning_time` | `cleaning_time` | s | | | 0 / 60 / 1 |
| Feeder Capacity | number | `feeder_capacity` | `feeder_capacity` | g/h | | | 400 / 8000 / 1 |
| Min Power | number | `min_power` | `min_power` | % | | | 10 / 100 / 1 |
| Max Power | number | `max_power` | `max_power` | % | | | 10 / 100 / 1 |
| Reset Alarm | button | `reset_alarm` | `reset_alarm` | | | | payload `PRESS` |
| Reset Ignition | button | `reset_ignition` | `reset_ignition` | | | | payload `PRESS` |
| (Burner ON / OFF: not published, D-07) | button | `burner_on`, `burner_off` | - | | | | cleanup only |

`[VERIFIED: export structure + datamap.py]` Unit `°C` is U+00B0 followed by C; write it as `°C` in Python source or a UTF-8 file, and let `json.dumps` escape it. All ten HA ranges equal the datamap `min/max` (boiler_temp_set 40-85, boiler_temp_min 10-70, diff_down 0-20, diff_up 0-15, chimney_draught 0-10, cleaning_interval 1-120, cleaning_time 0-60, feeder_capacity 400-8000, min_power 10-100, max_power 10-100), so D-02's "narrower range" rule currently changes nothing; still compute the intersection at runtime.

### Version-dependent items (D-05)
datamap version windows: `boiler_temp_min`, `boiler_temp_diff_down`, `cleaning_interval`, `cleaning_time`, `min_power`, `max_power`, `reset_alarm`, `reset_ignition` from 4.00; `boiler_temp_diff_up` from 4.99; `chimney_draught` only for `0000 <= version < 6.85` (absent on newer chips). Demo mode builds the db as 6.99, so demo has no `chimney_draught`. `[VERIFIED: datamap.py, protocol.py createDataBase]` The item set is fixed after `scottecom.activate` (chip version auto-detect runs synchronously there), but plugin order is not guaranteed, so compute the entity list from `db` keys at every (re)connect and on each refresh tick; if the set changed since the last discovery publish, republish discovery (idempotent).
Sensors: all exist on every version. Items the connected burner lacks are simply not published (and, for numbers, an old retained config for them stays in HA as whatever the old publisher left).

### Commands disabled (D-06) - recommended discovery behaviour
Home Assistant cannot show a `number` without a `command_topic`, and switching component type (number -> sensor) with the same unique_id creates a NEW entity (registry is per domain) and orphans history, so that option is rejected. Recommended: when commands are off, publish an empty retained config for the 10 number entities and the 2 reset buttons (entities are removed from HA, literal D-06 second option); when on, publish them. Also always clear `button/.../burner_on` and `burner_off` configs (D-07). Cost to flag to the user (Open Question 1): with commands OFF (the default) the setpoint numbers disappear from dashboards until commands are enabled. Fallback if the user dislikes that: keep the number/button discovery unchanged and only ignore+log `/set` (satisfies the "ignored and logged" half of D-06 only). Isolate the choice in one function `discovery_entities(commands_enabled)` so either is a one-line change. Whether HA keeps the entity registry entry (so entity_id and history survive a later re-enable) after an empty-payload removal is `[ASSUMED]`; verify on the real HA instance before finalising the default.

### Takeover mechanics (D-03, D-07)
From the export's structure: the device has ONE identifier; the discovery topic uses a separate `node_id`; and `unique_id` is `<prefix6>_<object_id>`, where the three values are different strings (the identifier has three underscore-separated hex groups, the node id two, the unique-id prefix one; the node id and the prefix appear to be built from parts of the identifier, but that is inferred from one sample, do not rely on it). HA keys entities on `(domain, platform, unique_id)`. If the old publisher's retained discovery messages remain on the broker and PellMon publishes the same unique_id under a different topic, HA sees two configs for one unique_id and ignores/complains about the duplicate. `[ASSUMED]` exact HA duplicate behaviour; the docs page fetched does not describe it. Therefore expose three settings: device identifier, discovery node id, unique-id prefix (last two under "Advanced: taking over an existing device", defaulting to values derived from the identifier so a fresh install works). Document how to read them from HA (Settings > Devices > MQTT INFO, or the diagnostics download) and to stop/remove the old publisher and its retained topics first.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MQTT protocol, keepalive, reconnect back-off, will, TLS | Own socket client | paho-mqtt `loop_start` + `reconnect_delay_set` + `will_set` + `tls_set` | Edge cases (partial reads, keepalive, CONNACK codes, TLS hostname checks) |
| Settings persistence | New file or table | `Keyval_storage` (`getval`/`writeval`) | Already 0600, on the data volume, in the backup tool |
| Auth / CSRF | New session logic | `@require()` + `check_same_origin()` | Same pattern as `Settings.save` |
| Value range validation | Own min/max tables | item `.min/.max` (from datamap) intersected with HA range | Single source of truth |
| Plugin loading | Special-case in daemon | yapsy Protocols plugin + `.pellmon-plugin` descriptor | Existing extension mechanism, descriptor-driven tests pick it up |
| Fake broker | Socket-level fake MQTT broker | In-memory `FakeMqttClient` | `--disable-socket` forbids sockets; verified |

**Key insight:** everything hard is already in paho or the repo; the risk is in concurrency and policy (who publishes when), so keep the bridge logic pure and single-threaded behind a queue.

## Runtime State Inventory

Not a rename/refactor phase. One relevant runtime-state item: **broker-side retained state.** The existing publisher's retained discovery configs and retained `<prefix>/status` live on the MQTT broker and in Home Assistant's entity registry, outside this repo. Action: docs must tell the user to stop the old publisher first and (optionally) delete its retained topics; PellMon overwrites same-topic configs and clears Burner ON/OFF.

## Common Pitfalls

### Pitfall 1: Topic names are not PellMon item names
**What goes wrong:** Publishing `scotte/power/state` instead of `scotte/power_percent/state` breaks every existing HA entity for that value.
**Why:** D-01 says `<item>` but four topic segments differ (see C1).
**How to avoid:** entity table with separate `object_id` and `item`. **Warning signs:** takeover leaves 4 entities `unavailable`/`unknown`.

### Pitfall 2: Live-client kicked by the test client
**What goes wrong:** pressing "Test connection" with the same client id makes the broker disconnect the running client; live status flaps.
**How to avoid:** random `pellmon-test-*` client id, separate paho instance, no publishing, no subscribing, always `disconnect()` + `loop_stop()`.

### Pitfall 3: LWT does not fire on a graceful stop
**What goes wrong:** `disconnect()` suppresses the will; `Database.terminate()` (which calls plugin `deactivate`) is never called by any SIGTERM handler today (grep: no caller), so HA would keep showing `online` until keepalive expiry, or forever if the process exits after a clean close.
**How to avoid:** the plugin registers `atexit` (runs after the GLib loop quits on SIGTERM, before daemon threads are torn down) that publishes retained `offline` with `wait_for_publish(timeout=2)` then `disconnect()`/`loop_stop()`. Do not rely on editing the three SIGTERM handlers (`test_sigterm_handling.py` guards them). If the process is killed hard the kernel closes the socket and the broker fires the will.

### Pitfall 4: Stale command replay via retained `/set`
**How to avoid:** ignore `message.retain` on command topics; subscribe to explicit topics only, and only when commands are enabled; unsubscribe/resubscribe on reconfigure.

### Pitfall 5: Missing first states after discovery
**What goes wrong:** HA creates the entity after processing discovery and subscribes to the state topic afterwards; non-retained state published in the same instant is lost, so numbers stay `unknown` for up to 60 s.
**How to avoid:** 2 s settle delay before first state publish, plus republish on HA birth message and on periodic refresh.

### Pitfall 6: paho callback API drift
**What goes wrong:** paho 1.x style callbacks (`on_connect(client, userdata, flags, rc)`) with paho 2 raise at construction or at callback time; Debian's apt `python3-paho-mqtt` is 1.x `[ASSUMED]`.
**How to avoid:** always `CallbackAPIVersion.VERSION2`, 5-argument `on_connect`/`on_disconnect`, exact pin `paho-mqtt==2.1.0`, plus one test that builds a real paho client via the default factory (allowed under `--disable-socket`).

### Pitfall 7: Docker image may lack CA certificates
**What goes wrong:** with TLS + verify on, `tls_set(cert_reqs=CERT_REQUIRED)` uses the system store; `ca-certificates` is only a Recommends of `libcurl4` in bookworm `[CITED: packages.debian.org/bookworm/libcurl4]`, and the Dockerfile uses `--no-install-recommends`, so `/etc/ssl/certs/ca-certificates.crt` may be missing. Could not verify in the image (Docker daemon not running in this session).
**How to avoid:** add `ca-certificates` explicitly to the Dockerfile apt list (tiny) and add a check in the plan's verification step.

### Pitfall 8: Broker host resolution inside Docker
`homeassistant.local` (mDNS) does not resolve from a bridge-network container; `host.docker.internal` is not defined on Linux by default. Document: use an IP or DNS name; use `extra_hosts` if needed. `[ASSUMED]` general Docker behaviour.

### Pitfall 9: `writeval` and confvalue
Phase 8 verified first-insert `writeval(key, value)` works (`test_first_insert_roundtrip_and_confvalue_not_null`). Use `writeval(key, str)`; never `Storeditem` for these (it would create a db item that GetItem can read, exposing the value).

### Pitfall 10: Status/last-publish needs a lock
Status fields are written by the worker and read by the D-Bus thread (GLib main loop); guard with a small `threading.Lock` or replace the whole status dict atomically.

### Pitfall 11: Form and password handling
Password input `type="password" autocomplete="new-password"`, never rendered back (`value` attribute absent), not in the query string (POST only), never in `logger`/`cherrypy.log` calls; `request.show_mismatched_params` is already False. The Mako template must escape every value (`| h`), as `settings.html` does.

### Pitfall 12: NBE / other burners
Entities are gated only by item-name presence, which is fine for Scotte. NBE support is out of scope; if the `nbecom` plugin happens to define items with the same names (e.g. `boiler_temp`) they would be published with Scotte semantics. Gate publishing on `burner_connection` existing (provided today only by `scottecom`) `[VERIFIED: grep, nbecom and pelletcalc do not define it]`, otherwise the plugin reports "no supported burner plugin" and publishes nothing.

## Code Examples

### Discovery payload builder (pure function, no paho)
```python
# Shape mirrors the existing device (structure only) and
# https://www.home-assistant.io/integrations/mqtt/ (availability_topic, retained config)
def discovery_message(cfg, ent, commands_enabled):
    """Return (topic, payload_or_empty) for one entity. cfg values come from settings."""
    base = cfg['topic_prefix']
    topic = '%s/%s/%s/%s/config' % (cfg['discovery_prefix'], ent.component, cfg['node_id'], ent.object_id)
    if ent.needs_commands and not commands_enabled:
        return topic, ''                       # empty retained payload removes the entity
    p = {
        'name': ent.name,
        'unique_id': '%s_%s' % (cfg['uid_prefix'], ent.object_id),
        'device': {'identifiers': [cfg['device_id']], 'name': cfg['device_name'],
                   'manufacturer': 'Bio Comfort', 'model': 'Scotte', 'sw_version': cfg['sw_version']},
        'availability_topic': '%s/status' % base,
        'payload_available': 'online',
        'payload_not_available': 'offline',
    }
    if ent.component in ('sensor', 'number'):
        p['state_topic'] = '%s/%s/state' % (base, ent.object_id)
    if ent.component in ('number', 'button'):
        p['command_topic'] = '%s/%s/set' % (base, ent.object_id)
    if ent.component == 'button':
        p['payload_press'] = 'PRESS'
    if ent.component == 'number':
        p.update(min=ent.min, max=ent.max, step=1, mode='box')
    for key in ('unit_of_measurement', 'device_class', 'state_class'):
        if getattr(ent, key, None):
            p[key] = getattr(ent, key)
    return topic, json.dumps(p)
```

### D-Bus additions (pattern from GetSetting/SetSetting)
```python
@dbus.service.method('org.pellmon.int', in_signature='s', out_signature='s')
def SetMqttSettings(self, payload):
    plugin = _ha_plugin()          # None when not loaded
    if plugin is None:
        return json.dumps({'ok': False, 'errors': {'_': 'plugin not loaded'}})
    return json.dumps(plugin.apply_settings_json(payload))   # never logs payload
```

### Web controller skeleton (mirror of Settings.save)
```python
@cherrypy.expose
@require()
def save(self, **form):
    if cherrypy.request.method != 'POST':
        return self._render(MSG_REJECTED, 'danger')
    if not check_same_origin():
        cherrypy.response.status = 403
        logger.warning('rejected cross-origin Home Assistant settings save')   # no form data in the log
        return self._render(MSG_REJECTED, 'danger')
    result = self.dbus.mqtt_set_settings(collect_fields(form))   # password only inside this dict
    ...
```
Routes: `index` (GET page), `save` (POST), `status` (GET JSON, `@require()`), `test` (POST, same-origin, starts test), `test_result` (GET JSON). Mount as `self.homeassistant = HomeAssistant(lookup, dbus, credentials)` in `PellMonWeb.__init__` (URL `/homeassistant/`). Navbar: add an `<li class="${'active' if context.get('active_page', '') == 'homeassistant' else ''}">` entry after Settings in `layout.html`.

## Settings validation (single authoritative module, `settings.py` in the plugin)

| Field | Rule (recommended) | Default |
|-------|--------------------|---------|
| enabled | bool | false |
| host | 1-253 chars, `[A-Za-z0-9.-]` or IPv6 literal, no scheme/path/space | empty |
| port | int 1-65535 | 1883 (8883 hint when TLS on) |
| username | 0-128 chars, no NUL/control | empty |
| password | 0-256 chars, no NUL; blank = keep; `clear_password` removes | unset |
| tls / tls_verify | bool / bool | false / true |
| topic_prefix | 1-64 chars, segments `[A-Za-z0-9_-]+` joined by `/`, no leading `/`, no `+`, `#`, `$`, no trailing `/` | `scotte` |
| discovery_prefix | same rule | `homeassistant` |
| device_id, node_id, uid_prefix | 1-64, `[A-Za-z0-9_-]` | device_id required to enable; node/uid derived when empty |
| device_name | 1-64 chars, no control chars | `Scotte Pellet Burner` |
| commands_enabled | bool | false |
| refresh_interval | int 10-3600 s | 60 |

Reject an `enabled` save with missing host or device_id. Return per-field errors as JSON; the web page renders them next to the fields (HTML-escaped).

## Web page and Phase 10 mobile contract (D-10, D-11)

- Layout: one `.container`, `h1` "Home Assistant / MQTT", one or two `panel panel-default` sections (Connection, Home Assistant device, Behaviour) using Bootstrap 3 `form-group`, `form-control`, `checkbox`. Every column class also carries a `col-xs-*` sibling (`col-xs-12 col-sm-6`) so fields stack on phones. Phase 10 phone rules already give `.form-control` `height: 44px` and 16px font; inputs need no new CSS. Buttons: `btn btn-primary` (Save) and `btn btn-default` (Test connection), full width on phones via existing pattern (`.btn` min-height 44px rule applies to `.sysimg-save`; add the new save/test button classes to that same phone rule or add a small block, see below). Use only the four allowed font sizes (14/16/18/24) and weights (400/600).
- CSS: `pellmon.css` may only receive additions in a clearly headed block; the Phase 10 tests (`test_css_block_spacing_scale`, allowed media queries, no `overflow-x: hidden`, only `pellmon.css` + Bootstrap linked) constrain what a new block may contain: padding/margin/gap values must be 0/4/8/16/24 px and only the three known media queries may be used. Prefer reusing existing classes and adding at most a few selectors inside the existing `@media (max-width: 767px)` block.
- JS: new `media/js/homeassistant.js` polls `homeassistant/status` every 5 s and drives the test button; use `.text()` and `textContent` only, never `.html()` (the repo has a source-scan test for the config editor's JS; follow the same rule). Page works without JS (form posts, server-rendered status).
- Save disabled until web login credentials exist (`auth_configured`), same as `Settings`.
- Daemon down: page renders with a warning and disabled save (same as `MSG_DAEMON_DOWN`).
- Browser tests: `tests/browser/stub_server.py` mounts the real `PellMonWeb`, whose `__init__` will now construct `HomeAssistant(lookup, dbus, ...)` against `FakeDbus`. Add to `FakeDbus` (`tests/browser/fake_dbus.py`): `mqtt_get_settings()` (return a full settings dict with `has_password: True`, long host/prefix strings to stress wrapping), `mqtt_set_settings(d)` (return `{"ok": True, "errors": {}}`), `mqtt_status()` (`state: connected`, reason, last_publish), `mqtt_test_start(d)` (True), `mqtt_test_result()` (`{"state": "ok", "message": "..."}`). Add `/homeassistant/` to `PAGES` in `tests/browser/test_mobile_overflow.py` and `tests/browser/test_browser_harness.py` so the 390/768 px no-sideways-scroll checks cover it; consider a tap-target check for the two buttons and the checkboxes (>= 44 px).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| paho 1.x callbacks `on_connect(c, u, flags, rc)` | paho 2.x `CallbackAPIVersion.VERSION2`, `reason_code` objects, `flags` on `on_disconnect` | paho 2.0.0, 2024-02-10 | Constructor requires the version argument |
| Per-entity discovery messages | Also supported: device-based discovery (`cmps`), `origin` mandatory there | HA docs current | Optional; keep per-entity to preserve unique IDs and topics |

**Deprecated/outdated:** paho 1.x API; Debian-packaged `python3-paho-mqtt` 1.x `[ASSUMED]`.

## Docker / CI impact (question 7)

- `requirements.txt`: add `paho-mqtt==2.1.0` under a `# Home Assistant plugin` comment (matches the existing `==` pinning style). `requirements-wsl.txt` needs no change unless it duplicates the list (check in planning).
- `Dockerfile`: the existing `pip3 install --break-system-packages -r requirements.txt` picks it up; add `ca-certificates` to the apt list (Pitfall 7). No build tools needed for paho (pycryptodome already builds with the installed gcc/python3-dev).
- CI (`.github/workflows/ci.yml`): `pip install -r requirements.txt` already runs for the test job; no workflow change. The multi-arch publish job (amd64, arm64, arm/v7 via QEMU) is unaffected for paho (pure wheel). Image size increase about 0.1-0.5 MB.
- Docs to update: `DEPLOY-PI.md` (new "Home Assistant / MQTT" section: enable plugin line for existing conf.d copies, takeover checklist, ACL advice, use IP not mDNS, data volume/backups now contain the MQTT password), `HARDWARE-BRINGUP.md` (supervised checklist: stop old publisher, run with `tools/burner_sim.py` first, verify a command with the real burner while watching the display), `DOCKER.md` (mention `extra_hosts` if the broker is the Docker host), `.env.example` (nothing), `CHANGELOG`/release notes (D-07 behaviour change). Existing users' `config/conf.d/enabled_plugins.conf` (an untracked local copy) will not have the new plugin line; the docs must say to add `p15 = HomeAssistant` (the shipped `src/conf.d/enabled_plugins.conf` gets the line enabled, since the plugin is inert until switched on in the GUI).
- `tools/pellmon_backup.py` already archives the settings DB (archive mode 0600, documented as containing secrets); add a sentence that the MQTT password is now in it.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | paho-mqtt is a legitimate package (slopcheck unavailable this session) | Package Legitimacy Audit | Supply-chain risk; mitigated by mandatory human-verify checkpoint |
| A2 | Debian bookworm `python3-paho-mqtt` is 1.6.1 | Alternatives | Low; we pip-pin 2.1.0 either way |
| A3 | Exact HA behaviour on two configs with the same unique_id (duplicate ignored) | Takeover mechanics | Medium; if HA replaces instead, takeover is easier; either way we reuse node id |
| A4 | HA keeps the entity registry entry after an empty-payload discovery removal | Commands disabled | Medium; if not, re-enable creates new entity ids and orphans history. Verify on real HA before finalising D-06 default |
| A5 | Rate-limit thresholds (2 s dedupe, 5 s per item, 10/min global, queue 20) | Command handling | Low; tunable constants |
| A6 | `min_power <= max_power` cross-check is desirable | Command handling | Low; can be dropped |
| A7 | Memory/thread cost is a few MB on a Pi 3A+ | Standard Stack | Low; measure in HARDWARE-BRINGUP |
| A8 | Docker bridge does not resolve mDNS; `host.docker.internal` absent on Linux | Pitfall 8 | Low; docs only |
| A9 | `ca-certificates` may be absent in the image (Recommends only) | Pitfall 7 | Medium; TLS verify would fail; fixed by adding the package regardless |
| A10 | EPL-2.0 OR BSD-3-Clause is acceptable next to the project's GPL | Standard Stack | Low; no linking concern raised, no legal review |
| A11 | Node id / uid prefix are derived from the identifier by a rule | Takeover mechanics | Low; we do not rely on it (separate settings) |

## Open Questions

1. **D-06 default: remove number/button entities when commands are off, or keep them inert?**
   - Known: literal D-06 allows removal; removal hides the setpoints from dashboards while commands are off (the default); keeping them silently ignores HA edits.
   - Unclear: user preference and A4.
   - Recommendation: implement removal (literal D-06), ask the user in plan review whether losing the setpoint display by default is acceptable; the alternative is a one-function change.
2. **Plugin enablement for existing installs.**
   - Recommendation: ship `p15 = HomeAssistant` enabled in `src/conf.d/enabled_plugins.conf`; plugin is inert until the GUI switch is on; the page explains how to add the line if the plugin is not loaded. (Auto-adding it in `config.__init__` was rejected as hidden magic.)
3. **Demo mode publishing (Claude's Discretion).** Recommendation: `demo` = availability `offline`, reason "demo mode, values simulated"; no setting in this phase.
4. **Unique-id prefix and node id for a fresh (non-takeover) install.** Recommendation: derive from the identifier (hash), user-overridable under Advanced.
5. **Real-broker verification.** No CI test uses a real broker; a manual UAT with mosquitto + `tools/burner_sim.py` + a real HA instance is required (list in HARDWARE-BRINGUP).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + pytest + pytest-socket + pytest-mock | tests | yes (dev venv) | pytest 9.x, per requirements-dev.txt | - |
| paho-mqtt | plugin + tests | yes locally (2.1.0 installed here); must be added to requirements.txt | 2.1.0 | fake client for most tests |
| Docker daemon | image verification (CA certs, size) | no (daemon not running in this session) | CLI 29.1.3 | verify in WSL/CI or on the Pi |
| MQTT broker (mosquitto) | manual UAT only | not checked | - | manual step, not CI |
| slopcheck | legitimacy gate | no | - | human-verify checkpoint |
| Playwright + Chromium | browser layout tests | CI and WSL per tests/README.md | 1.63.0 | skipped locally unless `PELLMON_BROWSER_TESTS=1` |

**Missing dependencies with no fallback:** none blocking.
**Missing dependencies with fallback:** Docker daemon (verify `ca-certificates` in CI or on the Pi), slopcheck (human-verify).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=9,<10 with pytest-mock, pytest-socket (`--disable-socket` in `pytest.ini`), Playwright 1.63.0 for `tests/browser` |
| Config file | `pytest.ini` (`pythonpath = src`, `addopts = --disable-socket`) |
| Quick run command | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv tests/Pellmonweb -k "homeassistant or mqtt" -x -q -m "not known_broken"` |
| Full suite command | `venv-py3/Scripts/python.exe -m pytest tests/ -m "not known_broken" -q` (CI: `pytest tests/ -v`; browser tests: `PYTHONPATH=src PELLMON_BROWSER_TESTS=1 pytest tests/browser -v -rs --allow-unix-socket` in WSL/CI) |

Windows note: the daemon module needs Linux `dbus/gi/pwd/grp`; use the existing `daemon_module` fixture (import stubs) for D-Bus method tests, and keep plugin logic in pure modules (`entities.py`, `settings.py`, `bridge.py`) that import on Windows.

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | Topics `<prefix>/<obj>/state|set`, `<prefix>/status`; object ids incl. the 4 renamed ones | unit | `pytest tests/Pellmonsrv/plugins/test_homeassistant_entities.py -x` | Wave 0 |
| D-02 | 23-entity table names/units/classes/ranges; ranges never wider than datamap | unit (cross-check vs `Scotteprotocol.datamap`) | same file | Wave 0 |
| D-03 | Identifier/name/node/uid prefix from settings, none hard-coded (source scan for the real identifier pattern is impossible; assert no default identifier constant) | unit | `pytest tests/Pellmonsrv/plugins/test_homeassistant_settings.py -x` | Wave 0 |
| D-04/D-17 | Discovery retained QoS1, state QoS0 not retained, status retained | unit (FakeMqttClient publish log) | `pytest tests/Pellmonsrv/plugins/test_homeassistant_bridge.py -x` | Wave 0 |
| D-05 | Only items present in db published; demo (6.99) omits chimney_draught; 4.00 omits diff_up | unit | entities test | Wave 0 |
| D-06 | Commands off: no number/button configs (empty payload), `/set` ignored+logged, not subscribed | unit | bridge test | Wave 0 |
| D-07 | Only Reset Alarm/Reset Ignition; ON/OFF configs cleared | unit | entities/bridge test | Wave 0 |
| D-08 | Readback published after success and after failure (ValueError/IOError) | unit | bridge test | Wave 0 |
| D-09 | Every command logged (topic, item, value, result); password never in caplog | unit | bridge + settings tests | Wave 0 |
| D-10 | Auth required, POST only, cross-origin rejected (403), headerless rejected | unit (mirror `test_settings_image.py`) | `pytest tests/Pellmonweb/test_homeassistant_page.py -x` | Wave 0 |
| D-11 | Validators accept/reject each field per table | unit | settings test | Wave 0 |
| D-12 | `GetSetting('mqtt.password')` empty; `GetMqttSettings` has no password, has `has_password`; rendered HTML never contains the secret; blank keeps, clear removes; `mqtt.*` not in `ALLOWED_SETTINGS` | unit (`daemon_module` fixture + Mako render) | `pytest tests/Pellmonsrv/test_homeassistant_dbus.py tests/Pellmonweb/test_homeassistant_page.py -x` | Wave 0 |
| D-13 | Reconfigure reconnects with new settings without restart; status JSON; test start/poll; test client id differs, never publishes | unit (fake client) | bridge test | Wave 0 |
| D-14 | `no_connection` -> `offline`, back to `connected` -> `online`; `demo` -> `offline`; item missing -> treated as unsupported | unit | bridge test | Wave 0 |
| D-15 | `will_set` args (topic, `offline`, retain); `online` after connect; atexit/shutdown publishes offline | unit | bridge test | Wave 0 |
| D-16 | Change event publishes once; identical payload deduped; refresh republishes all at interval | unit (injected clock) | bridge test | Wave 0 |
| Cross | Real paho client builds via default factory under `--disable-socket` (API drift guard) | unit | `pytest tests/Pellmonsrv/plugins/test_homeassistant_paho_factory.py -x` | Wave 0 |
| Cross | Plugin module imports without paho/dbus; descriptor discovered | unit | `pytest tests/test_plugin_imports.py tests/test_plugin_loader.py -q` | exists, auto-covers |
| Cross | `/homeassistant/` has no horizontal overflow at 390/768 px; tap targets | browser | `PELLMON_BROWSER_TESTS=1 pytest tests/browser -k homeassistant --allow-unix-socket` | extend existing |
| Cross | End-to-end with real broker + `tools/burner_sim.py` + real HA | manual UAT | documented in HARDWARE-BRINGUP | manual-only (needs network, broker, HA) |

### Sampling Rate
- **Per task commit:** the quick command above.
- **Per wave merge:** full suite command.
- **Phase gate:** full suite green plus browser tests in CI before `/gsd:verify-work`; manual UAT list signed off by the user (real HA takeover, real burner command).

### Wave 0 Gaps
- [ ] `tests/Pellmonsrv/plugins/fake_mqtt.py` - `FakeMqttClient` (records `publish/subscribe/will_set/username_pw_set/tls_*`, helpers `fire_connect(reason=0)`, `fire_disconnect`, `fire_message(topic, payload, retain=False)`) plus `FakeDb` fixture (dict of `Getsetitem`-like items with `.min/.max`, `set_value`/`get_text`, a `values` snapshot, `burner_connection` Plainitem).
- [ ] `tests/Pellmonsrv/plugins/test_homeassistant_{entities,settings,bridge,paho_factory}.py`
- [ ] `tests/Pellmonsrv/test_homeassistant_dbus.py` (uses `daemon_module`)
- [ ] `tests/Pellmonweb/test_homeassistant_page.py`
- [ ] Extend `tests/browser/fake_dbus.py`, `test_mobile_overflow.py`, `test_browser_harness.py`
- [ ] Framework install: none; `paho-mqtt==2.1.0` goes into `requirements.txt` (CI installs it; local dev venvs need `pip install -r requirements.txt`).
- [ ] Injectable `clock` and `sleep` in the bridge so refresh/settle/rate-limit tests need no real time.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (page login, broker credentials) | Existing PBKDF2 login (`@require()`); broker password stored 0600, write-only from the browser |
| V3 Session Management | yes (existing) | Existing CherryPy sessions (httponly, samesite Lax) |
| V4 Access Control | yes | Page and status/test endpoints behind `@require()`; `/set` gated by `commands_enabled`; fixed item whitelist |
| V5 Input Validation | yes | Central validators (table above); MQTT payload validation; explicit topics, no wildcard subscriptions |
| V6 Cryptography | yes (TLS) | paho `tls_set` with `CERT_REQUIRED` default and hostname check; no custom crypto |
| V7 Error handling and logging | yes | No secrets in logs; log commands without payloads of other topics |
| V8 Data protection | yes | Password only in `pellmon_settings.db` (0600, data volume); backups contain it (documented) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| CSRF on settings save/test | Tampering | `check_same_origin()` on every POST (save, test); SameSite=Lax cookie |
| Password disclosure via API | Information disclosure | Not in `ALLOWED_SETTINGS`; dedicated methods never return it; `has_password` boolean only; no `value=` in the HTML input; regression tests |
| Password in logs | Information disclosure | Never format settings dicts or D-Bus args into logs; caplog test after a full save/connect/test flow |
| Unauthenticated command injection via broker | Elevation of privilege | Commands off by default; whitelist of 10 numbers + 2 buttons; range/integer validation; rate limit; retained messages ignored; recommend broker ACLs (dedicated user, write only `scotte/#`) |
| MITM on broker link | Spoofing/Tampering | TLS verify default on; "verify certificate" off is an explicit opt-out with a warning |
| Topic injection through prefix | Tampering | Prefix validator forbids `+`, `#`, `$`, leading/trailing `/` |
| Test-connection SSRF (host/port scan from PellMon) | Information disclosure | Endpoint is auth + same-origin protected, one test at a time, short timeout, result reduced to ok/error text; note residual risk for an authenticated admin |
| Flooding / resource exhaustion | Denial of service | Bounded command queue (20), payload cap 32 B, `max_queued_messages_set(200)`, connected-only publishing |
| Replay of stale commands | Tampering | Ignore `retain=True` on `/set` |

## Corrections/Conflicts with CONTEXT

- **C1 (D-01/D-05): four topic segments differ from PellMon item names.** The existing device uses object ids `power_percent`, `power_kw`, `boiler_diff_down`, `boiler_diff_up`, while the PellMon items are `power`, `power_kW`, `boiler_temp_diff_down`, `boiler_temp_diff_up`. Implementing "`<prefix>/<item>/state`" literally would break those four entities (and their unique_ids, which end in the object id). Resolution: keep an explicit object-id column (table above); D-05's item mapping is unchanged.
- **C2 (D-03/D-11): takeover needs three identifiers, not one.** Device identifier, discovery `node_id` and unique-id prefix are three different strings in the existing device. Only the device identifier and name are in D-11's field list. Resolution: add node id and unique-id prefix as advanced settings with derived defaults (see Takeover mechanics).
- **C3 (D-06): "not controllable" has a concrete cost.** HA numbers cannot be read-only, and changing component type breaks unique_id continuity. Only "remove from discovery" is workable; it hides setpoints while commands are off. Flagged as Open Question 1.
- **C4 (D-02/D-07): entity count.** 23 in the old device, 21 published (9 sensors, 10 numbers, 2 buttons). Consistent with D-07; noted so the plan/tests assert 21, and that Burner ON/OFF configs are cleared.
- **C5 (D-15): last-will is not enough for a graceful stop.** `Database.terminate()`/plugin `deactivate()` are never called (no caller in `src/Pellmonsrv`), and a clean `disconnect()` suppresses the will. The plugin must publish `offline` itself at exit (atexit), keeping the LWT for crashes and network loss.
- **C6 (D-17): non-retained state loses values on HA restart.** Add a subscription to HA's birth message (`<discovery_prefix>/status`) to republish discovery and states; this is an addition, not a contradiction.
- **C7 (D-13): "Test connection" cannot be one blocking D-Bus call** without freezing the daemon's D-Bus thread; implemented as start + poll (same user-visible behaviour).
- **C8 (Phase 8 D-01 vs Phase 6 D-10):** Phase 8 said Phase 6 would add a section to the Settings page; Phase 6 D-10 (later, authoritative) asks for a dedicated page. Follow Phase 6: new controller and menu entry.

## Files the phase implies (question 10)

New: `src/Pellmonsrv/plugins/homeassistant.pellmon-plugin`; `src/Pellmonsrv/plugins/homeassistant/{__init__,entities,settings,bridge}.py` + `Makefile.am`; `src/Pellmonweb/homeassistant.py`; `src/Pellmonweb/html/homeassistant.html`; `src/Pellmonweb/media/js/homeassistant.js`; the tests listed under Wave 0.
Modified: `src/Pellmonsrv/pellmonsrv.py` (listener hook on `Database`, five D-Bus methods, `_ha_plugin()` lookup; `ALLOWED_SETTINGS` untouched); `src/Pellmonweb/pellmonweb.py` (five `Dbus_handler.mqtt_*` wrappers, controller construction); `src/Pellmonweb/html/layout.html` (menu entry); `src/Pellmonweb/media/css/pellmon.css` (minimal, test-constrained); `src/conf.d/enabled_plugins.conf`; `src/Pellmonsrv/plugins/Makefile.am` and `configure.ac` (legacy autotools lists); `requirements.txt`; `Dockerfile` (`ca-certificates`); `tests/browser/{fake_dbus,test_mobile_overflow,test_browser_harness}.py`; docs `DEPLOY-PI.md`, `HARDWARE-BRINGUP.md`, `DOCKER.md`, backup note in `tools/README` or DEPLOY-PI.

Main risks: (1) concurrency around the Database thread hook (must never block or raise); (2) HA takeover behaviour that only a real HA instance can confirm (A3/A4); (3) real-hardware command behaviour (mocked only, per project constraint); (4) not leaking the password through any of the ~6 places it could pass (D-Bus, logs, HTML, backup, tracebacks); (5) CSS tests constraining new styling; (6) `.dockerignore` excludes `config/` and `*.md`, so docs and config are not in the image (no impact, but the plugin line must come via the mounted `config/conf.d`).

## Sources

### Primary (HIGH confidence)
- Local code: `src/Pellmonsrv/{pellmonsrv,database,plugin_categories}.py`, `plugins/scottecom/scottecom.py`, `src/Scotteprotocol/{datamap,protocol}.py`, `src/Pellmonweb/{settings,security,pellmonweb,auth}.py`, `layout.html`, `settings.html`, `pellmon.css`, tests and CI files (read this session)
- paho-mqtt 2.1.0 installed package source (`client.py`: signatures of `Client.__init__`, `will_set`, `tls_set`, `tls_insecure_set`, `connect_async`, `reconnect_delay_set`, `loop_start`, `publish`, `max_queued_messages_set`) and an executed pytest-socket experiment (construct OK, `loop_start` blocked)
- PyPI JSON https://pypi.org/pypi/paho-mqtt/json and `pip index versions paho-mqtt` (2026-09-25)
- Home Assistant MQTT integration https://www.home-assistant.io/integrations/mqtt/ ; number https://www.home-assistant.io/integrations/number.mqtt/ ; button https://www.home-assistant.io/integrations/button.mqtt/
- paho migration notes https://raw.githubusercontent.com/eclipse-paho/paho.mqtt.python/master/docs/migrations.rst ; releases https://github.com/eclipse-paho/paho.mqtt.python/releases
- Debian libcurl4 (bookworm) https://packages.debian.org/bookworm/libcurl4 (ca-certificates = Recommends)
- Home Assistant MQTT diagnostics export (structure only; no identifiers recorded)

### Secondary (MEDIUM confidence)
- Web search results for paho release history (agree with PyPI)

### Tertiary (LOW confidence)
- Items tagged `[ASSUMED]` in the Assumptions Log (HA duplicate unique_id and registry-after-removal behaviour, Docker DNS behaviour, memory estimate, rate-limit numbers)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for version/wheel/API (verified locally and on PyPI); package legitimacy `[ASSUMED]` (slopcheck unavailable)
- Architecture: HIGH (built from read code; threading/queue design is standard); MEDIUM for real-HA takeover behaviour
- Pitfalls: HIGH for paho/pytest-socket/D-Bus/Keyval findings (executed or read); MEDIUM for Docker CA and HA registry points

**Research date:** 2026-09-25
**Valid until:** 2026-10-25 (paho and HA docs are slow-moving; re-check HA MQTT docs if HA majors change discovery/naming rules)
