# Phase 6: Home Assistant MQTT - Pattern Map

**Mapped:** 2026-09-25
**Files analyzed:** 33 new/modified
**Analogs found:** 30 / 33 (3 with no in-repo analog: paho bridge, FakeMqttClient, homeassistant.js)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `src/Pellmonsrv/plugins/homeassistant.pellmon-plugin` | config (descriptor) | n/a | `plugins/scottecom.pellmon-plugin` | exact |
| `src/Pellmonsrv/plugins/homeassistant/__init__.py` | plugin (protocols subclass) | event-driven | `plugins/scottecom/scottecom.py` (lines 19-118) | role-match |
| `.../homeassistant/entities.py` | utility (pure table + payload builder) | transform | RESEARCH "Discovery payload builder"; `scottecom/descriptions.py` (table style) | partial |
| `.../homeassistant/settings.py` | utility (validators, load/save) | CRUD | `Pellmonweb/settings.py` (whitelist/validator style) + `database.py` `Keyval_storage.getval/writeval` | role-match |
| `.../homeassistant/bridge.py` | service (worker thread, queue) | pub-sub / event-driven | none (no MQTT/queue-worker in repo); `Database.run` (pellmonsrv.py 119-141) for loop style | no analog |
| `.../homeassistant/Makefile.am` | config (autotools) | n/a | `plugins/scottecom/Makefile.am` | exact |
| `plugins/Makefile.am`, `configure.ac` | config | n/a | existing SUBDIRS / DATA / `AC_CONFIG_FILES` lists | exact |
| `src/conf.d/enabled_plugins.conf` | config | n/a | same file, `p12 = NBEcom` block | exact |
| `src/Pellmonsrv/pellmonsrv.py` (Database listener hook) | daemon thread | event-driven | `Database.run` lines 119-141 | exact (same file) |
| `src/Pellmonsrv/pellmonsrv.py` (5 D-Bus methods, `_ha_plugin`) | D-Bus service | request-response | `GetSetting`/`SetSetting` (218-242), `getPlugins` (210-216) | exact |
| `src/Pellmonweb/homeassistant.py` | controller | request-response | `src/Pellmonweb/settings.py` `Settings` (97-153) | exact |
| `src/Pellmonweb/html/homeassistant.html` | Mako template | request-response | `html/settings.html` | role-match |
| `src/Pellmonweb/html/layout.html` (nav entry) | template | n/a | Settings `<li>` at lines 54-55 | exact |
| `src/Pellmonweb/media/js/homeassistant.js` | client script | polling AJAX | `media/js/source.js` (rule: `.text()` only) | partial |
| `src/Pellmonweb/media/css/pellmon.css` | style | n/a | existing Phase 8/10 blocks | exact |
| `src/Pellmonweb/pellmonweb.py` (Dbus_handler `mqtt_*`, mount) | proxy | request-response | `get_setting`/`set_setting` (201-213); `self.settings = Settings(...)` line 255 | exact |
| `requirements.txt` | config | n/a | "Plugin dependencies" `==` pins | exact |
| `Dockerfile` | config | n/a | apt list lines 14-39 | exact |
| `tests/Pellmonsrv/plugins/fake_mqtt.py` | test helper | n/a | `tests/conftest.py` `mocked_udp_socket` (fake at boundary) | partial |
| `tests/Pellmonsrv/plugins/test_homeassistant_{entities,settings,bridge,paho_factory}.py` | test | unit | `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py`, `tests/Pellmonsrv/test_database.py` | role-match |
| `tests/Pellmonsrv/test_homeassistant_dbus.py` | test | unit | `tests/Pellmonsrv/test_settings_store.py` lines 41-65 (`svc` fixture) | exact |
| `tests/Pellmonweb/test_homeassistant_page.py` | test | unit | `tests/Pellmonweb/test_settings_image.py` + `test_settings_page.py` | exact |
| `tests/browser/fake_dbus.py`, `test_mobile_overflow.py`, `test_browser_harness.py` | test | browser | same files (extend) | exact |
| `DEPLOY-PI.md`, `HARDWARE-BRINGUP.md`, `DOCKER.md` | docs | n/a | existing sections | n/a |

