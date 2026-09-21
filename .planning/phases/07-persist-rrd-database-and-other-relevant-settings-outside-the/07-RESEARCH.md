# Phase 7: Persist RRD database and other settings outside the container - Research

**Researched:** 2026-09-21
**Domain:** Docker Compose bind mounts and init ordering, PellMon startup path checks, RRD/SQLite backup
**Confidence:** MEDIUM-HIGH. Code findings are read directly from the repo. Docker/rrdtool behaviour is from training knowledge and NOT re-verified this session unless marked otherwise; those items are in the Assumptions Log and must be smoke-tested.

<user_constraints>
## User Constraints (from 07-CONTEXT.md)

### Locked Decisions
- D-01: Host folder next to compose file, default `./pellmon-data`, override `PELLMON_DATA_DIR` in `.env` (documented in `.env.example`). NOT `./data` (repo has `data/`, Dockerfile does `COPY data/ ./data/`).
- D-02: Host folder bind-mounted over `/var/lib/pellmon` (RRD + `pellmon_settings.db`) and a log folder over `/var/log/pellmon`, replacing named volumes `pellmon-data`, `pellmon-logs`. Suggested layout `data/` and `logs/`; exact names left to planning.
- D-03: `pellmon-run` (`/var/run/pellmon`) stays a temporary named volume.
- D-04: Web container keeps data mount read-only (`pellmonweb` never writes next to the DB, does not open settings DB).
- D-05: `pellmon-data` added to `.gitignore`; `.env.example` documents `PELLMON_DATA_DIR`.
- D-06: One-shot init service in `docker-compose.yml` runs before `pellmonsrv`, creates data/log folders, chowns to uid/gid 999, exits; `pellmonsrv` depends on successful completion. Must work on first start, after restore, and when Docker created the folder as root.
- D-07: If data folder missing/unwritable at daemon startup, fail loudly (message naming folder and fix; container unhealthy or exits). No silent fallback to `/tmp` in Docker. Non-Docker/dev may keep a warning-level fallback if stated explicitly.
- D-08: Only `config/conf.d` mounted writable for the web config editor; `config/pellmon.conf` stays read-only. Editor must show a clear "read-only" message. Keep allowlist and same-origin check in `pellmonconf.py`. Planning decides whether `pellmonsrv` needs write to `conf.d` (should not).
- D-09: Storage rule: GUI-changed settings go to settings DB (`Keyval_storage`, `load_setting`/`store_setting`) in the data folder; config files keep install-time settings only.
- D-10: Backup/restore script + docs. Backup = portable `rrdtool dump` of RRD, consistent settings DB copy via SQLite backup mechanism, config folder. Restore rebuilds RRD via `rrdtool restore`, works PC to Pi.
- D-11: Old named-volume migration is a documented manual copy; no automation.
- D-12: No backup button in web GUI.

### Claude's Discretion
Init image/command, compose syntax, healthcheck interaction; backup script language/location/options/format (tar.gz) and how it gets a consistent view while daemon runs; folder layout and permission bits; how settings DB location is configured (`settings_db` vs default next to RRD); test approach.

### Deferred Ideas (OUT OF SCOPE)
Web backup button; automatic old-volume migration; log rotation / RRD retention; Windows/WSL data layout guidance; GUI form for known settings.
</user_constraints>

## Summary

The change is mostly compose plumbing plus three small code changes. Compose: replace two named volumes with bind mounts under `${PELLMON_DATA_DIR:-./pellmon-data}`, add a `pellmon-init` service reusing `pellmon:latest` as root, and gate `pellmonsrv` on `service_completed_successfully`. Code: add an explicit startup check in `run()` (after config parse, before daemonisation/`Database()`), close two silent-fallback holes in `config.__init__`, add friendly read-only handling in `pellmonconf.save`. Backup: run rrdtool and Python's `sqlite3` backup API inside the running container (`docker compose exec`), which needs no host rrdtool/sqlite3 and guarantees matching rrdtool version.

Important findings the planner must handle (details below): (1) the RRD path is defined twice with different values: `config/pellmon.conf` has `database = /var/lib/pellmon/pellmon.rrd` but `config/conf.d/database.conf` (read afterwards, overrides) has `/var/lib/pellmon/rrd.db`; effective path is `rrd.db`. The backup script must not hard-code either; read it from the effective config or accept an option. (2) `config/conf.d/` is untracked in git status and partly gitignored (`config/conf.d/.gitignore` ignores `database.conf`, `webinterface.conf`), so files there are host-created copies. (3) `config.__init__` has silent fallbacks that survive a Docker misconfiguration (list in section "Current code behaviour"). (4) The `pellmon-init` service without its own `build:` can hit a pull race on a fresh machine.

