# Codebase Structure

**Analysis Date:** 2026-09-17

## Directory Layout

```
PellMon-master/
├── src/
│   ├── Pellmonsrv/                # Monitoring daemon package (Python)
│   │   ├── pellmonsrv.py          # Daemon entry point, CLI, config, D-Bus service, poller
│   │   ├── daemon.py              # Generic Unix daemonization base class
│   │   ├── database.py            # In-memory Database + Item classes + SQLite keyval store
│   │   ├── plugin_categories.py   # `protocols` plugin interface (base class for all plugins)
│   │   ├── directories.py.in      # Autotools template → directories.py (DATADIR/CONFDIR/...)
│   │   ├── yapsy/                 # Vendored yapsy plugin-loading library
│   │   │   ├── PluginManager.py
│   │   │   ├── ConfigurablePluginManager.py
│   │   │   ├── VersionedPluginManager.py
│   │   │   └── IPlugin.py
│   │   └── plugins/                       # One subdirectory per plugin (see below)
│   │       ├── <plugin>.pellmon-plugin     # INI descriptor: [Core] Name/Module, [Documentation]
│   │       └── <plugin>/__init__.py        # Plugin implementation (subclasses `protocols`)
│   │           ├── calculate/              # Stack-based expression/alarm calculator plugin
│   │           ├── cleaning/                # Cleaning cycle tracking plugin
│   │           ├── consumption/             # Pellet consumption tracking (+ templates/)
│   │           ├── customalarms/            # User-defined alarm conditions
│   │           ├── exec/                    # Runs external commands as data sources
│   │           ├── heatingcircuit/          # Heating circuit control plugin
│   │           ├── nbecom/                  # NBE burner protocol plugin
│   │           │   └── nbeprotocol/         # NBE wire protocol implementation
│   │           │       ├── protocol.py, frames.py, language.py, langmap.py
│   │           │       ├── protocolexceptions.py
│   │           │       └── language/        # Language/translation data files
│   │           ├── onewire/                 # 1-Wire sensor plugin
│   │           ├── openweathermap/          # OpenWeatherMap API integration plugin
│   │           ├── owfs/                    # OWFS (1-Wire filesystem) plugin
│   │           ├── pelletcalc/              # Pellet usage calculation plugin
│   │           ├── raspberrygpio/           # Raspberry Pi GPIO plugin
│   │           ├── scottecom/               # Scotte burner protocol plugin
│   │           │   ├── scottecom.py         # Plugin class (imports Scotteprotocol)
│   │           │   ├── datamenu.py, menus.py, descriptions.py
│   │           ├── silolevel/               # Pellet silo level plugin
│   │           └── testplugin/              # Minimal example/test plugin
│   ├── Scotteprotocol/             # Standalone Scotte wire-protocol library (used by scottecom plugin)
│   │   ├── protocol.py, frames.py, datamap.py, enumerations.py, transformations.py
│   └── Pellmonweb/                 # Web UI package (CherryPy + Mako)
│       ├── pellmonweb.py           # Web entry point: CherryPy app, D-Bus client, websockets
│       ├── auth.py                 # Basic-auth login handling
│       ├── consumption.py          # Consumption page controller
│       ├── logview.py              # Log viewer page controller
│       ├── pellmonconf.py          # Web-based config editor controller
│       ├── html/                   # Mako templates for the main UI (index, graph, parameters, ...)
│       ├── html_conf/              # Mako templates for the config editor
│       └── media/                  # Static assets (bs3 CSS/JS, codemirror, flot charting, images)
├── config/
│   ├── pellmon.conf                # Active runtime config (daemon + web)
│   ├── pellmon.conf.example        # Documented example config (Docker-oriented)
│   └── conf.d/                     # Drop-in additional `.conf` fragments (config_dir)
├── data/
│   ├── Makefile.am
│   └── pellmon_dbus.conf.in        # D-Bus system-bus policy template
├── initscript/
│   ├── pellmonsrv.in                # Init script template for the daemon
│   └── pellmonweb.in                # Init script template for the web app
├── Archive/PellMon-master/          # Frozen pre-migration snapshot of the whole tree (reference only)
├── .snapshots/                      # Additional point-in-time snapshots (reference only)
├── requirements.txt                 # Python 3 runtime dependencies
├── requirements-wsl.txt             # WSL-specific dependency variant
├── Dockerfile / docker-compose.yml / DOCKER.md   # Container packaging
├── configure.ac / Makefile.am / autogen.sh        # Autotools build system (install paths, .in templates)
├── MIGRATION*.md, PHASE*-*.md, INSTALL-2TO3.md, modernize-*.txt  # Python 2→3 migration tracking docs
└── convert-to-py3.py / install-2to3.sh             # Migration helper scripts
```

