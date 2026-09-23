# Phase 8: Expose the burner SVG depiction in settings - Context

**Gathered:** 2026-09-21
**Status:** Ready for planning
**Mode:** --auto (recommended defaults chosen by Claude; review before relying on them)

<domain>
## Phase Boundary

Today the system diagram on the main page is chosen only by `system_image` in `webinterface.conf` (system.svg, system_nbe*.svg, system_matene.svg, or an absolute path) and served by `Root.systemimage`. This phase lets the user see and choose that depiction from the web GUI, so it no longer needs a config-file edit and a restart. It delivers a small web settings page for the burner/system image. It does not build the Home Assistant settings (Phase 6) or edit the SVG artwork.

</domain>

<decisions>
## Implementation Decisions

### Where the setting lives
- **D-01:** [auto] Add a new "Settings" entry in the web navbar (layout.html) leading to a page with a "System image" section. Phase 6 will add its own section to the same page later, so build it as a page with sections, not a one-off dialog.
- **D-02:** [auto] Only the shipped SVGs are selectable (the filenames listed in `webinterface.conf.in`). Custom absolute paths stay a config-file-only feature; the GUI never accepts a free path (avoids path traversal and arbitrary file serving).

### What the user sees
- **D-03:** [auto] The page shows a thumbnail gallery of the shipped variants with the current one marked, click to select, then Save. Each thumbnail is the real SVG file served from `/media/img/`.
- **D-04:** [auto] After saving, the main page shows the new image on next load; no daemon restart required.

### Persistence and precedence
- **D-05:** [auto] The choice is stored in the persistent data folder from Phase 7 (`/var/lib/pellmon`, the host `pellmon-data/data`), so it survives container recreation and is included in the backup tool. Precedence: GUI choice, then `system_image` in `webinterface.conf`, then `system.svg`.
- **D-06:** [auto] An invalid or missing stored value falls back to the config value, with one warning in the log, and never breaks the main page.

### Access control
- **D-07:** [auto] Saving requires the same login as other write actions and the same-origin (Origin/Referer) check used in `pellmonconf.save`. The page is not reachable without auth when authentication is configured.

### Claude's Discretion
- The storage mechanism (a small file or sqlite table next to the RRD, written by the web process, versus going through the daemon over D-Bus). Researcher/planner choose, honouring D-05 and the Phase 7 data-folder ownership (uid 999).
- Thumbnail sizing, page layout, and wording, matching the existing Bootstrap 3 look.
- Whether `Root.systemimage` needs cache headers or a cache-busting query so a changed image shows immediately.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing behavior
- `src/Pellmonweb/pellmonweb.py` ~lines 683-684 (`Root.systemimage`) and ~903-907 (`system_image` read from `[conf]`), ~915 (`frontpage_widgets` default including `systemimage`).
- `src/conf.d/webinterface.conf.in` lines 36-43 - the list of shipped variants and the `system_image` key.
- `src/Pellmonweb/media/img/system*.svg` - the shipped depictions.
- `src/Pellmonweb/html/layout.html` - navbar where the Settings link goes.
- `src/Pellmonweb/pellmonconf.py` (`_check_same_origin`, `_resolve`) - existing write-protection pattern.
- `src/Pellmonweb/auth.py` - login/session handling.

### Persistence (Phase 7)
- `.planning/phases/07-persist-rrd-database-and-other-relevant-settings-outside-the/07-CONTEXT.md` - data folder layout and ownership.
- `tools/pellmon_backup.py` - must include any new settings file.
- `DEPLOY-PI.md` - data folder and backup docs to update.

No external specs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Root.systemimage` already serves one file; it can resolve the effective image at request time instead of the module global.
- `_check_same_origin` in `pellmonconf.py` for the save endpoint.
- Bootstrap 3 and Mako templates in `src/Pellmonweb/html/`.

### Established Patterns
- Config read once at startup into module globals (`system_image`); the GUI choice needs a request-time lookup.
- Tests in `tests/` for web modules run under venv-wsl; dbus-dependent ones under system python.

### Integration Points
- Navbar link, new route on `Root`, `systemimage` route, backup tool, DEPLOY-PI.md.

</code_context>

<specifics>
## Specific Ideas

No specific requirements - open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

- Live value overlays or per-burner auto-selection of the diagram (detect NBE vs Scotte) - separate phase.
- Uploading custom SVGs through the GUI - security review needed first.
- Home Assistant settings section - Phase 6.

</deferred>

---

*Phase: 08-expose-the-burner-svg-depiction-in-settings-to-make-the-visi*
*Context gathered: 2026-09-21 (auto mode)*
