---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
reviewed: 2026-09-21T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - docker-compose.yml
  - src/Pellmonsrv/pellmonsrv.py
  - src/Pellmonsrv/database.py
  - src/Pellmonweb/pellmonconf.py
  - src/Pellmonweb/media/js/source.js
  - tools/pellmon_backup.py
  - DEPLOY-PI.md
  - HARDWARE-BRINGUP.md
  - Dockerfile
  - tests/test_backup_script.py
  - tests/Pellmonsrv/test_data_dir_check.py
  - tests/test_data_persistence.py
  - tests/Pellmonweb/test_pellmonconf_readonly.py
  - tests/test_ci_docker_config.py
findings:
  critical: 1
  warning: 10
  info: 4
  total: 15
status: issues_found
---

# Phase 7: Code Review Report

**Depth:** standard. Tar extraction, subprocess argv construction (no `shell=True`, list argv only) and `%r` quoting of paths inside the container python snippet are sound. The main defects are in restore semantics, the compose build duplication, and incomplete XSS sink cleanup.

## Critical Issues

### CR-01: Restore overwrites live data destructively, non-atomically, and can leave the stack half-restored and stopped

**File:** `tools/pellmon_backup.py:224-238, 264-286`
**Issue:**
- `restore_local` has no confirmation at all (`--yes` is only honoured in docker mode) and runs `rrdtool restore -f` directly onto the live RRD path. It also never checks that the daemon is stopped.
- `restore_docker` runs `rrdtool restore -f ... && cp /restore/pellmon_settings.db ...` after `compose stop`. If the archive has no `pellmon_settings.db` (local mode tolerates this, line 232), the `cp` fails after the RRD was already replaced. The exception propagates and `compose up -d` (line 284) is never reached, so the daemon stays stopped with a new RRD and the old settings.
- Same outcome if `--with-config` fails at line 283. After `pellmon-init` chowned `config/conf.d` to 999 (docker-compose.yml:24), a non-root host user gets PermissionError on `copytree`. This is exactly the documented setup, and it happens after data was already overwritten.
- No pre-restore copy of the existing RRD is made.
**Fix:** Restore to `<db>.new` and `os.replace` it. Keep a `.bak` of the old files. Require confirmation in `--local` too. Treat a missing settings DB the same way in both modes. Use `try/finally` so `compose up -d svc` always runs. Do the host config restore before stopping the service, or fail early with a clear message.

## Warnings

### WR-01: `pellmon-init` and `pellmonsrv` both `build:` and tag `pellmon:latest`

**File:** `docker-compose.yml:15-18, 38-41`
**Issue:** Two services build the same context and tag. Compose builds them in parallel, so both exporters race to tag `pellmon:latest` ("image already exists" failure, the reported smoke-test symptom). `pellmonweb` correctly reuses the image without a build block.
**Fix:** Build in one service only. Give `pellmon-init` `image: pellmon:latest` plus `pull_policy: never`, and `depends_on` nothing, or use `x-build` with a single builder. Alternatively drop `build:` from `pellmonsrv` and let `pellmon-init` be the builder, which is already what `pellmonsrv` depends on.

### WR-02: Hard-coded uid/gid 999 is not guaranteed by the Dockerfile

**File:** `docker-compose.yml:24`, `Dockerfile:42`
**Issue:** `useradd -r` picks the next free system uid, so 999 is an accident of the base image. The init chown/chmod, the doc `sudo chown 999:999` advice and `restore_docker` (`chown 999:999`) all depend on it. If the uid drifts, the daemon cannot write its data folder.
**Fix:** Pin it: `groupadd -r -g 999 pellmon && useradd -r -u 999 -g pellmon pellmon`. Better, `chown pellmon:pellmon` inside the container (init and restore) instead of numeric ids.

### WR-03: `pellmon-init` recursively chowns the host `config/conf.d` (and follows `-R` into whatever is mounted)

**File:** `docker-compose.yml:24`
**Issue:** The init service takes ownership of the whole config tree, including any `.conf` with password hashes, on every `up`. That is more than D-01..D-08 need (data and logs). It also locks the host user out of editing config (documented at DEPLOY-PI.md:152 as needing `sudo`). It breaks the backup/restore `--with-config` flow, and a `git pull` that touches `config/conf.d` files fails. A symlinked `conf.d` file is chowned as a link, but a symlinked mount root is followed.
**Fix:** Restrict the chown to the two data dirs. If the web GUI must edit `conf.d`, chown only that directory and its `*.conf` files, not `-R`. Use `chown -R --no-dereference` and quote the paths.

### WR-04: Archive written with 0600 only on create, then chmod afterwards

**File:** `tools/pellmon_backup.py:154-160`
**Issue:** `os.open(..., 0o600)` sets the mode only if the file is newly created. With an existing `--out` file (mode 0644, or a symlink) the secrets are written world-readable and the file is truncated silently. The chmod only happens at the end. `O_NOFOLLOW`/`O_EXCL` are absent.
**Fix:** Use `O_EXCL` (refuse to overwrite unless `--force`), and call `os.fchmod(fd, 0o600)` immediately after open.

### WR-05: Settings DB copied at default umask before chmod (local restore)

**File:** `tools/pellmon_backup.py:232-234`
**Issue:** `shutil.copyfile` creates the destination at umask 0644 and only afterwards chmods, leaving a window in which the file is readable by others. The same race exists in `Keyval_storage.__init__` (`src/Pellmonsrv/database.py:154-168`): `sqlite3.connect` creates the file at umask permissions, and `os.chmod` comes after the connection is closed. On a shared Pi another local user can open the file in that window. (The daemon itself sets `os.umask(0o033)` after dropping privileges, which yields 0644.)
**Fix:** `os.umask(0o077)` around creation, or pre-create with `os.open(path, O_CREAT|O_WRONLY, 0o600)` before `sqlite3.connect`.

