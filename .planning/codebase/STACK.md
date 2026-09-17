# Technology Stack

**Analysis Date:** 2026-09-17

## Languages

**Primary:**
- Python 3 (target: 3.13/3.14) — all application code under `src/Pellmonsrv/`, `src/Pellmonweb/`, `src/Scotteprotocol/`
  - Codebase is mid-migration from Python 2 to Python 3 (branch `python3-migration`). Every converted file has a `.py2bak` sibling (e.g. `src/Pellmonsrv/database.py.py2bak`) preserving the pre-migration source for reference/rollback.
  - Migration tooling: `convert-to-py3.py`, `install-2to3.sh`, `INSTALL-2TO3.md`, `MIGRATION.md`, `MIGRATION-SUMMARY.md`, `modernize-analysis.txt`, `modernize-summary.txt` (output of the `python-modernize` tool) document the conversion process and remaining gaps.
  - Root markers of in-progress work: `PHASE2-COMPLETE.md`, `PHASE3-COMPLETE.md`, `PHASE3-PROGRESS.md`, `PHASE4-TESTING.md`.

**Secondary:**
- Shell (bash) — `setup-wsl.sh`, `install-2to3.sh`, `autogen.sh`, `reinstall.sh`, `src/debugsrv.sh`, `src/debugweb.sh`
- Mako templates (HTML) — `src/Pellmonweb/html/` (server-rendered web UI)
- Autotools (`configure.ac`, `Makefile.am` throughout `src/`) — legacy GNU build system, still present but largely superseded by direct `pip`/venv installs for the Python 3 port

## Runtime

**Environment:**
- Python 3.14.0 (Windows dev venv, `venv-py3/pyvenv.cfg` — `C:\Python314`)
- Python 3.13 (WSL/Linux dev venv, `venv-wsl/pyvenv.cfg`)
- Production container target: Debian 12 "bookworm-slim" with Debian's system `python3` (see `Dockerfile`) — chosen specifically for `python3-dbus`/`python3-gi` compatibility, which are not reliably installable via pip.

**Package Manager:**
- `pip` (pip3), installed inside a `venv` per environment (`venv-py3/`, `venv-wsl/`)
- No lockfile present (no `requirements.lock`, `Pipfile.lock`, or `poetry.lock`) — `requirements.txt` uses `>=` version floors only, so builds are not pinned/reproducible.
- Two parallel requirements files: `requirements.txt` (cross-platform/Docker) and `requirements-wsl.txt` (WSL-specific additions).

## Frameworks

**Core:**
- CherryPy `>=18.8.0` — web server/framework for `src/Pellmonweb/pellmonweb.py` (HTTP request handling, sessions, static file serving via `cherrypy.lib.static`)
- Mako `>=1.2.0` — HTML templating engine, templates in `src/Pellmonweb/html/`, rendered via `mako.template.Template` / `mako.lookup.TemplateLookup`
- Yapsy (vendored, not a pip dependency) — plugin discovery/loading framework at `src/Pellmonsrv/yapsy/`, drives the `Pellmonsrv/plugins/*` plugin architecture (see `plugin_categories.py`)
- D-Bus / GLib (`dbus`, `dbus.service`, `gi.repository.GLib`/`GObject`) — inter-process communication between `pellmonsrv` (backend daemon) and `pellmonweb` (web frontend); requires system packages `python3-dbus`, `python3-gi` (not pip-installable, hence Debian system Python in Docker)

**Testing:**
- No formal test framework/runner detected (no `pytest`, `unittest` suite, or `tests/` directory found in `src/`).
- `test-imports.py` (repo root) is an ad-hoc smoke-test script that imports core modules (`Pellmonsrv.pellmonsrv`, `Pellmonweb.pellmonweb`, `Pellmonsrv.database`, `Pellmonweb.pellmonconf`) and reports success/failure — used to validate the Python 3 port, not a real test suite.

**Build/Dev:**
- GNU Autotools (`autogen.sh`, `configure.ac`, `Makefile.am`) — legacy `.in` template substitution for install paths (e.g. `src/Pellmonsrv/directories.py.in` → `directories.py` with `@datadir@`, `@confdir@`, `@localstatedir@` substituted at build/install time)
- `setup-wsl.sh` — WSL-specific dev environment bootstrap script
- Docker/`docker-compose.yml` — containerized deployment build+run

## Key Dependencies

