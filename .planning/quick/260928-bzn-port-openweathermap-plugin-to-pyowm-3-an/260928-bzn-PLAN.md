---
phase: quick-260928-bzn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/Pellmonsrv/plugins/openweathermap/__init__.py
  - src/Pellmonsrv/plugins/openweathermap/settings.py
  - src/Pellmonsrv/plugins/openweathermap/Makefile.am
  - tests/Pellmonsrv/plugins/test_openweathermap_plugin.py
  - src/Pellmonsrv/pellmonsrv.py
  - src/conf.d/enabled_plugins.conf
  - src/conf.d/plugins/openweathermap.conf
  - tests/test_config_interpolation.py
  - tests/Pellmonsrv/test_openweathermap_dbus.py
  - src/Pellmonweb/weather.py
  - src/Pellmonweb/html/weather.html
  - src/Pellmonweb/html/layout.html
  - src/Pellmonweb/pellmonweb.py
  - tests/Pellmonweb/test_weather_page.py
autonomous: true
requirements: [QUICK-260928-bzn]

must_haves:
  truths:
    - "Under pyowm 3.5.0 the Openweathermap plugin fills temperature, wind_speed, wind_direction, humidity and feelslike from weather_manager().weather_at_place(<str>).weather"
    - "A missing wind 'deg' does not fail the update: the other values are still set and wind_direction keeps its previous value"
    - "The plugin is always loaded (like HomeAssistant). It stays idle until it is enabled on the web page, and it never raises on activate, even with the placeholder key or without pyowm"
    - "On the /weather/ page a signed-in user can enable or disable the plugin and set the API key, location and unit. Changes apply to the running daemon without a restart and persist in the SQLite keyval DB (/var/lib/pellmon, Docker volume)"
    - "The stored API key is never sent back to the browser, returned over D-Bus or logged. The page only shows that a key is stored"
    - "The page shows the status: off / no key / waiting / last update time / last error reason / plugin not active / server not running"
  artifacts:
    - path: "src/Pellmonsrv/plugins/openweathermap/settings.py"
      provides: "DEFAULTS, validate, load, load_apikey, save, public_view (mirrors homeassistant/settings.py)"
    - path: "src/Pellmonsrv/plugins/openweathermap/__init__.py"
      provides: "pyowm 3 port + D-Bus contract get_settings_dict/apply_settings/status_dict + fetch_once"
    - path: "src/Pellmonweb/weather.py"
      provides: "Weather CherryPy controller: index, save"
    - path: "src/Pellmonweb/html/weather.html"
      provides: "Settings form + status line"
  key_links:
    - from: "src/Pellmonweb/weather.py"
      to: "Dbus_handler.owm_get_settings/owm_set_settings/owm_status"
      via: "self.dbus"
      pattern: "self\\.dbus\\.owm_(get_settings|set_settings|status)"
    - from: "src/Pellmonsrv/pellmonsrv.py"
      to: "Openweathermap plugin_object"
      via: "_owm_plugin() lookup in conf.database.protocols"
      pattern: "GetOwmSettings|SetOwmSettings|GetOwmStatus"
    - from: "src/Pellmonsrv/pellmonsrv.py"
      to: "ALWAYS_LOADED_PLUGINS"
      via: "tuple constant"
      pattern: "ALWAYS_LOADED_PLUGINS = \\('HomeAssistant', 'Openweathermap'\\)"
---

<objective>
Port the Openweathermap plugin to the pyowm 3 API (pyowm==3.5.0 is pinned in requirements.txt; the module is pyowm.weatherapi30). Add a "Weather" settings page built the same way as the Phase 06 Home Assistant page: the API key, location, unit and an enable switch are stored in the SQLite keyval store, applied live over JSON D-Bus methods, and shown on a CherryPy + Mako page with the same auth/CSRF guards.

Purpose: right now the plugin crashes under pyowm 3 (`weather_at_place` on OWM, `get_weather()`, `.encode()`), and it raises on activate when the key is a placeholder. Users also have to edit two conf files to turn it on.
Output: a working plugin, a /weather/ page, and three new test files.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@tests/README.md

