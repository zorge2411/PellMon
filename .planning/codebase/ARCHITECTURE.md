<!-- refreshed: 2026-09-17 -->
# Architecture

**Analysis Date:** 2026-09-17

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        Pellmonweb (web frontend)                     │
│  `src/Pellmonweb/pellmonweb.py` — CherryPy app + Mako templates      │
│  serves HTML/JS, websockets, graphs, auth, log viewer                │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ D-Bus (org.pellmon.int interface)
                                 │ GetItem / SetItem / GetDB / GetFullDB /
                                 │ changed_parameters signal
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Pellmonsrv (monitoring daemon)                    │
│  `src/Pellmonsrv/pellmonsrv.py` — daemon, D-Bus service, RRD poller  │
├───────────────────┬───────────────────┬───────────────────────────────┤
│  Database (in-mem)│  PluginManager     │  Poller / db_copy_thread     │
│ `database.py`     │  `yapsy/`          │  (threads inside pellmonsrv) │
└─────────┬─────────┴─────────┬─────────┴───────────────┬───────────────┘
          │                   │                          │
          │           loads & activates                  │ rrdtool subprocess
          │                   ▼                          ▼
          │        ┌───────────────────────┐   ┌──────────────────────┐
          │        │   plugins/*  (Protocol │   │  RRD database file   │
          │        │   + utility plugins)   │   │  (`conf.db`/`nvdb`)  │
          │        │ `src/Pellmonsrv/       │   └──────────────────────┘
          │        │   plugins/*/__init__.py`│
          │        └──────────┬─────────────┘
          │                   │ inserts Item objects
          ▼                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Shared in-memory Database (WeakValueDictionary of Item objects)     │
│  `src/Pellmonsrv/database.py`                                        │
│  + SQLite keyval store for persisted settings (`Keyval_storage`)     │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Hardware / external protocols (serial, TCP, one-wire, HTTP)         │
│  e.g. `Scotteprotocol/`, `plugins/nbecom/nbeprotocol/`,               │
│  `plugins/owfs/`, `plugins/openweathermap/`                          │
└─────────────────────────────────────────────────────────────────────┘
```

The system is two independently-run Python processes (`pellmonsrv` and `pellmonweb`) that communicate exclusively over a session/system D-Bus interface (`org.pellmon.int`). `pellmonsrv` owns all hardware/protocol communication and a shared in-memory "database" of named `Item` objects; `pellmonweb` is a stateless CherryPy web app that reads/writes those items only through D-Bus calls and receives live updates via a `changed_parameters` D-Bus signal relayed to browser websockets.

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

**Overall:** Plugin-based monitoring daemon + thin web front end, integrated via D-Bus IPC. Core pattern is "hardware protocol adapters register named data Items into a shared in-memory store; a poller persists a subset of those items to an RRD time-series database; a separate web process reads/writes items purely through D-Bus."

**Key Characteristics:**
- Two OS processes (`pellmonsrv`, `pellmonweb`), no shared memory — all cross-process communication is D-Bus method calls/signals.
- Plugin architecture (yapsy, vendored under `src/Pellmonsrv/yapsy/`) drives nearly all extensibility: every protocol/data-source is a plugin discovered at runtime from a `.pellmon-plugin` INI descriptor + Python package.
- Uniform "Item" abstraction decouples data producers (plugins) from consumers (D-Bus service, RRD poller, web UI) — everything is a named string-valued item with optional getter/setter/cache/persistence behavior.
- Config-driven wiring: which plugins are enabled, which items are polled into RRD, and per-plugin settings all come from `pellmon.conf` + `conf.d/*.conf` (parsed with `configparser`).
- Currently mid Python-2→3 migration (branch `python3-migration`); some plugins (e.g. `plugins/calculate/__init__.py`) still contain unported Python-2-only code (`from string import maketrans`, `unicode(value)`), meaning not all plugins are fully functional in Python 3 yet.

## Layers

**Entry/process layer:**
- Purpose: OS-level process bootstrap, daemonization, CLI parsing, signal handling.
- Location: `src/Pellmonsrv/pellmonsrv.py` (`run()`, `MyDaemon`, `config`), `src/Pellmonsrv/daemon.py`, `src/Pellmonweb/pellmonweb.py`.
- Contains: argparse CLI, config file parsing, privilege dropping (`drop_privileges`), D-Bus mainloop bootstrap.
- Depends on: `plugin_categories`, `database`, `yapsy`.
- Used by: init scripts (`initscript/pellmonsrv.in`, `initscript/pellmonweb.in`), Docker entrypoint (`Dockerfile`).