### WR-06: `resolve_config_dir` prefers a coincidental `/etc/pellmon/conf.d` on the host

**File:** `tools/pellmon_backup.py:82-84`
**Issue:** If the host has a native install (or any dir) at `/etc/pellmon/conf.d`, its `database.conf` is used instead of `./config/conf.d`, so the wrong `database` path and wrong config are backed up. The test at `tests/test_backup_script.py:34-35` skips itself in that situation, which confirms the hazard rather than covering it.
**Fix:** In docker mode, prefer the sibling `conf.d` (or `--host-config-dir`) and only use the configured path in `--local` mode.

### WR-07: XSS sinks remain in `source.js`

**File:** `src/Pellmonweb/media/js/source.js:22, 24, 42, 47`
**Issue:** Only the save-error line was converted to `.text()`. `filedata.filename` is still passed to `.html()` (lines 22, 42, 47), and `filedata.error` (server `str(e)`) is concatenated into HTML at line 24. `filename` is currently limited to an allow-list, but that is a defence-in-depth gap, and any OSError text containing a path is injected as markup.
**Fix:** Use `.text()` for every one of these; for line 24 use `$('<span>').text(filedata.error)` appended after a `<br>`.

### WR-08: Old-volume migration command fails if the target folder does not exist yet

**File:** `DEPLOY-PI.md:245-253`
**Issue:** `docker run ... -v "$PWD/pellmon-data/data":/to pellmon:latest cp -a` runs as user `pellmon` (uid 999). If `pellmon-data/data` does not exist, Docker creates it root-owned and the copy fails with permission denied, because `pellmon-init` has not yet run (`compose up` comes after). Similarly, `cp -a` running as non-root cannot preserve ownership.
**Fix:** Add `--user root` (and `mkdir -p pellmon-data/data pellmon-data/logs` first), then run `docker compose up -d` so init fixes ownership.

### WR-09: Documentation defects

**File:** `DEPLOY-PI.md:232-233`; `DEPLOY-PI.md:309-313`; `docker-compose.yml:51-52`
**Issue:** The sentence "The archive is mode 0600 and contains After a restore ... password hashes and the settings DB" is spliced (an inserted sentence in the middle of another). The loopback test uses `--group-add 46` and says to substitute `SERIAL_GID`, while compose and `.env.example` default to 20. `--device /dev/ttyUSB0` also does not match a container that mounts `/dev`.
**Fix:** Repair the paragraph and use `${SERIAL_GID}` consistently.

### WR-10: Docker backup and local mode misc robustness

**File:** `tools/pellmon_backup.py:173-175, 328-330, 268`
**Issue:**
- `sqlite3.connect(cfg['settings_db'])` silently creates an empty DB if the path is wrong, so the backup "succeeds" with an empty settings file.
- `sqlite3.Error` and `EOFError` are not caught, so the user gets tracebacks.
- Missing `rrdtool` in `--local` mode shows a bare `[Errno 2]`.
- Config-derived `database` values starting with `-` are passed as rrdtool argv without `--`.
- No size limits on extraction (tar bomb), and on Python older than 3.12 with no `data_filter`, extraction falls through to unfiltered `extractall` (mode/ownership bits preserved as root).
- `_TMP_SETTINGS` is a fixed name in container `/tmp`, left behind (with secrets) if the `cp` step fails.
**Fix:** Use `sqlite3.connect('file:%s?mode=ro', uri=True)`, check `shutil.which('rrdtool')` up front, catch `sqlite3.Error`, use `try/finally` around the container temp file removal, and pass `--` before the DB path.

## Info

### IN-01: `check_data_dirs` runs after `config()` has already opened the log file

**File:** `src/Pellmonsrv/pellmonsrv.py:655-664, 971`
**Issue:** An unwritable log dir is reported as a generic "logging to stderr" warning by the `config` class before `check_data_dirs` runs, and an existing unwritable logfile is not checked at all (only its directory). Behaviour is otherwise correct: not fatal when `PELLMON_REQUIRE_DATADIR` is unset, and it runs before forking. `os.access` returns true for root regardless of mode, so the check is meaningful only for the non-root container user.

### IN-02: Tests skip on precisely the environments where they matter

**File:** `tests/Pellmonsrv/test_data_dir_check.py:66-84`, `tests/test_data_persistence.py:12`
**Issue:** The `posix_user` marker skips as root or on Windows. The 0600 test covers only file creation, not the race in WR-05, or a pre-existing 0644 file (the chmod-on-existing path).

### IN-03: Manifest is written but never read on restore

**File:** `tools/pellmon_backup.py:116-127, 202-206`
**Issue:** `format`, `machine` and `rrdtool_version` are not validated, so an archive from a future format version restores silently. `rrd.xml` is required but `manifest.json` is not.

### IN-04: `pellmonweb` mounts the log dir read-write and `/var/lib/pellmon` read-only

**File:** `docker-compose.yml:135-139`
**Issue:** This is fine for graph generation, but the two containers now write the same logfile with no coordination (`WatchedFileHandler` in each process). The web container also mounts `conf.d` writable, so a compromise of the web app can alter daemon configuration (`database.conf`, plugin config). This is intended by the design (GUI editing) but is the most privileged writable surface.

---

_Reviewed: 2026-09-21T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
