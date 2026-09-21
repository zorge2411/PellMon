# Phase 8: Expose burner SVG in settings - Pattern Map

**Mapped:** 2026-09-21
**Files analyzed:** 11
**Analogs found:** 10 / 11

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/Pellmonweb/settings.py` (new; dbus-free whitelist, human names, effective_image, Settings controller) | controller + utility | request-response | `src/Pellmonweb/pellmonconf.py` (`Pellmonconf`, `_resolve`, `save`) | role-match |
| `src/Pellmonweb/security.py` (new; shared `check_same_origin`) | utility | request-response | `_check_same_origin` in `src/Pellmonweb/pellmonconf.py:154-164` | exact (move) |
| `src/Pellmonweb/pellmonconf.py` (modify: import shared helper) | controller | request-response | itself | exact |
| `src/Pellmonweb/pellmonweb.py` (modify: `Root.systemimage`, `Dbus_handler.get_setting/set_setting`, mount `settings`) | controller / client | request-response, D-Bus RPC | `Dbus_handler.getItem/setItem` (:187-199), `Root.__init__` mounts (:238-239) | exact |
| `src/Pellmonsrv/pellmonsrv.py` (modify: `GetSetting`/`SetSetting` on `MyDBUSService`) | service | request-response (D-Bus) | `MyDBUSService.GetItem/SetItem` (:157-168) | exact |
| `src/Pellmonweb/html/settings.html` (new Mako page) | component | request-response | `src/Pellmonweb/html/systemimage`, `layout.html` (extends) | partial |
| `src/Pellmonweb/html/layout.html` (modify: navbar link) | component | - | "View log" `<li>` at :51-53 | exact |
| `src/Pellmonweb/media/css/pellmon.css` (modify: `.sysimg-*`) | config/style | - | existing pellmon.css rules | partial |
| `src/conf.d/webinterface.conf.in` (comment) and `DEPLOY-PI.md` (docs) | config/docs | - | in place | n/a |
| `tests/Pellmonweb/test_settings_image.py` (new) | test | - | `tests/Pellmonweb/test_pellmonconf_csrf.py` | exact |
| `tests/Pellmonsrv/test_settings_store.py` (new) | test | CRUD | `tests/Pellmonsrv/test_database.py` (`test_writeval_readval_roundtrip`) | exact |
| `tests/test_backup_script.py` (extend) | test | file-I/O | itself | exact |

## Pattern Assignments

### `src/Pellmonweb/security.py` + `pellmonconf.py` (utility, request-response)

**Analog:** `src/Pellmonweb/pellmonconf.py:154-164` (move verbatim; needs `import cherrypy`, `import urllib.parse`)
```python
def _check_same_origin():
    """True only if the Origin (or Referer) header names the same host as the request Host header"""
    headers = cherrypy.request.headers
    origin = headers.get('Origin') or headers.get('Referer')
    if not origin:
        return False
    try:
        netloc = urllib.parse.urlparse(origin).netloc
    except ValueError:
        return False
    return bool(netloc) and netloc == headers.get('Host')
```
`pellmonconf.py` must keep calling it as `_check_same_origin()` (or alias `from Pellmonweb.security import check_same_origin as _check_same_origin`); `tests/Pellmonweb/test_pellmonconf_csrf.py` drives `Pellmonconf.save` and must stay green. Note the existing test file also extracts module source via `ast` at its bottom (line ~60 onward, "resolver is extracted from the module source"): read it before moving the function, it may parse `pellmonconf.py` for `_check_same_origin`.

### `src/Pellmonweb/settings.py` (controller, request-response)

**Analog:** `src/Pellmonweb/pellmonconf.py` (header, logger, save guard)

Header/logger (lines 1-19, 39): GPL block with `#!/usr/bin/env python3`, `# -*- coding: utf-8 -*-`; `logger = getLogger('pellMon')`. Use `%`-style logs, no `print` (`tests/test_no_ad_hoc_print.py` enforces), no `sys.path` shims.

POST guard pattern (`pellmonconf.py:120-128`):
```python
@cherrypy.expose
def save(self, filename='', data=None):
    if cherrypy.request.method == "POST":
        if not _check_same_origin():
            logger.warning('rejected cross-origin config save: origin=%r host=%r',
                           cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                           cherrypy.request.headers.get('Host'))
            return json.dumps({'success':False, 'error':'cross-origin request rejected'})
        ...
    else:
        return json.dumps({'success':False, 'error':{'msg':'only POST'}})
```
Whitelist-then-act pattern (`_resolve`, :95-101): reject anything not in allowed set with `logger.warning('rejected ...: %r', name)` and raise/return error.