## Pattern Assignments

### `homeassistant.pellmon-plugin` (descriptor)

**Analog:** `src/Pellmonsrv/plugins/scottecom.pellmon-plugin` (whole file, 10 lines). `Module` must equal package dir name; `Name` is what `enabled_plugins.conf` lists.
```ini
[Core]
Name = HomeAssistant
Module = homeassistant

[Documentation]
Author = PellMon
Version = 0.1
Website = http://github.com/motoz/PellMon
Description = Publishes the burner to Home Assistant as an MQTT device
```
Also add `homeassistant.pellmon-plugin` to `nobase_dist_plugins_DATA` and `homeassistant` to `SUBDIRS` in `plugins/Makefile.am`, and `src/Pellmonsrv/plugins/homeassistant/Makefile` to `configure.ac` (list at lines 43-58). Copy Makefile.am from scottecom (`scottecom/Makefile.am` lines 1-8):
```make
homeassistant_PYTHON = \
	entities.py \
	settings.py \
	bridge.py \
	__init__.py

homeassistantdir = $(pythondir)/Pellmonsrv/plugins/homeassistant
```
`enabled_plugins.conf`: add after the p12 block (format lines 45-46): comment line then `p15 = HomeAssistant` (uncommented, per RESEARCH Open Question 2).

---

### `plugins/homeassistant/__init__.py` (plugin class)

**Analog:** `plugins/scottecom/scottecom.py`

**Header/imports** (lines 1-26): GPL header block (`#!/usr/bin/env python3`, coding line, licence docstring), then
```python
import logging
import threading
from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Item, Getsetitem, Plainitem
```
Absolute `Pellmonsrv.*` imports across into the package; sibling modules relative (`from . import menus`). Keep `paho` import lazy inside `bridge`/`activate` so `tests/test_plugin_imports.py` still imports the module without paho.

**Class and activate order** (lines 27-36): lowercase class name subclassing `protocols`; `protocols.activate(...)` FIRST.
```python
class scottecom(protocols):
    def __init__(self):
        protocols.__init__(self)

    def activate(self, conf, glob, db, *args, **kwargs):
        protocols.activate(self, conf, glob, db, *args, **kwargs)
        self.logger = logging.getLogger('pellMon')
```
Class name here: `homeassistant(protocols)`. Whole setup in try/except that logs with `self.logger.exception(...)` and does not raise (lines 90-93) so a bad MQTT setup cannot abort daemon startup.

**Reading the burner state item** (lines 41-44, 106-111): `burner_connection` is a `Plainitem` whose `.value` is `connected|no_connection|demo`; read `db['burner_connection'].value` (db is a `WeakValueDictionary`, `database.py`). Gate on its presence (Pitfall 12).

**Item attributes for range checks** (lines 60-63): `dbitem.max = str(...)`, `dbitem.min = str(...)` are strings; convert with `float()` when intersecting with the HA range.

**Settings storage:** do NOT use `protocols.load_setting` (`plugin_categories.py` 62-63 calls `readval`, which logs a traceback and returns `'error'` for missing keys). Use:
```python
from Pellmonsrv.database import Keyval_storage
Keyval_storage.keyval_storage.getval('mqtt.config', '')          # database.py 176-187, exception-free
Keyval_storage.keyval_storage.writeval('mqtt.config', json_str)   # database.py 208; first insert works (test_settings_store.py 21-30)
```
Key names: `mqtt.config` (JSON), `mqtt.password`. Never `Storeditem` (would expose via GetItem).

**Timers (anti-pattern):** scottecom lines 80-87 create `threading.Timer` chains; do NOT copy. Use the single worker thread in `bridge.py`. Daemon-thread flag style in this codebase is `self.daemon = True` (`pellmonsrv.py` line 81), not `setDaemon`.

**Exit hook (C5):** no analog; use `atexit.register(...)` in `activate`. `Database.terminate()` (pellmonsrv.py 143-146) exists but has no caller.

