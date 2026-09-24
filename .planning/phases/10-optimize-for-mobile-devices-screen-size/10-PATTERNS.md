# Phase 10: Optimize for mobile devices screen size - Pattern Map

**Mapped:** 2026-09-24
**Files analyzed:** 27 new/modified (plus 4 extensionless consumption templates counted as one group)
**Analogs found:** 25 / 27 (2 have only partial analogs; see "No Analog Found")

Line numbers refer to the files as read on 2026-09-24. Templates/CSS/JS are edited in place, so for those the "analog" is the file itself plus the sibling whose idiom to copy.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/Pellmonweb/html/index.html` | template (grid loop) | request-response | itself (lines 15-24); `settings.html` line 23 for `col-xs-*` idiom | exact |
| `src/Pellmonweb/html/graph` | template (widget) | request-response | itself | exact |
| `src/Pellmonweb/html/events` | template (widget) | event-driven (`#lines` replaced by `getLog()`) | itself; `graph` for `data-*` attr idiom | exact |
| `src/Pellmonweb/html/systemimage` | template (widget) | request-response | no markup change (CSS only) | n/a |
| `src/Pellmonweb/html/parameters.html` | template (page) | CRUD (read/set params via JS) | itself; `settings.html` for panel/`col-xs` markup | exact |
| `src/Pellmonweb/html/settings.html` | template (page) | request-response | itself (line 23 already `col-xs-12 col-sm-6 col-md-4`) | exact |
| `src/Pellmonweb/html/consumption.html` | template (page) | request-response | itself (`col-md-6` x4) | exact |
| `src/Pellmonweb/html/layout.html` | template (shell) | request-response | itself (lines 33-43 navbar) | exact |
| `src/Pellmonweb/media/css/pellmon.css` | config (stylesheet) | n/a | itself: Phase 8 "settings page" block (lines 60-99), media rule (lines 37-46) | exact |
| `src/Pellmonweb/media/js/index.js` | component (client JS) | event-driven | itself lines 140-230 click handlers; `parameters.js` lines 15-32 | exact |
| `src/Pellmonweb/media/js/parameters.js` | component (client JS) | event-driven | itself lines 15-32 (`$('.editable').on('click', ...)`) | exact |
| `src/Pellmonsrv/plugins/consumption/__init__.py` (template string ~line 87) | plugin template string | request-response | itself; silolevel string | exact |
| `src/Pellmonsrv/plugins/silolevel/__init__.py` (template string ~line 109) | plugin template string | request-response | itself | exact |
| `src/Pellmonsrv/plugins/consumption/templates/consumption{24h,7d,8w,1y}` | template (widget) | request-response | itself (`style="height:400px"` line 2) | exact |
| `tests/Pellmonweb/test_mobile_layout.py` (new) | test (structural) | file-I/O text/regex + Mako render | `tests/Pellmonweb/test_settings_page.py`, `tests/Pellmonweb/test_source_js_no_html_sink.py` | exact |
| `tests/browser/conftest.py` (new) | test fixtures | subprocess + browser | `tests/conftest.py` (fixture idiom, docstring style) | role-match |
| `tests/browser/stub_server.py` (new) | test helper (server script) | request-response | `tests/Pellmonweb/test_settings_page.py` lines 78-109 (set module globals + fake dbus on `Pellmonweb.pellmonweb`); `pellmonweb.py run()` | partial |
| `tests/browser/fake_dbus.py` (new) | test helper (fake) | request-response | `_FakeDbus` in `test_settings_page.py` lines 85-88 | role-match |
| `tests/browser/plugin_templates.py` (new) | test helper (AST) | transform | `test_settings_page.py` `_class`/`_method` + `ast.get_source_segment` (lines 15-23) | role-match |
| `tests/browser/test_mobile_overflow.py` (new) | test (browser) | request-response | none for Playwright; text/assert style of `test_settings_page.py` | no analog (partial) |
| `tests/browser/test_mobile_interactions.py` (new) | test (browser) | event-driven | none for Playwright | no analog (partial) |
| `requirements-browser.txt` (new) | config | n/a | `requirements-dev.txt` | exact |
| `.github/workflows/ci.yml` (add steps to `test` job) | config (CI) | batch | itself lines 44-58 | exact |
| `tests/test_ci_docker_config.py` (additive asserts) | test | file-I/O text | itself `test_github_actions_workflow` lines 18-68 | exact |
| `tests/README.md` | doc | n/a | itself lines 60-66 | exact |
| `.gitignore` | config | n/a | existing `pellmon-data/` entry | exact |

