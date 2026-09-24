# Phase 10: Optimize for mobile devices screen size - Research

**Researched:** 2026-09-24
**Domain:** Responsive Bootstrap 3.0.0 / Mako / flot web UI, plus headless-browser layout verification in CI (Playwright, pytest, GitHub Actions)
**Confidence:** MEDIUM-HIGH (codebase findings HIGH; Playwright-in-this-CI recommendation MEDIUM until the Wave 0 spike passes)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Stay on the vendored Bootstrap 3. No framework upgrade or replacement. Use its existing `col-xs-*`/`col-sm-*` classes, `collapse`, and utility classes, plus targeted rules in `media/css/pellmon.css`.
- **D-02:** Design and verify at two widths: **390px** (primary phone target) and **768px** (tablet). Nothing may cause horizontal page scroll at either width. Desktop rendering (>= 992px) must not change.
- **D-03:** On phones the dashboard is a **single column**: system image first, then events, graph, consumption, silo level. The **events list is collapsed by default** on phones (a short preview with a tap-to-expand control). The SVG system image scales to the screen width (already an `<object>` with `image-responsive`; confirm it does not overflow or become unreadable).
- **D-04:** Graph height becomes **responsive** (about 260px on phones, keep 400px on desktop) instead of fixed `style="height:400px"`. `.lineselection`, `.timeChoice`, autorefresh become **larger tap targets** (>= 44px touch height) that wrap cleanly. Keep Back/Forward buttons. **No touch pan/pinch** gestures.
- **D-05:** Controls on **Parameters** and **Settings** stack vertically on phones (label above input, full-width inputs, >= 44px touch height) using `col-xs`/`col-sm`. **Settings image gallery = 2 tiles per row** on phones. **Parameters page gets collapsible sections** (Bootstrap collapse).
- **D-06:** Done means all of: (a) structural pytest checks (viewport meta present, no fixed pixel widths/heights that break at 390px in templates, required responsive classes present, in the style of the existing AST/text assertion tests); (b) **automated headless-browser checks in CI** that render the key pages at 390px and 768px and fail on horizontal overflow; (c) the user checks the real pages on their phone through `https://stoker.schoeler.pro/` (manual human-verify checkpoint).

### Claude's Discretion
- Exact CSS breakpoint values within the 390/768 targets, and how the events collapse is implemented (Bootstrap collapse vs small JS toggle), as long as it does not break websocket-driven event updates in `media/js/index.js`.
- Which headless browser tool to use for D-06(b) and how to serve pages to it in CI (static Mako output with stub data vs real stack). Must run on `ubuntu-latest`, must not add `actions/setup-python`.
- Where new CSS lives (extend `pellmon.css` or a small dedicated stylesheet).

### Deferred Ideas (OUT OF SCOPE)
- Touch pan/pinch gestures on the graph (flot navigate plugin).
- Compact status header with Diagram/Graph/Events tabs.
- PWA manifest / "add to home screen" / offline support.
- Dark mode.
- Upgrading off Bootstrap 3.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01 | Stay on vendored Bootstrap 3 | Vendored version is **3.0.0** (not 3.3): several classes/behaviours the UI-SPEC assumes do not exist (see "Corrections to the UI-SPEC") |
| D-02 | 390/768 verification, no horizontal scroll, desktop unchanged | Playwright overflow harness (Validation Architecture), `col-md-6.0` bug affects "desktop unchanged" |
| D-03 | Single-column dashboard, collapsed events, scaling SVG | `col-xs-12 col-md-N`, events wrap + toggle (`visible-xs` not `visible-xs-block`), `object#systemimage` aspect-ratio rule |
| D-04 | Responsive graph height, 44px controls | `.pellmon-graph`/`.pellmon-chart` CSS; **six** files hold inline 400px (not two) |
| D-05 | Stacked Parameters/Settings controls, 2-up gallery, collapsible sections | BS 3.0.0 collapse behaviour (no `aria-expanded` management), `collapsed` initial class |
| D-06 | Structural tests + CI headless checks + manual phone check | Playwright + stub server design, pytest-socket interplay, CI wiring that satisfies `tests/test_ci_docker_config.py` |
</phase_requirements>

## Summary

The UI-SPEC is sound and detailed, but researching the real code turned up **six facts that change the plan** (listed under "Corrections to the UI-SPEC"). The most important: (1) the vendored Bootstrap is **3.0.0**, which has no `visible-xs-block` and whose collapse plugin does not maintain `aria-expanded`; (2) `index.html` computes `width = 12 / len(row)`, which under Python 3 renders `col-md-6.0`/`col-md-12.0`, so **no `col-md-*` rule matches today and the desktop dashboard is already stacked** (a migration bug, not a design), meaning "desktop unchanged" and the fix `12 // len(row)` are in tension and need an explicit user-visible decision; (3) the four consumption chart templates (`plugins/consumption/templates/consumption{24h,7d,8w,1y}`, extensionless files) also hard-code `height:400px` and the UI-SPEC only names the two `__init__.py` strings, and the dashboard's default `consumption7d` widget is one of those files.

