---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
fixed_at: 2026-09-21T00:00:00Z
review_path: .planning/phases/07-persist-rrd-database-and-other-relevant-settings-outside-the/07-REVIEW.md
iteration: 1
findings_in_scope: 11
fixed: 11
skipped: 0
status: all_fixed
---

# Phase 7: Code Review Fix Report

**Source review:** 07-REVIEW.md (CR-01, WR-01..WR-10; IN-01..IN-04 deferred)
**Tests:** full suite 315 passed / 10 skipped before, 332 passed / 10 skipped after. System-python3 dbus/gi subset 213 before, 230 after.

## Fixed Issues

### CR-01: Restore overwrote live data destructively
**Commit:** ae87754. **Files:** tools/pellmon_backup.py, tests/test_backup_script.py
RRD and settings DB are built as `*.restore-new` next to the targets, verified (`rrdtool info`, SQLite integrity check), the old files are kept as `<name>.pre-restore` (0600, older one overwritten), then `os.replace`. `--local` needs `--yes` or an interactive confirmation. Docker mode does the same inside a root container script (mv at the very end); on any failure after `compose stop` it prints the recovery command, restarts the service best effort, and exits 1. `--with-config` writability is checked before the service is stopped. A missing settings DB in the archive is tolerated in both modes (current one left alone). Tests added: failed restore leaves originals intact, `.pre-restore` created (0600), `--local` without `--yes` refuses, docker failure restarts and explains. Marked for human verification because it is restore logic (fixed: requires human verification); the docker shell script was only syntax-checked (`sh -n`) and unit-tested with a faked `_run`, not run against a real container.

### WR-01: two services built pellmon:latest
**Commit:** 7d66b8a. `pellmon-init` has no build block, `image: pellmon:latest` plus `pull_policy: never`; test updated. Verified with `docker compose -p x config -q` and a scratch build in WSL ext4 (`docker compose -p pmfix up --no-start`, image and container names renamed in the scratch copy only): one build, no tag race, all three containers created. Scratch containers, network, volume, image and directory removed; the existing `pellmon:latest` (5c2bbb4e9469) was not touched.

### WR-02: uid/gid 999 not pinned
**Commit:** 0fd7100. Dockerfile: `groupadd -r -g 999 pellmon && useradd -r -u 999 -g pellmon pellmon` (command verified in a throwaway debian:bookworm-slim container, removed again). Text guard test added. Full image build not re-run for this.

### WR-03: init chowned host config/conf.d
**Commit:** 831c9f3. Init now only creates/chowns the data and log folders and no longer mounts `conf.d`. `pellmonweb` keeps the writable mount (D-08) with a comment; DEPLOY-PI.md now says the opposite of the old "needs sudo" text and explains that container writes need files writable by uid 999. **Deliberate deviation from the plan's default #1** (chown of conf.d), as decided by the orchestrator.

### WR-04: archive permissions
**Commit:** d682d15. Archive created with `O_CREAT|O_EXCL|O_NOFOLLOW`, 0600 from the start; existing `--out` (file or symlink) is refused before any work; partial archive removed on failure.

### WR-05: settings DB created at umask mode
**Commit:** bdbeb39. `Keyval_storage` pre-creates the file 0600 before `sqlite3.connect` (test spies on the first connect). The restore path is covered by CR-01 (staged with 0600 from creation).

### WR-06: coincidental /etc/pellmon/conf.d
**Commit:** 54e28c8. `resolve_config_dir(..., local=False)`: configured dir is trusted first only with `--local`; docker mode uses `<dirname(--config)>/conf.d`. Tests no longer skip on a host `/etc/pellmon/conf.d`; docs and module docstring updated.

### WR-07: XSS sinks in source.js
**Commit:** 564e122. All `.html()` uses replaced with `.text()`; the error line is appended as `$('<span>').text(...)`. Text/regex guard test in tests/Pellmonweb/test_source_js_no_html_sink.py. Not run in a browser.

### WR-08 and WR-09: docs
**Commit:** 36ea340. Volume migration runs `--user root`, creates the folders first and chowns to 999:999; loopback test derives the gid via `stat -c %g`; the spliced backup paragraph rewritten (also documents `.pre-restore` and `--local` confirmation). Guard assertions added. The migration command was not executed (the local image is arm/v7).

### WR-10: robustness
**Commit:** 5576645. Fixed: read-only URI for the settings DB (local and in-container) and an existence check so no empty DB is created; `sqlite3.Error`/`EOFError` caught with exit 1; clear error when `rrdtool` is missing; dash-prefixed `database`/`settings_db` values rejected (used instead of `--`, because `rrdtool` option handling of `--` was not confirmed); container temp copy always removed and created under umask 077; member-by-member validated extraction (regular files/dirs only, no setuid bits, total size capped at 4 GiB, no `extractall`). Skipped: nothing requiring a redesign.

## Deferred

- **IN-01** (`check_data_dirs` runs after `config()` opened the log file; existing unwritable logfile not checked): needs reordering of daemon start-up, not trivial or safe here.
- **IN-02** (tests skip as root/Windows; no pre-existing-0644 test): partly addressed by the WR-05 test; rest deferred.
- **IN-03** (manifest not validated on restore): deferred.
- **IN-04** (web container mounts conf.d writable, shared logfile): by design (D-08), documented only.

## Not verified

Restore against a real running docker stack, the docker restore shell script beyond `sh -n`, a full image build with the pinned uid, the volume-migration command, and the JS change in a browser.

---

_Fixed: 2026-09-21_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
