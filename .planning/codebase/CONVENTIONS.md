# Coding Conventions

**Analysis Date:** 2026-09-17

## Migration Context (read this first)

PellMon is mid-migration from Python 2 to Python 3 (branch `python3-migration`). This shapes nearly every convention below:

- **`.py2bak` sibling files:** Almost every migrated module in `src/Pellmonsrv/` has a matching `*.py2bak` file (e.g. `src/Pellmonsrv/pellmonsrv.py` + `src/Pellmonsrv/pellmonsrv.py.py2bak`, `src/Pellmonsrv/database.py` + `src/Pellmonsrv/database.py.py2bak`, and one per plugin `__init__.py`). These are **pre-migration snapshots of the Python 2 source**, kept as a reference/rollback copy during the port. Treat `.py` files as the current, authoritative source. Do not edit `.py2bak` files as if they were live code — they exist only for diffing against the pre-migration behavior (`diff foo.py.py2bak foo.py`). When adding new files that have no Python 2 predecessor, do **not** create a `.py2bak` counterpart — this pattern is a migration artifact, not a general project convention, and should be retired once the migration is complete.
- **Migration diff signature** (from `src/Pellmonsrv/pellmonsrv.py.py2bak` → `.py`): `Queue`→`queue`, `ConfigParser`→`configparser`, `urllib2`→`urllib.request`, `simplejson`→stdlib `json`, `except Exception, e:`→`except Exception as e:`, `from database import X`→`from .database import X` (relative imports), `self.setDaemon(True)`→`self.daemon = True`, `import gobject`→`from gi.repository import GLib, GObject`. When touching any not-yet-fully-verified module, expect these same patterns.
- Root-level docs `MIGRATION.md`, `MIGRATION-SUMMARY.md`, `PHASE2-COMPLETE.md`, `PHASE3-COMPLETE.md`, `PHASE3-PROGRESS.md`, `PHASE4-TESTING.md` track migration status — consult them for what's verified vs. still in progress before assuming a module is fully working under Python 3.

## Naming Patterns

**Files:**
- Module/package name matches its directory: plugins live at `src/Pellmonsrv/plugins/<pluginname>/__init__.py` (e.g. `src/Pellmonsrv/plugins/consumption/__init__.py`, `src/Pellmonsrv/plugins/onewire/__init__.py`).
- Lowercase, no separators for plugin directory names: `consumption`, `cleaning`, `customalarms`, `heatingcircuit`, `nbecom`, `onewire`, `openweathermap`, `owfs`, `pelletcalc`, `raspberrygpio`, `scottecom`, `silolevel`, `testplugin`.

**Functions/Methods:**
- `snake_case` throughout, e.g. `getItem`/`setItem` are the exception (see below) but most are snake_case: `store_setting`, `load_setting`, `migrate_settings`, `barchartdata`, `rrd_total`, `readval`, `writeval` (`src/Pellmonsrv/database.py`).
- A minority of methods use `camelCase` for legacy plugin-interface methods that predate the current convention: `getItem`, `setItem`, `getDataBase`, `getTemplate` (`src/Pellmonsrv/plugin_categories.py`, `src/Pellmonsrv/plugins/consumption/__init__.py`). Match the surrounding class's existing style rather than mixing both in one file.

**Classes:**
- Inconsistent across the codebase — no single enforced convention. Observed styles:
  - `PascalCase` for infra/framework classes: `Database`, `MyDBUSService`, `MyDaemon`, `Poller` (`src/Pellmonsrv/pellmonsrv.py`), `Daemon` (`src/Pellmonsrv/daemon.py`).
  - `lowercase_with_underscore` for plugin classes and small value types: `dbus_signal_handler`, `gpio_input`, `gpio_latched_input`, `gpio_counter` (`src/Pellmonsrv/plugins/raspberrygpio/__init__.py`), `protocol_error`, `seqnum_error`, `protocol_timeout` (`src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocolexceptions.py`).
  - `lowercase` plugin entry-point classes named after the plugin: `calculateplugin`, `cleaningplugin`, `alarmplugin`, `execplugin`, `nbecomplugin`, `onewireplugin`, `owmplugin`, `owfsplugin`, `pelletcalc`, `execplugin` — all subclass the shared `protocols` base (`src/Pellmonsrv/plugin_categories.py`).
  - Some `Capitalized_With_Underscore`: `Consumption_plugin` (`src/Pellmonsrv/plugins/consumption/__init__.py`), `Keyval_storage`, `Plainitem`, `Getsetitem`, `Cacheditem`, `Storeditem` (`src/Pellmonsrv/database.py`).