How the HA pattern works (verified in code). Mirror it; do NOT re-explore:
- Daemon: `ALWAYS_LOADED_PLUGINS = ('HomeAssistant',)` (src/Pellmonsrv/pellmonsrv.py ~line 744) appends the plugin to `conf.enabled_plugins` even when it is missing from enabled_plugins.conf (see the loop at ~line 837). The plugin idles until its stored `enabled` flag is true.
- Settings live in `Keyval_storage.keyval_storage` (SQLite `conf.keyval_db` under /var/lib/pellmon, a Docker bind-mounted volume, so it survives container restarts) as JSON under `mqtt.config`, with the secret stored separately under `mqtt.password`. The helpers are in src/Pellmonsrv/plugins/homeassistant/settings.py: `load(store)`, `load_password`, `has_password`, `save(store, clean, password=None, clear_password=False)`, `public_view`, `validate(data, for_test, current) -> (clean, errors)`, and `store.getval(key, '')` / `store.writeval(key, value)`.
- The plugin exposes `get_settings_dict()` (never includes the secret, adds `available`), `apply_settings(data) -> {ok, errors[, available]}` (validate, save, reconfigure live, no restart), and `status_dict()`. See src/Pellmonsrv/plugins/homeassistant/__init__.py lines 82-130.
- D-Bus (pellmonsrv.py ~177-345): `_ha_plugin()` finds the plugin object in `conf.database.protocols` by name. `GetMqttSettings` / `SetMqttSettings(s)` / `GetMqttStatus` send and receive JSON strings, return `{'available': False}` when the plugin is absent, parse input with `_mqtt_parse`, and log only `type(e).__name__`.
- Web client (src/Pellmonweb/pellmonweb.py ~218-252): the `Dbus_handler.mqtt_*` methods do `with self.lock:` then `simplejson.loads(str(self.remote_object.X(..., dbus_interface='org.pellmon.int')))`, and a bare except re-raises `DbusNotConnected("server not running")`. The page is mounted in `PellMonWeb.__init__` (~line 295) with `self.homeassistant = HomeAssistant(lookup, dbus, credentials)`.
- Web controller src/Pellmonweb/homeassistant.py:
  - `@cherrypy.expose` + `@require()` on every route.
  - `save` rejects non-POST requests with MSG_REJECTED, rejects `check_same_origin()` failures with a 403 and a `logger.warning` of origin/host, returns MSG_AUTH_DISABLED when `self.credentials` is empty, and returns MSG_DAEMON_DOWN on a D-Bus exception.
  - A result of `available is False` gives MSG_NOT_ACTIVE (commit e95f2f0). Daemon-side `errors` are echoed back to the form.
  - On success it answers with `HTTPRedirect(script_name + '/homeassistant/?saved=<code>', 303)`, and `index(saved)` maps the code to a success message.
  - `_last()` unwraps list form values. The secret is write-only: the password input is empty with placeholder "set", plus a "Remove the stored password" checkbox.
  - The intro reads "Changes are applied to the running server without a restart." There is no restart requirement, so the OWM page says the same.
- Template src/Pellmonweb/html/homeassistant.html: `<%inherit file="layout.html"/>`, `mqtt-page` / `mqtt-form` / `mqtt-intro` / `#mqtt-status` CSS classes (pellmon.css ~108-130, mobile styles already exist), `| h` escaping everywhere, and the status block `{level, glyph, word, text, title}` made by `_view()`. Nav: src/Pellmonweb/html/layout.html ~58-60 `<li class="${'active' if context.get('active_page','')=='homeassistant' else ''}">`.
- Tests: tests/Pellmonweb/test_homeassistant_page.py (FakeLookup/FakeTemplate return the render kwargs; FakeDbus; the `cherrypy_request_ctx` fixture; `_post(**headers)`; ORIGIN dict). tests/Pellmonsrv/test_homeassistant_dbus.py (`daemon_module` fixture, `init_keyval_storage(tmp)`, monkeypatched `conf.database.protocols` with SimpleNamespace(name=..., plugin_object=fake)). tests/Pellmonsrv/plugins/test_homeassistant_plugin.py (`store` fixture: `Keyval_storage(str(tmp_path/'kv.db'))` monkeypatched onto `Keyval_storage.keyval_storage`). The test runner is `venv-py3/Scripts/python.exe -m pytest ...`.
- tests/test_config_interpolation.py:123 asserts the literal `"ALWAYS_LOADED_PLUGINS = ('HomeAssistant',)"`, so it must be updated.

