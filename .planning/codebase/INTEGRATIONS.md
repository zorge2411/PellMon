# External Integrations

**Analysis Date:** 2026-09-17

## APIs & External Services

**Weather:**
- OpenWeatherMap — used for outdoor temperature/weather data feeding heating-circuit logic
  - SDK/Client: `pyowm` (`pyowm.OWM(...)`)
  - Implementation: `src/Pellmonsrv/plugins/openweathermap/__init__.py`
  - Auth: API key read from plugin config `self.conf['apikey']` (in `[openweathermap]` section of a `conf.d/*.conf` file, not an env var); import/init wrapped in try/except so the plugin is optional if `pyowm` is missing or the key is invalid.

**1-Wire Sensors (OWFS):**
- OWFS owserver — temperature/sensor bus for silo level, chute temp, etc.
  - SDK/Client: `pyownet.protocol` (dynamically imported via `__import__('pyownet.protocol')`)
  - Implementation: `src/Pellmonsrv/plugins/owfs/__init__.py`
  - Connection: owserver host/port configured via plugin's `ConfigParser`-based settings (`config_dir`/plugin conf files); optional — plugin activation fails gracefully if `pyownet` is absent.

**Pellet Burner Hardware Protocols (local network/serial, not cloud APIs):**
- Scotte pellet burner — serial (RS-232/USB) protocol
  - Implementation: `src/Pellmonsrv/plugins/scottecom/scottecom.py` (plugin), `src/Scotteprotocol/protocol.py` (protocol codec)
  - Transport: `pyserial`, configured via `serialport` / `chipversion` in `[ScotteCom]` plugin config (example: `/dev/ttyUSB0` in `config/pellmon.conf.example`)
  - Docs: `scotte_protocol_spec.md`
- NBE pellet burner — UDP/TCP network protocol over LAN (proprietary NBE discovery/control protocol)
  - Implementation: `src/Pellmonsrv/plugins/nbecom/__init__.py`, protocol layer in `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`
  - Transport: raw `socket` (`AF_INET`, `SOCK_DGRAM` for discovery on port 1920 by default; `Proxy` class handles connection), encrypted with RSA (`pycryptodome`, `Crypto.PublicKey.RSA`) and XTEA (`xtea` package)
  - Auth: burner network password passed to `Proxy(password, port=1920, addr=None, serial=None)`

**Raspberry Pi GPIO (hardware, not network):**
- Local GPIO pins for relay/sensor control
  - SDK/Client: `RPi.GPIO`
  - Implementation: `src/Pellmonsrv/plugins/raspberrygpio/__init__.py`
  - Hard import (no try/except) — plugin will fail to load on non-Raspberry-Pi hardware.

## Data Storage

**Databases:**
- RRDtool (round-robin database) — primary time-series store for burner metrics (power, temperatures, feeder time, oxygen levels, etc.)
  - Config: `src/conf.d/database.conf.in` defines `[pollvalues]` (data source mapping), `[conf]` (database file path, poll interval, optional `persistent_db` for ramdisk setups), `[rrd_ds_names]`, `[rrd_ds_types]`
  - Client: `rrdtool` Python bindings (system package `python3-rrdtool`, installed via Dockerfile `apt-get`; commented out in `requirements.txt` since it's not pip-installable cross-platform)
  - File location: `/var/lib/pellmon/pellmon.rrd` (Docker) or `@localstatedir@/lib/pellmon/rrd.db` (Autotools install)
- SQLite — used internally by `src/Pellmonsrv/database.py` (`sqlite3` module) for the in-memory/keyval item storage abstraction (`Keyval_storage`, `Item`/`Getsetitem`/`Cacheditem` classes); this is an in-process runtime cache/registry, not a persistent app database.

**File Storage:**
- Local filesystem only. No object storage (S3, etc.) detected.
- Config files: `/etc/pellmon/pellmon.conf`, `/etc/pellmon/conf.d/` (mounted read-only in Docker)
- Logs: `/var/log/pellmon/pellmon.log`, `access.log`, `error.log` (configured in `[weblog]` section of `pellmon.conf`)

**Caching:**
- In-process only: `Cacheditem` class in `src/Pellmonsrv/database.py` implements a time-based cache (`cachetime`, default 5s) around getter/setter pairs for live hardware values. No external cache service (Redis, Memcached) detected.

## Authentication & Identity

**Auth Provider:**
- Custom, CherryPy session-based form authentication (no third-party identity provider / OAuth).
  - Implementation: `src/Pellmonweb/auth.py` — `check_auth()` CherryPy tool checks `cherrypy.request.config['auth.require']`; on missing session, redirects to `/auth/login`.
  - Credentials stored in plaintext in `[authentication]` section of `pellmon.conf` (`username`, `password`, `realm` — see `config/pellmon.conf.example`); commented out by default (auth disabled unless configured).
  - Session key: `_cp_username` (CherryPy session storage, in-memory by default per CherryPy config).

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Rollbar, or similar service detected).

