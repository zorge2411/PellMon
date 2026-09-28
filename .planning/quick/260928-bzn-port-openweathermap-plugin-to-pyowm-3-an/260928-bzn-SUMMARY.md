---
phase: quick-260928-bzn
plan: 01
subsystem: plugins
tags: [pyowm, openweathermap, dbus, cherrypy, mako, keyval-storage]

requires:
  - phase: 06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g
    provides: "The always-loaded-plugin + keyval-settings + D-Bus JSON-method + CherryPy settings-page pattern (HomeAssistant/MQTT), mirrored here for OpenWeatherMap."
provides:
  - "Openweathermap plugin ported to the pyowm 3.5.0 weather_manager()/weather_at_place() API"
  - "settings.py keyval-backed validate/load/save/public_view for the plugin's enable/unit/apikey/location settings"
  - "get_settings_dict/apply_settings/status_dict D-Bus contract on the plugin, mirroring HomeAssistant"
  - "Openweathermap added to ALWAYS_LOADED_PLUGINS; GetOwmSettings/SetOwmSettings/GetOwmStatus D-Bus methods"
  - "/weather/ CherryPy page (src/Pellmonweb/weather.py + html/weather.html) with enable/apikey/location/unit form and status line"
affects: [web-settings-pages, openweathermap-plugin, dbus-contract]

tech-stack:
  added: []
  patterns:
    - "Always-loaded, idle-until-enabled plugin pattern (ALWAYS_LOADED_PLUGINS, _plugin_by_name) reused for a second plugin"
    - "keyval-backed settings module (validate/load/save/public_view) per plugin, secret stored under a separate key from the rest of the config"
    - "JSON-over-D-Bus settings methods (GetXSettings/SetXSettings/GetXStatus) with defensive secret-pop and type(e).__name__-only error logging"
    - "CherryPy settings-page controller (index/save, auth+CSRF guard order: method, origin, local validation, credentials, D-Bus) reused for a second page"

key-files:
  created:
    - src/Pellmonsrv/plugins/openweathermap/settings.py
    - src/Pellmonweb/weather.py
    - src/Pellmonweb/html/weather.html
    - tests/Pellmonsrv/plugins/test_openweathermap_plugin.py
    - tests/Pellmonsrv/test_openweathermap_dbus.py
    - tests/Pellmonweb/test_weather_page.py
  modified:
    - src/Pellmonsrv/plugins/openweathermap/__init__.py
    - src/Pellmonsrv/plugins/openweathermap/Makefile.am
    - src/Pellmonsrv/pellmonsrv.py
    - src/conf.d/enabled_plugins.conf
    - src/conf.d/plugins/openweathermap.conf
    - src/Pellmonweb/pellmonweb.py
    - src/Pellmonweb/__init__.py
    - src/Pellmonweb/html/layout.html
    - tests/test_config_interpolation.py

key-decisions:
  - "feelslike is always computed in Celsius from the formula, then converted to Fahrenheit (c*9/5+32) when unit=fahrenheit, since the formula only holds in Celsius"
  - "pyowm exceptions are mapped to a small stable set of reason strings and only type(e).__name__ is logged, never str(e), because pyowm request errors can embed the API key in the request URL (appid=<key>)"
  - "location stays in the existing 'location' Storeditem (not owm.config) so the dashboard R/W item and its persisted value keep working unchanged"
  - "apikey is stored under a separate keyval key (owm.apikey) from enabled/unit (owm.config), mirroring HA's mqtt.password/mqtt.config split"
  - "web-side payload to SetOwmSettings only includes 'apikey' when a new key was typed, and 'clear_apikey' only when that checkbox was ticked -- never both, never an empty apikey key"

requirements-completed: [QUICK-260928-bzn]

duration: ~45min
completed: 2026-09-28
---

# Quick Task 260928-bzn: Port OpenWeatherMap plugin to pyowm 3, add a Weather settings page

**Openweathermap plugin rewritten against pyowm 3.5.0's weather_manager()/weather_at_place() API with a keyval-backed settings module, always-loaded D-Bus contract (GetOwmSettings/SetOwmSettings/GetOwmStatus), and a new /weather/ CherryPy+Mako page mirroring the Home Assistant settings page.**

## Performance

- **Duration:** ~45 min
- **Tasks:** 3
- **Files modified:** 14 (6 created, 9 modified, including test files)

## Accomplishments

- Openweathermap plugin no longer crashes under pyowm 3: replaced `weather_at_place(...encode('utf-8'))` / `get_weather()` / `get_temperature()` / `get_wind()` / `get_humidity()` with the pyowm 3 `weather_manager().weather_at_place(str)` / `.weather` / `.temperature(unit)` / `.wind()` / `.humidity` surface, tolerating a missing wind `deg` and never raising from `activate()` (placeholder key, real key, or pyowm missing entirely).
- `activate()` never raises. It is now always loaded (like HomeAssistant) and stays idle until enabled, either via the web page or via a legacy non-placeholder conf apikey (migration path).
- A user can enable/disable the plugin and set the API key, location and unit on `/weather/` with no conf-file edit and no restart; the API key is never sent back to the browser, returned over D-Bus, or logged.

## Task Commits

Each task was committed atomically:

