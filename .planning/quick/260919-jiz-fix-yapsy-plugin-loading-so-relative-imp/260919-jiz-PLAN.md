---
phase: quick-260919-jiz
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/Pellmonsrv/yapsy/PluginManager.py
  - src/Pellmonsrv/pellmonsrv.py
  - tests/test_plugin_loader.py
autonomous: true
requirements: [LOAD-01, LOAD-02, LOAD-03]
must_haves:
  truths:
    - "PluginManager.loadPlugins imports each plugin as a real module/package, so PEP 328 relative imports inside a plugin package resolve"
    - "The ScotteCom plugin class is discovered by the real PluginManager (no KeyError: \"'__name__' not in globals\")"
    - "Every plugin in src/Pellmonsrv/plugins whose third-party deps are importable yields a plugin class; plugins with missing optional deps (RPi, pyownet, pyowm) fail with one clear logged error and do not abort the loop"
    - "In `pellmonsrv debug` mode a plugin load failure re-raises instead of being silently logged"
    - "Running pellmonsrv against tools/burner_sim.py exposes ScotteCom items over D-Bus and GetItem returns simulator-consistent values (WSL)"
  artifacts:
    - path: "src/Pellmonsrv/yapsy/PluginManager.py"
      provides: "importlib-based plugin loading with sys.modules registration"
      contains: "spec_from_file_location"
    - path: "tests/test_plugin_loader.py"
      provides: "real-PluginManager load test across all plugins + scottecom relative-import regression"
      contains: "collectPlugins"
  key_links:
    - from: "src/Pellmonsrv/yapsy/PluginManager.py"
      to: "sys.modules"
      via: "register package before exec_module so relative imports resolve"
      pattern: "sys\\.modules\\["
    - from: "src/Pellmonsrv/pellmonsrv.py"
      to: "PluginManager"
      via: "debug-mode re-raise flag set before collectPlugins"
      pattern: "raise_on_error"
---

<objective>
Fix the vendored yapsy loader so plugins are imported as real modules/packages instead of `exec`'d into a bare dict. Today `loadPlugins()` builds `candidate_globals = {"__file__": ...}` with no `__name__`/`__package__`/`__spec__`, so `from .scottecom import scottecom` in `src/Pellmonsrv/plugins/scottecom/__init__.py` raises `KeyError: "'__name__' not in globals"`. The exception is only logged, so `pellmonsrv` starts with zero Scotte items and every `GetItem` raises `KeyError`. `tests/test_plugin_imports.py` uses a plain `importlib.import_module`, which never exercises the loader and therefore missed the bug.

Purpose: restore the project's core value — the daemon actually talking to burner hardware through its protocol plugins.
Output: importlib-based loader, a debug-mode re-raise path, a real-PluginManager test across all 15 plugins, and a WSL end-to-end run against the burner simulator.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/quick/260919-gpe-scotte-burner-emulator-for-integration-t/260919-gpe-SUMMARY.md
@src/Pellmonsrv/yapsy/PluginManager.py
@tests/test_plugin_imports.py
@tools/README-burner-sim.md

<interfaces>
<!-- Contracts the executor needs. Do not re-derive by exploring. -->

Loader call site — src/Pellmonsrv/pellmonsrv.py, class `MyDaemon`/`Database.__init__` (~lines 82-107):
  manager = PluginManager(categories_filter={ "Protocols": protocols})
  manager.setPluginPlaces(conf.plugin_dirs)
  manager.collectPlugins()
  ... later, per-plugin activation already does:
      except Exception:
          failed_plugins.append(plugin.name)
          if conf.command == 'debug':
              raise
          else:
              logger.exception('%s plugin error'%plugin_name)

Candidate tuple produced by `locatePlugins()` (PluginManager.py ~line 246):
  self._candidates.append((candidate_infofile, candidate_filepath, plugin_info))
where `candidate_filepath` has NO `.py` suffix, and for a directory plugin it is
`<plugin_dir>/__init__` (PluginManager.py lines 242-245). `loadPlugins()` currently
opens `candidate_filepath + ".py"`.

Descriptor → package mapping (all 15 plugins today are directory plugins):
  src/Pellmonsrv/plugins/<name>.pellmon-plugin  ->  [Core] Module = <name>
  src/Pellmonsrv/plugins/<name>/__init__.py

Category interface: `from Pellmonsrv.plugin_categories import protocols` — imported
absolutely by every plugin, so `issubclass` identity is preserved regardless of the
name the loader registers the plugin module under.