## Directory Purposes

**`src/Pellmonsrv/`:**
- Purpose: The monitoring daemon — everything needed to talk to hardware, hold live data, and expose it over D-Bus.
- Contains: Entry point, daemonization, config parsing, in-memory database, plugin framework, all plugins.
- Key files: `src/Pellmonsrv/pellmonsrv.py`, `src/Pellmonsrv/database.py`, `src/Pellmonsrv/plugin_categories.py`.

**`src/Pellmonsrv/yapsy/`:**
- Purpose: Vendored copy of the yapsy plugin-discovery library (not a pip dependency — lives in-tree).
- Contains: `PluginManager`, `ConfigurablePluginManager`, `VersionedPluginManager`, `IPlugin` base class.
- Key files: `src/Pellmonsrv/yapsy/PluginManager.py`.

**`src/Pellmonsrv/plugins/`:**
- Purpose: Every hardware protocol adapter and every derived/computed data source, as independently loadable plugins.
- Contains: One directory per plugin (`<name>/__init__.py`) plus a sibling `<name>.pellmon-plugin` INI descriptor and `Makefile.am`.
- Key files: `src/Pellmonsrv/plugins/scottecom/__init__.py`, `src/Pellmonsrv/plugins/nbecom/__init__.py`, `src/Pellmonsrv/plugins/calculate/__init__.py`.

**`src/Scotteprotocol/`:**
- Purpose: Standalone library implementing the Scotte pellet burner serial protocol, independent of the plugin framework.
- Contains: Frame encode/decode, data maps, enumerations, unit transformations.
- Key files: `src/Scotteprotocol/protocol.py` (imported directly as `from Scotteprotocol import Protocol` in `scottecom.py`).

**`src/Pellmonweb/`:**
- Purpose: Web UI process — CherryPy app serving Mako-templated HTML, JSON endpoints, websockets, graphing.
- Contains: Page controllers, templates (`html/`, `html_conf/`), static assets (`media/`).
- Key files: `src/Pellmonweb/pellmonweb.py`, `src/Pellmonweb/auth.py`.

**`config/`:**
- Purpose: Runtime configuration consumed by both processes at startup.
- Contains: `pellmon.conf` (active), `pellmon.conf.example` (documented template), `conf.d/` (drop-in fragments merged via `config_dir` setting).
- Key files: `config/pellmon.conf`, `config/pellmon.conf.example`.

**`data/` and `initscript/`:**
- Purpose: Packaging/install-time support files (Autotools `.in` templates for D-Bus policy and init scripts).
- Contains: `pellmon_dbus.conf.in` (D-Bus system bus policy), `pellmonsrv.in`/`pellmonweb.in` (SysV-style init scripts).
- Generated: Rendered by the Autotools build (`configure` substitutes `@variables@`) — not hand-edited directly.

**`Archive/PellMon-master/` and `.snapshots/`:**
- Purpose: Frozen copies of the repository kept for reference/rollback during the Python 2→3 migration.
- Generated: Yes (migration tooling snapshots) — do not treat as live source; never edit files here expecting them to affect the running app.
- Committed: Currently tracked in the working tree per `git status`, but should be treated as read-only reference material, not part of the active codebase.

## Key File Locations

**Entry Points:**
- `src/Pellmonsrv/pellmonsrv.py`: Daemon process entry (`run()` at bottom of file, invoked via `if __name__ == "__main__"` or the `pellmonsrv` console script / init script).
- `src/Pellmonweb/pellmonweb.py`: Web process entry (CherryPy app bootstrap).

**Configuration:**
- `config/pellmon.conf`: Live daemon + web configuration (INI, parsed with `configparser`).
- `config/pellmon.conf.example`: Annotated template covering `[conf]`, `[weblog]`, `[authentication]`, `[enabled_plugins]`, `[pollvalues]`, `[plugin_settings]` sections.
- `config/conf.d/*.conf`: Optional additional config fragments, merged in when `config_dir` is set under `[conf]`.
- `src/Pellmonsrv/directories.py.in`: Autotools template that becomes `directories.py`, supplying `DATADIR`/`CONFDIR`/`LOCALSTATEDIR` at install time.
- `.env` / `.env.example`: Present at repo root (Docker-related environment variables — do not read/commit real `.env` contents).