<interfaces>
pyowm 3.5.0 (verified in venv-py3):
- `pyowm.OWM(api_key)`, then `.weather_manager()` returns a WeatherManager, and `.weather_at_place(name: str)` returns an Observation with `.weather`.
- `Weather.temperature(unit='kelvin')` returns a dict with 'temp' (unit: 'celsius' | 'fahrenheit' | 'kelvin').
- `Weather.wind(unit='meters_sec')` returns a dict with 'speed' and an OPTIONAL 'deg'. `Weather.humidity` is an int attribute.
- `pyowm.commons.exceptions`: UnauthorizedError, NotFoundError, TimeoutError, APIRequestError, InvalidSSLCertificateError, BadGatewayError, PyOWMError.

Existing plugin behavior to keep (src/Pellmonsrv/plugins/openweathermap/__init__.py):
- Conf items `owmN_item/_data/_longname/_description/_unit` become a `Storeditem('owm_stored_'+data)` plus a `Getsetitem(itemname, getter=itemvalues[data])` with tags ['All','Basic','Openweathermap'].
- `Storeditem('location', 'copenhagen,dk', setter=update_location)` is R/W, and its setter triggers a re-fetch within 1 s.
- The store_interval loop copies itemvalues into the stored items (10 s after start, then every 7200 s).
- feelslike = t + 0.348*((h/100)*6.105*(2.7182**((17.27*t)/(237.7+t)))) - 0.7*w, where t is in °C and w in m/s.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Port the plugin to pyowm 3 and add a keyval-backed settings module</name>
  <files>src/Pellmonsrv/plugins/openweathermap/settings.py, src/Pellmonsrv/plugins/openweathermap/__init__.py, src/Pellmonsrv/plugins/openweathermap/Makefile.am, tests/Pellmonsrv/plugins/test_openweathermap_plugin.py</files>
  <behavior>
    - fetch_once with a fake OWM (wind {'speed':3.0,'deg':180}, humidity 50, temp 20.0 celsius) sets itemvalues temperature='20.0', wind_speed='3.0', wind_direction='180', humidity='50', and feelslike='%.1f' of the formula. The fake weather_at_place receives a str (not bytes) equal to db['location'].value.
    - A wind dict without 'deg' still updates temperature, wind_speed, humidity and feelslike, leaves wind_direction at its previous value, and records no error.
    - When unit='fahrenheit', temperature comes from temperature('fahrenheit'). feelslike is computed from temperature('celsius') and converted to °F (c*9/5+32), because the formula only holds in °C.
    - A fake raising pyowm UnauthorizedError sets status reason 'invalid API key' and update_interval 300, and logs a WARNING that contains neither the API key nor the text of the exception. Each exception class maps to its reason (see the action text).
    - activate() with the placeholder conf apikey ('xxxx…') and an empty store does not raise; status state is 'disabled'. activate() with a real-looking conf apikey and an empty store seeds enabled=True and uses that key. This is the migration path for users who configured it in the conf file.
    - activate() when pyowm is not importable (monkeypatch sys.modules['pyowm']=None) does not raise; get_settings_dict()['available'] is False.
    - apply_settings with: enabled and no stored or entered key; unit 'kelvin2'; empty location; location with a control character; key 'abc' — each returns ok False with a keyed error and stores nothing.
    - A valid apply_settings stores the key under 'owm.apikey'. Afterwards get_settings_dict() has has_apikey True and no 'apikey' key; the new location is in db['location'].value; unit and enabled are persisted under 'owm.config'. clear_apikey=True removes the stored key.
  </behavior>
  <action>
