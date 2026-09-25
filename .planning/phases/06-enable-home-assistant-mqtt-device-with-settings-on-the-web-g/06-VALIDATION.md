---
phase: 06
slug: enable-home-assistant-mqtt-device-with-settings-on-the-web-g
status: planned
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-25
---

# Phase 06 - Validation Strategy

> Per-phase validation contract. Source: 06-RESEARCH.md "Validation Architecture". Requirement IDs are the local D-01..D-19 decisions in 06-CONTEXT.md.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9,<10 with pytest-mock, pytest-socket (`--disable-socket` in `pytest.ini`); Playwright 1.63.0 for `tests/browser` |
| **Config file** | `pytest.ini` (`pythonpath = src`, `addopts = --disable-socket`), unchanged |
| **Quick run command** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv tests/Pellmonweb -k "homeassistant or mqtt" -x -q` |
| **Full suite command** | `venv-py3/Scripts/python.exe -m pytest tests/ -q` (CI: `pytest tests/ -v`) |
| **Browser command (WSL/CI)** | `PELLMON_BROWSER_TESTS=1 PYTHONPATH=src pytest tests/browser -v -rs --allow-unix-socket` |
| **Estimated runtime** | quick ~5 s; full ~10 s; browser ~1 min |

Windows note: the daemon module needs Linux `dbus/gi/pwd/grp`; use the existing `daemon_module` fixture for D-Bus method tests and keep plugin logic in pure modules (`entities.py`, `settings.py`, `bridge.py`) that import on Windows.

## Sampling Rate

- **After every task commit:** the quick command.
- **After every plan wave:** the full suite, plus the browser command for any wave touching templates/CSS/JS.
- **Before verify-work:** full suite green, browser tests green in CI, manual UAT list signed off by the user.
- **Max feedback latency:** ~10 s (unit), ~1-2 min (browser).

## Per-Requirement Verification Map

| Req | Behavior | Test type | File | Status |
|-----|----------|-----------|------|--------|
| D-01 | Topics `<prefix>/<obj>/state|set`, `<prefix>/status`; the 4 renamed object ids | unit | tests/Pellmonsrv/plugins/test_homeassistant_entities.py | Wave 0 |
| D-02 | 23-entity table (names/units/classes/ranges), ranges never wider than the datamap | unit (cross-check vs `Scotteprotocol.datamap`) | same | Wave 0 |
| D-03 | Identifier, name, node id, unique-id prefix come from settings; no hard-coded identifier constant | unit | test_homeassistant_settings.py | Wave 0 |
| D-04/D-17 | Discovery retained QoS1; state not retained; status retained | unit (FakeMqttClient publish log) | test_homeassistant_bridge.py | Wave 0 |
| D-05 | Only items present in the db are published; demo/older chips omit missing items | unit | entities + bridge tests | Wave 0 |
| D-06/D-18 | Commands off: number and button configs removed (empty retained payload); the explicit per-entity `/set` topics stay subscribed and every message on them is ignored and logged (no db write); back on: configs published again | unit | bridge test | Wave 0 |
| D-07 | Only Reset Alarm and Reset Ignition; Burner ON/OFF configs cleared | unit | entities + bridge tests | Wave 0 |
| D-08 | Readback republished after success and after failure (ValueError/IOError) | unit | bridge test | Wave 0 |
| D-09 | Every command logged (topic, item, value, result); password never in caplog | unit | bridge + settings tests | Wave 0 |
| D-10 | Page: login required, POST only, cross-origin rejected (403), headerless rejected | unit (mirror `test_settings_image.py`) | tests/Pellmonweb/test_homeassistant_page.py | Wave 0 |
| D-11 | Validators accept/reject each field per the research table (bracketed IPv6 hosts rejected) | unit | settings test | Wave 0 |
| D-11/D-13 | `tls_verify` is only taken from the form when TLS is on and the `tls_verify_field` marker was submitted; TLS-off saves and TLS enabled from a TLS-off page keep the stored value (default True) | unit | settings, page and plugin tests | Wave 0 |
| D-12 | `GetSetting('mqtt.password')` empty; `GetMqttSettings` has no password, has `has_password`; rendered HTML never contains the secret; blank keeps, clear removes; `mqtt.*` not in `ALLOWED_SETTINGS` | unit (`daemon_module` + Mako render with a secret sentinel) | tests/Pellmonsrv/test_homeassistant_dbus.py + page test | Wave 0 |
| D-13 | Reconfigure reconnects without restart; status JSON; test start/poll; test client id differs and never publishes | unit (fake client) | bridge test | Wave 0 |
| D-14 | `no_connection` -> offline, `connected` -> online, `demo` -> offline | unit | bridge test | Wave 0 |
| D-15 | `will_set` args; `online` after connect; offline on clean shutdown (atexit) | unit | bridge test | Wave 0 |
| D-16 | Change event publishes once, identical payload deduped, periodic refresh (injected clock) | unit | bridge test | Wave 0 |
| D-19 | HA birth message triggers a republish; Test connection start-and-poll; daemon test ends within 8 s total (< 10 s web cap < 12 s browser abort) | unit | bridge, tester and page tests | Wave 0 |
| UI | `/homeassistant/` follows the approved 06-UI-SPEC: structural checks, no overflow at 390/768, 44px targets | structural + browser | tests/Pellmonweb/test_homeassistant_ui.py; tests/browser (extend fake_dbus.py, overflow page list) | Wave 0 |
| Cross | Real paho client builds via the default factory under `--disable-socket` (API drift guard) | unit | test_homeassistant_paho_factory.py | Wave 0 |
| Cross | Plugin module imports without paho/dbus; descriptor discovered | unit | tests/test_plugin_imports.py, test_plugin_loader.py | exists |
| Cross | End-to-end with a real broker, `tools/burner_sim.py` and real Home Assistant | manual UAT | HARDWARE-BRINGUP.md | manual-only |

## Wave 0 Requirements

- [ ] `tests/Pellmonsrv/plugins/fake_mqtt.py`: `FakeMqttClient` (records publish/subscribe/will_set/username_pw_set/tls_*, helpers to fire connect/disconnect/message) plus a `FakeDb` fixture.
- [ ] `tests/Pellmonsrv/plugins/test_homeassistant_{entities,settings,bridge,tester,paho_factory}.py`.
- [ ] `tests/Pellmonsrv/test_homeassistant_dbus.py` (uses `daemon_module`).
- [ ] `tests/Pellmonweb/test_homeassistant_page.py` and `test_homeassistant_ui.py`.
- [ ] Extend `tests/browser/fake_dbus.py`, `test_mobile_overflow.py`, `test_browser_harness.py`.
- [ ] Injectable `clock` and `sleep` in the bridge so refresh/settle/rate-limit tests need no real time.
- [ ] `paho-mqtt==2.1.0` in `requirements.txt`, after the human package-legitimacy check.

## Manual-Only Verifications

| Behavior | Requirement | Why manual | Instructions |
|----------|-------------|------------|--------------|
| Takeover of the existing Home Assistant device (same identifiers, entities and history continue) | D-03 | Needs the real HA instance and broker | Switch the old publisher off, enter the device identifier/name in the page, confirm entities and history continue |
| Number/button removal and return when commands are toggled | D-18 | HA registry behaviour is unverified | Toggle "Allow commands", watch the entities disappear/reappear; note whether history survives |
| A real command reaches the burner and reads back | D-08 | Needs real hardware | Change a setpoint from HA, confirm the burner value and the snap-back on failure |
| Availability follows the burner connection | D-14/D-15 | Real broker/HA | Unplug the burner serial, entities go unavailable; kill PellMon, last-will marks offline |

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