**Primary recommendation:** `pellmon-init` = same `image: pellmon:latest` + same `build:` block, `user: root`, `restart: "no"`, mounts `${PELLMON_DATA_DIR:-./pellmon-data}/data` and `/logs` plus `./config/conf.d`, command does `mkdir -p`, `chown -R 999:999`, `chmod`. Add an explicit writability check in `run()` that calls `sys.exit(1)` with a message.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary | Rationale |
|---|---|---|---|
| Host folder ownership/creation | Compose init service (root) | Docs | Only root in a container can chown a bind mount on Linux hosts |
| Fail-loud data-dir check | `pellmonsrv.run()` (daemon) | Compose healthcheck/restart | Daemon knows the effective paths from config |
| Read-only config message | `pellmonconf.save` (web) | JS in source page | Error is produced at the file write |
| Consistent RRD/SQLite backup | Script executing inside pellmonsrv container | Host tar of config | rrdtool/py sqlite3 versions match the writer |
| Settings storage rule | `Keyval_storage` (data folder) | — | D-09, already implemented |

## Standard Stack

No new packages. Everything used is already in the image or stdlib: `rrdtool` CLI (Debian package `rrdtool`, 1.7.2 on bookworm [ASSUMED]), `python3` stdlib `sqlite3` (`Connection.backup`, available since 3.7 [CITED: docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup]), `tarfile`/`tar`, `sh`, coreutils `chown`/`mkdir`/`chmod` (present in debian:bookworm-slim base [ASSUMED, coreutils is Essential]). The `sqlite3` CLI is NOT installed by the Dockerfile (apt list read: python3, rrdtool, dbus, curl, procps, udev, gcc...), so use Python's backup API. Host dev machine has an Android-SDK `sqlite3.exe` and no `rrdtool`.

### Package Legitimacy Audit
No external packages are added by this phase. Packages removed: none. Packages flagged: none.

Environment (probed): Docker 29.1.3, Compose v2.40.3-desktop.1 available on dev PC; host `rrdtool` absent (tests needing it must skip); Windows dev.

## Architecture Patterns

### Data flow
```
.env (PELLMON_DATA_DIR) -> compose interpolation -> host ./pellmon-data/{data,logs}
   pellmon-init (root): mkdir -p, chown 999:999, chmod  -> exits 0
       | depends_on: service_completed_successfully
   pellmonsrv (uid 999): run() checks dirs writable -> exit 1 w/ message if not
       -> creates rrd.db if absent -> Keyval_storage(pellmon_settings.db) -> logs
       | depends_on: service_healthy (existing)
   pellmonweb (uid 999): data :ro, logs rw, conf.d rw (config editor)
backup tool -> docker compose exec pellmonsrv: rrdtool dump | python sqlite3.backup | tar config
```