Create settings.py by mirroring src/Pellmonsrv/plugins/homeassistant/settings.py: same GPL header, `logger = getLogger('pellMon')`, `%`-formatting, no type hints. It needs:
- KEY_CONFIG='owm.config', KEY_APIKEY='owm.apikey', DEFAULTS={'enabled': False, 'unit': 'celsius'}, UNITS=('celsius','fahrenheit').
- Error copy constants: MSG_ERR_APIKEY 'API key must be 16 to 64 letters or digits.', MSG_ERR_APIKEY_MISSING 'Enter your OpenWeatherMap API key to turn the plugin on.', MSG_ERR_LOCATION 'Enter a location such as copenhagen,dk or 2100,dk (up to 100 characters).', MSG_ERR_UNIT 'Choose Celsius or Fahrenheit.'
- `is_placeholder(key)`: true when the key is empty or made only of 'x' characters, ignoring case and whitespace.
- `validate(data, has_stored_key) -> (clean, errors)`: `enabled` is coerced with the same `_coerce_bool` truth set as HA. unit must be in UNITS. location is stripped, must be 1-100 chars, and must have no control characters. An optional `apikey` is stripped and must match `[A-Za-z0-9]{16,64}`. `clear_apikey` is a bool. If enabled, and neither a new key nor a kept stored key is present, set errors['apikey']=MSG_ERR_APIKEY_MISSING.
- `load(store, conf)`: the stored JSON merged over DEFAULTS. With nothing stored, seed from conf: unit=conf['unit'] if it is in UNITS, and enabled = not is_placeholder(conf.get('apikey','')). Fall back to DEFAULTS with a logger.warning on corrupt data, the same way HA does.
- `load_apikey(store, conf)`: the stored value if present, else the conf apikey unless it is a placeholder, else ''.
- `save(store, clean, apikey=None, clear_apikey=False)`: stores only the enabled and unit keys as JSON. Location is NOT stored here; it stays in the existing 'location' Storeditem, so the dashboard R/W item and its persisted value keep working.
- `public_view(cfg, has_key)`.

Rewrite __init__.py and keep the class name `owmplugin` and its item creation. Changes:
1. activate() must never raise. Wrap `import pyowm` in try/except ImportError and set `self.available`. Set `self.store = Keyval_storage.keyval_storage`. Use class attributes `owm_factory = None` (None means pyowm.OWM) and `autostart = True` as test seams, the same way HA uses client_factory/autostart. Keep `self.location_item` as a reference to the location Storeditem. Add a `threading.Lock`, `self.owm=None`, `self.last_fetch=None` and `self.last_error=''`. Call `self.reconfigure(settings.load(store, self.conf), settings.load_apikey(store, self.conf))`. Start the Timer with `t.daemon = True` instead of setDaemon, and only when autostart is set. If enabled and not available, `logger.error('Openweathermap needs the pyowm module; the plugin stays inactive')`.
2. `reconfigure(cfg, apikey)`: under the lock, set self.cfg. Set self.owm = factory(apikey) when cfg['enabled'] is true and apikey and self.available, else None. Reset last_error, and set update_interval=1 so it fetches right away.
3. Move the loop body into `fetch_once()`, following the pyowm 3 API in <interfaces>. Pass location as a plain str with no .encode. Read wind via .get: set wind_direction only when 'deg' is present. Build humidity with str(weather.humidity). Compute feelslike in °C as in the behavior block. On success set last_fetch=time.time(), last_error='' and update_interval=900. On exception, map to a reason: UnauthorizedError is 'invalid API key'; NotFoundError is 'location not found'; TimeoutError, APIRequestError, BadGatewayError and InvalidSSLCertificateError are 'could not reach openweathermap.org'; anything else is 'unknown error (see the server log)'. Import the classes lazily and tolerate their absence. Then `logger.warning('Openweathermap update failed: %s (%s)' % (reason, type(e).__name__))`. Do not log str(e): pyowm request errors can embed the request URL including appid=<key>. Set update_interval=300. `update_thread` loops: sleep(1), decrement counters, call fetch_once only when self.owm is set, and keep the store_interval logic unchanged.
4. D-Bus contract, mirroring the HA plugin:
   - `get_settings_dict()` returns public_view plus location=self.location_item.value, has_apikey, and available=self.available. It never includes the key.
   - `apply_settings(data)` validates; on errors returns {'ok':False,'errors':...}. Otherwise it calls save, sets `self.location_item.value = clean['location']` only when it changed, and reconfigures with the effective key. It returns {'ok':True,'errors':{}}, plus 'available': False when pyowm is missing. It wraps everything in try/except that logs `logger.exception` and returns {'ok':False,'errors':{},'available':False}.
   - `status_dict()` returns {available, state, last_fetch, reason, location}, where state is one of 'disabled', 'no_key', 'waiting', 'ok' or 'error'.

Add settings.py to `openweathermap_PYTHON` in Makefile.am.