**Critical:**
- `pyserial>=3.5` — serial port communication with pellet burner hardware (used by `src/Pellmonsrv/plugins/scottecom/scottecom.py` via `Scotteprotocol`)
- `CherryPy>=18.8.0` — web server for `Pellmonweb`
- `Mako>=1.2.0` — HTML template rendering
- `simplejson>=3.19.0` — JSON serialization for web API responses (`src/Pellmonweb/pellmonweb.py`)
- `python-dateutil>=2.8.2` — date/time parsing
- `dbus-python` + `PyGObject` (`gi`) — commented out of `requirements.txt` (Linux system packages only, `apt-get install python3-dbus python3-gi`); required at runtime by both `pellmonsrv.py` and `pellmonweb.py` for IPC
- `rrdtool` (commented out of `requirements.txt`, installed via `apt-get install python3-rrdtool` / Docker) — round-robin database used for time-series storage of burner metrics; configured via `src/conf.d/database.conf.in`

**Infrastructure:**
- `argcomplete>=2.0.0` — CLI shell-completion for `pellmoncli`
- `ws4py>=0.5.1` (optional) — WebSocket support in `pellmonweb.py`; import is wrapped in try/except, falls back to `websockets = False` with a log message if missing
- `pyownet>=0.10.0` — OWFS (1-wire) client, used by `src/Pellmonsrv/plugins/owfs/__init__.py` (dynamically imported, optional)
- `pycryptodome>=3.15.0` (`Crypto.PublicKey.RSA`) + `xtea>=0.7.1` — cryptography for the NBE burner network protocol (`src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`); replaces the deprecated `python-crypto` package used pre-migration
- `pyowm>=3.3.0` — OpenWeatherMap client SDK, used by `src/Pellmonsrv/plugins/openweathermap/__init__.py`
- `RPi.GPIO` (not in requirements.txt; Raspberry Pi only) — used by `src/Pellmonsrv/plugins/raspberrygpio/__init__.py`, hard-imported (will fail off-Pi hardware)

## Configuration

**Environment:**
- `.env` / `.env.example` (repo root) — Docker Compose variables only: `TZ`, `PELLMON_WEB_PORT` (default 8081), `PELLMON_WS_PORT` (default 8082). Note: `.env` exists in the repo tree (contents not read/quoted per policy); only non-secret deployment knobs are expected here based on `.env.example`.
- Application configuration is INI-style, not environment-variable driven: main file `config/pellmon.conf` (Docker-mounted; template at `config/pellmon.conf.example`), plus a `conf.d/` directory of per-topic `.conf` files (`src/conf.d/database.conf.in`, `src/conf.d/email.conf`, `src/conf.d/enabled_plugins.conf`, `src/conf.d/webinterface.conf.in`, `src/conf.d/plugins/`). Parsed with Python's `configparser`.
- `directories.py.in` / `version.py.in` — Autotools `.in` templates for install-path and version constants, substituted at build time (`@datadir@`, `@confdir@`, `@localstatedir@`, `@VERSION@`).

**Build:**
- `configure.ac`, `Makefile.am` (root, `src/`, `data/`, `initscript/`, and per-package dirs) — Autotools build configuration
- `Dockerfile` — multi-stage-free, single-stage Debian bookworm-slim image; installs system Python + rrdtool + dbus/gi + build tools, then `pip3 install --break-system-packages -r requirements.txt`
- `docker-compose.yml` — defines two services (`pellmonsrv`, `pellmonweb`) sharing a private D-Bus session bus over a Unix socket volume (`pellmon-run`), plus `pellmon-data` (RRD persistence) and `pellmon-logs` volumes

## Platform Requirements

**Development:**
- Windows: Python 3.14 venv (`venv-py3/`) — used for Python 3 syntax porting/import checks; D-Bus/GLib/RPi.GPIO/rrdtool features are not usable on Windows.
- WSL/Linux: Python 3.13 venv (`venv-wsl/`) — full-feature dev environment, documented in `WSL-SETUP.md` and `WSL-VERIFICATION.md`.

**Production:**
- Linux only (Debian bookworm-slim container or bare-metal Linux/Raspberry Pi), required for: D-Bus/GLib IPC, `rrdtool`, serial device access (`/dev/ttyUSB0`), and (for the `raspberrygpio` plugin) Raspberry Pi GPIO hardware.
- Deployment via Docker Compose (`docker-compose.yml`, `DOCKER.md`) — `pellmonsrv` runs `privileged: true` for D-Bus and serial device access; `pellmonweb` exposes ports 8081 (HTTP) and 8082 (WebSocket).
- Legacy non-Docker deployment path still present: `initscript/pellmonsrv.in`, `initscript/pellmonweb.in` (SysV-style init scripts installed via Autotools).

---

*Stack analysis: 2026-09-17*
