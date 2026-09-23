# Phase 8: Expose burner SVG in settings - Research

**Researched:** 2026-09-21
**Domain:** CherryPy/Mako web settings page + persistence across web/daemon containers
**Confidence:** HIGH (all findings from codebase reads; no new packages needed)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01 New "Settings" navbar entry (layout.html) -> page with sections ("System image" section; Phase 6 adds its own later). Not a one-off dialog.
- D-02 Only shipped SVGs selectable (filenames in webinterface.conf.in). Absolute paths stay config-file-only; GUI never accepts a free path.
- D-03 Thumbnail gallery of shipped variants, current marked, click to select, then Save. Thumbnails are the real SVGs from `/media/img/`.
- D-04 After save, main page shows new image on next load; no daemon restart.
- D-05 Choice stored in the Phase 7 data folder (`/var/lib/pellmon`), survives container recreation, included in backup tool. Precedence: GUI choice > `system_image` in webinterface.conf > `system.svg`.
- D-06 Invalid/missing stored value falls back to config value with one warning; never breaks the main page.
- D-07 Save requires same login as other write actions and same-origin (Origin/Referer) check as `pellmonconf.save`. Page not reachable without auth when auth configured.

### Claude's Discretion
- Storage mechanism (web-written file/sqlite vs daemon over D-Bus), honouring D-05 and uid 999 ownership.
- Thumbnail sizing, layout, wording (Bootstrap 3).
- Cache headers / cache-busting for `Root.systemimage`.

### Deferred Ideas (OUT OF SCOPE)
- Live value overlays / per-burner auto-selection; SVG upload via GUI; Home Assistant settings (Phase 6).
</user_constraints>

<phase_requirements>
## Phase Requirements
None assigned (TBD). Planner should derive from D-01..D-07.
</phase_requirements>

## Summary

The pivotal finding: in `docker-compose.yml` the `pellmonweb` service mounts the data folder **read-only** (`${PELLMON_DATA_DIR}/data:/var/lib/pellmon:ro`, line 138; Phase 7 D-04 kept it `:ro` deliberately). So the web process cannot write a file there. Writing directly would require dropping `:ro` (weakens Phase 7 decision, and the web process runs as the same uid 999 image user) [VERIFIED: docker-compose.yml].

The daemon already owns a persistent, 0600, uid-999-owned SQLite settings DB (`Keyval_storage`, `pellmon_settings.db`, table `keyval(id,value,confvalue)`) in exactly that folder, and `tools/pellmon_backup.py` already backs it up via the SQLite backup API [VERIFIED: database.py, pellmon_backup.py backup_local]. Storing the choice there satisfies D-05 (persistent, in backup) with zero backup-tool change and zero compose change.

**Primary recommendation:** Add two D-Bus methods on `MyDBUSService` (`GetSetting(key)`, `SetSetting(key,value)`) in `pellmonsrv.py`, restricted server-side to a whitelist (`web.system_image`), backed by `Keyval_storage.keyval_storage`. Web side adds wrappers in `Dbus_handler`, a `settings` controller with `@require()` + same-origin check on POST, and `Root.systemimage` resolves the effective image per request with fallback to the config global.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary | Rationale |
|---|---|---|---|
| Persist choice | Daemon (pellmonsrv, Keyval_storage) | - | Only writer of /var/lib/pellmon; web mount is :ro |
| Whitelist validation | Web (Pellmonweb) | Daemon (re-validate) | Defense in depth; daemon must not store arbitrary keys/values |
| Auth + CSRF | Web | - | `require()` + same-origin |
| Serve effective image | Web (`Root.systemimage`) | - | Resolve per request; fallback to config |
| Thumbnails | Static (/media/img/) | - | Existing static route |

## Standard Stack
No new packages. Uses existing CherryPy >=18.8, Mako >=1.2, dbus-python, sqlite3 (stdlib), Bootstrap 3 (bundled at `media/bs3`). Package Legitimacy Audit: not applicable (no installs).

## Architecture Patterns