Write tests/Pellmonsrv/plugins/test_openweathermap_plugin.py with the `store` fixture copied from test_homeassistant_plugin.py, a small FakeDb (a dict with `insert(item)` that stores by item.name), a conf dict holding the owm1..owm5 items from src/conf.d/plugins/openweathermap.conf, a FakeOWM/FakeManager/FakeWeather, and `autostart=False`. No network: tests must never construct a real pyowm.OWM.
  </action>
  <verify>
    <automated>venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_openweathermap_plugin.py tests/test_plugin_imports.py -q</automated>
  </verify>
  <done>All behavior cases pass. `grep -n "setDaemon\|get_weather\|get_temperature\|get_wind\|get_humidity\|\.encode(" src/Pellmonsrv/plugins/openweathermap/__init__.py` returns nothing. Plugin imports stay green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Always load the plugin and add the D-Bus methods GetOwmSettings / SetOwmSettings / GetOwmStatus</name>
  <files>src/Pellmonsrv/pellmonsrv.py, src/conf.d/enabled_plugins.conf, src/conf.d/plugins/openweathermap.conf, tests/test_config_interpolation.py, tests/Pellmonsrv/test_openweathermap_dbus.py</files>
  <behavior>
    - With no Openweathermap plugin in conf.database.protocols: GetOwmSettings and GetOwmStatus return {"available": false}, and SetOwmSettings returns {"ok": false, "available": false, "errors": {}}.
    - GetOwmSettings output never contains the key sentinel, even if the fake plugin's dict wrongly includes 'apikey'. The method pops it defensively, the same way GetMqttSettings pops 'password'.
    - SetOwmSettings with invalid JSON or a JSON non-object returns ok false and does not call the plugin. Valid JSON is passed through to apply_settings as a dict.
    - When a plugin method raises ValueError(SENTINEL), the log has 'SetOwmSettings failed: ValueError' and does not contain SENTINEL.
    - A config with enabled_plugins lacking Openweathermap still ends up with it in conf.enabled_plugins exactly once, with plugin_conf filled from [plugin_Openweathermap]. If the section is uncommented in enabled_plugins, it is still only listed once.
  </behavior>
  <action>
In src/Pellmonsrv/pellmonsrv.py:
- Change the constant to `ALWAYS_LOADED_PLUGINS = ('HomeAssistant', 'Openweathermap')` and update the loop comment to name both.
- Generalize `_ha_plugin()` into `_plugin_by_name(name)` and keep `_ha_plugin()` as a thin wrapper so existing tests stay valid. Add `_owm_plugin()`.
- Add the three `@dbus.service.method('org.pellmon.int', ...)` methods GetOwmSettings (in '', out 's'), SetOwmSettings (in 's', out 's') and GetOwmStatus (in '', out 's'), placed right after GetMqttTestResult. Copy the structure and failure returns of GetMqttSettings / SetMqttSettings / GetMqttStatus exactly: reuse `_mqtt_parse`, pop 'apikey' from the settings result, and use `logger.error('%s failed: %s'%(name, type(e).__name__))`-style messages with no exception text.

Update tests/test_config_interpolation.py line ~123 to assert the new literal, and add a case that Openweathermap is in enabled_plugins exactly once. Follow the existing HomeAssistant test at ~line 110 for building the config.

In src/conf.d/enabled_plugins.conf, change the comment above `#p13 = Openweathermap` to say that it now stays inactive until it is enabled on the Weather page of the web interface, and that the line is kept only for older installs. Leave it commented. Do NOT touch config/conf.d/ (untracked local config).

In src/conf.d/plugins/openweathermap.conf, update the apikey comment to say the key is now normally entered on the Weather page. A key set here is only used as a first-time default when none has been saved on the page.