---

### `plugins/homeassistant/settings.py` (validators)

**Analog:** validator-per-key whitelist style from `pellmonsrv.py` 148-156 and `Pellmonweb/settings.py` 63-65 (`is_allowed`: pure function, `isinstance` check first, never sanitises, only matches):
```python
_SYSTEM_IMAGE_RE = re.compile(r'system[a-z0-9_]*\.svg')
def _valid_system_image(value):
    return isinstance(value, str) and _SYSTEM_IMAGE_RE.fullmatch(value) is not None
```
Use `re.fullmatch` per-field validators returning `{field: msg}` error dicts; error copy strings must be verbatim from UI-SPEC "Validation" table. Module-level `MSG_*` constants (settings.py 48-52) for copy strings so tests can assert them.

---

### `plugins/homeassistant/entities.py`

No repo analog for the table; use RESEARCH entity table (lines 282-307) with separate `object_id` and `item` columns (C1) and RESEARCH "Discovery payload builder" (lines 385-416). Module-level `camelCase`/plain data tables are the repo norm (`itemList`, `dataDescriptions` in `scottecom/descriptions.py`). Unit is written `°C` in UTF-8 source (file has the `# -*- coding: utf-8 -*-` header). Cross-check test reads `Scotteprotocol.datamap` min/max.

---

### `plugins/homeassistant/bridge.py`

**No analog.** Follow RESEARCH Patterns 1, 2, 5, 6: injectable `client_factory`, callbacks only `queue.put_nowait`, worker `queue.get(timeout=1.0)` with 1 s tick, injectable `clock`/`sleep`. Loop style reference (`pellmonsrv.py` 119-137): `while True: time.sleep(2)` and per-item `try/except Exception: pass` so one bad item never kills the thread; here log instead of `pass` (project prefers `logger.warning`/`error` over swallowing).

Logging conventions: `%`-formatting, `logger = getLogger('pellMon')`, never log settings dicts, payload of password, or D-Bus arguments.

---

### `pellmonsrv.py`: Database listener hook

**Analog:** same file, `Database.__init__` (73-111) and `run` (119-141). Insert `self.listeners = []` next to `self.values={}` (line 79, before plugins activate at line 83-106), add `add_change_listener`, `snapshot`, and call listeners after `changed_params` is built:
```python
            if changed_params:
                if self.dbus_service:
                    s = json.dumps(changed_params)
                    self.dbus_service.changed_parameters(s)
                # NEW: for cb in list(self.listeners): try: cb(changed_params) except Exception: logger.exception(...)
```
Listeners must only enqueue. Plugin uses `getattr(db, 'add_change_listener', None)` so plain `database.Database` in tests works.

### `pellmonsrv.py`: five new D-Bus methods

**Analog:** `GetSetting`/`SetSetting` (218-242) and `getPlugins` (210-216).

Decorator + docstring + logging style:
```python
    @dbus.service.method('org.pellmon.int', in_signature='s', out_signature='s')
    def GetSetting(self, key):
        """Get a whitelisted GUI setting, empty string when unset"""
        if key not in ALLOWED_SETTINGS:
            logger.warning('rejected settings read for unknown key %s'%key)
            return ''
        if Keyval_storage.keyval_storage is None:
            return ''
        return Keyval_storage.keyval_storage.getval(key, '')
```
Plugin lookup (copy `getPlugins`, lines 212-213): `for plugin in conf.database.protocols: ... plugin.name == 'HomeAssistant'` then `plugin.plugin_object`. When absent return `json.dumps({'available': False})`. All five: `in_signature='s', out_signature='s'` (JSON strings), except `StartMqttTest` `out_signature='b'` (as `SetSetting` uses `'b'`). Do NOT touch `ALLOWED_SETTINGS` (154-156). Never log arguments (SetSetting logs `%r` of the value at 235; do not copy that for the password).

---

### `src/Pellmonweb/homeassistant.py` (controller)

**Analog:** `src/Pellmonweb/settings.py`