### Data flow
```
Browser -GET /settings-> Settings.index (@require) -> Dbus_handler.get_setting -D-Bus-> daemon Keyval readval
Browser -POST /settings/save (image=system_nbe.svg)-> require + _check_same_origin -> whitelist check
        -> Dbus_handler.set_setting -D-Bus-> daemon whitelist re-check -> Keyval writeval (pellmon_settings.db in /var/lib/pellmon)
Browser -GET systemimage?rand=..-> Root.systemimage -> effective_image(): stored (whitelisted, file exists) else config global else system.svg -> serve_file
```

### Pattern: shared whitelist
Define `SYSTEM_IMAGES = ('system.svg','system_nbe.svg','system_nbe_2w.svg','system_nbe_3w.svg','system_nbe_v7.svg','system_matene.svg')` in one small module (e.g. `src/Pellmonweb/settings.py`); these match files present in `src/Pellmonweb/media/img/` and the Choices comment in `webinterface.conf.in` [VERIFIED]. Better: build the list by intersecting the constant with `os.listdir(MEDIA_DIR/img)` so a missing file is never offered. The daemon should hold its own copy of the same tuple (daemon does not import Pellmonweb) or validate with a strict regex `^system[a-z0-9_]*\.svg$`; no path separators possible.

### Effective image resolution (D-05/D-06)
```python
def effective_image(self):
    try:
        v = dbus.get_setting('web.system_image')   # '' when unset
        if v in SYSTEM_IMAGES:
            p = os.path.join(MEDIA_DIR, 'img', v)
            if os.path.isfile(p): return p
        elif v: warn_once('invalid stored system_image %r' % v)
    except Exception:
        pass   # daemon down -> config fallback, never break the page
    return system_image  # module global from webinterface.conf
```
Warn once via a module-level flag (D-06 "one warning").

### Anti-Patterns
- Accepting a filename and joining it to a path without whitelist (path traversal; D-02).
- Removing `:ro` from the web data mount (breaks Phase 7 D-04).
- Writing the choice into `conf.d/*.conf` (web `conf.d` mount is writable in name only: host-owned, not writable by uid 999 per compose comment; and edits need restart).

## Don't Hand-Roll
| Problem | Use Instead |
|---|---|
| Persistent settings store | Existing `Keyval_storage` (writeval/readval) |
| CSRF check | Existing `_check_same_origin` logic (see Pitfall 3) |
| Login gating | Existing `require()` from auth.py |
| Backup of the setting | Already covered by settings DB backup |

## Common Pitfalls

1. **`Keyval_storage.readval` returns the string `'error'` (and logs an exception) for a missing key** [VERIFIED: database.py]. Do not call it for an unset key naively: in the daemon `GetSetting`, check existence first (add a small `hasval`/direct SELECT, or treat any non-whitelisted result incl. `'error'` as unset). Otherwise every main-page image request logs a stack trace. Also `writeval(item, value)` with `confval=None` does the `INSERT OR REPLACE` with a subselect for confvalue; a first insert gets `confvalue` NULL against `NOT NULL DEFAULT '-'`, which can raise IntegrityError. Safest: call `writeval(key, value, confval=value)`-style or add a dedicated small method; plan a unit test with a real temp sqlite file to prove the first insert works.
2. **Per-request D-Bus call latency / daemon down.** `systemimage` is fetched each page load; wrap in try/except with short fallback. Cache the stored value in the web process (module var) and update it on save, with a TTL (e.g. 30 s) is optional; simple per-request call is acceptable at this traffic.
3. **`_check_same_origin` lives in `pellmonconf.py`**, which is a separate app (port 8083, separate module importing directories). Importing it into pellmonweb.py works but couples modules; better to move to a tiny shared helper (e.g. `Pellmonweb/security.py`) and have pellmonconf import it, keeping `tests/Pellmonweb/test_pellmonconf_csrf.py` passing (it patches through `Pellmonconf.save`). Behavior: requires Origin or Referer present and netloc == Host; a missing header is rejected (fails closed) [VERIFIED].
4. **Auth when authentication not configured.** `require()` (used at pellmonweb.py lines 503-628) is the existing gate; use exactly the same decorator on both GET and POST of the settings page. Check auth.py for how it behaves with no credentials (current code logs "web UI will reject all logins until credentials configured", so write pages are effectively locked until hashes exist; document this in the UI message).
5. **Browser caching of the SVG.** The `<object data="systemimage?rand=%s">` already adds `rand=self.rand` [VERIFIED: html/systemimage]; check what `self.rand` is (if constant per process it will not bust the cache after a change). Fix: set `Cache-Control: no-cache` in `Root.systemimage` (`cherrypy.response.headers`) and/or include the filename in the query (`systemimage?img=<name>`) as the cache key. Also note the `caching` tool imported in pellmonweb.py: confirm it is not applied to `/systemimage`.
6. **`serve_file` needs an absolute path** and correct content type; SVG served via `serve_file` gets `image/svg+xml` by extension. Keep using it.
7. **Thumbnails in the gallery:** use `<img src="${webroot}/media/img/system_nbe.svg">` (not `<object>`) to avoid script execution/size issues; CSS max-height. Radio inputs with labels, plus the CSRF-safe POST form; JS optional (progressive enhancement, form works with no JS).
8. **Mako auto-escaping / XSS:** render only whitelist values; flash messages must be escaped (`${msg | h}`).
9. **Do not run `Pellmonweb` tests requiring dbus under venv-wsl** (CONTEXT: dbus tests under system python). Keep new logic (whitelist, effective_image, same-origin helper) importable without dbus by placing it in a dbus-free module.