Write tests/Pellmonsrv/test_openweathermap_dbus.py by mirroring tests/Pellmonsrv/test_homeassistant_dbus.py (the `daemon_module` fixture, SimpleNamespace protocols with name='Openweathermap').
  </action>
  <verify>
    <automated>venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_openweathermap_dbus.py tests/Pellmonsrv/test_homeassistant_dbus.py tests/test_config_interpolation.py tests/test_plugin_loader.py -q</automated>
  </verify>
  <done>The new D-Bus tests pass and the HA D-Bus/config tests are still green. The Openweathermap plugin is loaded without any enabled_plugins.conf edit.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Weather settings page (controller, template, nav, D-Bus client), mirroring the Home Assistant page</name>
  <files>src/Pellmonweb/weather.py, src/Pellmonweb/html/weather.html, src/Pellmonweb/html/layout.html, src/Pellmonweb/pellmonweb.py, tests/Pellmonweb/test_weather_page.py</files>
  <behavior>
    - index and save carry 'auth.require' in _cp_config.
    - A GET on save returns MSG_REJECTED without any D-Bus call. A cross-origin POST returns status 403, logs a warning naming the origin, makes no D-Bus call, and the logs do not contain the submitted apikey. A POST without an Origin header is rejected too.
    - Empty credentials: save returns MSG_AUTH_DISABLED and makes no set call.
    - A valid POST sends {'enabled': True, 'location': 'copenhagen,dk', 'unit': 'celsius', 'apikey': KEY} to owm_set_settings and redirects 303 to '/weather/?saved=1'. With enabled unchecked it redirects to '?saved=off'.
    - A blank apikey field sends no 'apikey' key (the stored key is kept). With clear_apikey checked it sends clear_apikey=True.
    - A set result of {'ok': False, 'available': False} gives MSG_NOT_ACTIVE. A D-Bus exception gives MSG_DAEMON_DOWN. Daemon errors {'apikey': msg} are rendered as errors, and the submitted key is never echoed back into the render context: settings has no 'apikey', and apikey_reentered is True.
    - status_view maps: daemon down gives STATUS_DAEMON_DOWN; available False gives STATUS_NOT_ACTIVE; state disabled gives STATUS_OFF; no_key gives STATUS_NO_KEY; waiting gives STATUS_WAITING with the location; ok gives STATUS_OK with a HH:MM:SS stamp; error gives STATUS_ERROR with the reason, and any reason outside the known set becomes 'unknown error (see the server log)'.
    - The rendered weather.html (rendered with a real mako TemplateLookup over src/Pellmonweb/html, the same way test_homeassistant_ui.py does) contains an input type="password" name="apikey" whose value attribute is empty, and does not contain the stored key. The layout nav contains an href ending in '/weather/'.
  </behavior>
  <action>
Create src/Pellmonweb/weather.py by structurally copying src/Pellmonweb/homeassistant.py (header, imports `require`, `check_same_origin`, `_view`, `_last`, `_stamp`, `_OFF_VALUES`), minus the test/JSON-status routes. The copy constants:
- MSG_SAVED 'Settings saved. The weather is updated within a few seconds.'
- MSG_SAVED_OFF 'Settings saved. OpenWeatherMap is off.'
- MSG_INVALID, MSG_REJECTED, MSG_DAEMON_DOWN and MSG_AUTH_DISABLED worded exactly as in HA.
- MSG_NOT_ACTIVE 'Cannot save because the OpenWeatherMap plugin is not active on the server. Your changes were not saved. Update PellMon and restart the server.'
- STATUS_OFF 'Off. OpenWeatherMap is turned off. Turn on "Enable OpenWeatherMap" and save to fetch the weather.'
- STATUS_NO_KEY 'Waiting. Enter an API key and save to fetch the weather.'
- STATUS_WAITING 'Fetching the weather for %s...'
- STATUS_OK 'Updated. Last update for %s: %s.'
- STATUS_ERROR 'Update failed. %s. PellMon retries every 5 minutes.'
- STATUS_NOT_ACTIVE and STATUS_DAEMON_DOWN reworded from HA to name OpenWeatherMap.
- The REASONS frozenset holds the plugin's reason strings.

Only create JS or a /status route if a test needs them; the status line is rendered server-side on each load. `class Weather(object)` with `__init__(lookup, dbus, credentials=None)` and helpers:
- `_collect(form)`: `enabled` and `clear_apikey` are checkboxes; `location`, `unit` and `apikey` are text, stripped.
- `_load()` via `self.dbus.owm_get_settings()`.
- `_render(**overrides)` with active_page='weather'.
- `index(saved='')` and `save(**form)`, with exactly the HA guard order: method, then same origin, then local validation, then credentials, then D-Bus.

Local validation: reuse the plugin's validation by importing `Pellmonsrv.plugins.openweathermap.settings`, the same way homeassistant.py imports its settings. Pass has_stored_key from `_load()`. The daemon validates again.

Never put the submitted apikey into the render context or the logs.

Create html/weather.html by copying the homeassistant.html skeleton and CSS classes (`mqtt-page`, `mqtt-form`, `mqtt-intro`, `#mqtt-status`, panel sections) so the existing mobile CSS applies. It has one "OpenWeatherMap" panel with:
- An enable checkbox, "Enable OpenWeatherMap".
- An API key `<input type="password" name="apikey" autocomplete="new-password">`, empty, with placeholder 'set' when has_apikey. Help text: when a key is stored, "An API key is stored. Leave this field blank to keep it."; after a failed save, "Re-enter the API key. It is not kept when the form is redisplayed." Add a "Remove the stored API key" checkbox when one is stored, and a link to https://home.openweathermap.org/api_keys with rel="noopener noreferrer" target="_blank".
- A location text input with help "town,countrycode or zipcode,countrycode, for example copenhagen,dk".
- A unit select for Celsius/Fahrenheit.
- A save button.