**Core Logic:**
- `src/Pellmonsrv/database.py`: Shared in-memory data model (`Database`, `Item` classes, `Keyval_storage`).
- `src/Pellmonsrv/plugin_categories.py`: Base plugin interface (`protocols`) all plugins extend.
- `src/Pellmonsrv/plugins/*/__init__.py`: Individual plugin logic.

**Testing:**
- No dedicated top-level test directory or test runner config detected (no `pytest.ini`, `tox.ini`, or `tests/` directory found in `src/`). `src/Pellmonsrv/plugins/testplugin/__init__.py` is a minimal example/reference plugin, not an automated test suite.

## Naming Conventions

**Files:**
- Plugin packages: lowercase, no separators, matching the plugin's `Module` value in its `.pellmon-plugin` descriptor (e.g. `scottecom`, `nbecom`, `openweathermap`).
- Plugin descriptor files: `<plugin-package-name>.pellmon-plugin`, sibling to the plugin's directory under `src/Pellmonsrv/plugins/`.
- Autotools templates: `<name>.in` (rendered at build/install time by `configure`, e.g. `directories.py.in`, `pellmonsrv.in`).
- Python-2 migration backups: `<file>.py2bak` — pre-migration copy kept next to the live `.py` file during the ongoing port; not imported by anything.

**Directories:**
- Top-level source packages follow the `PellmonX` PascalCase convention (`Pellmonsrv`, `Pellmonweb`, `Scotteprotocol`) — this mirrors the Python package/module names exactly (case-sensitive imports).
- Plugin subdirectories are lowercase and match their module name (`plugins/scottecom/`, `plugins/nbecom/`).

## Where to Add New Code

**New hardware protocol / data-source plugin:**
- Create `src/Pellmonsrv/plugins/<newplugin>/__init__.py` subclassing `protocols` from `Pellmonsrv.plugin_categories`, implementing `activate(self, conf, glob, db, *args, **kwargs)` to insert `Item`/`Getsetitem`/`Storeditem` instances via `self.db.insert(...)`.
- Add a matching descriptor `src/Pellmonsrv/plugins/<newplugin>.pellmon-plugin` with `[Core] Name = <DisplayName>` and `Module = <newplugin>`.
- Add a `src/Pellmonsrv/plugins/<newplugin>/Makefile.am` following an existing plugin (e.g. `plugins/calculate/Makefile.am`) for Autotools packaging, and register the plugin directory in `src/Pellmonsrv/plugins/Makefile.am`.
- Enable it by adding `<newplugin> = yes` under `[enabled_plugins]` in `config/pellmon.conf`.

**New low-level wire-protocol library (like Scotteprotocol/nbeprotocol):**
- Create a standalone package (either top-level under `src/` like `Scotteprotocol`, or nested under the owning plugin like `plugins/nbecom/nbeprotocol/`) with no dependency on `Pellmonsrv.plugin_categories` — keep protocol/framing logic separate from the plugin adapter that wires it into the `Database`.

**New web page/endpoint:**
- Add a controller module in `src/Pellmonweb/` (pattern after `consumption.py` or `logview.py`) and a corresponding Mako template in `src/Pellmonweb/html/`; wire it into the CherryPy app tree in `src/Pellmonweb/pellmonweb.py`.

**Utilities shared across plugins:**
- Prefer adding to `src/Pellmonsrv/database.py` (for new `Item` value-storage strategies) or `src/Pellmonsrv/plugin_categories.py` (for new cross-plugin helper methods on `protocols`) rather than introducing new module-level globals inside a single plugin.

## Special Directories

**`src/Pellmonweb/media/`:**
- Purpose: Third-party/static frontend assets (Bootstrap 3 under `bs3/`, CodeMirror under `codemirror/`, Flot charting under `flot/`, plus project CSS under `css/`).
- Generated: No (vendored third-party libraries, checked in directly).
- Committed: Yes.

**`__pycache__/` directories (throughout `src/`):**
- Purpose: Python bytecode cache generated when running under Python 3.13/3.14 locally.
- Generated: Yes, automatically by the interpreter.
- Committed: Should not be committed (verify `.gitignore` coverage — present under most `src/**` subpackages as a build artifact of local test runs).

**`Archive/PellMon-master/` and `.snapshots/`:**
- Purpose: Historical/reference snapshots from the migration process (see Directory Purposes above).
- Generated: Yes.
- Committed: Currently present in the working tree; treat as non-authoritative reference, not a place to add new code.

---

*Structure analysis: 2026-09-17*