- **When adding a new plugin**, mirror the existing plugin file it's closest to (most use `lowercase` class names subclassing `protocols`) rather than introducing a new convention.

**Variables:**
- `snake_case` for locals and instance attributes: `self.rrdfile`, `self.feeder_time`, `self.cache_lock`, `self.itemrefs`.
- Module-level constants/data tables use `camelCase` in places, e.g. `itemList` in `src/Pellmonsrv/plugins/consumption/__init__.py` — not `ITEM_LIST`. No `UPPER_SNAKE_CASE` constant convention is enforced; `DATADIR`, `CONFDIR`, `LOCALSTATEDIR` (from `directories.py.in`, imported in `src/Pellmonsrv/pellmonsrv.py`) are the exception.

**Types:**
- No type hints anywhere in the codebase (pre-dates/was never adopted; not introduced during the Python 3 port either). Do not introduce type hints inconsistently in a single file — either fully type a new module or match the untyped surrounding style.

## Code Style

**Formatting:**
- No formatter (no `black`, `ruff format`, `.prettierrc`, or `pyproject.toml` `[tool.black]` section present). Indentation is inconsistent in places (mixed under-indented `except` blocks exist, e.g. `src/Pellmonsrv/database.py:113` `except Exception as e:\n           print(e)` uses irregular indentation). Match surrounding indentation exactly rather than reformatting whole blocks.
- Line length is not constrained; some lines (SQL statements, HTML/JS template strings embedded in plugin code) run very long, e.g. `src/Pellmonsrv/plugins/consumption/__init__.py:220`.

**Linting:**
- No linter config found (no `.flake8`, `.pylintrc`, `ruff.toml`, `setup.cfg` with lint sections). `convert-to-py3.py` (repo root) is a one-off migration helper script, not an ongoing lint/format tool.

**String formatting:**
- Old-style `%` formatting is the dominant convention for log/error messages: `logger.info('%s plugin error: %s'%(plugin_name, str(e)))` (`src/Pellmonsrv/pellmonsrv.py`), `'last %u'%bars` (`src/Pellmonsrv/plugins/consumption/__init__.py`). f-strings appear only in newer/migration-support scripts (`test-imports.py`). Prefer `%`-formatting inside `src/Pellmonsrv/` and `src/Pellmonsrv/plugins/` to stay consistent with existing modules; f-strings are acceptable in new top-level tooling scripts.

## Import Organization

**Order:**
- No enforced import ordering (no `isort` config). Typical pattern seen in `src/Pellmonsrv/pellmonsrv.py`: stdlib imports first (often several on one comma-separated line, e.g. `import signal, os, errno, queue, threading`), then third-party (`dbus`, `gi.repository`), then local package imports (`from Pellmonsrv.yapsy.PluginManager import PluginManager`, `from .database import Database as _Database`), with `try/except ImportError` fallback blocks for optional generated modules (`version`, `directories`).
- Comma-separated single-line imports are common and acceptable in this codebase (`import pwd, grp`, `import sqlite3, threading`) — not flagged as a style violation here.

**Relative vs absolute imports:**
- Within `Pellmonsrv` package, prefer relative imports for sibling modules: `from .database import Database as _Database` (this is one of the Python 3 migration fixes — Python 2 used bare `from database import X`). Use absolute `Pellmonsrv.x.y` imports when crossing into subpackages from a plugin: `from Pellmonsrv.plugin_categories import protocols`, `from Pellmonsrv.database import Item, Getsetitem`.

**Optional/platform dependencies:**
- Guard optional imports with `try/except ImportError`, falling back to sane defaults, rather than making the import hard-required. Example: `try: from version import __version__ \n except ImportError: __version__ = '_dev_'` (`src/Pellmonsrv/pellmonsrv.py`).

## Error Handling