## Code Examples

Daemon (pellmonsrv.py, in `MyDBUSService`, style-matched):
```python
@dbus.service.method('org.pellmon.int', in_signature='s', out_signature='s')
def GetSetting(self, key):
    if key not in ALLOWED_SETTINGS: return ''
    return conf_settings_get(key)   # '' when unset, never 'error'

@dbus.service.method('org.pellmon.int', in_signature='ss', out_signature='b')
def SetSetting(self, key, value):
    if key not in ALLOWED_SETTINGS or not ALLOWED_SETTINGS[key](value): return False
    Keyval_storage.keyval_storage.writeval(key, value); return True
```
Web save endpoint:
```python
@cherrypy.expose
@require()
def save(self, image=''):
    if cherrypy.request.method != 'POST' or not check_same_origin():
        cherrypy.response.status = 403; return json.dumps({'success': False, 'error': 'rejected'})
    if image not in SYSTEM_IMAGES: return json.dumps({'success': False, 'error': 'unknown image'})
    ok = dbus.set_setting('web.system_image', image)
    return json.dumps({'success': bool(ok)})
```
Route: mount as `Root.settings` (nested object `settings = Settings()`) so URL is `/settings/`; add `<li><a href="${webroot}/settings/">Settings</a></li>` in layout.html after "View log".

## Backup / docs
- `tools/pellmon_backup.py`: **no code change** if stored in Keyval DB (already archived as `pellmon_settings.db`; restore path verifies sqlite). Add a test/assertion in `tests/test_backup_script.py` that a `web.system_image` row round-trips. If planner instead chose a separate file, backup would need changes; not recommended.
- Update `DEPLOY-PI.md` (data folder/backup section, ~lines 141-160, 229-233) and the comment in `webinterface.conf.in` ("used unless overridden in Settings page").
- No `docker-compose.yml` change required.

## Runtime State Inventory
Not a rename phase. New state: one row `web.system_image` in `pellmon_settings.db`; no OS/service registrations.

## Environment Availability
No new external dependencies. dbus/gi needed only for the integration path (Linux/Docker); not available on the Windows dev venv, so unit tests must avoid importing dbus.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-mock, pytest-socket per conftest) [VERIFIED: tests/conftest.py] |
| Config | tests/conftest.py, fixture `cherrypy_request_ctx` for fake request/session |
| Quick run | `pytest tests/Pellmonweb/test_settings_image.py -x -q` |
| Full suite | `pytest tests -q` (venv-wsl; dbus-dependent under system python) |

