# Phase 10: Optimize for mobile devices screen size - Context

**Gathered:** 2026-09-24
**Status:** Ready for planning

<domain>
## Phase Boundary

The PellMon web UI is comfortable to read and operate on a phone (about 390px wide) and stays
correct on tablets (about 768px), without changing what it shows on desktop. In scope: the main
dashboard, the graph widget, the Parameters page, and the Settings page (plus the shared
navbar/layout they sit in). Out of scope: new features, new pages, a framework upgrade, and
touch-gesture graph navigation.

Today the site already has a viewport meta tag and a collapsing navbar (Bootstrap 3, vendored at
`src/Pellmonweb/media/bs3/`), but every page lays out with `col-md-*` only (no `col-xs`/`col-sm`
anywhere), the graph is a fixed 400px, the graph's line/time-range controls are small text links,
and `pellmon.css` has a single `@media` rule.

</domain>

<decisions>
## Implementation Decisions

### Framework and breakpoints
- **D-01:** Stay on the vendored Bootstrap 3. No framework upgrade or replacement — that is a
  separate, larger change. Use its existing `col-xs-*`/`col-sm-*` classes, `collapse`, and
  utility classes, plus targeted rules in `media/css/pellmon.css`.
- **D-02:** Design and verify at two widths: **390px** (primary phone target) and **768px**
  (tablet). Nothing may cause horizontal page scroll at either width. Desktop rendering (>= 992px)
  must not change.

- **D-07 (added after research, 2026-09-24):** Fix the Python 3 float-division bug in
  `index.html` (`12 / len(row)` renders `col-md-6.0`, which matches no Bootstrap rule, so the
  desktop dashboard is stacked today). Use integer division (`12 // len(row)`) so desktop gets the
  originally intended side-by-side widget rows again. This deliberately overrides D-02's
  "desktop unchanged" for this one visible regression; every other desktop rule stays unchanged.
  The user confirms the desktop look during the real-device check.

### Main page (dashboard)
- **D-03:** On phones the dashboard is a **single column**: system image first, then events, graph,
  consumption, silo level. The **events list is collapsed by default** on phones (a short preview
  with a tap-to-expand control) so the diagram and graph are reachable without scrolling past a
  long log. The SVG system image scales to the screen width (it is already an `<object>` with
  `image-responsive`; confirm it does not overflow or become unreadable).

### Graph
- **D-04:** The graph height becomes **responsive** (about 260px on phones, keep 400px on desktop)
  instead of the fixed `style="height:400px"`. The line-selection links and time-range links
  (`.lineselection`, `.timeChoice`, autorefresh) become **larger tap targets** (>= 44px touch
  height) that wrap cleanly. Keep the existing Back/Forward buttons for navigation. **No touch
  pan/pinch** gestures in this phase.

### Parameters and Settings pages
- **D-05:** Controls on the **Parameters** and **Settings** pages **stack vertically** on phones
  (label above input, full-width inputs, >= 44px touch height) using `col-xs`/`col-sm` classes.
  The **Settings image gallery** shows **2 tiles per row** on phones. The **Parameters page gets
  collapsible sections** (Bootstrap collapse) so the long page is navigable on a phone.

### Verification
- **D-06:** Done means all of: (a) structural pytest checks (viewport meta present, no fixed pixel
  widths/heights that break at 390px in the templates, required responsive classes present, in
  the style of the existing AST/text assertion tests); (b) **automated headless-browser checks in
  CI** that render the key pages at 390px and 768px and fail on horizontal overflow (the
  dependency-heavy part — see discretion below); (c) the user checks the real pages on their
  phone through `https://stoker.schoeler.pro/` (a manual human-verify checkpoint, like Phase 8/9).

### Claude's Discretion
- Exact CSS breakpoint values within the 390/768 targets, and how the events collapse is
  implemented (Bootstrap collapse vs a small JS toggle), as long as it works without breaking the
  existing websocket-driven event updates in `media/js/index.js`.