**Plugin framework layer:**
- Purpose: Discover, filter, and activate plugins by category.
- Location: `src/Pellmonsrv/yapsy/` (vendored yapsy library), `src/Pellmonsrv/plugin_categories.py`.
- Contains: `PluginManager`, `IPlugin`, category interface classes (`protocols`).
- Depends on: filesystem scan of plugin dirs (`conf.plugin_dirs`), `.pellmon-plugin` INI descriptors.
- Used by: `pellmonsrv.py` (`Database.__init__` — plugin activation loop).

**Plugin implementation layer:**
- Purpose: Concrete data sources/sinks — hardware protocol adapters and computed/derived data.
- Location: `src/Pellmonsrv/plugins/*/__init__.py` (one package per plugin, `Makefile.am` + `*.pellmon-plugin` descriptor per plugin).
- Contains: Subclasses of `protocols` (from `plugin_categories.py`); each inserts `Item`/`Getsetitem`/`Storeditem` instances into the shared `db`.
- Depends on: `plugin_categories.protocols`, `database.py` item classes, and (for hardware plugins) dedicated protocol packages (`Scotteprotocol`, `plugins/nbecom/nbeprotocol`).
- Used by: Loaded dynamically by `PluginManager`; never imported directly by other layers.

**Shared data layer:**
- Purpose: In-memory, weakly-referenced store of all data/parameter/command items; SQLite persistence for settings.
- Location: `src/Pellmonsrv/database.py`.
- Contains: `Database(WeakValueDictionary)`, `Item` subclasses, `Keyval_storage` (SQLite).
- Depends on: `sqlite3`, `threading`.
- Used by: All plugins (via `self.db.insert(...)`), `pellmonsrv.py` `Database` thread (polls values), `MyDBUSService` (exposes values over D-Bus).

**IPC/service layer:**
- Purpose: Expose the shared database to other processes.
- Location: `src/Pellmonsrv/pellmonsrv.py` (`MyDBUSService`), `src/Pellmonweb/pellmonweb.py` (`Dbus_handler`).
- Contains: D-Bus service methods/signals on the daemon side; a D-Bus client proxy + signal watcher on the web side.
- Depends on: `dbus-python`, `PyGObject` (`gi.repository.GLib`).
- Used by: Web layer for all data access; nothing else talks to the daemon's data directly.