1. **Task 1: Port the plugin to pyowm 3 and add a keyval-backed settings module** - `583323e` (feat)
2. **Task 2: Always load the plugin and add the D-Bus methods GetOwmSettings / SetOwmSettings / GetOwmStatus** - `bacbf6d` (feat)
3. **Task 3: Weather settings page (controller, template, nav, D-Bus client)** - `c2e0417` (feat)

_All three tasks were TDD (`tdd="true"`); tests were written alongside the implementation in the same commit per task, matching the existing HomeAssistant plugin's commit granularity in this codebase._

## Files Created/Modified

- `src/Pellmonsrv/plugins/openweathermap/settings.py` - KEY_CONFIG/KEY_APIKEY, DEFAULTS, validate/load/load_apikey/save/public_view/is_placeholder
- `src/Pellmonsrv/plugins/openweathermap/__init__.py` - pyowm 3 port: `fetch_once()`, `reconfigure()`, `_reason_for()` exception mapping, D-Bus contract (`get_settings_dict`/`apply_settings`/`status_dict`)
- `src/Pellmonsrv/plugins/openweathermap/Makefile.am` - added settings.py to `openweathermap_PYTHON`
- `src/Pellmonsrv/pellmonsrv.py` - `ALWAYS_LOADED_PLUGINS = ('HomeAssistant', 'Openweathermap')`, `_plugin_by_name()`/`_owm_plugin()`, `GetOwmSettings`/`SetOwmSettings`/`GetOwmStatus`
- `src/conf.d/enabled_plugins.conf` - comment update for p13 (kept commented, now optional/legacy)
- `src/conf.d/plugins/openweathermap.conf` - comment update: apikey is now normally set on the Weather page
- `src/Pellmonweb/weather.py` - `Weather` CherryPy controller (index/save), `status_view()`
- `src/Pellmonweb/html/weather.html` - settings form + status line, reusing the `mqtt-*` CSS classes
- `src/Pellmonweb/html/layout.html` - Weather nav entry after Home Assistant
- `src/Pellmonweb/pellmonweb.py` - `Dbus_handler.owm_get_settings/owm_set_settings/owm_status`, `self.weather = Weather(...)` mount
- `src/Pellmonweb/__init__.py` - `from .weather import Weather`
- `tests/Pellmonsrv/plugins/test_openweathermap_plugin.py` - fetch_once behavior, exception mapping, activate edge cases, apply_settings validation
- `tests/Pellmonsrv/test_openweathermap_dbus.py` - GetOwmSettings/SetOwmSettings/GetOwmStatus delegation, absent-plugin, exception-safety
- `tests/Pellmonweb/test_weather_page.py` - auth/CSRF guards, payload shape, status_view mapping, real-template render
- `tests/test_config_interpolation.py` - updated the `ALWAYS_LOADED_PLUGINS` literal assertion; added Openweathermap-always-loaded and uncommented-still-once tests

## Decisions Made

See `key-decisions` in the frontmatter above.

## Deviations from Plan

None - plan executed exactly as written. The `<action>` blocks in the plan were followed closely (mirroring `homeassistant/settings.py` and `homeassistant.py`/`homeassistant.html`); the only judgment calls were the `_view()` split=True/False choice per status string and the exact payload key-set built by `Weather._payload()`, both resolved by matching the literal example payload/status text given in the plan's `<behavior>` blocks.

## Issues Encountered

None. `pyowm==3.5.0` and its `pyowm.commons.exceptions` classes were already installed in `venv-py3`, confirming the interfaces documented in the plan.

## User Setup Required

None - no external service configuration required. (Users who want live weather data still need to enter their own OpenWeatherMap API key on the new `/weather/` page; no code/deploy change is needed for that.)

## Next Phase Readiness

- The plugin and page are fully wired end-to-end (daemon plugin -> D-Bus -> web page), matching the Home Assistant pattern exactly, so future "always-loaded plugin with a settings page" work can reuse the same three-file shape (plugin `settings.py`, plugin `__init__.py` D-Bus contract, `pellmonsrv.py` D-Bus methods, web controller + template).
- Real-hardware/live-network verification of the actual openweathermap.org API was out of scope per this codebase's testing strategy (mocked/unit-level verification only, no physical hardware or live network calls in tests).

## Test Results

`venv-py3/Scripts/python.exe -m pytest tests/ -m "not known_broken" -q` (from the main checkout's interpreter, run against the worktree): **762 passed, 116 skipped, 3 failed** (pre-existing, unrelated to this task -- see below), 0 regressions.

Pre-existing failures (confirmed present on the baseline commit `ea3c6c5` before any change in this plan, and unchanged after):
- `tests/test_backup_script.py::test_conf_d_overrides_pellmon_conf`
- `tests/test_plugin_loader.py::test_every_available_plugin_loads[consumption]`
- `tests/test_plugin_loader.py::test_every_available_plugin_loads[silolevel]`

Plan-specified grep verifications:
- `grep -rn "setDaemon\|weather_at_place(self.db\|get_weather" src/Pellmonsrv/plugins/openweathermap/` -> no matches (pass)
- `grep -n "ALWAYS_LOADED_PLUGINS = ('HomeAssistant', 'Openweathermap')" src/Pellmonsrv/pellmonsrv.py` -> matches (pass)

## Self-Check: PASSED

All 14 files listed in the plan's `files_modified` frontmatter exist on disk. All 3 task commits (`583323e`, `bacbf6d`, `c2e0417`) are present in `git log`.

---
*Phase: quick-260928-bzn*
*Completed: 2026-09-28*