## Pattern Assignments

### `src/Pellmonweb/html/index.html` (template, request-response)

**Analog:** itself + `settings.html:23`

Current loop (lines 15-24), the C3 bug (`12 / len(row)` renders `col-md-6.0` on Python 3):
```mako
    %for row in widgets:
        <div class="row">
            <% width = 12 / len(row) %>
            %for widget in row:
                <div class="col-md-${width}">
                    <%include file="${widget}"/>
                </div>
            %endfor
        </div>
    %endfor
```
Target: `<% width = 12 // len(row) %>` and `<div class="col-xs-12 col-md-${width}">`. The test asserts the exact strings `col-xs-12 col-md-${width}` and `12 // len(row)`. Grid-class idiom to copy from `settings.html:23`: `<div class="col-xs-12 col-sm-6 col-md-4">`.

### `src/Pellmonweb/html/graph` (template, request-response)

**Analog:** itself. Edit points:
- Line 3: `<div id="graph" style="height:400px"></div>` becomes `<div id="graph" class="pellmon-graph"></div>` (no inline height; flot `$.plot` in `index.js` needs a CSS-sized container, so the class rule must exist in always-loaded `pellmon.css`).
- Lines 10, 13, 19, 21: links built in `${'<a ... class="lineselection %s" ...>' % (...)}` Python-format strings. Keep the `%`-formatting and the `data-*` attributes (`data-linename`, `data-selected`, `data-time-choice`, `data-title-text`) unchanged; only add wrapper classes. `index.js` binds `$('.lineselection').click`, `$('.timeChoice').click`, `$('.autorefresh').click`, `$('.left')/$('.right').click` (lines 140-222), so keep those class tokens and the `.left`/`.right` classes on Back/Forward.
- Line 22: fix the malformed `</div   >`.
- Line 17: `<div class="pull-left">` must stay floated at >= 768px (reset only inside the phone media query).

### `src/Pellmonweb/html/events` (template, event-driven)

**Analog:** itself (3 lines) + `graph` for how `data-*` attributes are carried.

```mako
        <h4>Events</h4>
        <div id="lines" data-url="${webroot}/logview/getlines?linenum=7">
        </div>
```
Rules (RESEARCH C1/C5, Pitfall 5): keep `#lines` id and `data-url` untouched (`logview.js getLog()` does `container.html(data)` on it, `logview.js:19-22`); put the toggle button outside `#lines`; use `class="btn btn-default btn-block events-toggle visible-xs"` (BS 3.0.0 has no `visible-xs-block`); carry labels as `data-label-collapsed="Show all events"` / `data-label-expanded="Show fewer events"`. This template is included inside `<body>` before jQuery loads, so no inline `$` script here; the handler goes in `index.js`.

### `src/Pellmonweb/html/parameters.html` (template, CRUD)

**Analog:** itself, `settings.html` for panel markup.

Existing structure to modify: sidebar `col-md-2` with `nav nav-pills nav-stacked` (lines 29-38), content `col-md-10` (line 55) with `col-md-12` Control (58), `col-md-5` Data (71) and `col-md-5` Settings (90). Page-local `<style>` block (lines 7-25) owns `.details .form-inline .form-control {width:60%}`, only touch selectors it already owns there; everything else goes in `pellmon.css`. Keep the JS hooks `editable`, `details hidden`, `.select_enum`, `.save`, `.param.value`, `data-name`, ids `${key['name']}-value`, `-selectbox`, `-form` (used by `parameters.js`). Collapsible sections use Bootstrap 3.0.0 `data-toggle="collapse"`; the initially closed Settings trigger must carry `collapsed` in markup (plugin never sets it).

### `src/Pellmonweb/html/settings.html` / `consumption.html` / `layout.html`

- `settings.html:23` already `col-xs-12 col-sm-6 col-md-4`; D-05 wants 2-up on phones, so change to `col-xs-6 col-sm-6 col-md-4`. `test_settings_page.py` (radio/`checked`/`Current` counts) is unaffected.
- `consumption.html` lines 11, 14, 19, 22: `col-md-6` becomes `col-xs-12 col-md-6` (x4).
- `layout.html:35`: hamburger `<button data-target=".navbar-collapse" data-toggle="collapse" class="navbar-toggle" type="button">` gets `aria-label`, `aria-expanded="false"`, `sr-only` span. Do not change the viewport meta (line 8); a structural test asserts it exactly.

