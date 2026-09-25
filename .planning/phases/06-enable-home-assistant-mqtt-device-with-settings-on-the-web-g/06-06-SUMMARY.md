---
phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
plan: 06
subsystem: web-controller
tags: [cherrypy, mqtt, home-assistant, dbus, csrf]
requires: ["06-02", "06-04"]
provides:
  - HomeAssistant controller (index, save, test, status) and status_view()
  - Dbus_handler.mqtt_get_settings/mqtt_set_settings/mqtt_status/mqtt_test_start/mqtt_test_result
  - /homeassistant/ mount
affects: [06-08 JS, 06-09]
key-files:
  created:
    - src/Pellmonweb/homeassistant.py
    - tests/Pellmonweb/test_homeassistant_page.py
  modified:
    - src/Pellmonweb/pellmonweb.py
    - src/Pellmonweb/__init__.py
decisions:
  - "Test JSON states: ok, error, invalid, rejected, daemon_down, auth_disabled; level is success only for ok, danger otherwise"
  - "Payload tls_verify_field = tls_verify_explicit(raw); web validate() runs with current=None so a non-explicit form yields tls_verify True and the daemon keeps its stored value"
  - "saved=off takes precedence over saved=commands; commands only when allow_commands was off in the daemon's previous settings"
  - "clear_password is sent only when ticked and no new password was typed"
requirements-completed: [D-06, D-10, D-12, D-13]
completed: 2026-09-25
---

# Phase 6 Plan 06: Home Assistant web controller Summary

Login- and same-origin-protected `/homeassistant/` controller with write-only password handling, the exact UI-SPEC status copy, a polled (10 s cap) Test connection flow returning JSON or a re-render, and five locked D-Bus proxies in `Dbus_handler`.

## Commits
- 3a215eb: controller, status_view, controller tests
- ba7abfa: Dbus_handler proxies, mount, package export, AST/render tests

## Deviations from Plan
**1. [Rule 3 - Blocking] Worktree base was stale.** The worktree branch was created from an older commit lacking wave 1 (no `plugins/homeassistant`, no template). It was fast-forwarded (`git merge --ff-only fac7537`, the merged wave 1 tip) before starting; no code was changed by this.

**2. [Rule 3 - Blocking] Import of HomeAssistant lives in `src/Pellmonweb/__init__.py`.** `pellmonweb.py` obtains all controllers via `from Pellmonweb import *` (the Settings import is there too), so the "import next to the Settings import" was done in `__init__.py` (`from .homeassistant import HomeAssistant`), not in `pellmonweb.py`. The AST test asserts this arrangement.

Consequence to note for packaging (06-07/06-09): `Pellmonweb` now imports `Pellmonsrv.plugins.homeassistant.settings`, so that module must be installed alongside `Pellmonweb` (the web container already ships the whole `Pellmonsrv` package).

## Test results
- `tests/Pellmonweb/test_homeassistant_page.py`: 52 tests pass (auth `_cp_config`, GET/cross-origin/header-less rejections, all TLS-verify marker cases for save and test, payload types, redirect variants, write-only password via caplog and ctx sentinel checks, every status copy, test polling with injected clock incl. timeout, JSON states, AST proxy shape, real Mako render with `placeholder="set"`).
- `tests/Pellmonweb`: 247 passed, 8 skipped (test_mobile_stub_guard included; `tests/browser/stub_server.py` untouched).
- Full suite: 578 passed, 83 skipped, 3 failed = the known baseline failures (test_backup_script conf_d override, test_plugin_loader consumption and silolevel).
- The `dbus`/`gi` functional proxy test is skipped on Windows (importorskip); the AST test covers shape.

## Known Stubs
None. `tests/browser/stub_server.py` FakeDbus does not yet have `mqtt_*` methods; 06-08 extends it.

## Threat Flags
None beyond the plan's threat model (T-06-24..T-06-29 mitigated as tested).

## Self-Check: PASSED
Files and commits 3a215eb, ba7abfa exist.