- Which headless browser tool to use for D-06(b) and how to serve the pages to it in CI. The web
  app needs D-Bus/daemon for real data, so the planner/researcher must decide between rendering
  static Mako template output with stub data vs booting the real stack; this is a genuine research
  question for the plan. It must run on `ubuntu-latest` and must not add the `actions/setup-python`
  step (an existing test forbids it in `ci.yml`).
- Where new CSS lives (extend `pellmon.css`, or a small dedicated stylesheet linked from
  `layout.html`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Pages and assets being changed
- `src/Pellmonweb/html/layout.html` — shared page shell: viewport meta (line 8), Bootstrap 3
  include, navbar with `navbar-toggle`/`navbar-collapse`.
- `src/Pellmonweb/html/index.html` — dashboard grid: `row` / `col-md-${12/len(row)}` loop over
  `frontpage_widgets` (default rows: `systemimage, events` / `graph` / `consumption7d, silolevel`).
- `src/Pellmonweb/html/graph`, `systemimage`, `events`, `consumption.html`, `parameters.html`,
  `settings.html`, `logview.html`, `login.html` — widget and page templates.
- `src/Pellmonweb/media/css/pellmon.css` — the only site stylesheet (one `@media (min-width:
  768px)` rule today); `pellmonconf.css` / `pellmonconf_print.css` are separate.
- `src/Pellmonweb/media/js/index.js` — websocket updates, graph and line/time controls; must keep
  working with the collapsed events and resized graph (flot resize plugin is already loaded).

### Prior decisions to stay consistent with
- `.planning/phases/08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi/08-UI-SPEC.md`
  — the Settings gallery UI contract from Phase 8 (tile layout, "Current" marker); Phase 10
  changes only its small-screen behavior.
- `.github/workflows/ci.yml` and `tests/test_ci_docker_config.py` — CI uses the runner's system
  python3 (no `actions/setup-python`); any new CI job for D-06(b) must respect
  `test_github_actions_workflow`'s assertions and the `publish` job's `needs: test` gating.
- `CLAUDE.md` — Windows is dev-only; production is the Linux container/Pi. Tests must be
  runnable in the existing pytest suite and skip cleanly where Linux-only libs are missing.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Bootstrap 3 grid/collapse/utilities (vendored, `media/bs3/`), already loaded in `layout.html`.
- `flot.resize` plugin already included in `index.html`, so a responsive graph container reflows.
- AST/text-assertion test idiom in `tests/Pellmonweb/test_settings_page.py` and
  `tests/test_ci_docker_config.py` for the structural checks in D-06(a).

### Established Patterns
- Widgets are Mako includes selected by config (`frontpage_widgets`), so layout changes go in the
  shared `index.html` row/column loop and each widget template, not per-deployment.
- `%`-style formatting and untyped Python for any server-side change; the phase should be almost
  entirely template/CSS/JS.

### Integration Points
- `index.html` widget loop (single-column ordering on phones is a CSS/grid-class change there).
- `graph` widget's inline `style="height:400px"` and `.lineselection`/`.timeChoice` link markup.
- The websocket event feed in `index.js` writing into the events widget.

</code_context>

<specifics>
## Specific Ideas

- Test target device is the user's real phone over `https://stoker.schoeler.pro/` (behind the
  Pangolin auth proxy), against the real Raspberry Pi deployment.
- Minimum touch target 44px is the working rule for new tap targets.

</specifics>

<deferred>
## Deferred Ideas

- Touch pan/pinch gestures on the graph (flot navigate plugin) — possible follow-up once the
  responsive basics ship.
- Compact status header with Diagram/Graph/Events tabs (bigger phone-only redesign).
- PWA manifest / "add to home screen" and offline support.
- Dark mode.
- Upgrading off Bootstrap 3.

</deferred>

---

*Phase: 10-optimize-for-mobile-devices-screen-size*
*Context gathered: 2026-09-24*
