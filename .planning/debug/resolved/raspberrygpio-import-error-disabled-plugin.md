---
status: resolved
trigger: "ModuleNotFoundError: No module named 'RPi' traceback shown in PellMon on the Pi (v2.3.0)"
created: 2026-09-25
---

## Symptoms
- Traceback `ModuleNotFoundError: No module named 'RPi'` from `plugins/raspberrygpio/__init__.py:24` via `yapsy/PluginManager.py` `loadPlugins`, logged on every pellmonsrv start.
- RaspberryGPIO is not enabled (`#p03 = RaspberryGPIO` in conf.d/enabled_plugins.conf).

## Root cause
`PluginManager.loadPlugins` imports every discovered plugin, enabled or not; activation is filtered by `conf.enabled_plugins` only afterwards. RaspberryGPIO hard-imports `RPi.GPIO`, which is not in the Docker image, so the import fails and `logging.exception` records the traceback. `raise_only_for` (quick task 260919-jiz) only kept it from aborting debug mode; the error log remained.

## Fix
New `PluginManager.load_only` attribute; pellmonsrv sets it to the enabled plugins, so disabled plugins are never imported. Enabled plugins still import and still fail loudly.

## Verification
- tests/test_plugin_loader.py: disabled broken plugin is not imported and logs nothing at WARNING+; enabled broken plugin still raises; daemon sets load_only before collectPlugins.
- Full suite: 696 passed, 3 known baseline failures.
- Pending: confirm on the Pi that the traceback is gone after the next release.