### Requirements -> Test Map
| ID | Behavior | Type | Command | Exists |
|----|----------|------|---------|--------|
| D-02 | non-whitelisted / traversal names (`../x`, `/etc/passwd`, `system.svg/../..`) rejected | unit | `pytest tests/Pellmonweb/test_settings_image.py::test_whitelist -x` | Wave 0 |
| D-05 | precedence stored > config > system.svg (effective_image with stubbed getter) | unit | `...::test_precedence` | Wave 0 |
| D-06 | invalid/missing/'error'/daemon-raises falls back, one warning only | unit | `...::test_fallback_warns_once` | Wave 0 |
| D-07 | cross-origin/missing-Origin POST rejected; same-origin accepted; unauthenticated rejected | unit | `...::test_save_csrf` (mirror test_pellmonconf_csrf.py) | Wave 0 |
| D-05 | daemon setting round-trip in real temp sqlite (first insert works, unset returns '') | unit | `tests/Pellmonsrv/test_settings_store.py` | Wave 0 |
| D-05 | backup archive contains the row | unit | `pytest tests/test_backup_script.py -k system_image` | extend |
| D-01 | layout has Settings link; page template renders all 6 thumbnails, current checked, escaped | unit (Mako render) | `...::test_template` | Wave 0 |
| D-04 | systemimage response has no-cache header / changing choice changes served path | unit | `...::test_systemimage_headers` | Wave 0 |
| Guard | every whitelist entry exists in media/img; matches webinterface.conf.in Choices | unit | `...::test_whitelist_files_exist` | Wave 0 |
| D-03/D-04 | Live UAT on Pi: choose image, save, reload, restart containers, still selected | manual | checklist in DEPLOY-PI/UAT | manual (needs Docker+D-Bus) |

### Sampling
Per commit: quick file; per wave: `pytest tests -q`; phase gate: full suite green plus Pi UAT.

### Wave 0 Gaps
- [ ] `tests/Pellmonweb/test_settings_image.py`, `tests/Pellmonsrv/test_settings_store.py`
- [ ] dbus-free helper module (whitelist, effective_image logic, same-origin) so tests import without dbus
- [ ] Guard a no-print/no-sys.path-shim compliance (existing tests `test_no_ad_hoc_print.py`, `test_no_sys_path_shims.py` apply to new code: use `logger`, not `print`)

## Security Domain
| ASVS | Applies | Control |
|---|---|---|
| V2/V3 Auth/Session | yes | existing `require()` |
| V4 Access control | yes | POST needs login + same-origin |
| V5 Input validation | yes | strict whitelist, both tiers |
| V6 Crypto | no | - |

Threats: path traversal / arbitrary file serving (whitelist, no free path; Tampering/Info disclosure), CSRF on save (same-origin, fail closed on missing headers), arbitrary key write via D-Bus (daemon whitelist of keys AND values; session bus is private to the compose stack), XSS via stored value (whitelist + `| h`).

## Assumptions Log
| # | Claim | Risk |
|---|---|---|
| A1 | `self.rand` may be constant per process so cache-busting via it is insufficient (not read in this session) | Stale image after save; mitigated by no-cache header either way |
| A2 | First `writeval(item, value)` with confval None may violate the NOT NULL confvalue (reasoned from the SQL, not executed) | Save fails silently; test in Wave 0 covers it |
| A3 | `require()` behavior with no configured credentials not re-read (auth.py not opened) | Planner should read auth.py before finalizing |

## Open Questions
1. Should the setting key be namespaced `web.system_image` in the shared keyval table? Recommended yes (Phase 6 MQTT will add its own keys; `ALLOWED_SETTINGS` dict is the extension point).
2. Daemon-down behavior on the settings page: show "daemon unavailable, cannot save" (recommended) rather than falling back to file write.

## Sources
- Primary (codebase, HIGH): docker-compose.yml (web mount `:ro`, lines 129-141), src/Pellmonweb/pellmonweb.py (systemimage ~683, system_image ~903), pellmonconf.py (`_check_same_origin`, `save`), src/Pellmonsrv/database.py (Keyval_storage), pellmonsrv.py (MyDBUSService, keyval_db path), tools/pellmon_backup.py, html/layout.html, html/systemimage, tests/conftest.py, tests/Pellmonweb/test_pellmonconf_csrf.py, webinterface.conf.in.

## Metadata
Confidence: stack HIGH, architecture HIGH, pitfalls MEDIUM-HIGH (A1-A3 unverified by execution).
Valid until: 30 days.