**Logs:**
- Python stdlib `logging` module throughout (`logging.getLogger('pellMon')`), with `logging.handlers` for rotation.
- Custom D-Bus log handler: `dbus_signal_handler` class in `src/Pellmonsrv/pellmonsrv.py` emits log records as D-Bus signals, allowing `pellmonweb` (and other D-Bus clients) to subscribe to live log output over IPC rather than polling files.
- Log viewer UI: `src/Pellmonweb/logview.py` reads/tails the configured `logfile` for display in the web interface.

## CI/CD & Deployment

**Hosting:**
- Self-hosted / on-premises (runs on a Linux host or Raspberry Pi alongside the physical pellet burner). No cloud hosting platform (Heroku, Vercel, AWS ECS, etc.) detected.
- Container deployment via Docker Compose (`docker-compose.yml`, image `pellmon:latest` built from root `Dockerfile`); documented in `DOCKER.md`.
- Legacy non-container deployment via Autotools `make install` + SysV init scripts (`initscript/pellmonsrv.in`, `initscript/pellmonweb.in`).

**CI Pipeline:**
- None detected — no `.github/workflows/`, `.gitlab-ci.yml`, or other CI config found in the repository.

## Environment Configuration

**Required env vars (Docker Compose only — `.env` / `.env.example`):**
- `TZ` — container timezone (default `Europe/Stockholm`)
- `PELLMON_WEB_PORT` — HTTP port mapping (default `8081`)
- `PELLMON_WS_PORT` — WebSocket port mapping (default `8082`)
- `DBUS_SESSION_BUS_ADDRESS` — set directly in `docker-compose.yml` (not `.env`) to `unix:path=/var/run/pellmon/bus_socket`, shared between the `pellmonsrv` and `pellmonweb` containers via the `pellmon-run` volume.

**Application-level config (not env vars):** all burner/plugin/database/auth/email settings live in `config/pellmon.conf` + `config/conf.d/*.conf` (INI format via `configparser`), not environment variables. See `config/pellmon.conf.example` for the full schema (`[conf]`, `[weblog]`, `[authentication]`, `[enabled_plugins]`, `[pollvalues]`, `[plugin_settings]`).

**Secrets location:**
- No secrets manager / vault integration. Secrets (burner network password for NBEcom, OpenWeatherMap API key, email SMTP credentials, web auth password) are stored in plaintext inside INI config files under `config/conf.d/` and `src/conf.d/` (e.g. `src/conf.d/email.conf` has commented-out `username`/`password` fields for SMTP). These files are mounted read-only into containers and are `.gitignore`-excluded where user-specific (verify before committing real deployments' `config/pellmon.conf`).

## Webhooks & Callbacks

**Incoming:**
- None (no webhook receiver endpoints detected in `Pellmonweb`).

**Outgoing:**
- Email notifications (SMTP, not a webhook) — `src/conf.d/email.conf` configures `[email]` with `server:port` (e.g. `smtp.gmail.com:587`), `username`/`password`, `from`/`to`, `conditions` (send on `alarm`/`mode`/`parameter` change), optional embedded RRD graph image attachment (`graphsize`, `graphtimespan`, `graphlines`). Sent via Python stdlib `smtplib` (`SMTP`, `SMTP_SSL`) and `email.mime.*` from `src/Pellmonsrv/pellmonsrv.py`.
- Shell command execution plugin (`src/Pellmonsrv/plugins/exec/__init__.py`, uses `subprocess`) — allows running arbitrary local shell commands on data-driven conditions (e.g. alarm), effectively a local "outgoing webhook" substitute rather than an HTTP callback.

---

*Integration audit: 2026-09-17*