**Imports** (lines 19-26):
```python
import cherrypy
from logging import getLogger
from .auth import require
from .security import check_same_origin

logger = getLogger('pellMon')
```
**Copy strings as module constants** (48-52) `MSG_SAVED`, `MSG_REJECTED`, `MSG_DAEMON_DOWN` ... with UI-SPEC copy verbatim.

**Constructor and render** (97-115):
```python
class Settings(object):
    def __init__(self, lookup, dbus, img_dir, credentials=None):
        self.lookup = lookup; self.dbus = dbus; self.credentials = credentials

    def _render(self, msg='', msg_level='', current=None):
        ctx = dict(username=cherrypy.session.get('_cp_username'),
                   webroot=cherrypy.request.script_name,
                   active_page='settings', ...,
                   msg=msg, msg_level=msg_level,
                   auth_configured=bool(self.credentials))
        return self.lookup.get_template('settings.html').render(**ctx)
```
Use `active_page='homeassistant'`, template `'homeassistant.html'`.

**Read with daemon-down fallback** (117-123): `try: value = self.dbus.get_setting(...) except Exception: return '', False`.

**Auth + POST + same-origin + daemon-down** (125-153):
```python
    @cherrypy.expose
    @require()
    def save(self, image=''):
        if cherrypy.request.method != 'POST':
            return self._render(MSG_REJECTED, 'danger')
        if not check_same_origin():
            cherrypy.response.status = 403
            logger.warning('rejected cross-origin system image save: origin=%r host=%r',
                           cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                           cherrypy.request.headers.get('Host'))
            return self._render(MSG_REJECTED, 'danger')
        ...
        try:
            ok = self.dbus.set_setting(SETTING_KEY, image)
        except Exception:
            ok = False
        if not ok:
            return self._render(MSG_DAEMON_DOWN, 'warning')
```
Adjust: log only origin/host on rejection, never form data (password). Every route (`index`, `save`, `test`, `status`, `test_result`) gets `@cherrypy.expose` + `@require()`; `save` and `test` also POST + `check_same_origin()`. JSON endpoints set `cherrypy.response.headers['Content-Type'] = 'application/json'` and return `simplejson.dumps(...)` (idiom at `pellmonweb.py` 264-265). Validation happens before any D-Bus call (UI-SPEC AC 11).

### `pellmonweb.py` (Dbus_handler + mount)

**Analog:** lines 201-213:
```python
    def get_setting(self, key):
        with self.lock:
            try:
                return str(self.remote_object.GetSetting(key, dbus_interface ='org.pellmon.int'))
            except:
                raise DbusNotConnected("server not running")
```
Copy verbatim shape for `mqtt_get_settings`, `mqtt_set_settings`, `mqtt_status`, `mqtt_test_start`, `mqtt_test_result` (parse JSON with `simplejson.loads`, `bool()` for the `'b'` one). Hold `self.lock` per call. Mount: line 255 `self.settings = Settings(lookup, dbus, system_image_dir, credentials)` becomes an added `self.homeassistant = HomeAssistant(lookup, dbus, credentials)` in `PellMonWeb.__init__` (test `test_settings_mounted` in `test_settings_page.py` 112-114 asserts by AST source segment; write an analogous one).

---

### `html/homeassistant.html`

**Analog:** `html/settings.html`

Skeleton (lines 1-13): `<%inherit file="layout.html"/>`, `<%def name="title()">`, `.container`, `<h1>`, `section.panel.panel-default` with `.panel-heading`/`.panel-body`, message block:
```mako
% if msg:
<div class="alert alert-${msg_level | h}" role="${'status' if msg_level == 'success' else 'alert'}">${msg | h}</div>
% endif
```
Form (18): `<form method="post" action="${webroot | h}/settings/save">`. Escape every value with `| h`. Auth-disabled button (37, 39-41):
```mako
<button type="submit" class="btn btn-primary sysimg-save"${'' if auth_configured else ' disabled'}>Save image</button>
% if not auth_configured:
<p class="help-block">Saving is disabled until web login credentials are configured.</p>
```
Checked state pattern (25): `${' checked' if ... else ''}`. Password input: no `value=` attribute at all. Rest of layout per 06-UI-SPEC.

