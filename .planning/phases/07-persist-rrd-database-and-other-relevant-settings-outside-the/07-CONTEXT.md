# Phase 7: Persist RRD database and other relevant settings outside the Docker container - Context

**Gathered:** 2026-09-21
**Status:** Ready for planning

<domain>
## Phase Boundary

The data PellMon writes (the RRD database, the settings database, the logs) lives in a folder on the
host that the user controls: it survives container recreation, `docker compose down -v` and Docker
reinstalls, and is easy to see and back up. The Docker deployment gets a clean way to keep that folder
correctly owned, config editing from the web GUI works where it safely can, and there is a documented
and scripted backup/restore.

In scope: compose volume/bind-mount changes, an ownership init step, a clear failure when the data
folder is unusable, config mount permissions for the web config editor, the rule for where GUI
settings are stored, a backup/restore script, documentation, tests.

Out of scope (other phases): a backup/download button in the web GUI, automatic migration of old
volumes, RRD retention/size tuning, log rotation policy, Windows/WSL-specific data layouts, moving
the settings storage away from SQLite.

</domain>

<decisions>
## Implementation Decisions

### Where the data lives on the host
- **D-01:** Persistent data lives in a host folder next to the compose file, default `./pellmon-data`,
  overridable with `PELLMON_DATA_DIR` in `.env` (documented in `.env.example`, e.g. to point at an SSD).
  It must NOT be `./data`: the repository already has a `data/` folder (build files such as the D-Bus
  policy template) that the Dockerfile copies into the image (`COPY data/ ./data/`).
- **D-02:** The host folder is bind-mounted over `/var/lib/pellmon` (RRD database and the settings
  SQLite file, `pellmon_settings.db`, which the daemon places next to the RRD database) and a log
  folder over `/var/log/pellmon`, replacing the named volumes `pellmon-data` and `pellmon-logs`.
  Suggested layout under the host folder: `data/` (rrd.db, pellmon_settings.db) and `logs/`, exact
  names left to planning.
- **D-03:** The D-Bus socket volume (`pellmon-run`, `/var/run/pellmon`) stays a temporary named volume;
  it is not data.
- **D-04:** The web container keeps its data mount read-only: `pellmonweb` only computes (and never
  writes) file paths next to the database (`graph.png`, `consumption.png` are assigned but unused),
  and it does not open the settings database.
- **D-05:** `pellmon-data` is added to `.gitignore` (real data, possibly containing MQTT secrets from
  Phase 6); `.env.example` documents `PELLMON_DATA_DIR`.

### Ownership and first start
- **D-06:** Ownership is fixed automatically by a one-shot init step in `docker-compose.yml`: a small
  init service runs before `pellmonsrv`, creates the data and log folders if needed, sets ownership to
  the `pellmon` user (uid/gid 999, as created in the Dockerfile) and exits;
  `pellmonsrv` depends on it completing successfully. It must work on first start, after a restore,
  and when the folder was created by Docker as root.
- **D-07:** If the data folder is missing or not writable at daemon startup, the daemon fails loudly
  and clearly: a log/stderr message naming the folder and the fix, and the container ends up unhealthy
  or exits. It must NOT silently fall back to a temporary folder (today `pellmonsrv` falls back to
  `/tmp` paths when settings are missing, e.g. `/tmp/pellmon_rrd_database.db` and
  `/tmp/pellmon_settings.db`, which loses data on restart); check the existing fallbacks in
  `config.__init__` and make the Docker case fail instead. Behaviour for non-Docker/dev runs may keep
  a warning-level fallback if planning finds that necessary; state it explicitly.

### Config: what the web GUI may change
- **D-08:** Only `config/conf.d` is mounted writable for the web config editor. `config/pellmon.conf`
  (which holds the password hashes) stays read-only to the containers. The web config editor must
  handle a read-only file gracefully: a clear "this file is read-only" message instead of a generic
  error. The existing allowlist and same-origin check in `pellmonconf.py` (`_resolve`, `save`) stay.
  Decide in planning whether `pellmonsrv` also needs write access to `conf.d` (it should not).
- **D-09 (storage rule for the whole project, applies to Phases 6 and 8):** Settings changed in the
  web GUI are stored in the settings database (`pellmon_settings.db` via `Keyval_storage`,
  `load_setting`/`store_setting`), in the data folder. Config files keep only install-time settings
  (serial port, plugin list, password hashes, ports). The GUI does not rewrite config files except the
  existing raw config editor for `conf.d`.