Auth decorator, copy from `pellmonweb.py:503-504`:
```python
@cherrypy.expose
@require() #requires valid login
def getparam(self, param='-'):
```
Import `require` the same way pellmonweb.py does (it comes through `from Pellmonweb import *` / auth module; check `src/Pellmonweb/auth.py:105` `def require(*conditions)`; do NOT rely on star-import inside a dbus-free module, import explicitly `from Pellmonweb.auth import require`). Add `@require()` on both `index` and `save`.

Effective-image resolution: use RESEARCH.md `effective_image` snippet; keep module-level `_warned` flag for D-06 one warning; the getter is injected (stub in tests) so the module never imports `dbus`. Treat `''` and `'error'` as unset (silently).

Save response shape: `json.dumps({'success': ...})`, matching pellmonconf; on 403 set `cherrypy.response.status = 403`.

### `src/Pellmonweb/pellmonweb.py` (modify)

**Dbus wrappers analog** (`Dbus_handler`, :187-199):
```python
def getItem(self, itm):
    with self.lock:
        try:
            return self.remote_object.GetItem(itm, dbus_interface ='org.pellmon.int')
        except:
            raise DbusNotConnected("server not running")
```
Add `get_setting(key)` / `set_setting(key, value)` identically, calling `GetSetting` / `SetSetting`.

**Mount analog** (`Root.__init__`, :238-239):
```python
self.logview = LogViewer(logfile, lookup)
self.auth = AuthController(credentials, lookup)
```
Add `self.settings = Settings(lookup, dbus)` alongside (constructor signature `(credentials, lookup)` style; `lookup` is the Mako TemplateLookup).