### `src/Pellmonweb/media/css/pellmon.css` (stylesheet)

**Analog:** itself. Conventions: plain selectors, one comment header per feature block, 4-space indent, existing single media rule:
```css
/* settings page: system image gallery */
.sysimg-tile {
    display: block;
    ...
    min-height: 44px;
```
```css
@media (min-width: 768px) {
    .dl-horizontal dt { width:250px; white-space: normal; }
```
Append one block headed `/* Phase 10: mobile / responsive */`. Existing rules to remember: `html { overflow-y: scroll; }` (line 6-8), global `object { width: 100%; }` (line 50), `.sysimg-tile-selected { border: 2px solid #337ab7; padding: 15px; }` (line 78; reset border on phones to avoid 1px size drift). No `overflow-x:hidden` on body/html (the overflow test detects it).

### `src/Pellmonweb/media/js/index.js` and `parameters.js` (client JS, event-driven)

**Analog:** `parameters.js:15-32` and `index.js:140-230`.

Style: jQuery, `.click(function(e){ e.preventDefault(); ...})` or `.on('click', ...)`, `.text()` for writes (`index.js:278 $('h4.graphtitle').text(title)`, `327 $('#conn-reason').text('')`). New handlers use the delegated form so they survive DOM replacement:
```javascript
$('.editable').on('click', function(e) {
	e.preventDefault();
	var me = $(this);
```
Events toggle: `$(document).on('click', '.events-toggle', function(e){ ... $(this).text(...) })` reading `data-label-*`. Aria sync (C2): `show.bs.collapse` / `hide.bs.collapse` handlers setting `aria-expanded`. No `.html(` in new code (repo rule; only `logview.js:22` still uses it for server-rendered log rows, do not extend).

### Plugin template strings and `plugins/consumption/templates/*`

**Analog:** themselves.
- `consumption/__init__.py:87-90`: `<div class="image-responsive" id="consumption" style="height:400px">` inside `self._insert_template('consumption', """...""")`.
- `silolevel/__init__.py:109-111`: `<div class="image-responsive" id="silolevel" style="height:400px">`.
- `consumption/templates/consumption7d` line 2: `<div id="consumption7d" style="height:400px">` (same in 24h, 8w, 1y).
Replace the inline style with `class="pellmon-chart"` in all six (C4). Keep the `id` values and the following `<script>` blocks (`$.plot($('#silolevel'), ...)`, `insertAfter`). `%`-style and plain triple-quoted strings stay as is; do not add a `.py2bak`.

### `tests/Pellmonweb/test_mobile_layout.py` (structural test, no imports of pellmonweb so it runs on Windows)

**Analog:** `tests/Pellmonweb/test_settings_page.py` and `test_source_js_no_html_sink.py`.

Header/paths idiom (`test_settings_page.py:3-16`):
```python
import ast
import re
import sys
from pathlib import Path

import pytest
from mako.lookup import TemplateLookup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
HTML_DIR = ROOT / "src" / "Pellmonweb" / "html"
```
Mako render helper (lines 155-160) to reuse for rendering `index.html`, `graph`, `events`, `parameters.html`, `settings.html` and asserting emitted classes:
```python
def render(name="settings.html", **kw):
    ctx = dict(username="u", webroot="", active_page="settings", images=images(),
               current=SYSTEM_IMAGES[1], msg="", msg_level="", auth_configured=True)
    ctx.update(kw)
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    return lookup.get_template(name).render(**ctx)
```
Regex-on-rendered-HTML assertions (lines 163-175): `re.findall(r'<input type="radio"[^>]*value="([^"]*)"', html)`, `html.count(" checked") == 1`. Text-file check idiom for JS (`test_source_js_no_html_sink.py:6-13`):
```python
SOURCE_JS = Path(__file__).resolve().parents[2] / "src" / "Pellmonweb" / "media" / "js" / "source.js"

def test_source_js_uses_text_not_html_for_filenames_and_errors():
    js = SOURCE_JS.read_text(encoding="utf-8")
    assert not re.search(r"\.html\(", js), ".html() sink found in source.js; use .text()"
```
Copy this for a "new toggle code uses `.text()`" check (do not assert `.html(` absent in whole `index.js`/`logview.js` blindly; `logview.js` legitimately has `container.html(data)`, so scope the assertion to the new handler block). AST helpers for the stub-drift guard (every `ast.Global` name in `run()` is assigned by the stub) come from lines 18-23:
```python
def _class(name):
    return next(n for n in ast.walk(TREE) if isinstance(n, ast.ClassDef) and n.name == name)
def _method(cls, name):
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
```
Docstring convention: module docstring one line; regression tests explain the failure they guard. Use `read_text(encoding="utf-8")` (`test_ci_docker_config.py` style; `test_settings_page.py:13` omits the encoding, avoid that on Windows). Unique module basenames (no `__init__.py` in test dirs). Plugin inline-height check must glob `plugins/consumption/templates/*` plus both `__init__.py` strings.