### Backup, restore and old data
- **D-10:** Deliver a backup/restore script plus documentation (in the deploy guide). The backup
  includes: the RRD database saved as a portable `rrdtool dump` (RRD files are not portable between
  machine types, so a raw file copy cannot be assumed valid across them), a consistent copy of the
  settings database (use SQLite's own backup mechanism, not a raw copy of a live file), and the
  config folder. Restore rebuilds the RRD from the dump (`rrdtool restore`) and puts the files in
  place, including onto a different machine type (for example PC to Pi).
- **D-11:** Migrating data from the old Docker named volume is a documented one-time manual copy
  (a short guide step). No automatic migration. Existing data is test data, so this is best effort.
- **D-12:** No backup button in the web GUI in this phase (deferred).

### Claude's Discretion
- The init container image and command (a small existing image, or reuse the project image with a
  root override; prefer no new external image if the project image works), exact compose syntax
  (`depends_on` with `service_completed_successfully`), and healthcheck interaction.
- The backup script's language and location (`tools/` shell script vs Python), option names, output
  format (tar.gz), and how it obtains a consistent view while the daemon is running.
- Exact folder layout under `PELLMON_DATA_DIR` and permission bits.
- How the settings database's location is configured (`settings_db` in `[conf]` exists) versus its
  default next to the RRD database.
- Tests: how to test compose changes (extend `tests/test_ci_docker_config.py` style checks), the
  backup script (on temp dirs with a real `rrdtool` where available, skip otherwise), and the startup
  failure path.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project and prior decisions
- `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md` - constraints (Linux-only production, Debian bookworm-slim container, Raspberry Pi 3A+ with 512 MB RAM and one USB port).
- `.planning/phases/05-security-ci-deployment-hardening/05-CONTEXT.md` - Docker healthchecks, graceful SIGTERM (`copy_db('store')`), CI decisions.
- `.planning/phases/06-enable-home-assistant-mqtt-device-with-settings-on-the-web-g/06-CONTEXT.md` - D-12: the MQTT password is stored in the settings database in the data folder, so this phase's storage location and protection matter to it.
- `tests/test_ci_docker_config.py` - the regression tests that pin the compose fixes made while deploying to a real Pi (health check form, `dbus-daemon` flags, `SERIAL_GID` group, font cache, start period); new compose changes must keep them passing.

### Runtime storage
- `docker-compose.yml`, `Dockerfile`, `.env.example` - current named volumes (`pellmon-data`, `pellmon-logs`, `pellmon-run`), read-only config bind mounts, `COPY data/ ./data/`, directories created and chowned to `pellmon`, `VOLUME` declarations, non-root user.
- `src/conf.d/database.conf.in` (`database`, `db_store_interval`, optional `persistent_db`), `config/pellmon.conf.example` (`[conf] database`), `src/Pellmonsrv/pellmonsrv.py` (`config.__init__` database/settings paths and fallbacks, `copy_db`, `mkdir_p`), `src/Pellmonsrv/database.py` (`Keyval_storage`).
- `src/Pellmonweb/pellmonconf.py` - config editor, `self.dirs` allowlist, `_resolve`, `save`, same-origin check.
- `DEPLOY-PI.md`, `HARDWARE-BRINGUP.md` - guides to update (volumes, backup, ownership, troubleshooting).

No external specs. Docker Compose documentation on `depends_on` `service_completed_successfully` and bind-mount behaviour should be consulted by research.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Keyval_storage` (`database.py`): SQLite settings store with `load_setting`/`store_setting` (used by plugins); Phase 6/8 GUI settings go here.
- `copy_db('store'/'restore')` and `db_store_interval`: an existing mechanism for RRD persistence when `persistent_db` differs from `database` (not needed when both point at the same file, as in Docker).
- `tests/test_ci_docker_config.py`: text checks on `docker-compose.yml`, `.env.example`, the CI workflow, and the Dockerfile; extend for the new volumes and init step.
- `tools/` folder (`burner_sim.py`) exists for helper scripts.

### Established Patterns
- Settings from `.env` with defaults in compose (`${VAR:-default}`), documented in `.env.example`.
- Non-root `pellmon` user (uid 999) in the image; `group_add: ${SERIAL_GID}` for serial access.
- Broad `sed` edits on `docker-compose.yml` have broken it before; changes are made and tested carefully (see the compose regression tests).
- New files carry the GPL header; `%`-formatting and the shared `pellMon` logger in Python code.

### Integration Points
- `docker-compose.yml` (volumes, init service, `depends_on`), `.env.example`, `.gitignore`, `Dockerfile` (directory creation may become redundant), `pellmonsrv.py` startup checks, `pellmonconf.py` read-only handling, new `tools/` backup script, docs.

</code_context>

<specifics>
## Specific Ideas

- Host folder `pellmon-data` next to the compose file by default, easy to copy over SFTP and back up.
- Backups must work between different machine types (PC to Pi), which is why the RRD is dumped to XML.

</specifics>

<deferred>
## Deferred Ideas

- Backup/download button in the web GUI.
- Automatic detection and migration of data from the old named volume.
- Log rotation and RRD retention/size limits.
- Windows/WSL-specific data layout guidance.
- Moving the config editor to a GUI form for known settings (partly Phases 6 and 8).

</deferred>

---

*Phase: 7-Persist RRD database and other relevant settings outside the Docker container*
*Context gathered: 2026-09-21*