**Web layer:**
- Purpose: HTTP UI, REST-ish endpoints, graph rendering, websocket live updates, auth, config editing, log viewing.
- Location: `src/Pellmonweb/pellmonweb.py`, `auth.py`, `consumption.py`, `logview.py`, `pellmonconf.py`, templates in `src/Pellmonweb/html*`, static assets in `src/Pellmonweb/media/`.
- Contains: CherryPy `Root`-style page classes, Mako templates, `Sensor`/websocket classes.
- Depends on: `cherrypy`, `mako`, `Dbus_handler` (this file's D-Bus client), `simplejson`.
- Used by: Browsers; nothing internal depends on this layer.

## Data Flow

### Primary polling/persistence path (daemon side)

1. `MyDaemon.run()` starts `Poller` thread and installs `SIGALRM` handler firing every `conf.poll_interval` seconds (`src/Pellmonsrv/pellmonsrv.py:493-499`).
2. `periodic_signal_handler` sets `self.pollevent`, waking `Poller.run()` (`pellmonsrv.py:204-291`).
3. `Poller.run()` iterates `conf.pollData` (built from `[pollvalues]`/`[rrd_ds_names]`/`[rrd_ds_types]` config sections), reads each item's current value from `conf.database[name].value` (`pellmonsrv.py:225-271`).
4. Values are joined into a colon-separated string and shelled out to `rrdtool update <db> <timestamp>:<values>` via `subprocess.Popen` (`pellmonsrv.py:278-284`).
5. Separately, the daemon-side `Database` thread (`class Database(threading.Thread, _Database)`) wakes every 2s, diffs current item values against `self.values`, and on change emits the D-Bus signal `changed_parameters` with a JSON payload (`pellmonsrv.py:110-132`).

### Plugin activation path

1. `Database.__init__()` builds a `PluginManager` filtered to category `Protocols` (`plugin_categories.protocols`), points it at `conf.plugin_dirs`, calls `collectPlugins()` (`pellmonsrv.py:84-87`).
2. For each name in `conf.enabled_plugins`, the matching plugin object's `activate(conf.plugin_conf[name], globals(), self)` is called (`pellmonsrv.py:91-103`); `self` is the shared `Database` instance passed in as `db`.
3. Inside `activate()`, plugin code (e.g. `scottecom.py`, `plugins/nbecom/__init__.py`) constructs `Getsetitem`/`Storeditem` objects with `getter`/`setter` callables bound to its own protocol object, and calls `self.db.insert(dbitem)` for each data point (`scottecom.py:44-66`).
4. Failed activations are caught and logged; in `debug` command mode the exception is re-raised (`pellmonsrv.py:98-103`).

### Web request / live-update path

1. Browser requests a page from CherryPy app in `pellmonweb.py`; page controllers call into `Dbus_handler` methods, which invoke the daemon's `MyDBUSService` methods (`GetItem`, `SetItem`, `GetDB`, `GetFullDB`, `getMenutags`) over D-Bus (`pellmonsrv.py:149-197`).
2. For live updates, the browser opens a websocket; a `Sensor` object registers itself and receives pushes whenever the daemon emits `changed_parameters` (`pellmonweb.py:67-116`, `pellmonsrv.py:200-202`).
3. `Dbus_handler.start()` watches D-Bus name ownership of `org.pellmon.int`; if the daemon isn't running, `remote_object` is `None` and calls raise/handle `DbusNotConnected` (`pellmonweb.py:117-146`).

**State Management:**
- Daemon-side state lives entirely in the process: the `Database` (`WeakValueDictionary` of `Item`s), `conf` (global `config` instance), and per-plugin instance attributes. There is no shared memory or shared file used for live values between processes — only D-Bus.
- Persisted state is split between an RRD time-series file (`conf.db`/`conf.nvdb`, optionally copied to/from a ramdisk via `copy_db`) and a SQLite key/value database (`conf.keyval_db`) for plugin settings (`Keyval_storage` in `database.py`).
- Web-side state is minimal/stateless per request; `Sensor.sensorlist` is the only process-level mutable list, tracking active websocket subscribers.

## Key Abstractions

**`Item` / `Getsetitem` / `Cacheditem` / `Storeditem` (`src/Pellmonsrv/database.py`):**
- Purpose: Represent one named data/parameter/command point with pluggable value semantics — static value, live getter/setter callback, time-windowed cache, or SQLite-persisted value.
- Examples: `Getsetitem` used by `scottecom.py:49`, `plugins/nbecom/__init__.py:55`; `Storeditem` used by `plugins/nbecom/__init__.py:71`, `plugins/calculate/__init__.py:300`.
- Pattern: composition via constructor-injected `getter`/`setter` callables rather than subclass-per-source; thread-safety via per-item `threading.Lock`.

**`protocols` plugin interface (`src/Pellmonsrv/plugin_categories.py`):**
- Purpose: Common contract every plugin implements — `activate(conf, glob, db)`, template registry, settings load/store, `settings_changed` callback into the daemon's alarm/email logic, `migrate_settings` for legacy `values.conf` files.
- Examples: `src/Pellmonsrv/plugins/*/__init__.py` all subclass this via `from Pellmonsrv.plugin_categories import protocols`.
- Pattern: Template-method-like base class combined with yapsy's `IPlugin` lifecycle (`activate`/`deactivate`).

**Yapsy plugin descriptors (`*.pellmon-plugin`):**
- Purpose: INI file per plugin (`[Core] Name`, `Module`, `[Documentation]`) that `PluginManager.collectPlugins()` scans to locate and import the plugin's Python module.
- Examples: `src/Pellmonsrv/plugins/calculate.pellmon-plugin`, `src/Pellmonsrv/plugins/scottecom.pellmon-plugin` (sibling to each `plugins/<name>/` directory).
- Pattern: Convention — descriptor file lives one level above the plugin package it describes; `Module` value must match the package/module name.

**D-Bus interface `org.pellmon.int` (`MyDBUSService` in `pellmonsrv.py`):**
- Purpose: The single, versioned public API surface between daemon and any client (web app, CLI tools).
- Examples: `GetItem`, `SetItem`, `GetDB`, `GetFullDB`, `getMenutags`, `getPlugins`, `changed_parameters` signal (`pellmonsrv.py:139-202`).
- Pattern: Thin RPC facade directly over the `Database`/`Item` abstraction — no separate DTO layer.

## Entry Points

**`pellmonsrv` (monitoring daemon):**
- Location: `src/Pellmonsrv/pellmonsrv.py` (`if __name__ == "__main__": run()`), installed via `initscript/pellmonsrv.in`.
- Triggers: System init/systemd or manual CLI (`pellmonsrv start|stop|restart|debug`).
- Responsibilities: Load config, load/activate plugins, start D-Bus service, poll data into RRD, run forever inside a GLib main loop.

**`pellmonweb` (web UI):**
- Location: `src/Pellmonweb/pellmonweb.py`, installed via `initscript/pellmonweb.in`.
- Triggers: System init/systemd or manual CLI; runs a CherryPy HTTP server.
- Responsibilities: Serve UI/API, proxy reads/writes to the daemon over D-Bus, render RRD graphs, handle auth/login.

**Docker entrypoint:**
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

**What happens:** Very large numbers of `try/except` blocks (config parsing, plugin activation, item polling, email sending) catch bare `except:` or `except Exception as e:` and merely `pass` or `logger.info(str(e))`, e.g. `pellmonsrv.py:126-128` (`Poller` item value collection), `config.__init__` (`pellmonsrv.py:524-751`, dozens of bare excepts for every config option).
**Why it's wrong:** Failures (missing config, protocol errors, bad plugin state) are silently absorbed; root causes are hard to diagnose from logs, and typos in config keys fail silently instead of erroring.
**Do this instead:** Prefer narrow exception types and surface unexpected errors at `warning`/`error` log level; reserve bare `except: pass` only for genuinely optional/best-effort operations (already partially done via `logger.info` in some places — extend that consistently).

### Module-level mutable globals in plugins

**What happens:** `src/Pellmonsrv/plugins/calculate/__init__.py` defines `itemList=[]`, `itemTags={}`, `itemValues={}`, `gstore = {}` at module scope instead of as instance attributes of `calculateplugin`.
**Why it's wrong:** State leaks across plugin instances/reloads and is not encapsulated by the `protocols` activation lifecycle; makes testing and multiple-instance use impossible.
**Do this instead:** Move these into `self` inside `calculateplugin.activate()`, matching the pattern already used in `scottecom.py` (`self.dbvalues`, `self.itemrefs`).

## Error Handling

**Strategy:** Defensive, per-operation try/except with logging via the module-level `logger = logging.getLogger('pellMon')`; most failures degrade gracefully (item shows `'U'`/`'error'`, plugin fails to activate but daemon continues) rather than crashing the process.

**Patterns:**
- Plugin activation failures are caught individually so one broken plugin doesn't prevent others from loading (`pellmonsrv.py:93-103`); in `debug` command mode exceptions are re-raised for visibility.
- Polling failures write the RRD sentinel value `'U'` (undefined) instead of raising (`Poller.run`, `pellmonsrv.py:226-268`).
- A dedicated `dbus_signal_handler(logging.Handler)` forwards `logger` records to `MyDBUSService.changed_parameters` as a synthetic `__event__` item, letting the web UI surface daemon log messages live (`pellmonsrv.py:57-65`).

## Cross-Cutting Concerns

**Logging:** Single named logger `'pellMon'` (`logging.getLogger('pellMon')`) shared across the daemon and imported by every plugin module; configured once in `config.__init__` with a `WatchedFileHandler` (or `StreamHandler` fallback) plus a `dbus_signal_handler` added later in `MyDaemon.run()`.
**Validation:** No schema validation layer; config values are read with `try/except`-guarded `configparser` calls and defaulted inline; plugin config validation is ad hoc per plugin (e.g. `scottecom.py` falls back to a "testprotocol" if `serialport`/`chipversion` config is missing/invalid).
**Authentication:** Handled only in the web layer via `src/Pellmonweb/auth.py` (basic-auth-style, configured under `[authentication]` in `pellmon.conf`); the daemon and its D-Bus interface have no authentication — access is controlled solely by D-Bus bus policy (session vs. system bus).

---

*Architecture analysis: 2026-09-17*