### `tests/browser/conftest.py`, `fake_dbus.py`, `stub_server.py`

**Analogs:** `tests/conftest.py` (fixture + docstring style), `_FakeDbus` in `test_settings_page.py`.

Fixture style (`tests/conftest.py:37-61`): decorator `@pytest.fixture`, docstring explaining the "codebase-specific gotcha", `mocker.patch...`. For browser fixtures use `scope="session"`, `yield`, teardown after yield, and the gate rule from RESEARCH (`PELLMON_BROWSER_TESTS` unset: skip; `1`: `pytest.fail` on any missing prerequisite). Guard pattern for platform-only libs already used in this suite:
```python
pytest.importorskip("cherrypy")
pytest.importorskip("dbus")
pytest.importorskip("gi")
```
Fake dbus and module-globals technique (`test_settings_page.py:85-101`):
```python
    class _FakeDbus:
        def get_setting(self, key):
            assert key == web.SETTING_KEY
            return 'system_nbe.svg'
    ...
    web.dbus = _FakeDbus()
    web.system_image_dir = str(HTML_DIR.parent / 'media' / 'img')
    web.system_image = str(HTML_DIR.parent / 'media' / 'img' / 'system.svg')  # the fallback
```
`myLookup` fallback that `FakeDbus.getPlugins(uri)` must satisfy (`pellmonweb.py:761-771`): on `TemplateLookupException` it calls `self.dbus.getPlugins(uri)` then `put_string(uri, plugin)`. Globals list to set in the stub comes from `pellmonweb.py run()` `global` statements (lines 814-974): `dbus, lookup, polling, db, colorsDict, polldata, graph_lines, logtick, credentials, logfile, system_image, system_image_dir, frontpage_widgets, timeChoices, timeNames, timeSeconds` (plus `consumption_graph`, `websockets` per RESEARCH; confirm against `run()` when writing the drift-guard test). Run the stub as a subprocess (own process is not subject to `--disable-socket`); read `READY port=N` from its stdout pipe.

### `tests/browser/plugin_templates.py`

**Analog:** AST idiom from `test_settings_page.py`. Extract the string from `self._insert_template('<name>', """...""")` calls (defined `plugin_categories.py:37 def _insert_template(self, name, template)`) via `ast.walk` for `ast.Call` with `func.attr == "_insert_template"` and `args[1]` an `ast.Constant`. No plugin import (avoids `grp`/`pwd`).

### `tests/browser/test_mobile_overflow.py`, `test_mobile_interactions.py`

No Playwright analog exists. Copy assertion style (`assert cond, "message"`) and module-header idiom from the existing tests; take probes (`OVERFLOW_JS`), waits (`#graph canvas`, `contentDocument` SVG, no `networkidle`) and viewport contexts from RESEARCH Patterns 2-4. Compare `scrollWidth` against the intended 390/768 constants.

### `requirements-browser.txt`

**Analog:** `requirements-dev.txt` (comment header + one pin per line):
```
# Test/dev-only dependencies -- NOT installed in production Docker image
pytest>=9.0,<10
```
New file: same header style, single line `playwright==1.63.0`.

### `.github/workflows/ci.yml` (extra steps in existing `test` job, after "Run test suite")

**Analog:** itself lines 37-58:
```yaml
      - name: Install Python dependencies
        run: |
          python -c "import sys; print(sys.executable)"
          pip --version
          pip install -r requirements.txt
          pip install pytest pytest-mock pytest-socket
      ...
      - name: Run test suite
        env:
          PYTHONPATH: src
        run: |
          pytest tests/ -v
```
Add steps in the same 6-space-indented, spaces-only format. Constraints from `test_ci_docker_config.py`: no tabs, no `actions/setup-python`, no `--force` (so not `--force-enable-socket`), no `install --upgrade pip`, keep `PYTHONPATH: src`, keep `pytest tests/` match, keep `needs: test` on `publish` (so the browser run stays a step of `test`, not a new job). Note the existing `pytest tests/ -v` will collect `tests/browser`; the fixtures skip when `PELLMON_BROWSER_TESTS` is unset so this stays green, but the browser tests must then run separately with `--allow-unix-socket`.