The intro reads "Show outside weather from openweathermap.org on the dashboard. Changes are applied to the running server without a restart." Apply `| h` to every interpolated value.

In layout.html, add a `<li>` Weather nav entry right after the Home Assistant entry using the same active_page pattern with 'weather'.

In pellmonweb.py:
- Add `owm_get_settings`, `owm_set_settings(d)` and `owm_status` to Dbus_handler, copying the mqtt_* methods (GetOwmSettings / SetOwmSettings / GetOwmStatus), with the same "never log the arguments" comment.
- Import Weather next to the HomeAssistant import.
- Mount it with `self.weather = Weather(lookup, dbus, credentials)` in PellMonWeb.__init__.

Write tests/Pellmonweb/test_weather_page.py by mirroring test_homeassistant_page.py (FakeLookup asserting 'weather.html', FakeDbus with owm_* methods, `cherrypy_request_ctx`, `_post`, the ORIGIN dict). Mirror test_homeassistant_ui.py for the real-template render check.
  </action>
  <verify>
    <automated>venv-py3/Scripts/python.exe -m pytest tests/Pellmonweb/test_weather_page.py tests/Pellmonweb/test_homeassistant_page.py tests/Pellmonweb/test_homeassistant_ui.py tests/Pellmonweb/test_mobile_css.py -q && venv-py3/Scripts/python.exe -m pytest tests/ -m "not known_broken" -q</automated>
  </verify>
  <done>The /weather/ page renders, saves through D-Bus with HA-equivalent guards, never echoes the key, and shows the status line. The full green-baseline suite passes.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| browser → pellmonweb /weather/save | untrusted form input, CSRF exposure |
| pellmonweb → pellmonsrv D-Bus (SetOwmSettings) | JSON string crosses the process boundary |
| pellmonsrv → api.openweathermap.org | outbound HTTPS; error text may carry the request URL with appid |
| pellmon log / web log view | anything logged is visible to web users |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-bzn-01 | Spoofing/Tampering | Weather.save | mitigate | @require() auth, POST-only, check_same_origin() → 403 + warning, MSG_AUTH_DISABLED when no credentials (identical to HA) |
| T-bzn-02 | Information disclosure | API key in HTML/D-Bus | mitigate | key write-only: never in render ctx, get_settings_dict/GetOwmSettings pop 'apikey', password input with empty value; tests assert the sentinel is absent |
| T-bzn-03 | Information disclosure | logs | mitigate | plugin logs reason + type(e).__name__ only (pyowm errors may embed appid URL); D-Bus logs type name only; web never logs form values |
| T-bzn-04 | Tampering | location/unit/apikey values | mitigate | validate() on both web and daemon side: unit whitelist, location length + no control chars, key regex [A-Za-z0-9]{16,64}; Mako `| h` escaping |
| T-bzn-05 | Denial of service | fetch loop | accept | fixed 900 s / 300 s intervals, re-fetch only on explicit save; the single user is authenticated |
</threat_model>

<verification>
- `venv-py3/Scripts/python.exe -m pytest tests/ -m "not known_broken" -q` passes (green baseline).
- `grep -rn "setDaemon\|weather_at_place(self.db\|get_weather" src/Pellmonsrv/plugins/openweathermap/` returns nothing.
- `grep -n "ALWAYS_LOADED_PLUGINS = ('HomeAssistant', 'Openweathermap')" src/Pellmonsrv/pellmonsrv.py` matches.
</verification>

<success_criteria>
- The plugin works with pyowm 3.5.0 (mocked). Missing wind 'deg' is tolerated. activate never raises.
- A user can enable/disable the plugin and set the key, location and unit on /weather/ with no conf-file edit and no restart. The values persist in the keyval DB on the Docker data volume.
- The key is never shown, returned or logged. The status line reflects off / no key / waiting / ok / error / not active / server down.
</success_criteria>

<output>
Create `.planning/quick/260928-bzn-port-openweathermap-plugin-to-pyowm-3-an/260928-bzn-SUMMARY.md` when done
</output>