### `html/layout.html` nav

**Analog:** lines 54-55; add right after:
```mako
<li class="${'active' if context.get('active_page', '') == 'homeassistant' else ''}">
	<a href="${webroot}/homeassistant/">Home Assistant</a>
</li>
```

### `media/js/homeassistant.js`

No direct analog. Rule from `tests/Pellmonweb/test_source_js_no_html_sink.py` (whole file): scan the JS with `re.search(r"\.html\(", js)`; use `.text()`/`textContent` only. Add a sibling test for `homeassistant.js`. Load via the same script-include mechanism other pages use (check `settings.html`/`logview.html` for `<script src="${webroot}/media/js/...">`; jQuery 1.11 already in layout).

---

### `requirements.txt`

Analog: tail of file, exact-pin style with a comment header per plugin:
```
# Home Assistant plugin
paho-mqtt==2.1.0
```
Planner: gate behind `checkpoint:human-verify` (RESEARCH audit).

### `Dockerfile`

Analog lines 14-39: add under a comment inside the `apt-get install` list (comment-per-group style: `# Network and utilities` `curl \` `procps \`):
```
    ca-certificates \
```

---

## Test patterns

### `tests/Pellmonweb/test_homeassistant_page.py`

**Analogs:** `test_settings_image.py`, `test_settings_page.py`

Fixtures/idioms to copy:
- `cherrypy_request_ctx` from `tests/conftest.py` lines 37-61 (mandatory for anything touching `cherrypy.request/session`).
- POST helper (test_settings_image.py 10-13):
```python
def _post(cherrypy_request_ctx, **headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)
```
- Fakes (115-153): `FakeTemplate.render(**kw)` returns the ctx dict; `FakeLookup.get_template(name)` asserts name; `FakeDbus` records `set_calls`, `fail=True` raises. Build `FakeDbus` with `mqtt_*` methods.
- Auth: `assert 'auth.require' in HomeAssistant.index._cp_config` (157-160).
- Cases to mirror: GET does not save (181-186); cross-origin -> 403 + `evil.example` in warning and D-Bus not called (188-198); headerless POST rejected (200-205); success uses `Origin='http://localhost:8081', Host='localhost:8081'` (214-220); `@pytest.mark.parametrize('kw', [{'fail': True}, ...])` daemon-down (222-227). Add: caplog never contains the password sentinel.
- Mako render tests (test_settings_page.py 155-160):
```python
def render(name="settings.html", **kw):
    ctx = dict(username="u", webroot="", active_page="settings", ..., msg="", msg_level="", auth_configured=True)
    ctx.update(kw)
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    return lookup.get_template(name).render(**ctx)
```
  Regex assertions (`re.search(r'<button[^>]*btn-primary[^>]*disabled', html)`), escape test (182-185), navbar-active test (200-206; layout regex `<li class="active">\s*<a href="/settings/">Settings`; note the new nav `<li>` has the same shape).
- AST wiring tests: `_class`/`_method` helpers on `pellmonweb.py` source (test_settings_page.py 18-23, 117-120 for `Dbus_handler` proxies, 129-142 for `DbusNotConnected` via `Dbus_handler.__new__` + `Lock`, guarded by `pytest.importorskip("dbus"/"gi"/"cherrypy")`).

### `tests/Pellmonsrv/test_homeassistant_dbus.py`

**Analog:** `tests/Pellmonsrv/test_settings_store.py` lines 41-65:
```python
@pytest.fixture
def svc(daemon_module, tmp_path):
    from Pellmonsrv.database import init_keyval_storage
    init_keyval_storage(str(tmp_path / "settings.db"))
    cls = daemon_module.MyDBUSService      # call unbound: svc.GetSetting(None, key)
    yield cls
    Keyval_storage.keyval_storage = None
```
`daemon_module` (tests/Pellmonsrv/conftest.py 121-162) stubs dbus/gi/pwd/grp with identity decorators; methods are invoked as `cls.Method(None, args)`. To reach the plugin, set `daemon_module.conf` to a stub with `.database.protocols = [SimpleNamespace(name='HomeAssistant', plugin_object=fake)]`. Regression tests: `GetSetting(None, 'mqtt.password') == ''` (see unknown-key test lines 60-65 with `caplog.at_level(logging.WARNING, logger="pellMon")`), and `not any(k.startswith('mqtt.') for k in daemon_module.ALLOWED_SETTINGS)`.

### `tests/Pellmonsrv/plugins/test_homeassistant_*.py` and `fake_mqtt.py`

No in-repo MQTT analog. Follow the guardrail rule in `tests/conftest.py` 21-34: patch at the boundary, never open sockets (`--disable-socket`; `enable_socket` is forbidden). `FakeMqttClient` spec is in RESEARCH Wave 0 (record `publish/subscribe/will_set/username_pw_set/tls_*`, `fire_connect/fire_disconnect/fire_message`). Keyval tests: `Keyval_storage(str(tmp_path / "test.db"))` (test_settings_store.py 9-18). Logging assertions: `caplog.at_level(logging.WARNING, logger='pellMon')`; the autouse `_restore_pellmon_logger` fixture (conftest 64-82) restores logger state. `test_homeassistant_paho_factory.py`: build a real `paho.Client` via default factory (allowed), never `loop_start()`.

### Browser tests

- `tests/browser/fake_dbus.py`: `FakeDbus` is a class of canned methods (`get_setting` returns `"system.svg"`, `set_setting` returns `True`, lines 95-99). Append `mqtt_get_settings`, `mqtt_set_settings`, `mqtt_status`, `mqtt_test_start`, `mqtt_test_result` in the same plain-method style; `has_password: True`, long host/prefix strings.
- `tests/browser/stub_server.py`: no edit required unless `PellMonWeb.__init__` needs extra module globals (it uses `web.dbus`, `web.lookup`, `web.credentials = []`, lines 30-37); `HomeAssistant(lookup, dbus, credentials)` reads them the same way as `Settings`.
- `test_mobile_overflow.py` line 6-7 and `test_browser_harness.py` line 4-5: both have an identical `PAGES = [...]` list; append `"/homeassistant/"` to both.

## Shared Patterns

### Auth + CSRF (all Pellmonweb controller routes)
**Source:** `Pellmonweb/settings.py` lines 21-24, 125-143 (`@cherrypy.expose` then `@require()`, `check_same_origin()` on POST, 403 on failure).

### D-Bus JSON facade
**Source:** `pellmonsrv.py` 218-242 (daemon) + `pellmonweb.py` 201-213 (web). Errors on web side always collapse to `DbusNotConnected("server not running")`; controllers catch `Exception` and render the daemon-down message.

### Logging
`logger = getLogger('pellMon')`, `%`-formatting, correct level (`warning`/`error`, not `info`). Never log secrets. New files carry the GPL header and `#!/usr/bin/env python3` / `# -*- coding: utf-8 -*-` (copy from `database.py`/`settings.py`). No `.py2bak` for new files.

### Error containment in daemon threads
`Database.run` per-item try/except (pellmonsrv.py 125-137) and plugin activation try/except (94-106; `conf.command == 'debug'` re-raises). Listener callbacks and worker loop must never propagate.

### Copy strings
Constants at module top of the module that renders them (settings.py 48-52); tests assert them verbatim.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `homeassistant/bridge.py` | service | pub-sub | No MQTT client or queue-worker thread exists; use RESEARCH Patterns 1-6 |
| `tests/.../fake_mqtt.py` | test helper | n/a | No fake client exists; closest idea is `mocked_udp_socket` fixture |
| `media/js/homeassistant.js` | script | polling | Existing page scripts are page-specific; only the no-`.html()` rule applies |

## Metadata

**Analog search scope:** `src/Pellmonsrv`, `src/Pellmonweb`, `src/conf.d`, `tests/`, `tests/browser`, Dockerfile, requirements.txt, `configure.ac`
**Files scanned/read:** about 20
**Pattern extraction date:** 2026-09-25