**systemimage** (:682-684), currently `return serve_file(system_image)`. Change to resolve per request and set no-cache, mirroring the existing header idiom at :~500 (`cherrypy.response.headers['Pragma'] = 'no-cache'`):
```python
@cherrypy.expose
def systemimage(self, **args):
    cherrypy.response.headers['Cache-Control'] = 'no-cache'
    return serve_file(effective_image(...))
```
`system_image` global is set at :903-907 (`os.path.join(os.path.join(MEDIA_DIR,'img'), parser.get('conf','system_image'))` with fallback `system.svg`); keep as config fallback. `systemimage` template (`html/systemimage`) already uses `data="systemimage?rand=%s"` with `rand=self.rand` (:241, `random.random()` once per process, so it does not bust cache; Cache-Control fixes that, see RESEARCH A1). `render(..., webroot=cherrypy.request.script_name, ...)` is the template context convention (:680): pass `webroot` and `username=cherrypy.session.get('_cp_username')` to settings.html too (layout.html needs `username`, `version`, etc.; read layout.html's top-of-file variables before rendering).

### `src/Pellmonsrv/pellmonsrv.py` (modify `MyDBUSService`)

**Analog:** `MyDBUSService` :157-168
```python
@dbus.service.method('org.pellmon.int')
def GetItem(self, param):
    """Get the value for a data/parameter item"""
    ...
@dbus.service.method('org.pellmon.int', out_signature='as')
def GetDB(self):
```
Add `GetSetting` (`in_signature='s', out_signature='s'`) and `SetSetting` (`in_signature='ss', out_signature='b'`) using `Keyval_storage.keyval_storage` (imported at :45 as `from .database import init_keyval_storage`; also import `Keyval_storage` class). Storage object is initialized at :75. Add daemon-side whitelist dict `ALLOWED_SETTINGS = {'web.system_image': validator}`; validator = regex `^system[a-z0-9_]*\.svg$` or a copied tuple. For unset keys avoid `readval` (returns `'error'` and calls `logger.exception`, database.py:176-187): add a small `hasval`/`getval(item, default='')` method to `Keyval_storage` (database.py, next to `readval`, same `with self.lock:` + `sqlite3.connect(self.dbfile)` structure).

Excerpt to copy for the new method (`database.py:176-187`):
```python
def readval(self, item):
    with self.lock:
        try:
            conn = sqlite3.connect(self.dbfile)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM keyval WHERE id=?", (item,))
            value, = next(cursor)
            conn.close()
            return value
        except Exception:
            logger.exception('error reading value for %s'%item)
            return 'error'
```
Write side: `writeval(item, value=None, confval=None)` (:189+). With `confval=None` it inserts `(select confvalue from keyval where id=?)`, which is NULL on first insert against `confvalue TEXT NOT NULL DEFAULT '-'` (:166). Pass `confval` explicitly (e.g. `writeval(key, value, confval='-')` is NOT safe either: the confval branch at :208-211 does `next(cursor)` on a missing row first; read the rest of writeval, lines 208-230, before choosing) or add a dedicated `setval`. Wave 0 test with real temp sqlite proves it.

### `src/Pellmonweb/html/layout.html` (modify)

**Analog** (lines 51-53):
```html
<li class="">
	<a href="${webroot}/logview/logView">View log</a>
</li>
```
Insert `<li class=""><a href="${webroot}/settings/">Settings</a></li>` after it (tab indentation as in file). Active state per UI-SPEC: pass a flag such as `active_page` (default via `context.get`) so other templates need no change.

### `src/Pellmonweb/html/settings.html` (new)

Extend layout as other pages do (check `html/parameters.html` or `logview` template for the `<%inherit file="layout.html"/>` and `<%block>`/`${self.body()}` convention before writing; not opened in this mapping). Escape all dynamic text with `${msg | h}`; render only whitelist values; radios inside `<fieldset><legend>`; POST form to `${webroot}/settings/save`. Copy tokens/copy strings from `08-UI-SPEC.md`.

### Tests

**`tests/Pellmonweb/test_settings_image.py`** analog `tests/Pellmonweb/test_pellmonconf_csrf.py`:
```python
def _post(cherrypy_request_ctx, **headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)

def test_cross_origin_rejected(inst, cherrypy_request_ctx, mocker):
    _post(cherrypy_request_ctx, Origin='http://evil.example', Host='localhost:8083')
```
Reuse fixture `cherrypy_request_ctx` (`tests/conftest.py`); stub the dbus wrapper with a fake object (no dbus import). Same-origin/missing-Origin/Referer-fallback cases map 1:1.

**`tests/Pellmonsrv/test_settings_store.py`** analog `tests/Pellmonsrv/test_database.py`:
```python
def test_writeval_readval_roundtrip(tmp_path):
    store = Keyval_storage(str(tmp_path / "test.db"))
    store.writeval("mykey", value="42")
    assert store.readval("mykey") == "42"
```
This existing first-insert round-trip suggests A2 (NOT NULL violation) may not bite, but `writeval` with `confval=None` and no prior row was only tested here; extend with unset-key returns `''` and the whitelist-rejection cases.

**`tests/test_backup_script.py`**: extend with a `web.system_image` row round-trip through the existing settings-db backup case (read the file for its fixture style first).

## Shared Patterns

### Auth gate
**Source:** `src/Pellmonweb/auth.py:105-115` (`require`), used as `@cherrypy.expose` then `@require()`. Apply to Settings `index` and `save`.

### CSRF (same-origin, fail closed)
**Source:** `_check_same_origin` (moved to `Pellmonweb/security.py`). Apply to `Settings.save` POST.

### Logging
`from logging import getLogger; logger = getLogger('pellMon')`; `%`-style args; use `warning` for rejections. No `print`.

### Error surface for D-Bus
`Dbus_handler` methods raise `DbusNotConnected("server not running")`; callers in the new controller catch it and show the UI-SPEC "daemon down" message; `effective_image` catches all exceptions and falls back to the config global.

### Whitelist both tiers
Web tuple `SYSTEM_IMAGES` in `settings.py` (intersected with `os.listdir(MEDIA_DIR/img)`); daemon `ALLOWED_SETTINGS`. Filenames: system.svg, system_nbe.svg, system_nbe_2w.svg, system_nbe_3w.svg, system_nbe_v7.svg, system_matene.svg (confirm against `src/Pellmonweb/media/img/` and `webinterface.conf.in` :36-43).

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `settings.html` gallery markup / `.sysimg-*` CSS | component | request-response | No existing radio-tile gallery; use UI-SPEC and Bootstrap 3 panels |

## Metadata

**Analog search scope:** `src/Pellmonweb`, `src/Pellmonsrv/{pellmonsrv,database}.py`, `tests/`
**Not opened (planner should read):** `html/layout.html` header vars, an existing page template for inherit syntax, `auth.py` no-credentials behavior (RESEARCH A3), `database.py:208-230`, `tests/test_backup_script.py`, rest of `test_pellmonconf_csrf.py`.
**Pattern extraction date:** 2026-09-21
