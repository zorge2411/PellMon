---
status: complete
phase: quick-260919-jiz
plan: 01
requirements: [LOAD-01, LOAD-02, LOAD-03]
commits: [a6b2cc1]
---

# Quick 260919-jiz: yapsy plugin loading via importlib

## What changed
- `src/Pellmonsrv/yapsy/PluginManager.py`: `loadPlugins()` no longer execs plugin source into a bare dict. New `_load_plugin_module()` uses `importlib.util.spec_from_file_location` (package `submodule_search_locations` for directory plugins), registers the module in `sys.modules` under `pellmon_plugin_<name>_<sha1(path)[:8]>` before `exec_module`, and pops it on failure. A failed plugin now `continue`s (previously fell through). New `raise_on_error` attribute (default False).
- `src/Pellmonsrv/pellmonsrv.py`: `manager.raise_on_error = conf.command == 'debug'` before `collectPlugins()`.
- `tests/test_plugin_loader.py`: real-PluginManager tests (discovery, per-plugin load, no loader errors, scottecom regression, raise_on_error, allowlist tripwire).

## Results
- WSL full suite: before 208 passed / 3 skipped; after 240 passed / 5 skipped (the 2 new skips are raspberrygpio needing RPi).
- Plugins loading in WSL: all except raspberrygpio (`ModuleNotFoundError: RPi`, off-Pi). pyownet and pyowm are installed in venv-wsl so owfs/openweathermap load; they are allowlisted to skip where absent.
- Windows: new loader tests pass; 3 pre-existing failures in test_plugin_imports.py (missing cherrypy / nbecom deps in the Windows venv) are unrelated and untouched.

## End-to-end check (WSL Debian, system python3 + venv-wsl site-packages on PYTHONPATH for pyserial)
Verified: `pellmonsrv debug` with `tools/burner_sim.py --seed 1`, throwaway config under /tmp, only the scottecom plugin exposed via a symlinked /tmp plugin dir. Log showed `Activated plugins: ScotteCom`. Over D-Bus, `GetDB` listed ~80 Scotte items and `GetItem` returned boiler_temp=57.6, power=64, mode=Running, version=' 6.99', chute_temp=29, matching the simulator; simulator RX/TX logs show real Z-frame traffic with checksums OK.
Not verified: real hardware; NBEcom; writes (`SetItem`); the pellmonweb side; non-debug (daemonized) mode.
Caveats: (1) with the full plugin dir in debug mode, the daemon aborts because raspberrygpio raises (RPi missing) -- this is the planned debug re-raise behaviour, so the e2e run used a scottecom-only plugin dir. (2) The daemon log file was appended across three attempts (two earlier attempts failed for RPi and missing pyserial in system python, which is why a grep of the shared log counted 2 loader-error lines); the final run's stdout was empty and it activated ScotteCom. (3) venv-wsl lacks dbus/gi, so system python3 was used.
None of the four known out-of-scope bugs blocked the check.

## Deviations
None to source. Cleanup done: simulator and daemon killed (timeouts), /tmp artifacts and the helper script removed.