### `tests/test_ci_docker_config.py` (additive asserts)

**Analog:** `test_github_actions_workflow` (lines 18-68) and `test_publish_workflow_permissions_and_skip_ci`. Add a new function; do not edit existing ones. Idiom:
```python
def test_publish_workflow_permissions_and_skip_ci():
    """D-03/D-04: ..."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_path.read_text(encoding="utf-8")

    assert "needs: test" in content, "publish must be gated on the existing test job (D-03)"
```
New assertions in the same style with a decision-tagged message, e.g. `"tests/browser" in content`, `'PELLMON_BROWSER_TESTS: "1"' in content`, `"playwright install" in content`, `"--allow-unix-socket" in content`, `"actions/upload-artifact" in content`, and a `requirements-browser.txt` pinned-playwright check reading `REPO_ROOT / "requirements-browser.txt"`.

### `tests/README.md` and `.gitignore`

`tests/README.md:60-66` "Anything a later phase must not do" states no `--disable-socket` removal and no `@pytest.mark.enable_socket`; add a short section documenting the `--allow-unix-socket` exception (a CLI flag, no marker) and `PELLMON_BROWSER_TESTS`. `.gitignore`: add `tests/browser/_shots/` next to the existing `pellmon-data/` entry style.

## Shared Patterns

### JS writes text, never HTML
**Source:** `tests/Pellmonweb/test_source_js_no_html_sink.py:9-13`, `index.js:278,327`
**Apply to:** all new JS in `index.js`, `parameters.js`.
```javascript
$('h4.graphtitle').text(title);
$('#conn-reason').text('');
```

### `%`-formatted Python strings in Mako for links
**Source:** `graph` lines 10-21 (`${'<a ... %s ...>' % (...)}`)
**Apply to:** any new markup emitted from `graph`, `systemimage`; and `%`-formatting (not f-strings) in any plugin `__init__.py` edit per CLAUDE.md.

### Bootstrap 3.0.0 only
**Source:** vendored `media/bs3/css/bootstrap.css` v3.0.0
**Apply to:** every template class choice. Use `.visible-xs` (no `-block`), `col-xs-*`/`col-sm-*`/`col-md-*`, `data-toggle="collapse"`; put `collapsed` in markup; sync `aria-expanded` manually.

### Real handlers over a fake `dbus`
**Source:** `tests/Pellmonweb/test_settings_page.py:78-109`
**Apply to:** `tests/browser/stub_server.py`, `fake_dbus.py`. Set module globals on `Pellmonweb.pellmonweb`, do not re-implement handlers.

### Socket guardrail
**Source:** `pytest.ini` (`addopts = --disable-socket`), `tests/README.md:62-63`
**Apply to:** all `tests/browser/*`. No `enable_socket` marker, no removal of the addopts; the browser run in CI uses `--allow-unix-socket` and a subprocess stub server.

### Windows-safe structural tests
**Source:** `tests/Pellmonweb/test_settings_page.py` `importorskip` lines and `tests/README.md` (Pellmonweb.pellmonweb needs `gi`)
**Apply to:** `test_mobile_layout.py` must not import `Pellmonweb.pellmonweb`; use text/regex/AST/Mako only. Browser modules skip without `PELLMON_BROWSER_TESTS=1`.

### File header
Test files in `tests/` open with a one-line module docstring, no GPL header (unlike `src/Pellmonsrv/*`). Do not create `.py2bak` files.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `tests/browser/test_mobile_overflow.py` | test | browser-driven | No Playwright/headless-browser test exists; use RESEARCH Patterns 2-4 |
| `tests/browser/test_mobile_interactions.py` | test | browser-driven | Same |
| `tests/browser/stub_server.py` (partially) | helper server | request-response | Only the fake-dbus-on-module-globals technique exists; no subprocess CherryPy server or `cherrypy.tree.mount` test exists (see `test_engine_exit_process_restart.py` / `test_websocket_dbus_down.py` for possibly related process idioms, not read) |

## Metadata

**Analog search scope:** `tests/**`, `src/Pellmonweb/html`, `src/Pellmonweb/media/{css,js}`, `src/Pellmonsrv/plugins/{consumption,silolevel}`, `.github/workflows/ci.yml`, `requirements-dev.txt`, `pytest.ini`
**Files scanned:** about 30 (46 test files listed)
**Pattern extraction date:** 2026-09-24