### Compose recommendation (syntax to adapt; keep edits surgical, existing regression tests pin other parts)
```yaml
  pellmon-init:
    build: { context: ., dockerfile: Dockerfile }   # same tag => avoids pull race, see A1
    image: pellmon:latest
    container_name: pellmon-init
    user: root
    restart: "no"
    command: >
      sh -c "mkdir -p /var/lib/pellmon /var/log/pellmon &&
             chown -R 999:999 /var/lib/pellmon /var/log/pellmon /etc/pellmon/conf.d &&
             chmod 755 /var/lib/pellmon /var/log/pellmon"
    volumes:
      - ${PELLMON_DATA_DIR:-./pellmon-data}/data:/var/lib/pellmon
      - ${PELLMON_DATA_DIR:-./pellmon-data}/logs:/var/log/pellmon
      - ./config/conf.d:/etc/pellmon/conf.d
    networks: [pellmon-network]      # optional; can omit
  pellmonsrv:
    depends_on:
      pellmon-init:
        condition: service_completed_successfully
    volumes:
      - ${PELLMON_DATA_DIR:-./pellmon-data}/data:/var/lib/pellmon
      - ${PELLMON_DATA_DIR:-./pellmon-data}/logs:/var/log/pellmon
      - ./config/conf.d:/etc/pellmon/conf.d:ro   # srv does not need write (D-08 discretion)
  pellmonweb:
    volumes:
      - ${PELLMON_DATA_DIR:-./pellmon-data}/data:/var/lib/pellmon:ro
      - ${PELLMON_DATA_DIR:-./pellmon-data}/logs:/var/log/pellmon
      - ./config/conf.d:/etc/pellmon/conf.d      # writable
```
Remove `pellmon-data` and `pellmon-logs` from the top-level `volumes:`; keep `pellmon-run`. Notes:
- `depends_on.condition: service_completed_successfully` is supported by Compose v2 (Compose Specification) [CITED: docs.docker.com/reference/compose-file/services/#depends_on]. Legacy docker-compose v1 (1.x) does not support it in file format 3; users on get.docker.com get the v2 plugin, but `DEPLOY-PI.md` and the header comment still say `docker-compose`; make sure docs say `docker compose`. The existing file already uses `service_healthy`, so v2 is already required. `up -d` returns non-zero if the init container fails, which is a loud failure by itself.
- `restart: "no"` (quoted, YAML would otherwise parse bare `no` as boolean false) [CITED: compose spec].
- Interpolation `${VAR:-default}` works in short-syntax volume strings [CITED: compose spec interpolation]. Relative paths (`./...`) are resolved against the project directory (dir of the compose file) and are what makes it a bind mount rather than a named volume; an absolute `PELLMON_DATA_DIR` also works. A value without `/` or `.` prefix would be read as a named volume, so `.env.example` must say "use `./name` or an absolute path".
- Missing bind source dir with short syntax: the daemon auto-creates it as root:root (Linux host). With long syntax `type: bind` and `create_host_path: false` compose errors instead. Keep short syntax + init chown; init makes the container-side path (host dir is created by Docker, then chowned through the mount).
- Nested/overlapping mounts: current file mount `/etc/pellmon/pellmon.conf:ro` and dir mount `/etc/pellmon/conf.d` are siblings, not nested, so no overlap. Do NOT switch to mounting all of `./config` (then a `:ro` file inside a rw dir would be needed; nested mounts do work in Docker, ordered by path depth, but it is unneeded risk). The `privileged: true` flag does not defeat `:ro` bind mounts (ro is a mount flag), but the container could remount; irrelevant for threat model.
- Init and healthchecks: the init service has no healthcheck; the image's Dockerfile `HEALTHCHECK` (curl :8081) would apply to the init container but it exits immediately so it is harmless. `pellmonweb` needs no change: it already waits on `pellmonsrv` healthy, which transitively waits on init. If init fails, `pellmonsrv` is never created.
- The Dockerfile `VOLUME [...]` lines and the mkdir/chown for `/var/lib/pellmon` become redundant but harmless; bind mounts override. Leave them (minimal change).

### Layout and modes (Claude's discretion, recommendation)
`pellmon-data/data/` (rrd.db, pellmon_settings.db) and `pellmon-data/logs/`. Dirs 755 owner 999:999 so the host user can browse; settings DB file 0600 (holds the future MQTT password, D-09/Phase 6). Trade-off: host user (typically uid 1000) then cannot read the settings DB without sudo; the backup tool runs in-container so that is acceptable. Set 0600 in `Keyval_storage.__init__` via `os.chmod(dbfile, 0o600)` in try/except (journal files created by SQLite inherit the main file's mode).

### Config editor writable conf.d: ownership
Files in `config/conf.d` are created on the host by the user (uid 1000, mode 644). The container runs as uid 999 and cannot write them. Recommendation: the init step also `chown -R 999:999 /etc/pellmon/conf.d` (as sketched), which makes web saves work; consequence: the host user needs sudo (or the web editor) to edit those files afterward. Alternative is `chmod -R a+rw`, which keeps host editing but makes files world-writable on the Pi. Present this trade-off in docs; recommended is chown, with `pellmon.conf` untouched (not mounted in init). Caveat: `chown -R` over a bind mount of the host's `config/conf.d` changes host ownership of tracked/untracked files, and git only tracks mode bits so `git status` stays clean.

## Current code behaviour (pellmonsrv.py, database.py)

Effective path facts (read from source):
- `config.__init__` reads `pellmon.conf`, then walks `config_dir` and `parser.read()`s every `*.conf`; later files override earlier. `[conf] database` = `/var/lib/pellmon/rrd.db` (conf.d/database.conf) overrides `pellmon.rrd` (pellmon.conf). `[conf] logfile` = `/var/log/pellmon/pellmon.log`. No `settings_db`, so default is `dirname(nvdb)/pellmon_settings.db` = `/var/lib/pellmon/pellmon_settings.db` (D-02 matches).
- Silent fallbacks:
  1. `self.db` (line ~739): missing `database` => `/tmp/pellmon_rrd_database.db`. Docker sets it explicitly, so not hit unless config is broken.
  2. `self.nvdb` (line ~745): only assigned when `polling` is true. If polling is False (invalid DB definition) `self.nvdb` is undefined, so line ~837 raises AttributeError, caught by bare `except`, and settings go to `/tmp/pellmon_settings.db` silently. Fix: derive from `self.db` instead of `self.nvdb`.
  3. Logfile (lines ~654-663): any failure (unwritable dir, permission) drops to `logging.StreamHandler()` silently; `mkdir_p(logdir)` errors are swallowed. Docker logs still show it via stderr, so not fatal, but D-07 asks for a clear message.
  4. `mkdir_p(os.path.dirname(self.keyval_db))` (line ~840) is unguarded and raises on an unwritable parent: crashes with traceback (loud but unclear), and only runs when `settings_db` is not set.
  5. `run()` (line ~925): `if conf.polling: mkdir_p(dbdir)` raises on failure; `os.chown` only when `-U/-G` were passed (compose command does not pass them).
  6. RRD create (line ~566-573): `if not os.path.exists(conf.nvdb)` then `subprocess.run(rrdtool create ...)`; failure is caught and only logged, and the daemon keeps running with no RRD. If the file exists but is unreadable/unwritable (e.g. root-owned after a restore), `exists` is true so creation is skipped; the failure surfaces later in `read_lastupdate` / `rrdtool update` as errors (`'U'` sentinel writes). No check today.
  7. `Keyval_storage.__init__` does `sqlite3.connect(dbfile)`; unwritable dir raises `sqlite3.OperationalError: unable to open database file` inside `Database()` (line ~75 `init_keyval_storage`), which is an unclear traceback. The class opens/closes a connection per operation, default journal mode (DELETE); no WAL set [VERIFIED: database.py read].
- Recommended minimal loud failure: a function `check_data_dirs(conf)` called in `run()` right after `conf` is built and before `daemon.start/run` (where `dbdir`/`logdir` are computed today). For dirs of `conf.db`, `conf.keyval_db`, `conf.logfile`: `os.makedirs(exist_ok=True)` wrapped, then `os.access(W_OK|X_OK)` and, for existing `conf.db` / `keyval_db` files, `os.access(R_OK|W_OK)`. On failure write to stderr and the logger a message like `pellmonsrv: data directory /var/lib/pellmon is not writable by uid N. Run 'docker compose up' (pellmon-init fixes ownership) or chown -R 999:999 <PELLMON_DATA_DIR>` and `sys.exit(1)`. Under compose `restart: unless-stopped` the container restart-loops and is visibly `Restarting`; acceptable and loud. To preserve non-Docker/dev behaviour and existing tests, gate hard exit on `polling` being on and on a config value or env (`PELLMON_REQUIRE_DATADIR=1`, set in compose) and otherwise log a warning; state this in the plan (D-07 explicitly permits it). Also fix fallback 2 to use `self.db`.
- Because the daemon mode is `debug` (foreground) in compose, `run()` is the earliest safe place; `sys.exit(1)` there is before any threads exist.

## Web config editor (pellmonconf.py)
- `self.dirs` is a dict filename -> base dir: `pellmon.conf` -> dirname of the `-C` path (`/etc/pellmon`), plus every `*.conf` under `config_dir` (`/etc/pellmon/conf.d`) as `conf.d/<relpath>` -> `/etc/pellmon` (so includes `conf.d/plugins/*.conf`). So `pellmon.conf` IS offered (the index default filename) and would be saved to `/etc/pellmon/pellmon.conf`.
- `save()`: `_resolve` (allowlist + realpath containment) then `codecs.open(path, 'w')`. On a `:ro` bind mount `open` raises `OSError` errno 30 (EROFS) before truncation, so the file is safe; on a permission problem `PermissionError` (EACCES, errno 13). Both are caught by `except (ValueError, OSError)` and returned as `{'success': False, 'error': str(e)}` = e.g. `[Errno 30] Read-only file system: '/etc/pellmon/pellmon.conf'`. Plan: catch `OSError` with `e.errno in (errno.EROFS, errno.EACCES, errno.EPERM)` and return a friendly `"<filename> is read-only (mounted read-only or not writable by the web user)"`. Also test: a file that is a single-file bind mount (pellmon.conf) can additionally give `EBUSY` on rename-style writes, but codecs.open('w') truncates in place so it is not an issue. Check how the JS in the source page shows `error` (I did not locate the template `source.html` under `src/Pellmonweb/html/`; planner should grep for `save` handler) [ASSUMED it displays `error` text].
- Also note `source()` (read) of `conf.d` works on ro or rw. Saving a file does not restart the daemon; docs should say restart is required (existing behaviour).

## RRD and SQLite backup

RRD [ASSUMED from rrdtool docs; confirm in smoke test]:
- `rrdtool dump rrd.db > rrd.xml` and `rrdtool restore rrd.xml new.rrd` (`--force-overwrite`/`-f` to replace an existing file; in 1.7 `-r/--range-check` optional). The XML dump is architecture independent, whereas native RRD files are not portable across endianness/word size (rrdtool docs say to use dump/restore). Restoring x86_64 to armv7 or arm64 via XML is the documented route.
- Consistency while running: `rrdtool update` and `dump` take file locks (flock); dump opens read-only and locks so it sees a consistent state, and concurrent update may briefly block or log `could not lock RRD`. Mitigate with a small retry (3 attempts, 1 s sleep) in the script, and for restore stop `pellmonsrv` first (`docker compose stop pellmonsrv` or `run --rm --no-deps`), since replacing the file under a running daemon is unsafe. Also the daemon caches `lastupdate` at startup only, so restart it after restore.
- Ownership after restore: run `rrdtool restore` inside a container as uid 999 (files owned correctly), or run the init service again (`docker compose run --rm pellmon-init`) afterwards. Do not restore as host root into the folder without re-running init.
- RRD schema: the DS list depends on config, so a restore requires the same `conf.d/database.conf`; include config in the backup (D-10 does).

SQLite: use `python3 -c` inside the container: `src=sqlite3.connect(path); dst=sqlite3.connect(out); src.backup(dst)` [CITED: Python sqlite3 docs]. Works with default journal mode and while writers run. `sqlite3` CLI is not in the image.

Suggested tool: `tools/pellmon_backup.py` (Python 3 stdlib only, GPL header, `%`-formatting) with subcommands `backup [--out FILE.tar.gz]` and `restore FILE.tar.gz`, options `--data-dir`, `--compose-file`, `--local` (operate directly on paths using local `rrdtool` and `sqlite3` module, used by tests and usable inside the container) and default docker mode (uses `docker compose exec -T pellmonsrv ...` for dump and sqlite backup and `docker compose stop pellmonsrv; run --rm --no-deps -T pellmonsrv ...` for restore). Archive layout: `rrd.xml`, `pellmon_settings.db`, `config/` (pellmon.conf and conf.d), `manifest.json` (source rrd filename, date, arch, rrdtool version). Backup archive contains password hashes and the MQTT secret: create it mode 0600 and say so in docs. The effective RRD filename must come from the manifest/config (pellmon.rrd vs rrd.db conflict noted above).

## Don't Hand-Roll
| Problem | Use instead |
|---|---|
| Ownership of bind mounts | init service chown, not entrypoint hacks in Python |
| Consistent SQLite copy | `sqlite3.Connection.backup`, not `cp` |
| Portable RRD copy | `rrdtool dump/restore`, not `cp` |
| Startup ordering | `depends_on` conditions, not sleep loops |

## Common Pitfalls
1. **Pull race for init service.** With `image: pellmon:latest` and no `build:`, on a fresh host compose may try to pull `pellmon:latest` from Docker Hub (fails) because the image is built by another service. Give init the same `build:` block [ASSUMED behaviour; verify with `docker compose up` on a clean image cache].
2. **Root-owned `pellmon-data/` inside the build context.** Docker creates missing bind sources as root; a later `docker compose build` then can fail reading the context (permission denied) for an unreadable root dir. Add `pellmon-data/` to `.dockerignore` (file exists, untracked) and `.gitignore` (D-05). Existing `.gitignore` has `*.db` but not the folder. Note `.dockerignore` is currently untracked; commit it or the fix is local only.
3. **`chown` on Docker Desktop for Windows/macOS mounts is a no-op or unreliable**: a Windows path (`C:\...`) uses a 9p/virtiofs share; ownership is faked and `chown` returns success without effect, so a passing init on Windows proves nothing. RRD uses mmap-style and flock I/O that behaves poorly on such shares [ASSUMED]. Test ownership only on Linux ext4: WSL2 Debian with a folder under `~` (not `/mnt/c`) and Docker engine there or Docker Desktop WSL integration, or on the Pi. Windows-specific layout is out of scope (deferred) but the test note matters.
4. **YAML `restart: no`** must be quoted.
5. **`docker compose down -v`** removes named volumes only (`pellmon-run`); bind-mounted `pellmon-data` survives (this is the goal). Old named volumes `<project>_pellmon-data` are left orphaned; migration step (D-11): `docker run --rm -v <project>_pellmon-data:/from -v "$PWD/pellmon-data/data":/to pellmon:latest sh -c 'cp -a /from/. /to/'` as root, then start (init fixes ownership). The RRD raw copy is valid only on the same machine type; otherwise dump/restore. Project name prefix: check `docker volume ls`.
6. **SELinux `:z`**: not relevant on Raspberry Pi OS/Debian; mention only for Fedora-type hosts [ASSUMED].
7. **Settings DB secrecy**: 0600 file and note that the archive holds secrets; `.gitignore` covers `pellmon-data/`.
8. **Silent settings loss**: fallback 2 above writes settings to `/tmp` when polling is disabled; fix.
9. **`chown -R` on every start** is cheap for these small dirs but recursion over `conf.d` would also touch host-edited files each start; acceptable, document.
10. **Existing regression tests** (`test_compose_raspberry_pi_fixes`, `test_docker_healthchecks`) parse compose by service block via `_service_block`; adding a service before/after must keep that helper working (check how it delimits blocks: two-space-indented `name:` keys). New init service should not contain the strings those tests forbid.

## Validation Architecture

### Test Framework
| Property | Value |
|---|---|
| Framework | pytest (existing `tests/`, `conftest.py`) |
| Quick run | `python -m pytest tests/test_ci_docker_config.py tests/test_data_persistence.py -q` |
| Full suite | `python -m pytest tests -q` |

### Decision to Test Map
| ID | Behavior | Type | Command / approach | Exists? |
|---|---|---|---|---|
| D-01/02/03/04 | bind mounts use `${PELLMON_DATA_DIR:-./pellmon-data}`, srv rw, web data `:ro`, `pellmon-run` still named, no `pellmon-data`/`pellmon-logs` volumes | text check | extend `tests/test_ci_docker_config.py` (regex on service blocks) | extend |
| D-05 | `.gitignore`, `.dockerignore` contain `pellmon-data`; `.env.example` documents `PELLMON_DATA_DIR` | text | same file | extend |
| D-06 | init service: `user: root`, `restart: "no"`, 999:999 chown, srv `depends_on` `service_completed_successfully` | text + `docker compose config -q` (needs no daemon; run in CI if `docker` present, else skip) | new test | Wave 0 |
| D-07 | `check_data_dirs` exits/raises on unwritable, missing-unfixable, unreadable rrd file; passes on tmp dir; warning-only when not required | unit, tmp_path (skip permission cases if running as root: `os.geteuid()==0`; use `os.chmod(0o500)`; on Windows skip) | `tests/Pellmonsrv/test_data_dir_check.py` | Wave 0 |
| D-07 | settings DB path derives from `self.db` when polling off | unit on `config` with temp conf | same | Wave 0 |
| D-08 | `save()` on read-only file gives friendly message; allowlist and same-origin tests still pass | unit with tmp file `chmod 0o444` (skip as root/Windows) or monkeypatch `codecs.open` to raise `OSError(errno.EROFS,...)` (portable, preferred) | `tests/Pellmonweb/` | Wave 0 |
| D-09 | `Keyval_storage` file mode 0600 | unit tmp_path (skip on Windows) | new | Wave 0 |
| D-10 | backup/restore round trip in `--local` mode: create RRD from `rrdtool create`, backup, delete, restore, `rrdtool info` matches; SQLite value survives; archive mode 0600 | integration; `shutil.which('rrdtool')` else skip (not on dev Windows; runs in CI ubuntu if `apt install rrdtool` added, or in WSL) | `tests/test_backup_script.py` | Wave 0 |
| D-10 | docker-mode command construction | unit with fake `docker` (monkeypatch runner, assert argv) | same | Wave 0 |
| D-11/docs | DEPLOY-PI.md mentions `pellmon-data`, backup, migration | text | grep test | Wave 0 |

### Real smoke test (manual, one time, recorded in VERIFICATION)
On WSL2 Debian ext4 or the Pi: `PELLMON_DATA_DIR=./pd docker compose up -d --build`; expect `pellmon-init` Exited (0), `pd/data` owned 999:999, `rrd.db` and `pellmon_settings.db` present, `docker compose down -v && up -d` keeps data; make `pd` read-only (`chattr`/`chmod` after removing init dependency) to see the loud failure; run backup, wipe, restore. On the Windows dev PC the build is host arch (amd64), takes a few minutes (apt + pip), the stack starts without a burner (fake data fallback); burner_sim needs a pty (Linux/WSL only), so leave it out of this phase's smoke test. CI stays static plus `docker compose config -q`; no Docker-in-Docker.

### Sampling
Per commit: quick run. Per wave: full suite. Gate: full suite green plus manual smoke on Linux.

### Wave 0 gaps
New test files listed above; `pip install`/`apt install rrdtool` only in CI if the workflow is edited (optional; tests skip otherwise).

## Security Domain
| ASVS | Applies | Control |
|---|---|---|
| V4 Access control | yes | pellmon.conf `:ro`; conf.d only writable for web; data `:ro` for web |
| V5 Input validation | yes | keep `_resolve` allowlist/realpath and same-origin check |
| V6 Cryptography | no | no new crypto; secrets stay in 0600 DB |
| V8 Data protection | yes | 0600 settings DB and backup archive; `.gitignore` for data folder |

Threats: path traversal via editor (existing `_resolve`), secret exposure via committed data folder or world-readable backup, world-writable conf.d (avoid `a+rw`), init container root scope limited to three paths.

## Assumptions Log
| # | Claim | Risk if wrong |
|---|---|---|
| A1 | init service without `build:` may attempt a pull on a fresh host | Low; duplicating `build:` is harmless |
| A2 | `rrdtool dump` locks read-consistently; concurrent update can print `could not lock RRD` | Retry logic unneeded or insufficient; smoke test |
| A3 | rrdtool 1.7.2 in bookworm supports `restore -f` | Adjust flags |
| A4 | Docker Desktop mounts fake chown; RRD misbehaves on 9p/virtiofs | Testing advice differs |
| A5 | Debian bookworm-slim has coreutils chown/mkdir/chmod | Init fails; verify with `docker run --rm pellmon:latest sh -c 'command -v chown mkdir chmod'` |
| A6 | JS in the config page shows the `error` string from `save` | Friendly message not visible |
| A7 | SELinux irrelevant on Pi OS | Add `:z` note |

## Open Questions
1. conf.d ownership model: chown to 999 (host edits need sudo) vs `a+rw`. Recommendation: chown; confirm with user in plan.
2. Effective RRD filename mismatch (`pellmon.rrd` vs `rrd.db`): fix `config/pellmon.conf.example` to avoid confusion? Recommend removing `database` from `pellmon.conf.example` or aligning it; in scope only as documentation clarity.
3. Whether to gate the hard exit behind `PELLMON_REQUIRE_DATADIR` (recommended) or always exit when polling is on.

## Sources
- Repo files read: docker-compose.yml, Dockerfile, .env.example, .gitignore, config/pellmon.conf, config/conf.d/database.conf, src/Pellmonsrv/pellmonsrv.py (config.__init__, run, main startup), src/Pellmonsrv/database.py (Keyval_storage), src/Pellmonweb/pellmonconf.py, tests/test_ci_docker_config.py [VERIFIED]
- docs.docker.com Compose spec (depends_on, interpolation) [CITED from training; not re-fetched]
- Python sqlite3 backup API [CITED from training]
- rrdtool dump/restore man pages [ASSUMED from training]

## Metadata
Confidence: code findings HIGH; Docker/rrdtool behaviour MEDIUM (unverified this session). Valid until: 30 days.