Module-level logger in PluginManager.py: `logging = getLogger('pellMon')` (shadows the
stdlib name — keep it, do not rename).

pytest config (pytest.ini): `pythonpath = src`, `testpaths = tests`,
`addopts = --disable-socket`, custom marker `known_broken`.
`tests/test_no_sys_path_shims.py` forbids any `sys.path` mutation inside tests/.

Platform-skip allowlist already established in tests/test_plugin_imports.py:
  PLATFORM_UNAVAILABLE = {"grp","pwd","RPi","RPi.GPIO","dbus","gi","rrdtool"}
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace exec-into-dict plugin loading with importlib module loading</name>
  <files>src/Pellmonsrv/yapsy/PluginManager.py, src/Pellmonsrv/pellmonsrv.py</files>
  <behavior>
    - A directory plugin (`<dir>/__init__.py`) is imported as a package: its `__path__` is set to `[<dir>]`, so `from .scottecom import scottecom` resolves.
    - A single-file plugin (`<dir>/<name>.py`, no `__init__` in the candidate path) still loads as a plain module (backward compat).
    - The loaded module is registered in `sys.modules` under a stable, unique name BEFORE `exec_module` runs, and removed again if execution raises.
    - Two plugins with the same `Module` name in different directories get distinct `sys.modules` keys and both load.
    - A plugin whose import raises `ModuleNotFoundError` (e.g. `RPi` off-Pi) logs one error and the loop continues to the next candidate.
    - With the loader's error-raising flag enabled, a failing plugin re-raises instead of being swallowed.
    - Plugin-class discovery is unchanged: the first attribute of the module that is a strict subclass of a category interface becomes `plugin_info.plugin_object`.
  </behavior>
  <action>
In `src/Pellmonsrv/yapsy/PluginManager.py`:

1. Add `import importlib.util` and `import hashlib` to the existing stdlib import line group at the top (keep the file's tab indentation and existing `import sys, os` style).

2. Add an attribute `self.raise_on_error = False` in `PluginManager.__init__` (do NOT add a constructor argument — the call site in pellmonsrv.py passes `categories_filter` positionally and the decorators mirror the signature). Document it in the `__init__` docstring as "if True, plugin load failures propagate instead of being logged (used by `pellmonsrv debug`)".

3. Add a private helper `_load_plugin_module(self, candidate_filepath)` that returns the imported module object:
   - Compute `source_path = candidate_filepath + ".py"`.
   - Derive the module basename: if `os.path.basename(candidate_filepath) == "__init__"`, this is a package — `pkg_dir = os.path.dirname(candidate_filepath)`, `short_name = os.path.basename(pkg_dir)`, and `submodule_search_locations = [pkg_dir]`. Otherwise it is a single-file plugin — `short_name = os.path.basename(candidate_filepath)`, `submodule_search_locations = None`.
   - Build a stable unique `sys.modules` key: `"pellmon_plugin_%s_%s" % (short_name, hashlib.sha1(os.path.abspath(source_path).encode("utf-8")).hexdigest()[:8])`. The path hash guarantees two same-named plugins in different plugin_dirs do not collide, and guarantees the same plugin re-loads under the same key.
   - If that key is already in `sys.modules`, return the cached module (re-collecting plugins must not re-execute module-level side effects).
   - Create the spec with `importlib.util.spec_from_file_location(unique_name, source_path, submodule_search_locations=submodule_search_locations)`; if `spec` or `spec.loader` is None, raise `ImportError` naming `source_path`.
   - `module = importlib.util.module_from_spec(spec)`, then `sys.modules[unique_name] = module`, then `spec.loader.exec_module(module)` inside a `try`; on exception `sys.modules.pop(unique_name, None)` and re-raise.
   - Return the module.

4. Rewrite the load block inside `loadPlugins()` (currently PluginManager.py lines 271-278). Replace `candidate_globals` + `exec(compile(...))` with:
   - `try: plugin_module = self._load_plugin_module(candidate_filepath)`
   - `except Exception:` — `logging.exception("Unable to execute the code in plugin: %s", candidate_filepath)`; if `getattr(self, 'raise_on_error', False)` then `raise`; else `continue` to the next candidate.
   Keep the log message string EXACTLY as it is today ("Unable to execute the code in plugin: %s") — the new test asserts on it. Note the current code does not `continue` after the failure and falls through into discovery over a half-populated dict; the new code must `continue`.

5. Change the discovery loop to iterate over module attributes instead of dict values: `for element in list(vars(plugin_module).values()):`. Leave the rest of the subclass-matching / `plugin_info.plugin_object = element()` / category-mapping logic byte-for-byte unchanged.

In `src/Pellmonsrv/pellmonsrv.py`, in the plugin-loading block (~lines 84-86), set the flag between `setPluginPlaces` and `collectPlugins`:
`manager.raise_on_error = conf.command == 'debug'`
This mirrors the existing `if conf.command == 'debug': raise` policy already used for activation failures a few lines below; no other behaviour changes.

Style: this file uses TABS for indentation and `%`-style logging — match exactly. No type hints. Do not touch `ConfigurablePluginManager.py` or `VersionedPluginManager.py` (both simply delegate to `self._component.loadPlugins`).
  </action>
  <verify>
    <automated>cd /d/Antigravity/PellMon-master &amp;&amp; python -c "import ast,sys; ast.parse(open('src/Pellmonsrv/yapsy/PluginManager.py').read())" &amp;&amp; grep -v '^\s*#' src/Pellmonsrv/yapsy/PluginManager.py | grep -c 'spec_from_file_location' &amp;&amp; grep -v '^\s*#' src/Pellmonsrv/yapsy/PluginManager.py | grep -c 'exec(compile'</automated>
  </verify>
  <done>`spec_from_file_location` count is 1 and `exec(compile` count is 0 in non-comment lines; `pellmonsrv.py` sets `raise_on_error` before `collectPlugins()`; file parses.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Real-PluginManager load test across all plugins</name>
  <files>tests/test_plugin_loader.py</files>
  <behavior>
    - Discovery is not vacuous: the real `locatePlugins()` finds >= 15 candidates in src/Pellmonsrv/plugins.
    - For every plugin whose deps are importable on this platform, `collectPlugins()` produces a `PluginInfo` with a non-None `plugin_object` in the "Protocols" category.
    - For those same plugins, caplog contains NO "Unable to execute the code in plugin" record.
    - Regression: `scottecom` specifically loads, and no record mentions `'__name__' not in globals`.
    - Plugins whose only failure cause is a platform-unavailable dependency are skipped/xfailed by name, not blanket-ignored.
  </behavior>
  <action>
Create `tests/test_plugin_loader.py`. It must run on both Windows (Python 3.14) and WSL (Python 3.13); do NOT mutate `sys.path` (tests/test_no_sys_path_shims.py forbids it — `pytest.ini` already sets `pythonpath = src`).

Structure:

- Reuse the descriptor discovery idea from `tests/test_plugin_imports.py` but drive it through the real manager. Import `from Pellmonsrv.yapsy.PluginManager import PluginManager` and `from Pellmonsrv.plugin_categories import protocols`.
- `PLUGINS_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "Pellmonsrv" / "plugins"`.
- Copy the `PLATFORM_UNAVAILABLE` set from test_plugin_imports.py and extend it with the optional third-party deps named in the bug report that may legitimately be absent: `pyownet` (owfs), `pyowm` (openweathermap), plus `RPi`/`RPi.GPIO` already present. Add a one-line justification comment per new name, matching the existing file's convention. Do NOT add any name from the tripwire set (`protocol`, `frames`, `Scotteprotocol`, `nbeprotocol`, `datamap`, `menus`).
- Module-scoped fixture `loaded_manager(caplog)` is NOT viable (caplog is function-scoped). Instead use a function-scoped fixture that, per test, sets `caplog.set_level(logging.DEBUG, logger="pellMon")`, builds `PluginManager(categories_filter={"Protocols": protocols})`, calls `setPluginPlaces([str(PLUGINS_DIR)])`, `locatePlugins()`, `loadPlugins()`, and returns `(manager, caplog)`. Keep `raise_on_error` at its default False so one unavailable dep does not abort collection.
- Helper `_expected_loadable(name)`: attempt `importlib.import_module("Pellmonsrv.plugins." + name)` and return `(True, None)` on success; on `ModuleNotFoundError` whose `exc.name` is in `PLATFORM_UNAVAILABLE` return `(False, exc.name)`; on any other exception re-raise (a real defect must fail loudly, per the existing suite's policy).
- Tests:
  1. `test_locate_plugins_finds_all_descriptors` — `locatePlugins()` returns >= 15 and the parsed candidate set covers every `*.pellmon-plugin` `[Core] Module` value, including `scottecom` and `nbecom`.
  2. `test_every_available_plugin_loads` parametrized over discovered module names — skip with the named unavailable dep if `_expected_loadable` says so; otherwise assert a `PluginInfo` for that plugin exists in `manager.getPluginsOfCategory("Protocols")` with `plugin_object is not None` and `isinstance(plugin_object, protocols)`.
  3. `test_no_loader_errors_for_available_plugins` — for each available plugin, assert no `caplog` record whose message/`getMessage()` contains "Unable to execute the code in plugin" AND names that plugin's path segment.
  4. `test_scottecom_relative_import_regression` — the explicit regression: ScotteCom's `PluginInfo` is present with a live `plugin_object`, and no caplog record contains `"'__name__' not in globals"`.
  5. `test_platform_skip_allowlist_cannot_hide_defects` — same tripwire as test_plugin_imports.py: assert `PLATFORM_UNAVAILABLE.isdisjoint({"protocol","frames","Scotteprotocol","nbeprotocol","datamap","menus","scottecom","nbecom"})`.
- Match the descriptor `[Core] Name` (e.g. "ScotteCom") vs `[Core] Module` (e.g. "scottecom") distinction carefully: `PluginInfo.name` is the Name, and `PluginInfo.path` ends with the Module directory. Map between them by re-reading the descriptor with `configparser`, not by casing assumptions.
- Use f-strings freely here (top-level tooling/test scripts, per CLAUDE.md), and give every test a docstring explaining what defect it guards.

Do not modify `tests/test_plugin_imports.py` — the two files are complementary (plain import vs. real loader).
  </action>
  <verify>
    <automated>cd /d/Antigravity/PellMon-master &amp;&amp; python -m pytest tests/test_plugin_loader.py tests/test_plugin_imports.py -q</automated>
  </verify>
  <done>New test file passes on Windows (skips only where a dep is genuinely unavailable), test_plugin_imports.py still passes, and the scottecom regression test fails if Task 1's loader change is reverted.</done>
</task>

<task type="auto">
  <name>Task 3: WSL end-to-end verification against the burner simulator + full suite before/after</name>
  <files>(no source edits — verification only; results recorded in the SUMMARY)</files>
  <action>
All commands run in WSL Debian against `/mnt/d/Antigravity/PellMon-master`. Treat `venv-wsl` as read-only; if a package must be installed, create a throwaway venv under `/tmp`. Every command that reads a subprocess pipe must use `python3 -u` and a `timeout`, and every spawned process must be killed in a trap/finally — the prior attempt (quick 260919-gpe) hit hanging pipe reads here.

1. Baseline: run the full suite in WSL and record the numbers. Expected starting point per 260919-gpe: 208 passed, 3 skipped. Record actual.
   `cd /mnt/d/Antigravity/PellMon-master && timeout 600 ./venv-wsl/bin/python -m pytest -q`
   If the baseline differs from 208/3, record the delta and its cause before proceeding; do not "fix" unrelated failures.

2. Start the simulator in the background, capture the printed pty path, and keep the PID for cleanup:
   `timeout 300 ./venv-wsl/bin/python3 -u tools/burner_sim.py > /tmp/jiz-sim.log 2>&1 &`
   then poll `/tmp/jiz-sim.log` (bounded, e.g. 20 x 0.5s) for the `pty: /dev/pts/N` line. See `tools/README-burner-sim.md` for flags.

3. Write a throwaway pellmon config OUTSIDE the repo (e.g. `/tmp/jiz-pellmon.conf`), modelled on `config/pellmon.conf.example`, with `scottecom` in `enabled_plugins`, its `serialport` set to the printed pty, and all data/RRD paths pointed under `/tmp`. Never write config into the repo tree.

4. Run the daemon and confirm plugin load + items:
   `dbus-run-session -- timeout 60 ./venv-wsl/bin/python3 -u -m Pellmonsrv.pellmonsrv -C /tmp/jiz-pellmon.conf -D SESSION debug > /tmp/jiz-srv.log 2>&1`
   (adjust the interpreter if venv-wsl lacks dbus/gi — the prior run used system `python3` with venv-wsl site-packages; reuse whatever 260919-gpe found workable.)
   While it runs, query D-Bus in the SAME session: list the DB via `GetFullDB`/`GetDB` and `GetItem` a few Scotte items (`boiler_temp`, `power`, `mode`, `version`). Confirm the values match what the simulator serves (the 260919-gpe run saw power=64, boiler_temp~58 drifting, chute_temp=27, mode=Running, version=' 6.99').
   Simplest robust shape: a single `dbus-run-session -- bash -c '...'` that backgrounds the daemon, sleeps a bounded interval, runs a short python D-Bus client, then kills the daemon.

5. Confirm the log shows `Activated plugins: ... ScotteCom ...` and contains NO `Unable to execute the code in plugin` / `'__name__' not in globals` line.

6. Re-run the full suite in WSL and record the after numbers. Report before vs after explicitly.

7. Clean up: kill the simulator and any daemon PID, remove /tmp artifacts.

8. In the SUMMARY, state EXACTLY what was and was not verified. If any of the four known out-of-scope src bugs from 260919-gpe blocks this end-to-end check, list which one and how it blocked — do NOT fix them here. Out of scope: `Protocol.run` CRLF retry double-`\r\n`, `setDaemon` at `src/Scotteprotocol/protocol.py:77`, shared module-level `Frame` singletons in `src/Scotteprotocol/frames.py`, `setItem` returning raw error bytes.

Commit only the three touched files by explicit path (`src/Pellmonsrv/yapsy/PluginManager.py`, `src/Pellmonsrv/pellmonsrv.py`, `tests/test_plugin_loader.py`) plus the planning artifacts. NEVER `git add -A`/`.`, never `git stash`/`restore`/`checkout --`. The untracked `mqtt-*.json` is sensitive and must never be staged. Do not push.
  </action>
  <verify>
    <automated>cd /mnt/d/Antigravity/PellMon-master &amp;&amp; timeout 600 ./venv-wsl/bin/python -m pytest -q 2>&amp;1 | tail -3 &amp;&amp; grep -c "Unable to execute the code in plugin" /tmp/jiz-srv.log; test $? -ne 0 -o "$(grep -c 'Unable to execute the code in plugin' /tmp/jiz-srv.log)" = "0"</automated>
  </verify>
  <done>WSL full suite is >= the recorded baseline with zero new failures; the daemon log shows ScotteCom activated with no loader error; GetItem returns simulator-consistent values, or the SUMMARY names the precise blocker if it does not.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| plugin_dirs -> daemon process | Files under `conf.plugin_dirs` are executed with daemon privileges. This boundary is unchanged by this plan: the old code already `exec`'d the same files. |
| burner pty/serial -> Scotte plugin | Simulator/hardware bytes parsed by the protocol layer (test-only here). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-jiz-01 | Elevation of Privilege | `PluginManager._load_plugin_module` | accept | Arbitrary code execution from `plugin_dirs` is the pre-existing, intended design of the plugin system; importlib is no broader than the `exec` it replaces. Directory contents are admin-controlled and the daemon already drops privileges via `drop_privileges`. |
| T-jiz-02 | Tampering | `sys.modules` key collision | mitigate | Unique key derived from the absolute source path SHA-1 prefix, so a plugin cannot shadow a stdlib/app module or another plugin of the same name. |
| T-jiz-03 | Information Disclosure | throwaway WSL config + logs | mitigate | Config and logs written under `/tmp`, never into the repo tree; commits by explicit path only; the untracked `mqtt-*.json` is never staged. |
| T-jiz-SC | Tampering | package installs | mitigate | No new dependencies are added (`importlib.util`, `hashlib` are stdlib). No install task exists, so no legitimacy gate is required. |
</threat_model>

<verification>
- `python -m pytest tests/test_plugin_loader.py tests/test_plugin_imports.py -q` passes on Windows.
- Full WSL suite before and after recorded; no new failures.
- `grep -v '^\s*#' src/Pellmonsrv/yapsy/PluginManager.py | grep -c 'exec(compile'` returns 0.
- `pellmonsrv debug` against `tools/burner_sim.py` lists ScotteCom under "Activated plugins" and `GetItem` returns values, not `KeyError`.
</verification>

<success_criteria>
- ScotteCom (and every dep-available plugin) loads through the real `PluginManager`, verified by an automated test that fails if the loader change is reverted.
- Plugins with unavailable optional deps log one clear error and do not abort collection.
- `pellmonsrv debug` re-raises loader failures; non-debug mode logs them.
- End-to-end WSL check performed and its exact verified/not-verified scope reported.
- Only the three touched source/test files plus planning artifacts are committed, by explicit path, nothing pushed.
</success_criteria>

<output>
Create `.planning/quick/260919-jiz-fix-yapsy-plugin-loading-so-relative-imp/260919-jiz-SUMMARY.md` when done.
</output>