For D-06(b), recommend **Playwright (Python, sync API) with its bundled Chromium**, a **stub server run as a subprocess that imports the real `Pellmonweb.pellmonweb` module and mounts the real `PellMonWeb` handlers over a fake `Dbus_handler`** (option c, in its cheapest form), and **a step inside the existing `test` job** (not a new job). The two hard constraints discovered in the repo are: `pytest.ini` has `--disable-socket` (Playwright's asyncio loop needs a Unix `socketpair`, so the browser tests need `--allow-unix-socket`), and `tests/test_ci_docker_config.py` asserts `"--force" not in content` and `"needs: test" in content` on `ci.yml` (so `--force-enable-socket` and a `needs: [test, browser]` publish gate are both forbidden without editing that guard test). Local runs stay green because the browser fixtures skip unless `PELLMON_BROWSER_TESTS=1`; CI sets it, which turns a missing browser into a hard failure.

**Primary recommendation:** Add `tests/Pellmonweb/test_mobile_layout.py` (structural, runs everywhere) plus `tests/browser/` (Playwright + real-handlers stub server, opt-in by env var, mandatory in CI as an extra step of the existing `test` job run with `--allow-unix-socket`), and apply the six UI-SPEC corrections below before writing plans.

## Corrections to the UI-SPEC (planner must apply)

| # | UI-SPEC says | Reality (verified) | Required change |
|---|--------------|--------------------|-----------------|
| C1 | Events toggle uses `visible-xs-block` | Vendored `media/bs3/css/bootstrap.css` is **v3.0.0**; `grep visible-xs-block` = 0 matches. Only `.visible-xs` exists (`display:block !important` below 768px, `display:none !important` otherwise). [VERIFIED: codebase grep] | Use `class="btn btn-default btn-block events-toggle visible-xs"`. Without this the toggle is visible at 768px+ and E1 fails. |
| C2 | "Bootstrap 3 updates `aria-expanded` on toggle" | 3.0.0 `collapse` data-api only toggles the `collapsed` class on the trigger; **no `aria-expanded` handling** (`grep aria-expanded bootstrap.js` = 0). [VERIFIED: codebase grep] Also the plugin never sets the initial `collapsed` class. | Add ~6 lines of JS in `index.js`/`parameters.js` on `show.bs.collapse`/`hide.bs.collapse` (events exist in 3.0.0) to sync `aria-expanded` for the Parameters toggles and the navbar hamburger. Put the `collapsed` class **in the markup** on the initially-closed Settings toggle (`class="param-section-toggle btn btn-default btn-block collapsed"`). |
| C3 | Change `col-md-${width}` to `col-xs-12 col-md-${width}` | `width = 12 / len(row)` is float division in Python 3: rendered `col-md-6.0`, `col-md-12.0` (reproduced with Mako). No Bootstrap `.col-md-6.0` rule exists, so on the current build desktop widgets are unstyled full-width blocks. [VERIFIED: reproduced] | Use `<% width = 12 // len(row) %>`. This is a **visible desktop change** (restores the intended side-by-side systemimage/events and consumption/silolevel). Needs explicit user confirmation (Open Question 1). Structural check #2 must assert `//`. |
| C4 | Plugin inline heights are in two `__init__.py` strings | Also in four extensionless template files: `src/Pellmonsrv/plugins/consumption/templates/consumption24h`, `consumption7d`, `consumption8w`, `consumption1y` (`style="height:400px"` on line 2 of each). `consumption7d` is the dashboard's default widget; all four are on the Consumption page. The UI-SPEC's `*.py,*.html` style greps miss them. [VERIFIED: codebase grep] | Edit all six sources to `class="pellmon-chart"` (drop the inline height). Structural checks #3b/#9 must scan `plugins/*/templates/*` and both `__init__.py` strings. |
| C5 | Events toggle via "~10-line inline script at the bottom of the events template (or index.js)" | The `events` widget is included inside `<body>` **before** jQuery loads (scripts are at the end of `layout.html`). An inline `$`-based script there throws. | Put the handler in `index.js` (delegated: `$(document).on('click', '.events-toggle', ...)`), or write vanilla JS. Keep the two strings in the template as `data-label-collapsed="Show all events"` / `data-label-expanded="Show fewer events"` on the button so structural check #4 still finds them in the template. Use `.text()`, never `.html()` (repo convention, see `test_source_js_no_html_sink.py`). |
| C6 | `object#systemimage` "already has `image-responsive`" | `image-responsive` is not a Bootstrap class (only `.img-responsive` exists), so it is a **no-op** everywhere it appears (systemimage, both plugin strings). | Harmless; do not rely on it. The explicit `object#systemimage` rule in the UI-SPEC is the real fix. Keep the class token or not; do not "fix" the spelling in a way that changes desktop rendering. |

Smaller observations (no action unless cheap): default `system.svg` viewBox is 330x280 (ratio 1.18) but the phone rule forces the object to ratio 11/7, so the SVG is letterboxed (about 270px wide inside the 360px object). Acceptable and within the spec; verify visually in the manual checkpoint. On phones the existing `.sysimg-tile-selected` keeps `border: 2px`, so the selected tile is 1px larger per side than the others unless the phone block also resets `border: 1px solid #337ab7` (the spec's inset-shadow intent). At >= 768px a keyboard-activated `.param-section-toggle` still toggles `.in` (pointer-events:none only blocks the mouse); `display:block !important` keeps the content visible, so this is cosmetic only.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Responsive grid / breakpoints / tap targets | Browser (CSS in `pellmon.css`) | Frontend server (Mako class attributes) | Pure presentation; server only emits `col-xs-12 col-md-N` and wrapper classes |
| Events collapse, section chevrons, aria sync | Browser (small JS in `index.js`/`parameters.js`) | Frontend server (markup, data attributes) | State is client-only, not persisted |
| Graph/chart height | Browser (CSS classes) | API tier (plugin template strings served over D-Bus) | Heights move from inline style to `.pellmon-graph`/`.pellmon-chart` CSS; plugin strings only swap the class |
| Plugin widget templates (consumption/silolevel) | Daemon (`pellmonsrv` plugins, delivered via `getPlugins` D-Bus call) | Frontend server (`myLookup` fallback) | Templates live in the daemon image; the web process fetches them by name |
| Mobile layout verification | CI (Playwright test process) | Test-only stub web server | Never shipped in the runtime image (`.dockerignore` excludes `tests/`, Dockerfile installs only `requirements.txt`) |

## Standard Stack

### Core (test-time only; not shipped)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| playwright (Python) | 1.63.0 (pip index shows it as latest; requires Python >= 3.10; classifiers list 3.10-3.14) | Headless Chromium driver, mobile emulation (`is_mobile`, `device_scale_factor`, `has_touch`), full-page screenshots | First-party Microsoft tool, one pip package pins driver + browser build, documented CI recipe `playwright install --with-deps chromium` |
| pytest / pytest-mock / pytest-socket | already installed in CI | Test runner | Existing suite |

No new **runtime** dependency. Chromium comes from `playwright install`, not from apt or the Docker image.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Playwright bundled Chromium | Playwright `channel="chrome"` using the runner's preinstalled Google Chrome (runner image lists Chrome 152 + ChromeDriver, [CITED: actions/runner-images Ubuntu2404-Readme]) | Skips the ~100MB download but Chrome floats with the runner image (geometry/flakiness drift); Playwright docs still say to run `playwright install chrome`; unverified without a run. Keep as a fallback only. |
| Playwright | Selenium + preinstalled ChromeDriver | Works on runners without a download, but mobile emulation and per-element rect/screenshot ergonomics are weaker, and Chrome/ChromeDriver float with the image. |
| Playwright | pyppeteer | Unmaintained [ASSUMED]; do not use. |
| Playwright | `apt install chromium` | On Ubuntu 24.04 the `chromium-browser` package is a snap stub, unreliable on CI [ASSUMED]; avoid. |
| `pytest-playwright` plugin | plain `playwright.sync_api` with own fixtures | Plugin adds its own CLI options/fixtures and interacts with `--disable-socket`/`pytest-asyncio` (installed locally); own 30-line fixtures are simpler and controllable. Use plain `playwright`. |

**Installation (CI step, after the existing pip install; note ci.yml must not contain `--force` or `install --upgrade pip`):**
```bash
pip install -r requirements-browser.txt          # contains: playwright==1.63.0
playwright install --with-deps --only-shell chromium
```
`requirements-browser.txt` is a new file (keeps the 38 MB wheel out of `requirements-dev.txt` and out of the Docker build). `--only-shell` installs just the headless shell that `launch(headless=True)` uses [CITED: playwright.dev/python/docs/browsers]; if the flag misbehaves in the spike, drop it.

**Version verification:** `pip index versions playwright` on 2026-09-24 listed 1.63.0 as latest; `pip download playwright==1.63.0` fetched a 38.6 MB wheel; PyPI JSON reports `requires_python >=3.10`, homepage github.com/Microsoft/playwright-python. Publish date not obtained. The CI runner's system python3 (Ubuntu 24.04) is 3.12 [ASSUMED], within range.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| playwright | PyPI | multi-year (versions back to 1.9.0) | not retrieved | github.com/Microsoft/playwright-python | unavailable (pip install slopcheck ran, `slopcheck` command not found) | Tagged [ASSUMED] per protocol; corroborated by official docs (playwright.dev/python) and PyPI metadata. Planner: add one `checkpoint:human-verify` before adding the pin, or accept the corroboration. |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none (slopcheck could not run; pip packages have no npm-style postinstall scripts)

## Architecture Patterns

### System Architecture Diagram

```
pytest (CI step, PELLMON_BROWSER_TESTS=1, --allow-unix-socket)
   |
   |-- session fixture: spawn stub server subprocess  ------------------------.
   |        python tests/browser/stub_server.py  (PYTHONPATH=src)             |
   |        prints "READY port=NNNNN" on stdout (read via pipe, no TCP)       v
   |                                                       +------------------------------+
   |                                                       | stub_server.py (own process, |
   |                                                       | not subject to pytest-socket)|
   |                                                       |  import Pellmonweb.pellmonweb|
   |                                                       |  set module globals (dbus=   |
   |                                                       |  FakeDbus, lookup=myLookup,  |
   |                                                       |  graph_lines, ...)           |
   |                                                       |  mount StubWeb(PellMonWeb)   |
   |                                                       |  /media -> src/Pellmonweb/   |
   |                                                       |  media (staticdir)           |
   |                                                       +---------------+--------------+
   |                                                                       ^ HTTP 127.0.0.1
   |-- session fixture: sync_playwright -> chromium (headless shell)       |
   |        context(viewport=390x844, dsf=2, is_mobile, has_touch)  ------+
   |        route CDN jQuery -> local media/jquery/jquery.min.js
   |
   |-- per (page, width): goto -> wait for flot canvas / SVG doc -> run JS probes
   |        scrollWidth / element rects / computed styles  -> assertions
   |        full_page screenshot -> $PELLMON_SHOTS_DIR  -> actions/upload-artifact
   v
 pass / fail (fail-not-skip when PELLMON_BROWSER_TESTS=1)

Stub request path (real code, fake data):
 GET /  -> PellMonWeb.index -> FakeDbus.getFullDB/getItem -> Mako index.html
        -> <%include file="consumption7d"/> -> myLookup miss -> FakeDbus.getPlugins(name)
        -> plugin template text (file under plugins/*/templates or AST-extracted _insert_template string)
 GET /export (overridden in StubWeb) -> canned flot JSON
 GET /consumptionview/flotconsumption7d -> FakeDbus.getItem -> canned bar JSON
```

### Recommended Project Structure
```
tests/
  Pellmonweb/
    test_mobile_layout.py        # D-06(a) structural, no browser, runs on Windows + Linux
  browser/
    conftest.py                  # env gate, stub server + playwright fixtures, CDN route
    stub_server.py               # script (not collected); real handlers + FakeDbus
    fake_dbus.py                 # canned getFullDB/getItem/getMenutags/getPlugins/get_setting
    plugin_templates.py          # AST extraction of _insert_template(...) strings (shared with structural test)
    test_mobile_overflow.py      # A1-A3 across pages x widths
    test_mobile_interactions.py  # B/C/D/E acceptance conditions
requirements-browser.txt         # playwright==1.63.0
```
Existing test dirs have no `__init__.py`, so test module basenames must be unique across `tests/` (use the names above).

### Pattern 1: Stub server = real handlers over a fake Dbus (recommended option c)
**What:** A standalone script imports `Pellmonweb.pellmonweb` (needs `gi`/`dbus`, present in the CI job), assigns the module globals that `run()` normally creates, subclasses `PellMonWeb` only to replace `export` with canned JSON, mounts it with session tool on and `tools.auth.on` **off** (so `@require()` pages such as `/parameters/Overview` and `/settings/` render without login), and serves `/media`.
**Why this over (a) and (b):**
- (a) Pure Mako render to static files + `http.server`: no gi/dbus needed, but it re-implements the context built in `index()`/`parameters()` and the relative-URL routes (`systemimage?rand=`, `export`, `graphsession`, `getlines`) so it drifts from real code.
- (b) Real stack with dbusmock: needs a dbus-daemon session in the runner and `python-dbusmock`; highest fidelity but slowest and most fragile; overkill for layout-only assertions.
- (c) is one process, no D-Bus daemon, real `index()`/`parameters()`/`settings`/`logview`/`consumption`/`auth` handlers and the real `myLookup` plugin-template fallback. The `test_settings_page.py` file already sets `web.dbus = _FakeDbus()` on this module, so the technique is established.

**Globals the stub must set** (from `run()`; add an AST guard test that every `ast.Global` name in `run()` is assigned by the stub, so drift fails loudly): `dbus, lookup, polling, db, colorsDict, polldata, graph_lines, logtick, credentials, logfile, system_image, system_image_dir, frontpage_widgets, timeChoices, timeNames, timeSeconds, consumption_graph, websockets`.

```python
# tests/browser/stub_server.py  (sketch; Source: derived from src/Pellmonweb/pellmonweb.py run())
import os, sys, tempfile, cherrypy
from Pellmonweb import pellmonweb as web
from tests.browser.fake_dbus import FakeDbus   # or sys.path tweak; keep import style used elsewhere in tests

MEDIA = os.path.join(os.path.dirname(web.__file__), "media")
HTML = os.path.join(os.path.dirname(web.__file__), "html")

web.websockets = False            # index.js -> setupPolling (deterministic, no ws upgrade)
web.dbus = FakeDbus()
web.lookup = web.myLookup(directories=[HTML], dbus=web.dbus)
web.polling = True; web.db = ""; web.logtick = None; web.consumption_graph = True
web.credentials = []              # login page renders; nothing authenticates
web.logfile = write_sample_log()  # ~40 lines incl. one 200-char unbroken token
web.system_image_dir = os.path.join(MEDIA, "img")
web.system_image = os.path.join(MEDIA, "img", "system.svg")
web.frontpage_widgets = [["systemimage", "events"], ["graph"], ["consumption7d", "silolevel"]]
web.timeChoices = ["time1h", "time3h", "time8h", "time24h", "time3d", "time1w"]
web.timeNames = [t.replace(" ", "&nbsp;") for t in ["1 hour","3 hours","8 hours","24 hours","3 days","1 week"]]
web.timeSeconds = [3600, 3*3600, 8*3600, 24*3600, 3*86400, 7*86400]
web.polldata = []; web.colorsDict = {}
web.graph_lines = [ {"name": n, "color": c, "ds_name": n} for n, c in EIGHT_LINES ]  # long labels supplied by FakeDbus.getFullDB

class StubWeb(web.PellMonWeb):
    @cherrypy.expose
    def export(self, **kw):
        cherrypy.response.headers["Content-Type"] = "application/json"
        return CANNED_FLOT_JSON

cherrypy.config.update({"tools.sessions.on": True, "server.socket_host": "127.0.0.1",
                        "server.socket_port": 0, "log.screen": False, "engine.autoreload.on": False})
cherrypy.tree.mount(StubWeb(), "/", {"/media": {"tools.staticdir.on": True, "tools.staticdir.dir": MEDIA}})
cherrypy.engine.start()
print("READY port=%d" % cherrypy.server.httpserver.bind_addr[1], flush=True)
cherrypy.engine.block()
```
`FakeDbus.getPlugins(name)`: first look for a file `src/Pellmonsrv/plugins/*/templates/<name>`, else use AST-extracted `_insert_template('<name>', """...""")` strings from `plugins/*/__init__.py` (finds `consumption` and `silolevel`; no plugin activation, works without `grp`/`pwd`). The same helper backs the structural test for the plugin inline heights.
`FakeDbus.getFullDB` for `/`: items with `name`/`label` matching `graph_lines`. For `/parameters/*`: about 12 R items, 8 R/W items (some with `get_enum_list`, some with `min`/`max`), 4 W commands, with long `longname`/`description` values; `getMenutags` returns about 8 tags (to exercise two-per-row pills). `getItem('burner_connection')` returns `'connected'`.

### Pattern 2: Session-scoped Playwright fixtures with hermetic jQuery
`layout.html` loads jQuery from the CDN (`//ajax.googleapis.com/.../jquery/1.11.0/jquery.min.js`) with a *relative* fallback (`media/jquery/jquery.min.js`) that 404s on any nested URL (`/parameters/Overview`). Make CI hermetic by routing the CDN URL to the vendored file (same 1.11.0):
```python
ctx.route("**/ajax.googleapis.com/**",
          lambda r: r.fulfill(path=JQUERY_MIN, content_type="application/javascript"))
```

### Pattern 3: Overflow probes (A1-A3)
```python
OVERFLOW_JS = """
(W) => {
  const de = document.documentElement, b = document.body;
  const out = {scrollW: de.scrollWidth, bodyScrollW: b.scrollWidth, clientW: de.clientWidth,
               bodyOverflowX: getComputedStyle(b).overflowX, htmlOverflowX: getComputedStyle(de).overflowX,
               viewport: !!document.querySelector('meta[name=viewport]'), offenders: []};
  const clipped = (el) => { for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'hidden' || ox === 'auto' || ox === 'scroll') {
        const r = p.getBoundingClientRect(); if (r.right <= W + 1) return true; } } return false; };
  for (const el of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > W + 1 && !clipped(el))
      out.offenders.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + String(el.className).split(' ').join('.') + ' right=' + Math.round(r.right));
  }
  return out;
}"""
# assert res["scrollW"] <= WIDTH and res["bodyScrollW"] <= WIDTH and not res["offenders"]
# assert res["viewport"] and res["bodyOverflowX"] != "hidden" and res["htmlOverflowX"] != "hidden"
```
Compare against the **intended** width constant (390/768), not `window.innerWidth`: under `is_mobile=True`, Chromium can widen the layout viewport to fit overflowing content, which would make `scrollWidth <= innerWidth` pass vacuously. Note `pellmon.css` has `html { overflow-y: scroll }`; that computes `overflow-x` to `auto` (not `hidden`), so the masking check on `<html>` is still meaningful.

### Pattern 4: Waiting without `networkidle`
Pages poll (`setupPolling` re-arms a 15s timer; the graph optionally autorefreshes) so `networkidle` never settles reliably. Wait on concrete signals:
- flot drawn: `page.wait_for_selector("#graph canvas")`; charts: `#consumption7d canvas`, `#silolevel canvas`.
- SVG loaded: `page.wait_for_function("() => { const o = document.getElementById('systemimage'); return o && o.contentDocument && o.contentDocument.querySelector('svg'); }")`.
- Bootstrap collapse animates (`.collapsing`, ~350ms): assert with `expect`/`wait_for_function` on the `in` class, not immediate `offsetHeight`.
- Use `locator.bounding_box()`/`evaluate` for rects; `has_touch=True` is set, so `locator.tap()` works, `click()` also fine.

### Anti-Patterns to Avoid
- **`body { overflow-x: hidden }` as a fix** (forbidden by UI-SPEC and detected by A3).
- **Booting the daemon or D-Bus in CI for a layout test** (slow, flaky, no added layout fidelity).
- **`networkidle` waits, fixed `sleep`s.**
- **`.html()` in new JS** (repo convention; use `.text()`).
- **Adding `@pytest.mark.enable_socket` or removing `--disable-socket`** (`tests/README.md` forbids both).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mobile viewport/DPR emulation | Manual UA/window resizing | `browser.new_context(viewport=..., device_scale_factor=2, is_mobile=True, has_touch=True)` | `is_mobile` makes Chromium honour the meta viewport (the thing being tested) |
| Collapsible sections | Custom show/hide JS | Bootstrap 3.0.0 `data-toggle="collapse"` | Already vendored; only add the small aria sync (C2) |
| Responsive grid | Custom flex grid | `col-xs-*`/`col-sm-*`/`col-md-*` | D-01 |
| Serving pages for the browser | A second copy of the context-building code | Real `PellMonWeb` handlers over `FakeDbus` | Avoids drift from `index()`/`parameters()` |
| Plugin template lookup in tests | Regex-scraping ad hoc in each test | One AST helper (`plugin_templates.py`) | Used by both the stub and the structural test |
| Test-time graph data | Real rrdtool | Canned flot JSON in `StubWeb.export` | The graph endpoint shells out to rrdtool against a non-existent RRD |

**Key insight:** the layout risks live in the templates plus CSS; everything the templates need at render time can be produced by a fake `getFullDB/getItem/getPlugins`. Reusing the real handlers means the test fails when a handler changes what the templates receive.

## Common Pitfalls

### Pitfall 1: `--disable-socket` blocks Playwright's own event loop
**What goes wrong:** `pytest.ini` has `addopts = --disable-socket`. Playwright's sync client runs an asyncio loop, whose selector self-pipe uses `socket.socketpair()` (Unix domain), so launching the browser raises `SocketBlockedError`.
**How to avoid:** Run the browser tests with `--allow-unix-socket` (documented pytest-socket option; TCP from the test process stays blocked, which is exactly what we want because Chromium and the stub server do the networking). Read the stub's port from its stdout pipe, not by connecting. Do **not** use `--force-enable-socket` in `ci.yml`: see Pitfall 2. Fallback if the spike shows `--allow-unix-socket` is insufficient: `pytest -o addopts="" tests/browser`. [MEDIUM: pytest-socket README says `--allow-unix-socket` is for async use; that asyncio `socketpair` is covered was not confirmed by a run, so it is the first Wave 0 spike.]
**Warning signs:** `SocketBlockedError` from `asyncio/selector_events.py` or `playwright/_impl`.

### Pitfall 2: `test_ci_docker_config.py` guards on `ci.yml` text
Verified assertions that constrain the workflow edit [VERIFIED: file read]:
- `"--force" not in content` (so `--force-enable-socket` is forbidden; use `--allow-unix-socket`).
- `"needs: test" in content` (a `publish` job with `needs: [test, browser]` or a list breaks it). Hence the browser run is a **step in the existing `test` job**, which keeps `publish` gated on it automatically with zero guard-test edits.
- `"actions/setup-python" not in content`, `"install --upgrade pip" not in content`, no tabs, `PYTHONPATH: src` present, `pytest\s+tests/` regex must still match, `"workflow_run" not in content`, `"git tag -f"` absent.
- New assertions to add to that file: browser step present (`tests/browser`, `PELLMON_BROWSER_TESTS: "1"`, `playwright install`, `--allow-unix-socket`, an `upload-artifact` step), so nobody silently removes the mandatory gate.

### Pitfall 3: Silent skip in CI
If the gate is only "skip when playwright missing", CI could go green having run nothing. **Avoid:** the fixtures call `pytest.skip` only when `PELLMON_BROWSER_TESTS` is unset; when it is `1`, import/launch failure calls `pytest.fail`. Also run the CI step with `-rs` and add the ci.yml guard test above.

### Pitfall 4: Bootstrap 3.0.0 gaps (see C1, C2)
Also: no `.visible-*-block`, no `aria-expanded` sync, `collapsed` class must be pre-set in markup for closed sections, `.hidden`/`.visible-xs` use `!important`. Anything the UI-SPEC copies from 3.3 docs must be checked against `media/bs3/css/bootstrap.css` (v3.0.0) before use.

### Pitfall 5: Events toggle vs. `getLog()`
`logview.js` `getLog()` replaces `#lines` innerHTML on every event (`container.html(data)`), and also runs once on load. Keep the toggle outside `#lines`, keep `#lines` id/`data-url`, and never bind handlers to children of `#lines` from the toggle code. On `/logview/logView` the same `#lines` id gets the `#lines { overflow-wrap:anywhere }` rule (intended: the log page must not overflow either). Log rows are a `table table-striped table-bordered`; `overflow-wrap:anywhere` (not `break-word`) is what lets auto table layout shrink cells, so keep `anywhere` for `#lines`.

### Pitfall 6: flot needs a sized container and assets
`$.plot` throws on zero-width/height containers. `#graph` gets height from `.pellmon-graph` (must be in `pellmon.css`, always loaded), and `index.js` calls `$.plot($('#graph'), [], options)` on DOM ready, so a missing height rule surfaces as a JS error, not just a bad layout. The consumption/silo divs need the same (`.pellmon-chart`). flot assets come from `media/flot/*` (loaded by the page's `scripts`), so the stub only has to serve `/media`. The `#tooltip` is appended to `body` with `position:absolute`; the spec's `max-width:200px` prevents overflow.

### Pitfall 7: Websocket / polling JS in the stub
With the real `websockets = True`, `<object data-websocket=1>` makes `index.js` open `ws://host/websocket/ws/...`; the stub does not mount that. Set `web.websockets = False` in the stub so `setupPolling()` runs (`/getparamlist` is real and `FakeDbus.getdb()` returns a list). Note `setupPolling` waits for the SVG subdocument's `text` elements with ids `paramname:*`; a missing SVG doc only causes a 1s retry loop, not an error.

### Pitfall 8: `<object>` SVG sizing
`aspect-ratio` on `<object>` is supported by Chromium >= 88 and iOS Safari 15+ [ASSUMED]; the rendered test B2 (`#systemimage` 340-360 wide, >= 230 tall) is the authority. Do not gate on `contentDocument` geometry, only on the object element.

### Pitfall 9: Plugin template caching
`myLookup.get_template` calls `put_string` after the first plugin fetch, so the web process caches plugin templates for its lifetime. Deploying the plugin-string edits requires the new image (daemon supplies templates) and a web restart; both come with a normal `docker compose up` of the new image. No code change, but mention in the manual checkpoint (hard refresh, ensure both containers were recreated).

## Code Examples

### Structural test idiom (D-06a) matching the existing style
```python
# tests/Pellmonweb/test_mobile_layout.py
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "src" / "Pellmonweb" / "html"
CSS = (ROOT / "src" / "Pellmonweb" / "media" / "css" / "pellmon.css").read_text(encoding="utf-8")
PLUGINS = ROOT / "src" / "Pellmonsrv" / "plugins"

def test_viewport_meta_exact_and_zoom_allowed():
    t = (HTML / "layout.html").read_text(encoding="utf-8")
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in t
    assert "user-scalable" not in t and "maximum-scale" not in t

def test_dashboard_columns_use_integer_division_and_xs12():
    t = (HTML / "index.html").read_text(encoding="utf-8")
    assert "col-xs-12 col-md-${width}" in t and "12 // len(row)" in t

def test_no_inline_400px_anywhere_including_plugin_templates():
    files = [HTML / "graph", PLUGINS / "consumption" / "__init__.py", PLUGINS / "silolevel" / "__init__.py",
             *(PLUGINS / "consumption" / "templates").glob("*")]
    for f in files:
        assert "height:400px" not in f.read_text(encoding="utf-8").replace(" ", ""), f.name
    for f in [PLUGINS / "consumption" / "__init__.py", PLUGINS / "silolevel" / "__init__.py",
              *(PLUGINS / "consumption" / "templates").glob("*")]:
        assert "pellmon-chart" in f.read_text(encoding="utf-8"), f.name
```
Structural checks 1-9 from the UI-SPEC map 1:1 onto tests like these (all text/regex; no imports of `pellmonweb`, so they run on Windows).

### Browser gate fixture
```python
# tests/browser/conftest.py (sketch)
import os, pytest
MANDATORY = os.environ.get("PELLMON_BROWSER_TESTS") == "1"

def _unavailable(msg):
    (pytest.fail if MANDATORY else pytest.skip)(msg)

@pytest.fixture(scope="session")
def browser():
    if not MANDATORY and os.environ.get("PELLMON_BROWSER_TESTS") != "0" and not os.environ.get("PELLMON_BROWSER_TESTS"):
        pytest.skip("set PELLMON_BROWSER_TESTS=1 to run headless-browser layout tests")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _unavailable("playwright not installed")
    pytest.importorskip("gi") if not MANDATORY else None      # stub imports pellmonweb (gi/dbus)
    pw = sync_playwright().start()
    try:
        b = pw.chromium.launch()
    except Exception as e:
        _unavailable("chromium not launchable: %s" % e)
    yield b
    b.close(); pw.stop()
```
(Keep the gate logic simple in the real file: unset -> skip with reason; `1` -> hard fail on any missing prerequisite.)

### CI step (fits the guard tests)
```yaml
      - name: Install browser test dependencies
        run: |
          pip install -r requirements-browser.txt
          playwright install --with-deps --only-shell chromium

      - name: Run mobile layout browser tests
        env:
          PYTHONPATH: src
          PELLMON_BROWSER_TESTS: "1"
          PELLMON_SHOTS_DIR: ${{ runner.temp }}/pellmon-shots
        run: |
          pytest tests/browser -v -rs --allow-unix-socket

      - name: Upload layout screenshots
        if: always()
        uses: actions/upload-artifact@v7
        with:
          name: mobile-layout-screenshots
          path: ${{ runner.temp }}/pellmon-shots
          retention-days: 7
          if-no-files-found: ignore
```
`upload-artifact` latest major was v7 on the releases page when fetched [CITED: github.com/actions/upload-artifact/releases; the page's dates looked unreliable, so confirm the tag exists]. Existing docker actions in this file are already on v4-v7 majors.

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `playwright install chromium` (full browser incl. headed) | `--only-shell` headless shell for headless CI | Smaller download; `launch(headless=True)` uses it [CITED: playwright.dev/python/docs/browsers] |
| Viewport-only emulation | `is_mobile=True` + `device_scale_factor` + `has_touch` | Meta viewport honoured, touch events enabled [CITED: playwright.dev/python/docs/emulation] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `--allow-unix-socket` alone is enough for Playwright's asyncio `socketpair` under `--disable-socket` | Pitfall 1 | Browser tests fail at launch; fallback `-o addopts=""` (Wave 0 spike decides) |
| A2 | `playwright install --with-deps --only-shell chromium` works on ubuntu-latest with the venv CLI (about 1 minute) | Standard Stack | Drop `--only-shell` or run `python -m playwright ...`; CI +1-2 min |
| A3 | Runner system python3 is 3.12 (within playwright's `>=3.10`) | Standard Stack | Version pin adjustments |
| A4 | `chromium-browser` on Ubuntu 24.04 is a snap stub; pyppeteer unmaintained | Alternatives | None (not recommended anyway) |
| A5 | `aspect-ratio` on `<object>` works in Chromium and iOS Safari 15+ | Pitfall 8 | Fallback: wrapper div with padding-bottom ratio (B2 test catches it in Chromium; only the manual phone check covers Safari) |
| A6 | `playwright` package legitimacy (slopcheck unavailable) | Package Audit | Supply-chain risk; mitigated by official-docs corroboration |
| A7 | CI cost +1-2 min on the existing `test` job is acceptable | Recommendation | Could move to a separate job at the price of editing the `needs: test` guard test |
| A8 | Restoring side-by-side desktop widgets (fix `col-md-6.0`) is what the user wants | Correction C3 | Desktop "unchanged" contract violated visibly; needs user confirmation |

## Open Questions

1. **Fix `col-md-6.0` (C3) in this phase?**
   - Known: on the current Python 3 build the desktop dashboard renders stacked because of the float class token; CONTEXT says desktop must not change, but the intended (Py2/original) layout is two-up.
   - Recommendation: fix with `12 // len(row)` (the phase already edits that exact line and phones need `col-xs-12` there). Have the planner list it as an explicit deviation and let the human-verify checkpoint confirm the desktop look on `https://stoker.schoeler.pro/`. If the user prefers strictly unchanged desktop, keep `12 / len(row)` and drop the 1280 "side by side" smoke assertion (assert stacked instead).
2. **`--allow-unix-socket` sufficiency** (A1): resolve with a 15-minute spike in Wave 0 before writing the rest of the harness.
3. **Consumption page (`/consumptionview/consumption`) on phones**: the four charts each draw a `<p>` summary after the div (`insertAfter`, one floated right). With 260px charts this should be fine; the browser test covers overflow only.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python + venv (dev, Windows) | structural tests | yes | 3.14.0 | none needed |
| playwright (pip) locally | browser tests (opt-in) | no (not installed) | - | tests skip unless `PELLMON_BROWSER_TESTS=1`; can be run in WSL (`venv-wsl`) |
| `gi`/`dbus` locally (Windows) | stub server importing pellmonweb | no | - | browser tests skip on Windows; run in WSL or CI |
| Chromium via `playwright install` | CI | installed at run time | bundled with playwright 1.63.0 | `channel="chrome"` (runner Chrome) |
| Google Chrome on runner | fallback only | yes per runner-images README (152.x) | - | - |
| slopcheck | package audit | no (command not found after pip install) | - | packages tagged [ASSUMED] |
| Network from runner | `playwright install`, apt | yes (standard GH runner) | - | - |

**Missing dependencies with no fallback:** none.
**Missing with fallback:** local playwright/gi (skip locally, mandatory in CI).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x (+ pytest-mock, pytest-socket); browser layer adds playwright 1.63.0 |
| Config file | `pytest.ini` (`pythonpath = src`, `testpaths = tests`, `addopts = --disable-socket`); no change |
| Quick run command | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonweb/test_mobile_layout.py tests/test_ci_docker_config.py -q` |
| Full suite command | `pytest tests/ -v` (browser tests skip when `PELLMON_BROWSER_TESTS` unset) |
| Browser command (CI/WSL) | `PELLMON_BROWSER_TESTS=1 PYTHONPATH=src pytest tests/browser -v -rs --allow-unix-socket` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | No new framework; BS3 classes only (`col-xs-*`, `collapse`), no new stylesheet/link | structural | `pytest tests/Pellmonweb/test_mobile_layout.py -k "framework or css_block"` | Wave 0 |
| D-02 | No horizontal overflow at 390 and 768 on 6 pages; body/html not `overflow-x:hidden`; 1280 smoke | browser | `pytest tests/browser/test_mobile_overflow.py` | Wave 0 |
| D-03 | Order/size of systemimage, events collapsed + toggle, single column at 390/768 | browser + structural | `pytest tests/browser/test_mobile_interactions.py -k "main"` ; structural checks #2, #4 | Wave 0 |
| D-04 | `.pellmon-graph`/`.pellmon-chart` heights 260/320/400, no inline 400px in 6 sources, control tap targets >= 44 | structural + browser | structural #3b/#8/#9; browser B4/B5/B7/E1 | Wave 0 |
| D-05 | Parameters sections/pills/inputs, Settings 2-up + 44px buttons | structural + browser | structural #5/#6/#7; browser C1-C3/D1-D2/E2-E3 | Wave 0 |
| D-06(a) | Structural pytest checks | unit | `pytest tests/Pellmonweb/test_mobile_layout.py` | Wave 0 |
| D-06(b) | Browser checks mandatory in CI | CI guard | `pytest tests/test_ci_docker_config.py` (new asserts: browser step, env var, `--allow-unix-socket`, upload-artifact; existing guards still pass) | modify existing file |
| D-06(c) | Real phone check via stoker.schoeler.pro | manual | human-verify checkpoint (main page, graph controls, events, Parameters sections, 2-up gallery, no sideways scroll, desktop col fix C3) | n/a |
| (extra) | Stub drift guard: every `global` name in `run()` is set by the stub; JS aria sync present | structural | `pytest tests/Pellmonweb/test_mobile_layout.py -k "stub or aria"` | Wave 0 |

### Sampling Rate
- **Per task commit:** quick command above (about 2 s, Windows-safe).
- **Per wave merge:** `pytest tests/ -v` locally plus, for CSS/JS/template waves, the browser command in WSL or CI.
- **Phase gate:** full suite green including the CI browser step, then the D-06(c) manual checkpoint.

### Wave 0 Gaps
- [ ] Spike: prove `pytest tests/browser --allow-unix-socket` can launch Playwright under `--disable-socket` (else use `-o addopts=""`).
- [ ] `requirements-browser.txt` (`playwright==1.63.0`).
- [ ] `tests/Pellmonweb/test_mobile_layout.py` (structural checks 1-9 plus C1-C5/C4 additions, stub-drift guard).
- [ ] `tests/browser/{conftest.py, stub_server.py, fake_dbus.py, plugin_templates.py, test_mobile_overflow.py, test_mobile_interactions.py}`.
- [ ] `tests/test_ci_docker_config.py`: add browser-step assertions (do not touch existing ones).
- [ ] `.gitignore`: `tests/browser/_shots/` (default of `PELLMON_SHOTS_DIR` locally).
- [ ] `tests/README.md`: document `--allow-unix-socket` exception (no `enable_socket` marker is introduced) and `PELLMON_BROWSER_TESTS`.

## Security Domain

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (unchanged) | Existing `@require()`; the stub disables `tools.auth` only inside the test process bound to 127.0.0.1 |
| V3 Session Management | no | unchanged |
| V4 Access Control | no | unchanged; stub is CI-only and never in the image |
| V5 Input Validation | minimal | New JS sets static strings via `.text()`; no user data in the toggle; events content path (`#lines`) untouched |
| V6 Cryptography | no | none |

### Known Threat Patterns
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| DOM injection via new JS | Tampering | `.text()`/`textContent` only (repo rule, cf. `test_source_js_no_html_sink.py`) |
| Test tooling leaking into prod | Elevation | `requirements-browser.txt` separate; Dockerfile installs only `requirements.txt`; `.dockerignore` excludes `tests/` |
| Third-party CDN script in CI | Tampering | Route CDN jQuery to the vendored copy so CI executes only repo files |
| Supply chain (new pip package) | Tampering | Pin `playwright==1.63.0`; slopcheck unavailable so audit row flagged [ASSUMED] |

## File List the Phase Implies (refined)

**Modify**
- `src/Pellmonweb/html/layout.html`: hamburger `aria-label`, `aria-expanded`, `sr-only` span (viewport meta unchanged).
- `src/Pellmonweb/html/index.html`: `col-xs-12 col-md-${width}` and `12 // len(row)` (C3).
- `src/Pellmonweb/html/graph`: drop inline height, `pellmon-graph`, wrapper classes, fix `</div   >`.
- `src/Pellmonweb/html/events`: `#events-wrap`, toggle button (`visible-xs`, data-label attrs).
- `src/Pellmonweb/html/systemimage`: no markup change required (CSS rule targets `object#systemimage`).
- `src/Pellmonweb/html/parameters.html`: grid classes, `.param-tags`, three collapsible sections (Settings trigger pre-marked `collapsed`), page-local style additions only for selectors it already owns.
- `src/Pellmonweb/html/settings.html`: `col-xs-6 col-sm-6 col-md-4`.
- `src/Pellmonweb/html/consumption.html`: `col-xs-12 col-md-6` x4.
- `src/Pellmonweb/media/css/pellmon.css`: one appended `/* Phase 10: mobile / responsive */` block.
- `src/Pellmonweb/media/js/index.js` (events toggle + aria sync for navbar) and `parameters.js` (aria sync for sections). Both keep `.text()`-only style.
- `src/Pellmonsrv/plugins/consumption/__init__.py` (line ~87), `src/Pellmonsrv/plugins/silolevel/__init__.py` (line ~109), and the four `src/Pellmonsrv/plugins/consumption/templates/consumption{24h,7d,8w,1y}` files (C4).
- `.github/workflows/ci.yml` (extra steps in `test` job), `tests/test_ci_docker_config.py` (additive asserts), `tests/README.md`, `.gitignore`.

**Create:** `requirements-browser.txt`, `tests/Pellmonweb/test_mobile_layout.py`, `tests/browser/*` (above).

**Existing tests touched by these edits:** none found asserting the 400px strings or the affected templates (grep of `tests/`); `test_settings_page.py` renders `settings.html` and asserts radios/`checked`/`Current` counts, none of which change with `col-xs-6`. `test_plugin_rrd_bytes.py` imports the plugin modules but only exercises rrd parsing.

**Desktop (>= 992px) regression risks**
- C3 (`col-md-6.0` fix) is a deliberate visible change (Open Question 1).
- The `.param-section-toggle` link is a `btn btn-default btn-block` restyled to look like the old `h3` at >= 768px; hover/focus/`:active` background rules from `.btn-default` beat a plain `background:none` (use `.param-section-toggle, .param-section-toggle:hover, :focus, :active` or `!important`) and `.btn` `white-space:nowrap` must be reset. Verify Parameters at 1280 by geometry (sections visible, headings similar size) and by eye in the manual checkpoint.
- Global `img, object, svg { max-width:100% }` and `.container { overflow-wrap: break-word }` apply on desktop too; low risk (navbar brand image, plugin charts unaffected).
- Graph wrappers: `.graph-times.pull-left` / `.graph-nav.pull-right` must stay floated at >= 768px (only reset inside the phone query).
- `col-xs-12` adds float on `< md` widths where blocks used to stack; `.row` clearfix makes it equivalent, verified only by the E1 tablet assertion.

## Sources

### Primary (HIGH confidence)
- Repository files read: `10-CONTEXT.md`, `10-UI-SPEC.md`, `.github/workflows/ci.yml`, `tests/test_ci_docker_config.py`, `tests/Pellmonweb/test_settings_page.py`, `tests/conftest.py`, `pytest.ini`, `tests/README.md`, `src/Pellmonweb/pellmonweb.py`, `html/*`, `media/css/pellmon.css`, `media/js/{index,logview,parameters}.js`, `media/bs3/css/bootstrap.css` (v3.0.0), `media/bs3/js/bootstrap.js`, `plugins/{consumption,silolevel}/__init__.py`, `plugins/consumption/templates/*`.
- Mako render reproduction of `12 / len(row)` -> `6.0`.
- playwright.dev/python/docs/browsers (channel, `--with-deps`, `--only-shell`, cache path), playwright.dev/python/docs/emulation (`is_mobile`, `device_scale_factor`, `has_touch`).
- PyPI JSON for playwright (version 1.63.0, requires_python >= 3.10) and `pip index versions`.

### Secondary (MEDIUM confidence)
- github.com/miketheman/pytest-socket README (option semantics: `--force-enable-socket` overrides `--disable-socket`; `--allow-unix-socket` exists for async use).
- actions/runner-images Ubuntu2404-Readme (Chrome/ChromeDriver preinstalled, version 152.x at the time of the search).
- github.com/actions/upload-artifact/releases (v7 latest).

### Tertiary (LOW confidence)
- Install-time and CI-cost estimates, snap-stub claim for Ubuntu chromium, aspect-ratio browser support (all flagged [ASSUMED] above).

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM. Playwright choice is well supported; slopcheck unavailable and the socket-guard interplay is unverified until the spike.
- Architecture: HIGH for stub-with-real-handlers (globals enumerated from source, `test_settings_page.py` precedent); MEDIUM for `FakeDbus` completeness until first run.
- Pitfalls: HIGH for the Bootstrap 3.0.0 / `col-md-6.0` / six-file / CI-guard findings (all reproduced from the repo); MEDIUM for runtime pitfalls (socketpair, aspect-ratio).

**Research date:** 2026-09-24
**Valid until:** about 2026-10-24 (Playwright ships roughly monthly; re-check the pin at plan time)
