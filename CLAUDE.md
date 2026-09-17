<!-- GSD:project-start source:PROJECT.md -->
## Project

**PellMon Python 3 Migration**

PellMon is a two-process Linux monitoring system for pellet-burning stoves: `pellmonsrv`, a daemon that talks to burner hardware over serial/TCP protocols (Scotte, NBE) and polls sensors (OWFS, 1-Wire, GPIO), and `pellmonweb`, a CherryPy web app that reads/writes that data over D-Bus and serves a live dashboard. It's mid-migration from Python 2 to Python 3 on the `python3-migration` branch — this project finishes that migration and gets the result production-ready.

**Core Value:** The daemon must actually talk to real burner hardware through its protocol plugins (Scotte, NBE) under Python 3 — a port where only the core modules import but the hardware plugins silently fail isn't done, no matter what the commit messages say.

### Constraints

- **Tech stack**: Python 3.13/3.14, CherryPy, Mako, D-Bus/GLib, rrdtool, pyserial — production runtime is Linux-only (Debian bookworm-slim container or Raspberry Pi/bare-metal Linux); Windows is dev-only for syntax porting
- **Hardware**: ScotteCom and NBEcom protocol fixes can't be fully runtime-verified without physical burner hardware — testing strategy must rely on mocked/unit-level verification for those paths
- **Compatibility**: `.py2bak` files exist as a rollback reference per already-migrated module; only remove once that module's Python 3 behavior is confirmed correct
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3 (target: 3.13/3.14) — all application code under `src/Pellmonsrv/`, `src/Pellmonweb/`, `src/Scotteprotocol/`
- Shell (bash) — `setup-wsl.sh`, `install-2to3.sh`, `autogen.sh`, `reinstall.sh`, `src/debugsrv.sh`, `src/debugweb.sh`
- Mako templates (HTML) — `src/Pellmonweb/html/` (server-rendered web UI)
- Autotools (`configure.ac`, `Makefile.am` throughout `src/`) — legacy GNU build system, still present but largely superseded by direct `pip`/venv installs for the Python 3 port
## Runtime
- Python 3.14.0 (Windows dev venv, `venv-py3/pyvenv.cfg` — `C:\Python314`)
- Python 3.13 (WSL/Linux dev venv, `venv-wsl/pyvenv.cfg`)
- Production container target: Debian 12 "bookworm-slim" with Debian's system `python3` (see `Dockerfile`) — chosen specifically for `python3-dbus`/`python3-gi` compatibility, which are not reliably installable via pip.
- `pip` (pip3), installed inside a `venv` per environment (`venv-py3/`, `venv-wsl/`)
- No lockfile present (no `requirements.lock`, `Pipfile.lock`, or `poetry.lock`) — `requirements.txt` uses `>=` version floors only, so builds are not pinned/reproducible.
- Two parallel requirements files: `requirements.txt` (cross-platform/Docker) and `requirements-wsl.txt` (WSL-specific additions).
## Frameworks
- CherryPy `>=18.8.0` — web server/framework for `src/Pellmonweb/pellmonweb.py` (HTTP request handling, sessions, static file serving via `cherrypy.lib.static`)
- Mako `>=1.2.0` — HTML templating engine, templates in `src/Pellmonweb/html/`, rendered via `mako.template.Template` / `mako.lookup.TemplateLookup`
- Yapsy (vendored, not a pip dependency) — plugin discovery/loading framework at `src/Pellmonsrv/yapsy/`, drives the `Pellmonsrv/plugins/*` plugin architecture (see `plugin_categories.py`)
- D-Bus / GLib (`dbus`, `dbus.service`, `gi.repository.GLib`/`GObject`) — inter-process communication between `pellmonsrv` (backend daemon) and `pellmonweb` (web frontend); requires system packages `python3-dbus`, `python3-gi` (not pip-installable, hence Debian system Python in Docker)
- No formal test framework/runner detected (no `pytest`, `unittest` suite, or `tests/` directory found in `src/`).
- `test-imports.py` (repo root) is an ad-hoc smoke-test script that imports core modules (`Pellmonsrv.pellmonsrv`, `Pellmonweb.pellmonweb`, `Pellmonsrv.database`, `Pellmonweb.pellmonconf`) and reports success/failure — used to validate the Python 3 port, not a real test suite.
- GNU Autotools (`autogen.sh`, `configure.ac`, `Makefile.am`) — legacy `.in` template substitution for install paths (e.g. `src/Pellmonsrv/directories.py.in` → `directories.py` with `@datadir@`, `@confdir@`, `@localstatedir@` substituted at build/install time)
- `setup-wsl.sh` — WSL-specific dev environment bootstrap script
- Docker/`docker-compose.yml` — containerized deployment build+run
## Key Dependencies
- `pyserial>=3.5` — serial port communication with pellet burner hardware (used by `src/Pellmonsrv/plugins/scottecom/scottecom.py` via `Scotteprotocol`)
- `CherryPy>=18.8.0` — web server for `Pellmonweb`
- `Mako>=1.2.0` — HTML template rendering
- `simplejson>=3.19.0` — JSON serialization for web API responses (`src/Pellmonweb/pellmonweb.py`)
- `python-dateutil>=2.8.2` — date/time parsing
- `dbus-python` + `PyGObject` (`gi`) — commented out of `requirements.txt` (Linux system packages only, `apt-get install python3-dbus python3-gi`); required at runtime by both `pellmonsrv.py` and `pellmonweb.py` for IPC
- `rrdtool` (commented out of `requirements.txt`, installed via `apt-get install python3-rrdtool` / Docker) — round-robin database used for time-series storage of burner metrics; configured via `src/conf.d/database.conf.in`
- `argcomplete>=2.0.0` — CLI shell-completion for `pellmoncli`
- `ws4py>=0.5.1` (optional) — WebSocket support in `pellmonweb.py`; import is wrapped in try/except, falls back to `websockets = False` with a log message if missing
- `pyownet>=0.10.0` — OWFS (1-wire) client, used by `src/Pellmonsrv/plugins/owfs/__init__.py` (dynamically imported, optional)
- `pycryptodome>=3.15.0` (`Crypto.PublicKey.RSA`) + `xtea>=0.7.1` — cryptography for the NBE burner network protocol (`src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`); replaces the deprecated `python-crypto` package used pre-migration
- `pyowm>=3.3.0` — OpenWeatherMap client SDK, used by `src/Pellmonsrv/plugins/openweathermap/__init__.py`
- `RPi.GPIO` (not in requirements.txt; Raspberry Pi only) — used by `src/Pellmonsrv/plugins/raspberrygpio/__init__.py`, hard-imported (will fail off-Pi hardware)
## Configuration
- `.env` / `.env.example` (repo root) — Docker Compose variables only: `TZ`, `PELLMON_WEB_PORT` (default 8081), `PELLMON_WS_PORT` (default 8082). Note: `.env` exists in the repo tree (contents not read/quoted per policy); only non-secret deployment knobs are expected here based on `.env.example`.
- Application configuration is INI-style, not environment-variable driven: main file `config/pellmon.conf` (Docker-mounted; template at `config/pellmon.conf.example`), plus a `conf.d/` directory of per-topic `.conf` files (`src/conf.d/database.conf.in`, `src/conf.d/email.conf`, `src/conf.d/enabled_plugins.conf`, `src/conf.d/webinterface.conf.in`, `src/conf.d/plugins/`). Parsed with Python's `configparser`.
- `directories.py.in` / `version.py.in` — Autotools `.in` templates for install-path and version constants, substituted at build time (`@datadir@`, `@confdir@`, `@localstatedir@`, `@VERSION@`).
- `configure.ac`, `Makefile.am` (root, `src/`, `data/`, `initscript/`, and per-package dirs) — Autotools build configuration
- `Dockerfile` — multi-stage-free, single-stage Debian bookworm-slim image; installs system Python + rrdtool + dbus/gi + build tools, then `pip3 install --break-system-packages -r requirements.txt`
- `docker-compose.yml` — defines two services (`pellmonsrv`, `pellmonweb`) sharing a private D-Bus session bus over a Unix socket volume (`pellmon-run`), plus `pellmon-data` (RRD persistence) and `pellmon-logs` volumes
## Platform Requirements
- Windows: Python 3.14 venv (`venv-py3/`) — used for Python 3 syntax porting/import checks; D-Bus/GLib/RPi.GPIO/rrdtool features are not usable on Windows.
- WSL/Linux: Python 3.13 venv (`venv-wsl/`) — full-feature dev environment, documented in `WSL-SETUP.md` and `WSL-VERIFICATION.md`.
- Linux only (Debian bookworm-slim container or bare-metal Linux/Raspberry Pi), required for: D-Bus/GLib IPC, `rrdtool`, serial device access (`/dev/ttyUSB0`), and (for the `raspberrygpio` plugin) Raspberry Pi GPIO hardware.
- Deployment via Docker Compose (`docker-compose.yml`, `DOCKER.md`) — `pellmonsrv` runs `privileged: true` for D-Bus and serial device access; `pellmonweb` exposes ports 8081 (HTTP) and 8082 (WebSocket).
- Legacy non-Docker deployment path still present: `initscript/pellmonsrv.in`, `initscript/pellmonweb.in` (SysV-style init scripts installed via Autotools).
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Migration Context (read this first)
- **`.py2bak` sibling files:** Almost every migrated module in `src/Pellmonsrv/` has a matching `*.py2bak` file (e.g. `src/Pellmonsrv/pellmonsrv.py` + `src/Pellmonsrv/pellmonsrv.py.py2bak`, `src/Pellmonsrv/database.py` + `src/Pellmonsrv/database.py.py2bak`, and one per plugin `__init__.py`). These are **pre-migration snapshots of the Python 2 source**, kept as a reference/rollback copy during the port. Treat `.py` files as the current, authoritative source. Do not edit `.py2bak` files as if they were live code — they exist only for diffing against the pre-migration behavior (`diff foo.py.py2bak foo.py`). When adding new files that have no Python 2 predecessor, do **not** create a `.py2bak` counterpart — this pattern is a migration artifact, not a general project convention, and should be retired once the migration is complete.
- **Migration diff signature** (from `src/Pellmonsrv/pellmonsrv.py.py2bak` → `.py`): `Queue`→`queue`, `ConfigParser`→`configparser`, `urllib2`→`urllib.request`, `simplejson`→stdlib `json`, `except Exception, e:`→`except Exception as e:`, `from database import X`→`from .database import X` (relative imports), `self.setDaemon(True)`→`self.daemon = True`, `import gobject`→`from gi.repository import GLib, GObject`. When touching any not-yet-fully-verified module, expect these same patterns.
- Root-level docs `MIGRATION.md`, `MIGRATION-SUMMARY.md`, `PHASE2-COMPLETE.md`, `PHASE3-COMPLETE.md`, `PHASE3-PROGRESS.md`, `PHASE4-TESTING.md` track migration status — consult them for what's verified vs. still in progress before assuming a module is fully working under Python 3.
## Naming Patterns
- Module/package name matches its directory: plugins live at `src/Pellmonsrv/plugins/<pluginname>/__init__.py` (e.g. `src/Pellmonsrv/plugins/consumption/__init__.py`, `src/Pellmonsrv/plugins/onewire/__init__.py`).
- Lowercase, no separators for plugin directory names: `consumption`, `cleaning`, `customalarms`, `heatingcircuit`, `nbecom`, `onewire`, `openweathermap`, `owfs`, `pelletcalc`, `raspberrygpio`, `scottecom`, `silolevel`, `testplugin`.
- `snake_case` throughout, e.g. `getItem`/`setItem` are the exception (see below) but most are snake_case: `store_setting`, `load_setting`, `migrate_settings`, `barchartdata`, `rrd_total`, `readval`, `writeval` (`src/Pellmonsrv/database.py`).
- A minority of methods use `camelCase` for legacy plugin-interface methods that predate the current convention: `getItem`, `setItem`, `getDataBase`, `getTemplate` (`src/Pellmonsrv/plugin_categories.py`, `src/Pellmonsrv/plugins/consumption/__init__.py`). Match the surrounding class's existing style rather than mixing both in one file.
- Inconsistent across the codebase — no single enforced convention. Observed styles:
- **When adding a new plugin**, mirror the existing plugin file it's closest to (most use `lowercase` class names subclassing `protocols`) rather than introducing a new convention.
- `snake_case` for locals and instance attributes: `self.rrdfile`, `self.feeder_time`, `self.cache_lock`, `self.itemrefs`.
- Module-level constants/data tables use `camelCase` in places, e.g. `itemList` in `src/Pellmonsrv/plugins/consumption/__init__.py` — not `ITEM_LIST`. No `UPPER_SNAKE_CASE` constant convention is enforced; `DATADIR`, `CONFDIR`, `LOCALSTATEDIR` (from `directories.py.in`, imported in `src/Pellmonsrv/pellmonsrv.py`) are the exception.
- No type hints anywhere in the codebase (pre-dates/was never adopted; not introduced during the Python 3 port either). Do not introduce type hints inconsistently in a single file — either fully type a new module or match the untyped surrounding style.
## Code Style
- No formatter (no `black`, `ruff format`, `.prettierrc`, or `pyproject.toml` `[tool.black]` section present). Indentation is inconsistent in places (mixed under-indented `except` blocks exist, e.g. `src/Pellmonsrv/database.py:113` `except Exception as e:\n           print(e)` uses irregular indentation). Match surrounding indentation exactly rather than reformatting whole blocks.
- Line length is not constrained; some lines (SQL statements, HTML/JS template strings embedded in plugin code) run very long, e.g. `src/Pellmonsrv/plugins/consumption/__init__.py:220`.
- No linter config found (no `.flake8`, `.pylintrc`, `ruff.toml`, `setup.cfg` with lint sections). `convert-to-py3.py` (repo root) is a one-off migration helper script, not an ongoing lint/format tool.
- Old-style `%` formatting is the dominant convention for log/error messages: `logger.info('%s plugin error: %s'%(plugin_name, str(e)))` (`src/Pellmonsrv/pellmonsrv.py`), `'last %u'%bars` (`src/Pellmonsrv/plugins/consumption/__init__.py`). f-strings appear only in newer/migration-support scripts (`test-imports.py`). Prefer `%`-formatting inside `src/Pellmonsrv/` and `src/Pellmonsrv/plugins/` to stay consistent with existing modules; f-strings are acceptable in new top-level tooling scripts.
## Import Organization
- No enforced import ordering (no `isort` config). Typical pattern seen in `src/Pellmonsrv/pellmonsrv.py`: stdlib imports first (often several on one comma-separated line, e.g. `import signal, os, errno, queue, threading`), then third-party (`dbus`, `gi.repository`), then local package imports (`from Pellmonsrv.yapsy.PluginManager import PluginManager`, `from .database import Database as _Database`), with `try/except ImportError` fallback blocks for optional generated modules (`version`, `directories`).
- Comma-separated single-line imports are common and acceptable in this codebase (`import pwd, grp`, `import sqlite3, threading`) — not flagged as a style violation here.
- Within `Pellmonsrv` package, prefer relative imports for sibling modules: `from .database import Database as _Database` (this is one of the Python 3 migration fixes — Python 2 used bare `from database import X`). Use absolute `Pellmonsrv.x.y` imports when crossing into subpackages from a plugin: `from Pellmonsrv.plugin_categories import protocols`, `from Pellmonsrv.database import Item, Getsetitem`.
- Guard optional imports with `try/except ImportError`, falling back to sane defaults, rather than making the import hard-required. Example: `try: from version import __version__ \n except ImportError: __version__ = '_dev_'` (`src/Pellmonsrv/pellmonsrv.py`).
## Error Handling
- `except Exception as e:` is the dominant catch pattern (72+ occurrences across `src/`); broad bare `except:` also appears (148+ occurrences, e.g. `src/Pellmonsrv/database.py:198`, `src/Pellmonsrv/plugins/consumption/__init__.py:228`) — used for best-effort cache/lookup fallbacks where failure is expected and non-fatal.
- Errors are commonly logged and swallowed rather than propagated: `logger.info('%s plugin error: %s'%(plugin_name, str(e)))` then continue (`src/Pellmonsrv/pellmonsrv.py`). Some intentionally re-raise after logging in "debug" mode: `if conf.command == 'debug': raise else: logger.info(...)` (`src/Pellmonsrv/pellmonsrv.py`).
- Plugin-specific exceptions subclass a shared base rather than using bare `Exception`: `protocol_error` → `seqnum_error`, `protocol_timeout`, `protocol_offline` (`src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocolexceptions.py`).
- `print(e)` is used as a fallback error surface in some database code paths (`src/Pellmonsrv/database.py:113`, `:170`) instead of `logger` — this is inconsistent with the rest of the codebase, which otherwise uses the `pellMon` logger. Prefer `logger.info`/`logger.error` over bare `print()` in new code.
## Logging
- Every module that logs gets its own logger via `logger = getLogger('pellMon')` (e.g. `src/Pellmonsrv/database.py` — note: not present in `database.py`, but consistently in `src/Pellmonsrv/plugin_categories.py`, `src/Pellmonsrv/plugins/consumption/__init__.py`, `src/Pellmonsrv/pellmonsrv.py`, and 15 other files). All modules share the single `'pellMon'` named logger rather than using `__name__`-based per-module loggers.
- `logger.info(...)` is used even for what are effectively warnings/errors (e.g. failed plugin activation, migration failures) — there's no consistent use of `logger.warning`/`logger.error` levels. New code should prefer the correct level (`warning`/`error`) rather than mirroring this over-use of `info`.
- A custom `logging.Handler` subclass, `dbus_signal_handler` (`src/Pellmonsrv/pellmonsrv.py`), forwards log records as DBus signals — follow this pattern if adding another log sink.
## Comments
- Sparse inline comments, mostly explaining non-obvious workarounds, e.g. `#invalidate cache when writing` (`src/Pellmonsrv/database.py`), `#store a reference to the starts dict so it's not freed until empty` (`src/Pellmonsrv/plugins/consumption/__init__.py`).
- No systematic use of docstrings on every function; docstrings appear mainly on plugin-interface methods to document the contract, e.g. `"""Return the value for one item"""` on `getItem` (`src/Pellmonsrv/plugin_categories.py`).
- Every source file under `src/Pellmonsrv/` opens with the same GPL license header (`Copyright (C) 2013 Anders Nylund`) plus `#!/usr/bin/env python3` and `# -*- coding: utf-8 -*-`. New files added to this package should carry the same header block for consistency (copy from `src/Pellmonsrv/database.py`).
## Function Design
## Module Design
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## System Overview
```text
```
## Component Responsibilities
| Component | Responsibility | File |
|-----------|----------------|------|
| Daemon entry point / CLI | Parses args, loads config, starts/stops the daemon | `src/Pellmonsrv/pellmonsrv.py` |
| `MyDaemon` | Double-forks, initializes D-Bus, plugin loading, signal handlers, main glib loop | `src/Pellmonsrv/pellmonsrv.py` (class `MyDaemon`) |
| `Daemon` base class | Generic Unix daemonization (fork/pidfile) via `python-daemon`-style logic | `src/Pellmonsrv/daemon.py` |
| `config` | Parses `pellmon.conf` (+ `conf.d/*.conf`), builds RRD create string, email settings, plugin dirs | `src/Pellmonsrv/pellmonsrv.py` (class `config`) |
| `Database` (daemon-side) | Threaded wrapper around the in-memory DB; polls item values every 2s, emits D-Bus signal on change | `src/Pellmonsrv/pellmonsrv.py` (class `Database(threading.Thread, _Database)`) |
| `Database` (core) | `WeakValueDictionary` mapping item name → `Item`; get/set value/text helpers | `src/Pellmonsrv/database.py` |
| `Item` hierarchy | `Item`, `Plainitem`, `Getsetitem`, `Cacheditem`, `Storeditem` — different value-storage strategies (static, getter/setter callback, time-cached, SQLite-persisted) | `src/Pellmonsrv/database.py` |
| `Keyval_storage` | SQLite-backed key/value store for persisted plugin settings | `src/Pellmonsrv/database.py` |
| `MyDBUSService` | Exposes `org.pellmon.int` D-Bus interface (GetItem, SetItem, GetDB, GetFullDB, getMenutags, getPlugins, changed_parameters signal) | `src/Pellmonsrv/pellmonsrv.py` (class `MyDBUSService`) |
| `Poller` | Background thread; on `SIGALRM` reads configured DB items and shells out to `rrdtool update` | `src/Pellmonsrv/pellmonsrv.py` (class `Poller`) |
| Plugin framework (yapsy) | Discovers `*.pellmon-plugin` descriptor files, imports matching module, filters by category, instantiates plugin object | `src/Pellmonsrv/yapsy/PluginManager.py`, `ConfigurablePluginManager.py`, `VersionedPluginManager.py`, `IPlugin.py` |
| `protocols` category interface | Base class all "Protocols" plugins inherit; provides `activate`, template registry, settings load/store/migrate, `sendmail` callback | `src/Pellmonsrv/plugin_categories.py` |
| Protocol plugins | Talk to real hardware (pellet burner controllers) and insert `Item`s into the shared DB | `src/Pellmonsrv/plugins/scottecom/`, `src/Pellmonsrv/plugins/nbecom/` |
| Utility/derived-data plugins | Compute/derive values, alarms, GPIO, one-wire sensors, weather, silo level, etc. — also inherit `protocols` | `src/Pellmonsrv/plugins/calculate/`, `cleaning/`, `consumption/`, `customalarms/`, `exec/`, `heatingcircuit/`, `onewire/`, `openweathermap/`, `owfs/`, `pelletcalc/`, `raspberrygpio/`, `silolevel/` |
| Scotte protocol library | Low-level frame/serial protocol implementation used by `scottecom` plugin | `src/Scotteprotocol/protocol.py`, `frames.py`, `datamap.py`, `enumerations.py`, `transformations.py` |
| NBE protocol library | Low-level TCP/UDP protocol implementation used by `nbecom` plugin | `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`, `frames.py`, `language.py`, `langmap.py`, `protocolexceptions.py` |
| Web app entry point | CherryPy application: routes, mako templates, D-Bus client, websockets, auth | `src/Pellmonweb/pellmonweb.py` |
| Web `Dbus_handler` | Client-side D-Bus proxy; connects to `org.pellmon.int`, watches name owner, relays `changed_parameters` signal to `Sensor` websocket subscribers | `src/Pellmonweb/pellmonweb.py` (class `Dbus_handler`) |
| Auth module | HTTP basic-auth style login for the web UI | `src/Pellmonweb/auth.py` |
| Consumption / logview / conf pages | Secondary CherryPy page controllers | `src/Pellmonweb/consumption.py`, `src/Pellmonweb/logview.py`, `src/Pellmonweb/pellmonconf.py` |
## Pattern Overview
- Two OS processes (`pellmonsrv`, `pellmonweb`), no shared memory — all cross-process communication is D-Bus method calls/signals.
- Plugin architecture (yapsy, vendored under `src/Pellmonsrv/yapsy/`) drives nearly all extensibility: every protocol/data-source is a plugin discovered at runtime from a `.pellmon-plugin` INI descriptor + Python package.
- Uniform "Item" abstraction decouples data producers (plugins) from consumers (D-Bus service, RRD poller, web UI) — everything is a named string-valued item with optional getter/setter/cache/persistence behavior.
- Config-driven wiring: which plugins are enabled, which items are polled into RRD, and per-plugin settings all come from `pellmon.conf` + `conf.d/*.conf` (parsed with `configparser`).
- Currently mid Python-2→3 migration (branch `python3-migration`); some plugins (e.g. `plugins/calculate/__init__.py`) still contain unported Python-2-only code (`from string import maketrans`, `unicode(value)`), meaning not all plugins are fully functional in Python 3 yet.
## Layers
- Purpose: OS-level process bootstrap, daemonization, CLI parsing, signal handling.
- Location: `src/Pellmonsrv/pellmonsrv.py` (`run()`, `MyDaemon`, `config`), `src/Pellmonsrv/daemon.py`, `src/Pellmonweb/pellmonweb.py`.
- Contains: argparse CLI, config file parsing, privilege dropping (`drop_privileges`), D-Bus mainloop bootstrap.
- Depends on: `plugin_categories`, `database`, `yapsy`.
- Used by: init scripts (`initscript/pellmonsrv.in`, `initscript/pellmonweb.in`), Docker entrypoint (`Dockerfile`).
- Purpose: Discover, filter, and activate plugins by category.
- Location: `src/Pellmonsrv/yapsy/` (vendored yapsy library), `src/Pellmonsrv/plugin_categories.py`.
- Contains: `PluginManager`, `IPlugin`, category interface classes (`protocols`).
- Depends on: filesystem scan of plugin dirs (`conf.plugin_dirs`), `.pellmon-plugin` INI descriptors.
- Used by: `pellmonsrv.py` (`Database.__init__` — plugin activation loop).
- Purpose: Concrete data sources/sinks — hardware protocol adapters and computed/derived data.
- Location: `src/Pellmonsrv/plugins/*/__init__.py` (one package per plugin, `Makefile.am` + `*.pellmon-plugin` descriptor per plugin).
- Contains: Subclasses of `protocols` (from `plugin_categories.py`); each inserts `Item`/`Getsetitem`/`Storeditem` instances into the shared `db`.
- Depends on: `plugin_categories.protocols`, `database.py` item classes, and (for hardware plugins) dedicated protocol packages (`Scotteprotocol`, `plugins/nbecom/nbeprotocol`).
- Used by: Loaded dynamically by `PluginManager`; never imported directly by other layers.
- Purpose: In-memory, weakly-referenced store of all data/parameter/command items; SQLite persistence for settings.
- Location: `src/Pellmonsrv/database.py`.
- Contains: `Database(WeakValueDictionary)`, `Item` subclasses, `Keyval_storage` (SQLite).
- Depends on: `sqlite3`, `threading`.
- Used by: All plugins (via `self.db.insert(...)`), `pellmonsrv.py` `Database` thread (polls values), `MyDBUSService` (exposes values over D-Bus).
- Purpose: Expose the shared database to other processes.
- Location: `src/Pellmonsrv/pellmonsrv.py` (`MyDBUSService`), `src/Pellmonweb/pellmonweb.py` (`Dbus_handler`).
- Contains: D-Bus service methods/signals on the daemon side; a D-Bus client proxy + signal watcher on the web side.
- Depends on: `dbus-python`, `PyGObject` (`gi.repository.GLib`).
- Used by: Web layer for all data access; nothing else talks to the daemon's data directly.
- Purpose: HTTP UI, REST-ish endpoints, graph rendering, websocket live updates, auth, config editing, log viewing.
- Location: `src/Pellmonweb/pellmonweb.py`, `auth.py`, `consumption.py`, `logview.py`, `pellmonconf.py`, templates in `src/Pellmonweb/html*`, static assets in `src/Pellmonweb/media/`.
- Contains: CherryPy `Root`-style page classes, Mako templates, `Sensor`/websocket classes.
- Depends on: `cherrypy`, `mako`, `Dbus_handler` (this file's D-Bus client), `simplejson`.
- Used by: Browsers; nothing internal depends on this layer.
## Data Flow
### Primary polling/persistence path (daemon side)
### Plugin activation path
### Web request / live-update path
- Daemon-side state lives entirely in the process: the `Database` (`WeakValueDictionary` of `Item`s), `conf` (global `config` instance), and per-plugin instance attributes. There is no shared memory or shared file used for live values between processes — only D-Bus.
- Persisted state is split between an RRD time-series file (`conf.db`/`conf.nvdb`, optionally copied to/from a ramdisk via `copy_db`) and a SQLite key/value database (`conf.keyval_db`) for plugin settings (`Keyval_storage` in `database.py`).
- Web-side state is minimal/stateless per request; `Sensor.sensorlist` is the only process-level mutable list, tracking active websocket subscribers.
## Key Abstractions
- Purpose: Represent one named data/parameter/command point with pluggable value semantics — static value, live getter/setter callback, time-windowed cache, or SQLite-persisted value.
- Examples: `Getsetitem` used by `scottecom.py:49`, `plugins/nbecom/__init__.py:55`; `Storeditem` used by `plugins/nbecom/__init__.py:71`, `plugins/calculate/__init__.py:300`.
- Pattern: composition via constructor-injected `getter`/`setter` callables rather than subclass-per-source; thread-safety via per-item `threading.Lock`.
- Purpose: Common contract every plugin implements — `activate(conf, glob, db)`, template registry, settings load/store, `settings_changed` callback into the daemon's alarm/email logic, `migrate_settings` for legacy `values.conf` files.
- Examples: `src/Pellmonsrv/plugins/*/__init__.py` all subclass this via `from Pellmonsrv.plugin_categories import protocols`.
- Pattern: Template-method-like base class combined with yapsy's `IPlugin` lifecycle (`activate`/`deactivate`).
- Purpose: INI file per plugin (`[Core] Name`, `Module`, `[Documentation]`) that `PluginManager.collectPlugins()` scans to locate and import the plugin's Python module.
- Examples: `src/Pellmonsrv/plugins/calculate.pellmon-plugin`, `src/Pellmonsrv/plugins/scottecom.pellmon-plugin` (sibling to each `plugins/<name>/` directory).
- Pattern: Convention — descriptor file lives one level above the plugin package it describes; `Module` value must match the package/module name.
- Purpose: The single, versioned public API surface between daemon and any client (web app, CLI tools).
- Examples: `GetItem`, `SetItem`, `GetDB`, `GetFullDB`, `getMenutags`, `getPlugins`, `changed_parameters` signal (`pellmonsrv.py:139-202`).
- Pattern: Thin RPC facade directly over the `Database`/`Item` abstraction — no separate DTO layer.
## Entry Points
- Location: `src/Pellmonsrv/pellmonsrv.py` (`if __name__ == "__main__": run()`), installed via `initscript/pellmonsrv.in`.
- Triggers: System init/systemd or manual CLI (`pellmonsrv start|stop|restart|debug`).
- Responsibilities: Load config, load/activate plugins, start D-Bus service, poll data into RRD, run forever inside a GLib main loop.
- Location: `src/Pellmonweb/pellmonweb.py`, installed via `initscript/pellmonweb.in`.
- Triggers: System init/systemd or manual CLI; runs a CherryPy HTTP server.
- Responsibilities: Serve UI/API, proxy reads/writes to the daemon over D-Bus, render RRD graphs, handle auth/login.
- Location: `Dockerfile`, `docker-compose.yml`.
- Triggers: `docker compose up`.
- Responsibilities: Container packaging of both processes for containerized deployment (see `DOCKER.md`).
## Architectural Constraints
- **Threading:** Multiple long-lived daemon threads coexist in the `pellmonsrv` process: the `Database` thread (2s value-diff/D-Bus-signal loop), the `Poller` thread (RRD update loop, gated by a `threading.Event` set from a `SIGALRM` handler), a `db_copy_thread` self-rescheduling `threading.Timer`, plus per-plugin threads/timers (e.g. `scottecom.py` settings/alarm poll threads, `plugins/calculate/__init__.py` `calcthread`). There is no central thread supervisor; failures are individually try/except-swallowed.
- **Global state:** `conf` (the `config` instance) and `logger` are process-globals set via `global` statements inside `run()`/`MyDaemon.run()`/`config.__init__` (`pellmonsrv.py`); plugin modules also use module-level globals for shared state, e.g. `itemList`, `itemTags`, `itemValues`, `gstore` in `src/Pellmonsrv/plugins/calculate/__init__.py:32-35`, which means only one instance of the `calculate` plugin can safely be active per process.
- **IPC boundary:** The daemon and web process must both reach the same D-Bus bus (`SESSION` or `SYSTEM`, chosen via `-D`/`--DBUS` CLI flag on each); if buses differ, the web app cannot see the daemon (`Dbus_handler` reports "server not running").
- **Plugin ordering:** Plugins register their own D-Bus/logging side effects; the base `protocols.activate()` must run before any plugin-specific setup (all plugins call `protocols.activate(self, conf, glob, db, ...)` first).
- **Python 2→3 migration in progress:** Not all modules are verified fully Python 3-clean; `src/Pellmonsrv/plugins/calculate/__init__.py` still imports `from string import maketrans` (Python 2-only) and calls `unicode(...)` (removed in Python 3), meaning that plugin will `NameError`/`ImportError` at runtime until fixed. `.py2bak` backup files alongside many modules (e.g. `pellmonsrv.py.py2bak`) are pre-migration snapshots kept for reference/rollback, not part of the running codebase.
## Anti-Patterns
### Bare/broad `except:` swallowing errors
### Module-level mutable globals in plugins
## Error Handling
- Plugin activation failures are caught individually so one broken plugin doesn't prevent others from loading (`pellmonsrv.py:93-103`); in `debug` command mode exceptions are re-raised for visibility.
- Polling failures write the RRD sentinel value `'U'` (undefined) instead of raising (`Poller.run`, `pellmonsrv.py:226-268`).
- A dedicated `dbus_signal_handler(logging.Handler)` forwards `logger` records to `MyDBUSService.changed_parameters` as a synthetic `__event__` item, letting the web UI surface daemon log messages live (`pellmonsrv.py:57-65`).
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