**Patterns:**
- `except Exception as e:` is the dominant catch pattern (72+ occurrences across `src/`); broad bare `except:` also appears (148+ occurrences, e.g. `src/Pellmonsrv/database.py:198`, `src/Pellmonsrv/plugins/consumption/__init__.py:228`) — used for best-effort cache/lookup fallbacks where failure is expected and non-fatal.
- Errors are commonly logged and swallowed rather than propagated: `logger.info('%s plugin error: %s'%(plugin_name, str(e)))` then continue (`src/Pellmonsrv/pellmonsrv.py`). Some intentionally re-raise after logging in "debug" mode: `if conf.command == 'debug': raise else: logger.info(...)` (`src/Pellmonsrv/pellmonsrv.py`).
- Plugin-specific exceptions subclass a shared base rather than using bare `Exception`: `protocol_error` → `seqnum_error`, `protocol_timeout`, `protocol_offline` (`src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocolexceptions.py`).
- `print(e)` is used as a fallback error surface in some database code paths (`src/Pellmonsrv/database.py:113`, `:170`) instead of `logger` — this is inconsistent with the rest of the codebase, which otherwise uses the `pellMon` logger. Prefer `logger.info`/`logger.error` over bare `print()` in new code.

## Logging

**Framework:** Standard library `logging` (`import logging`, `import logging.handlers`).

**Patterns:**
- Every module that logs gets its own logger via `logger = getLogger('pellMon')` (e.g. `src/Pellmonsrv/database.py` — note: not present in `database.py`, but consistently in `src/Pellmonsrv/plugin_categories.py`, `src/Pellmonsrv/plugins/consumption/__init__.py`, `src/Pellmonsrv/pellmonsrv.py`, and 15 other files). All modules share the single `'pellMon'` named logger rather than using `__name__`-based per-module loggers.
- `logger.info(...)` is used even for what are effectively warnings/errors (e.g. failed plugin activation, migration failures) — there's no consistent use of `logger.warning`/`logger.error` levels. New code should prefer the correct level (`warning`/`error`) rather than mirroring this over-use of `info`.
- A custom `logging.Handler` subclass, `dbus_signal_handler` (`src/Pellmonsrv/pellmonsrv.py`), forwards log records as DBus signals — follow this pattern if adding another log sink.

## Comments

**When to Comment:**
- Sparse inline comments, mostly explaining non-obvious workarounds, e.g. `#invalidate cache when writing` (`src/Pellmonsrv/database.py`), `#store a reference to the starts dict so it's not freed until empty` (`src/Pellmonsrv/plugins/consumption/__init__.py`).
- No systematic use of docstrings on every function; docstrings appear mainly on plugin-interface methods to document the contract, e.g. `"""Return the value for one item"""` on `getItem` (`src/Pellmonsrv/plugin_categories.py`).

**Module header:**
- Every source file under `src/Pellmonsrv/` opens with the same GPL license header (`Copyright (C) 2013 Anders Nylund`) plus `#!/usr/bin/env python3` and `# -*- coding: utf-8 -*-`. New files added to this package should carry the same header block for consistency (copy from `src/Pellmonsrv/database.py`).

**JSDoc/TSDoc:** Not applicable (Python-only codebase).

## Function Design

**Size:** No enforced limit; several methods mix business logic with embedded HTML/JS template strings inline (e.g. `Consumption_plugin.activate`, `src/Pellmonsrv/plugins/consumption/__init__.py:61-139`), producing large functions. This is an established (if not ideal) pattern for plugin `activate()` methods — templates are registered via `self._insert_template(name, template_string)`.

**Parameters:** Plugin lifecycle methods follow a fixed signature contract inherited from `protocols` (`src/Pellmonsrv/plugin_categories.py`): `activate(self, conf, glob, db, *args, **kwargs)`, `getItem(self, item)`, `setItem(self, item, value)`. New plugins must implement this same signature to be compatible with `PluginManager`.

**Return Values:** Item getters return plain values or the string `'Error'`/`'error'` on failure rather than raising or returning `None` in several places (`src/Pellmonsrv/plugins/consumption/__init__.py:167`, `src/Pellmonsrv/database.py:171`) — an inconsistency to be aware of when consuming these APIs (callers must check for sentinel strings, not just falsy values).

## Module Design

**Exports:** No `__all__` declarations; modules rely on plain top-level names. Plugins are discovered dynamically via the `yapsy` plugin framework (`src/Pellmonsrv/yapsy/PluginManager.py`) using `.pellmon-plugin` descriptor files (e.g. `src/conf.d/plugins/testplugin.conf`, `src/Pellmonsrv/plugins/testplugin.pellmon-plugin`) rather than static imports/registries.

**Plugin contract:** Every plugin package's `__init__.py` must define a class subclassing `protocols` (`src/Pellmonsrv/plugin_categories.py`) and be paired with a `.pellmon-plugin` metadata file describing name/category for `yapsy` to load it.

**Barrel Files:** Not used; `__init__.py` files are the plugin implementation itself, not a re-export barrel.

---

*Convention analysis: 2026-09-17*
