# Phase 13: Restore on web UI - Research

**Researched:** 2026-11-06
**Domain:** In-daemon restore of an RRD dump + SQLite settings DB from a Phase 12 archive, driven from the CherryPy Backup page over D-Bus
**Confidence:** HIGH on the codebase facts (all read in this session), MEDIUM on Docker restart-policy behaviour and rrdtool restore runtime on a Pi (not run here)

No CONTEXT.md exists (auto mode). Every design choice below is a proposed decision D-xx for the planner to adopt. No new external packages are needed (stdlib + the `rrdtool` binary already in the image), so there is no Package Legitimacy Audit.

## Summary

Restore must run **inside `pellmonsrv`** (the Backup plugin), not in pellmonweb and not on the host. Only the daemon container has the data dir writable (pellmonweb mounts it `:ro`), the `rrdtool` binary, uid 999 ownership, the settings DB, and `/backups` (rw already). It does NOT have the Docker socket, so it cannot do what `tools/pellmon_backup.py restore` does (`docker compose stop` / `run` / `up`). It therefore has to restore "under" itself: stage and verify new files while running, pause the writers for a very short swap, then exit so Docker's `restart: unless-stopped` brings it back with the restored data (the RRD `lastupdate` and plugin settings are only read at startup anyway).

Two hard facts from the code shape everything: (1) `config/pellmon.conf` and `config/conf.d` are mounted **read-only** into `pellmonsrv`, so the daemon cannot restore config. Web restore = RRD + settings DB only; config stays a host-tool step (`--with-config`). (2) `tools/` is **not in the Docker image** (`COPY src/ data/ VERSION` only), so the daemon cannot import the tool's `_safe_extract` / `_verify_sqlite`; that logic must be moved/duplicated into `src/Pellmonsrv/backup_core.py` and kept in parity by a test.

The most dangerous trap: all three SIGTERM handlers in `pellmonsrv.py` (`sigterm_handler` module level ~line 641, `MyDaemon.sigterm_handler` ~739, nested one in `MyDaemon.run` ~775) call `copy_db('store')` when `nvdb != db`, and `db_copy_thread` does the same periodically. A restore that swaps `conf.db` and then shuts down gracefully would **overwrite the restored persistent RRD with the old live one** in ramdisk setups. Restore must set a "restore done, do not store" flag that `copy_db('store')` honours, and must replace both `db` and `nvdb`.

**Primary recommendation:** Add a `Restore` state machine to the existing Backup plugin (worker thread, fixed-string reasons, progress states, result persisted in a small 0600 JSON file next to the RRD since the settings DB itself gets replaced), expose it through 3 new D-Bus methods, a confirm page + status polling on the Backup page, swap files with `os.replace` under a lock shared with the Poller and `copy_db`, keep `.pre-restore` copies exactly like the tool, then SIGTERM-self with the store flag set so Docker restarts the daemon.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Choose archive, confirm, show progress/result | Frontend server (CherryPy `Backup` controller + Mako) | Browser (small polling JS) | Page already exists; same auth/same-origin guards |
| Archive name allow-listing, auth, CSRF | Frontend server | API/Backend (daemon re-validates name vs listing) | Defence in depth; the client never supplies a path |
| Archive validation, extraction, `rrdtool restore`, `.pre-restore`, swap | API/Backend (pellmonsrv Backup plugin) | -- | Only tier with rw data dir, rrdtool, settings DB |
| Pausing poller / copy_db / settings writes | API/Backend (pellmonsrv core) | -- | Writers live in the daemon |
| Restart so new data is loaded | Container supervisor (Docker `restart: unless-stopped`) | Host operator (non-Docker installs) | Daemon cannot reload RRD lastupdate/plugin state in-process |
| Config files restore | Host (`tools/pellmon_backup.py --with-config`) | -- | `config/` is mounted `:ro` in the daemon |
| Archive storage/listing | Database/Storage (`/backups` mount) | -- | Phase 12 |

## Locked-by-code facts (verified in this session)

- `[VERIFIED: codebase]` Archive layout (Phase 12, same as tool): `config/`, `manifest.json`, `pellmon_settings.db`, `rrd.xml`; names `pellmon-backup-YYYYmmdd-HHMMSS.tar.gz` matched by `backup_core.NAME_RE`; `list_archives()` only returns regular, non-symlink files with that name; sorted tar member order means `manifest.json` precedes the big members (cheap to peek).
- `[VERIFIED: codebase]` `Keyval_storage` opens a fresh sqlite connection per call (`getval` etc. under `self.lock`), so an atomic `os.replace` of the file is safe for the storage layer. But plugins hold settings in memory (`self.cfg`, HA, OWM) and would write stale values back -> restart after restore is mandatory.
- `[VERIFIED: codebase]` Poller does `rrdtool update conf.db ...` with positional values (DS order matters); `conf.lastupdate_time` / `conf.lastupdate` read once via `read_lastupdate(conf.db)` at startup. A restored RRD with a different DS set/order than `conf.pollData` would break updates.
- `[VERIFIED: codebase]` Daemon runs as uid 999; data dir `/var/lib/pellmon` rw in pellmonsrv, `:ro` in pellmonweb; `/backups` rw in pellmonsrv; `pellmon.conf` and `conf.d` `:ro` in pellmonsrv. Compose runs `python3 -m Pellmonsrv.pellmonsrv ... debug` (foreground) with `restart: unless-stopped`; `pellmon-dbus` is a separate long-lived service so pellmonweb's D-Bus connection survives a pellmonsrv restart (comment in compose, and `Dbus_handler` watch_name_owner).
- `[VERIFIED: codebase]` Web credentials live in `pellmon.conf [authentication]` (config), not the settings DB -> a settings-DB restore cannot lock the user out of the web UI. The settings DB does carry `backup.config` / `backup.state`, HA/MQTT secrets, OWM key, chosen system image.
- `[VERIFIED: codebase]` Existing guard pattern in `Pellmonweb/backup.py`: `@require()`, `_guard()` = POST only + `check_same_origin()` + `credentials` configured; PRG redirect with `?done=` keys; fixed-string reasons filtered through `REASONS`; D-Bus calls are JSON strings through `Dbus_handler.backup_*`.
- `[VERIFIED: codebase]` Test infra: pytest, `tests/Pellmonsrv/test_backup_core.py` uses a fake `rrdtool` shell script (`fake_rrdtool`), `tests/Pellmonsrv/test_backup_dbus.py` uses a `FakePlugin`, `tests/Pellmonweb/test_backup_page.py` uses fake template/dbus; `tests/test_backup_script.py` has the traversal/symlink/size tests for the tool's extractor. CI (`.github/workflows`) has real rrdtool + gi; dev container does not.

## Standard Stack

No new dependencies. Use only: Python stdlib (`tarfile`, `sqlite3`, `subprocess`, `tempfile`, `shutil`, `threading`, `json`, `os`), the `rrdtool` CLI (Debian bookworm package already in the Dockerfile), CherryPy/Mako/simplejson already present. Do not add `rrdtool` Python-binding usage for restore (binding has no restore).

**Version verification:** n/a (no installs). `[ASSUMED]` Debian bookworm ships Python 3.11.x without the `tarfile` extraction `filter=` argument guaranteed -> keep the manual per-member validation from the tool (do not rely on `filter='data'`).

## Design decisions (recommendations)

- **D-01 (where restore runs): in the daemon**, Backup plugin, new `restore_*` methods; never in pellmonweb (ro data dir) and never via Docker socket. Host tool stays the fallback and the only path for config.
- **D-02 (scope): RRD + settings DB only; config is NOT restored from the web.** Reason: `:ro` mounts. The confirm page states "Configuration files in the archive are not restored here; use `tools/pellmon_backup.py restore --with-config`". Do not change the compose mounts to rw (would widen the attack surface of a daemon that holds hardware access; out of scope). If the archive holds `config/`, show an informational note only.
- **D-03 (archive selection): by name from the listing only.** Client posts `name`; both web and daemon check `NAME_RE` full-match (no `/`, no `..`) AND that the name appears in a fresh `core.list_archives(folder)`; the path is `os.path.join(folder, name)` built server-side. Re-check `os.path.isfile` and not a symlink (`os.lstat`) at open time. Open with `O_NOFOLLOW`.
- **D-04 (move shared extraction into backup_core):** copy `_safe_extract` (members validated first: regular files/dirs only, no abs/`..`, size cap `MAX_EXTRACT_BYTES = 4 GiB`, realpath containment, `O_EXCL|O_NOFOLLOW`, no setuid) and `_verify_sqlite` into `backup_core.py`; a parity test feeds the same malicious archives to both implementations. Extract only the members needed (`manifest.json`, `rrd.xml`, `pellmon_settings.db`), never `config/` (skip it; avoids writing secrets to scratch needlessly).
- **D-05 (staging location): inside the data dir**, e.g. `<dirname(conf.db)>/.restore-tmp/` (0700, uid 999), NOT `/tmp`. `rrd.xml` can be 100 MB+, `/tmp` in the container is the writable layer on the SD card, and staged files must be on the same filesystem as targets so `os.replace` is atomic. Staged outputs are `<db>.restore-new` / `<settings_db>.restore-new` exactly like the tool. Wipe `.restore-tmp` and stale `*.restore-new` at daemon startup and at the start of every restore (killed run leftovers).
- **D-06 (free-space pre-check):** before extracting, require free space on the data dir >= sum of the needed member sizes (from tar headers, needs a first pass anyway for validation) + 2 x current RRD size + margin (e.g. 64 MiB). Fail with new reason "not enough free space to restore".
- **D-07 (validation before any change; nothing touched on failure):** (1) open + read-through the tar (gzip CRC) with member validation; (2) manifest present, `format == 1`; (3) `rrd.xml` and `pellmon_settings.db` present (settings DB optional in the tool; for web require both, reject otherwise - a partial restore is a footgun; document); (4) `rrdtool restore rrd.xml <db>.restore-new` with `timeout` (900 s like dump; run in the worker thread) and `rrdtool info` on the result; (5) compare staged DS names/order and step with the current live RRD (`rrdtool info` on `conf.db`, fall back to `conf.pollData` names); mismatch -> refuse with "archive RRD layout does not match this installation" (host tool remains for forced cases); (6) `rrdtool lastupdate` of the staged file must not be more than ~1 day in the future vs `time.time()` (otherwise Poller updates fail with "illegal attempt to update using time"); (7) `_verify_sqlite` (`PRAGMA integrity_check`) and that table `keyval` exists with the expected columns.
- **D-08 (pre-restore safety copy): reuse the tool's convention** - copy live `db` -> `db.pre-restore` and live settings DB -> `settings_db.pre-restore` (0600, overwrite older) taken under the swap lock (consistent with no concurrent `rrdtool update`); if `nvdb != db` also `nvdb.pre-restore`. Do not take a full tar safety backup (needs a minutes-long `rrdtool dump` + a reachable NAS; adds a failure mode before a recovery action). Surface in the result: "Previous data kept as ...pre-restore in the data folder" (name only, no path leak beyond the fixed file names). Optional extra (planner's discretion): also copy `.pre-restore` for RRD with `shutil.copyfile` via `call_with_timeout` is NOT needed, data dir is local.
- **D-09 (quiesce protocol, in order):**
  1. Acquire the plugin's `self.lock`, set `self.running`-style flag `restoring=True` (reject backup runs, scheduler `tick()` returns early, `start_now()` returns busy, second restore refused).
  2. Stage + verify everything (long part; poller keeps running, nothing live is touched).
  3. Take a new module-level `restore_lock` (add to `pellmonsrv.py`; Poller wraps its `rrdtool update` + `conf.lastupdate` assignment, `copy_db()` wraps its copy, with it) and hold it for the swap only (seconds). Under it: pre-restore copies -> `os.replace(new, target)` for `conf.db`, then for `conf.nvdb` if different (replace nvdb with the staged file and copy to `conf.db`, or stage twice) -> settings DB `os.replace` (also hold `Keyval_storage.keyval_storage.lock`) -> set `conf.restore_done = True`.
  4. Before replacing the settings DB, carry over the current `backup.config` and `backup.state` rows into the staged copy (`INSERT OR REPLACE`) so the Backup page settings the operator is looking at do not silently revert to the archive's. Recommended; a few lines of sqlite.
  5. Write the result file (D-12), log, then trigger shutdown (D-10).
  Web graph readers (`rrdtool graph/fetch` in pellmonweb via the ro mount) are unaffected by `os.replace` (old inode stays valid for open readers).
- **D-10 (restart): exit, let the supervisor restart.** Self-`os.kill(os.getpid(), signal.SIGTERM)` after swap, with `conf.restore_done` making all three SIGTERM paths and `db_copy_thread` **skip `copy_db('store')`** (otherwise the old ramdisk RRD overwrites the restored persistent one). Compose has `restart: unless-stopped`, which restarts on any exit code `[ASSUMED: Docker docs, restart policies; verify on the Pi]`. Detect a supervised container with `os.path.exists('/.dockerenv')` and word the result accordingly ("The server is restarting" vs "Restored. Restart the PellMon server now"). Do NOT `os.execv` self (serial fds, GLib/D-Bus state, `python3 -m` argv). Non-Docker (initscript) installs get the "restart manually" message.
- **D-11 (rollback / failure semantics):** pre-swap failure -> nothing changed, remove staging, state `failed` with reason, backup scheduler resumes. Swap-phase failure after the first `os.replace` (e.g. settings replace fails after RRD replaced): roll back the already-replaced target from its `.pre-restore` copy (`os.replace`) inside the same lock, then report failure. Post-restart failure (restored RRD makes startup `read_lastupdate` crash) is prevented by D-07(4)-(6) pre-validation; manual recovery = `mv <file>.pre-restore <file>` documented in DEPLOY-PI.md.
- **D-12 (progress + result persistence):** a state machine with fixed names: `idle, checking, extracting, building, swapping, restarting, done, failed`, plus `percent`-free coarse progress (step n of 5). Held in memory, exposed by `GetBackupStatus` (add a `restore` key) so the existing status poll works. Because the settings DB (the plugin's normal store) is replaced, persist the final result in `<data dir>/.restore-result.json` (0600, written atomically via temp+`os.replace`, content: `{name, time, ok, reason}`), read at plugin `activate()` and shown once on the page ("Restored from X at HH:MM"), then marked as acknowledged. Reasons are fixed strings added to `REASONS` (and must be added to the DEPLOY-PI failure table; the existing test enforces every reason is explained): archive not found / archive unreadable or damaged / archive unsafe / archive has no RRD or settings / not enough free space / rrdtool restore failed / archive RRD layout does not match this installation / archive is newer than the system clock / settings database in archive is damaged / restore already running / swap failed (previous data restored). Never send paths or exception text to the browser (D-07 of Phase 12 still applies).
- **D-13 (web flow, CSRF/auth/confirmation):** `GET /backup/restore?name=<n>` (login required) renders a confirm page: archive name/time/size, manifest `created`, `machine`, `rrdtool_version`, what will be replaced and kept (`.pre-restore`), warning that live data newer than the archive is lost, that config is not restored, that the server will restart and the page will reconnect, and a typed confirmation field (`type RESTORE`) + submit. `POST /backup/restore_run` uses the existing `_guard()` (POST, `check_same_origin`, credentials configured), re-validates name, calls D-Bus `StartRestore(name)`, `303` to `/backup/?done=restoring`. Also add a "Restore..." link per row in the archives table (a GET link to the confirm page, no state change on GET). Manifest peek for the confirm page comes from a bounded (`call_with_timeout`, ~10 s) D-Bus call `PreviewBackup(name)` returning only whitelisted manifest fields. Refuse restore when `credentials` is not configured (same as saves).
- **D-14 (progress UI):** the Backup page, when `restore.state` is not idle/done/failed or the daemon is down right after a restore, polls `GET /backup/restore_status` (JSON, login required) every 2 s with a small script (`textContent` only, per `tests/Pellmonweb/test_source_js_no_html_sink.py`), shows the step, then on daemon down "Restarting the server..." and keeps polling until the daemon answers, then shows the persisted result. Works with no JS via a `<meta http-equiv="refresh">` fallback only if the planner wants it; the existing "Reload this page" pattern is the minimum.
- **D-15 (D-Bus API):** add to `pellmonsrv.py` `MyDBUSService` (same pattern as `StartBackup`): `PreviewBackup(s)->s`, `StartRestore(s)->s` (returns at once; `{ok, reason}`), restore state in `GetBackupStatus`. Add `Dbus_handler.backup_preview(name)`, `backup_restore(name)` in `pellmonweb.py` (JSON over D-Bus, never log arguments is not needed here; no secrets). Note D-Bus string methods have a ~25 s default client timeout: all long work is in the worker thread.
- **D-16 (docs):** update the "Restore" text in `backup.html` help line, `DEPLOY-PI.md` (web restore, what it does not do, `.pre-restore` manual rollback, failure table rows), `12-CONTEXT` deferred item note. Keep `tools/pellmon_backup.py` unchanged except optionally sharing semantics.

## Alternatives considered

| Decision | Alternative | Why not |
|----------|-------------|---------|
| In-daemon restore | Web container runs `docker compose` | No docker socket; mounting it gives root on host |
| In-daemon restore | One-shot "restore" sidecar triggered by a marker file | Extra service, host-side plumbing, slower UX; reconsider only if `:ro` config restore becomes a requirement |
| Exit + supervisor restart | In-process reload | Plugins cache settings, RRD lastupdate only read at start, GPIO/serial state; high risk |
| Staged files + atomic `os.replace` | `rrdtool restore --force-overwrite` onto live DB | Poller/graph readers see a half-written file; no rollback |
| `.pre-restore` file copies | Full safety tar archive first | Minutes-long dump, needs NAS up, adds failure mode |
| Config restore from web | Make `config/` rw | Out of scope, widens attack surface, running daemon would not re-read it anyway |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Portable RRD import | Custom RRD parser | `rrdtool restore` + `rrdtool info`/`lastupdate` | Format is arch-specific; XML dump is the portable path (already the Phase 12 design) |
| SQLite integrity | Custom check | `PRAGMA integrity_check` (as in the tool) | |
| Safe tar extraction | `tar.extractall` | The tool's member-by-member validated extractor (moved to `backup_core`) | Traversal/symlink/tar-bomb already tested |
| Bounded I/O on NAS | Blocking calls on the D-Bus thread | `backup_core.call_with_timeout` + worker thread | Hung NFS froze daemon before (Phase 12 decision) |
| Origin/CSRF/auth | New mechanism | `Pellmonweb.security.check_same_origin`, `@require()`, `_guard()` | Consistent with every other POST page |
| Atomic file replace | Copy over target | stage + `os.replace` on same filesystem | |

## Architecture Patterns

```
Browser --GET /backup/restore?name=N--> Backup controller --PreviewBackup(N)--> daemon (bounded read of manifest)
   |                                                                                   |
   | POST /backup/restore_run (name, confirm word; Origin check, auth)                  |
   v                                                                                   v
Backup.restore_run --StartRestore(N)--> Backup plugin: lock, restoring=True, return {ok}
                                              worker thread:
                                              checking (list+lstat+gzip read-through+member rules)
                                              extracting (data dir/.restore-tmp, space check)
                                              building  (rrdtool restore -> db.restore-new, info, DS/lastupdate checks; sqlite verify; carry over backup.* keys)
                                              swapping  (restore_lock: pre-restore copies, os.replace db[/nvdb], settings; rollback on error)
                                              result file, restore_done flag, SIGTERM self (no copy_db store)
Docker restart policy --> pellmonsrv restarts (reads restored RRD lastupdate + settings) --> pellmonweb reconnects (watch_name_owner)
Browser polls /backup/restore_status (-> GetBackupStatus.restore) -> "Restarting..." -> persisted result
```

Recommended structure (additive): `src/Pellmonsrv/backup_core.py` gains `safe_extract`, `verify_sqlite`, `inspect_archive`, `restore_archive` (pure, injected paths, callbacks for progress and lock, no D-Bus, easy to test); `plugins/backup/__init__.py` gains `restore_*`/`preview_*` thin wrappers + state; `pellmonsrv.py` gains `restore_lock`, `restore_done` handling and 2 D-Bus methods; `Pellmonweb/backup.py` gains `restore`, `restore_run`, `restore_status`; `html/backup.html` gains row links; new `html/backup_restore.html` confirm page (or a section of `backup.html`).

Anti-patterns: replacing files without the shared lock; letting any SIGTERM handler `copy_db('store')` after the swap; staging in `/tmp`; trusting a client path; returning exception text to the browser; creating `.py2bak` files (CLAUDE.md); f-strings in `src/Pellmonsrv` (use `%`).

## Common Pitfalls

1. **Old RRD overwrites restored one at shutdown** (`copy_db('store')` in 3 SIGTERM handlers + `db_copy_thread`) when `persistent_db != database`. Avoid with `conf.restore_done` guard inside `copy_db` and by replacing both files. Test: simulate nvdb != db, assert nvdb content is the restored one after shutdown path runs.
2. **Poller writing during swap** -> corrupt/inconsistent copy or write to a replaced inode. Use the shared lock around `rrdtool update` and `copy_db`.
3. **DS layout mismatch** (user changed poll items since backup) -> Poller's positional `update` fails forever. Validate DS names/order/step (D-07-5).
4. **Archive from a clock-ahead machine** -> `rrdtool update` "illegal attempt to update using time". Validate lastupdate vs now.
5. **Settings DB swap resurrects stale plugin state / backup settings revert**; carry over `backup.*` rows, and restart.
6. **Result lost because the DB holding it is replaced** -> persist result in a file in the data dir.
7. **Leftover `.restore-tmp`/`*.restore-new` after a kill** -> clean at startup and before each run.
8. **Scheduler fires mid-restore / during restart window**: `tick()` returns early while `restoring`; the daemon restart has `startup_delay = 120`, fine.
9. **Hung NAS during archive read**: read-through in the worker thread, never on the D-Bus thread; preview through `call_with_timeout`. A hung read leaves state `checking`: add an overall timeout watchdog (e.g. 30 min) that marks failed with "archive unreadable" only if safe (before swap).
10. **rrdtool restore on a Pi is slow and memory hungry for a multi-year dump**; use the 900 s timeout pattern from `_dump_rrd` but consider raising for restore (`RRD_RESTORE_TIMEOUT = 1800`), and never block the UI.
11. **Non-Docker installs do not restart**: state "done, restart required".
12. **Double-submit / two tabs**: single `restoring` flag under lock; second request returns "restore already running".
13. **Confirm only on GET page is bypassable by a forged POST**: POST re-checks Origin and the typed word server-side; the daemon is the final authority on name validity.
14. **Archives contain secrets** (hash, MQTT/OWM keys): preview exposes only whitelisted manifest fields; scratch dir 0700, files 0600, wiped after.
15. **Web graph pages during swap**: harmless due to `os.replace`; but pellmonweb opens the ro data dir - no change needed.

## Runtime State Inventory (restore touches runtime state)

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | RRD (`conf.db`, optional `conf.nvdb`), settings SQLite (`conf.keyval_db`) incl. `backup.config`/`backup.state` | Replace both atomically; carry over `backup.*` keys; keep `.pre-restore` |
| Live service config | In-memory plugin settings (HA/MQTT, OWM, Backup `cfg`), `conf.lastupdate*` | Restart daemon after swap |
| OS-registered state | None -- Docker restart policy is the only supervisor dependency | Document non-Docker restart |
| Secrets/env vars | Secrets inside the archived settings DB; web credentials are in `pellmon.conf` (not restored) | None; do not leak in preview/status |
| Build artifacts | None | None |

## Code Examples

Swap under the shared lock with rollback (sketch, follows tool + `%` style):

```python
# Source: derived from tools/pellmon_backup.py restore_local and Pellmonsrv/backup_core.py
def swap_in(pairs, lock):
    """pairs: [(target, staged)]. Returns nothing; on error restores already replaced targets."""
    done = []
    with lock:
        try:
            for target, staged in pairs:
                keep_pre_restore(target)            # target -> target + '.pre-restore', 0600
                os.replace(staged, target)
                done.append(target)
        except OSError:
            for target in done:
                pre = target + '.pre-restore'
                if os.path.isfile(pre):
                    os.replace(pre, target)         # best effort rollback
            raise BackupError(REASON_SWAP)
```

Poller integration (one line each site):

```python
with restore_lock:                       # new module-level threading.Lock in pellmonsrv.py
    cmd = subprocess.Popen(RRD_command, ...)
```

```python
def copy_db(direction='store'):
    if direction == 'store' and getattr(conf, 'restore_done', False):
        return                           # never overwrite restored persistent RRD
```

## State of the Art

| Old | Current | Impact |
|-----|---------|--------|
| Restore only via host CLI (Phase 12 D-08) | In-daemon web restore | Needs daemon to exit and rely on supervisor |
| Tool-only extraction code | Shared in `backup_core` | Parity test required |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Docker `restart: unless-stopped` restarts a container whose PID 1 exits with code 0 after SIGTERM-self | D-10 | Daemon stays down after restore; mitigate by exiting non-zero or verifying on the Pi (Phase 12 summary says real-device verification is pending anyway) |
| A2 | Debian bookworm `python3` lacks guaranteed `tarfile` `filter=` | Standard Stack | Only affects whether manual validation is still needed (keep it either way) |
| A3 | `rrdtool restore` of a multi-year dump on a Pi takes minutes, memory acceptable | Pitfall 10 | Timeouts too short; make constant configurable, test on the Pi |
| A4 | Requiring both `rrd.xml` and `pellmon_settings.db` for web restore is acceptable (tool allows missing settings DB) | D-07 | Rare old archives rejected; host tool remains |
| A5 | Refusing on DS layout mismatch is the right default | D-07 | Users with changed poll items must use host tool; confirm with user |
| A6 | Carrying over `backup.config`/`backup.state` is desired | D-09 | Alternative: full revert to archive settings; low risk either way |

## Open Questions

1. **Force option for DS mismatch?** Recommend no (host tool), confirm with user.
2. **Should restore also be offered for archives in a sub-folder other than the configured one?** Recommend no: only the configured folder listing (`LIST_LIMIT = 20` shown; restore of older archives not in the newest-20 list needs the host tool or raising the limit -- decide whether the restore list should show all).
3. **Exit code / supervision on the Pi** needs real verification (A1).
4. **Auto-rollback if restarted daemon fails within N seconds** - not recommended for v1; manual `.pre-restore` rollback documented.

## Environment Availability

| Dependency | Required By | Available (dev) | Fallback |
|------------|------------|-----------------|----------|
| rrdtool | restore build/verify | not in dev container; present in image and CI | fake `rrdtool` script in tests (extend `fake_rrdtool` with `restore`, `info`, `lastupdate`) |
| gi/dbus | D-Bus + browser suites | CI only | FakePlugin / fake dbus in unit tests |
| Docker + Pi + NAS | end-to-end | not here | manual UAT checklist |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-mock, pytest-socket) |
| Config file | `tests/conftest.py`, `tests/Pellmonsrv/conftest.py` (no pytest.ini seen) |
| Quick run command | `python -m pytest tests/Pellmonsrv/test_backup_core.py tests/Pellmonsrv/test_backup_dbus.py tests/Pellmonweb/test_backup_page.py tests/test_backup_script.py -x -q` |
| Full suite command | `python -m pytest tests/ -v` (CI also `pytest tests/browser -v -rs --allow-unix-socket`) |

### Proposed requirement -> test map (D-xx stand in for requirement IDs)
| ID | Behavior | Test Type | Automated Command | File Exists? |
|----|----------|-----------|-------------------|-------------|
| D-03 | Only listed names accepted; traversal/slashes/symlink rejected daemon- and web-side | unit | `pytest tests/Pellmonsrv/test_backup_restore.py -k name` | Wave 0 |
| D-04 | Extractor parity with tool (traversal, symlink, device, size cap, setuid) | unit | `pytest tests/Pellmonsrv/test_backup_restore.py -k extract` | Wave 0 |
| D-05/06 | Staging in data dir, leftovers cleaned, low-space refusal | unit | `-k staging` | Wave 0 |
| D-07 | Each validation failure leaves live files byte-identical and returns the fixed reason (damaged gzip, missing rrd.xml/settings, bad manifest, bad sqlite, rrdtool failure via fake, DS mismatch, future lastupdate) | unit | `-k validate` | Wave 0 |
| D-08/09 | `.pre-restore` copies made, swap atomic, backup.* keys carried over, backups blocked while restoring, lock excludes Poller update | unit | `-k swap` | Wave 0 |
| D-10 | `copy_db('store')` skipped after `restore_done`; nvdb != db case ends with restored content | unit (tests/Pellmonsrv/test_db_copy.py extension) | `pytest tests/Pellmonsrv/test_db_copy.py -k restore` | extend existing |
| D-11 | Swap failure rolls back already-replaced files | unit (monkeypatch `os.replace` to fail on 2nd call) | `-k rollback` | Wave 0 |
| D-12 | Result file written atomically, read once at activate, fixed reasons only, every reason documented in DEPLOY-PI.md | unit | `-k result`; extend doc test in `tests/test_backup_compose.py` | Wave 0 |
| D-13 | Confirm page GET has no side effects; POST needs same-origin, login, credentials, typed word; redirects PRG | unit | `pytest tests/Pellmonweb/test_backup_page.py -k restore` | extend existing |
| D-14 | JS uses textContent only (no HTML sink); status endpoint requires login | unit | `tests/Pellmonweb/test_source_js_no_html_sink.py` + new | extend |
| D-15 | D-Bus `StartRestore`/`PreviewBackup` never leak exception text/paths, plugin missing -> `available: False` | unit | `pytest tests/Pellmonsrv/test_backup_dbus.py -k restore` | extend |
| D-01/E2E | Archive made by `create_archive` restores through `restore_archive` with real rrdtool (CI) and also still restores with the host tool | integration (skip if no rrdtool) | `pytest tests/Pellmonsrv/test_backup_restore.py -k roundtrip` | Wave 0 |
| UAT | Real Pi + NAS: restore, container restarts, graphs show restored data, `.pre-restore` present | manual-only | checklist in phase VERIFICATION | -- |

### Sampling Rate
- Per task commit: quick command above.
- Per wave merge: `python -m pytest tests/ -q`.
- Phase gate: full suite green plus manual Pi UAT (A1, A3 cannot be proven in the dev container).

### Wave 0 Gaps
- [ ] `tests/Pellmonsrv/test_backup_restore.py` - core restore tests, extend `fake_rrdtool` to implement `restore`, `info`, `lastupdate`
- [ ] Extend `tests/Pellmonsrv/test_backup_dbus.py` FakePlugin with `preview_backup`, `start_restore`
- [ ] Extend `tests/Pellmonweb/test_backup_page.py` fake dbus with restore methods
- [ ] Extend `tests/Pellmonsrv/test_db_copy.py` for the `restore_done` guard

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | existing `@require()` + `credentials` configured |
| V3 Session Management | yes | existing CherryPy sessions |
| V4 Access Control | yes | login required for all restore routes, daemon-side name validation |
| V5 Input Validation | yes | `NAME_RE` + listing allow-list, manifest whitelist, tar member rules |
| V6 Cryptography | no | none (archives unencrypted, Phase 12 D-03) |
| V12 Files/Resources | yes | `O_NOFOLLOW`/`O_EXCL`, size cap, 0700/0600 scratch, no symlinks |

| Threat | STRIDE | Mitigation |
|--------|--------|------------|
| Cross-site forged restore POST | Tampering | `check_same_origin`, POST-only, typed confirmation, no state change on GET |
| Path traversal via archive name | Tampering/Info disclosure | allow-list from listing, server-built path |
| Malicious archive (traversal, symlink, tar bomb, setuid) | Tampering/DoS | validated extractor + 4 GiB cap + space check |
| Malicious RRD XML crashing rrdtool / huge | DoS | staged restore with timeout; live data untouched until verified |
| Secrets in preview/status/errors | Info disclosure | whitelist fields, fixed-string reasons, no paths |
| Denial by repeated restores | DoS | single-flight flag; login required |
| Restoring an attacker-supplied archive placed on the NAS | Tampering | inherent to unencrypted archives; documented (Phase 12 D-09); restore requires an authenticated human and shows archive time/machine |

## Project Constraints (from CLAUDE.md)

- Python 3 only; `%` formatting inside `src/Pellmonsrv/`; GPL header block on new source files; no new `.py2bak`; relative imports within `Pellmonsrv`, absolute across subpackages; prefer `logger.warning/error` over `info` for failures; reuse the `pellMon` logger; no `print`.
- Hardware paths verified by mocks; here: fake `rrdtool`, fake D-Bus; real rrdtool only in CI/Pi.
- Work must go through GSD workflow (`/gsd-execute-phase`).
- Match surrounding indentation; no formatter changes.

## Sources

### Primary (HIGH, codebase read this session)
- `tools/pellmon_backup.py`, `src/Pellmonsrv/backup_core.py`, `src/Pellmonsrv/plugins/backup/__init__.py`, `settings.py`, `src/Pellmonweb/backup.py`, `html/backup.html`, `pellmonsrv.py` (Poller, `copy_db`, SIGTERM handlers, D-Bus methods, startup), `database.py` `Keyval_storage`, `docker-compose.yml`, `Dockerfile`, `DEPLOY-PI.md`, Phase 12 CONTEXT/SUMMARY, `tests/` layout.

### Tertiary (LOW, from training knowledge, not re-verified)
- Docker restart policy semantics for exit code 0 (A1), rrdtool restore resource use (A3).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (nothing new)
- Architecture: HIGH (constraints derived from mounts/code); MEDIUM for restart behaviour on the Pi
- Pitfalls: HIGH for code-derived (1-8), MEDIUM for runtime ones (9-10)

**Research date:** 2026-11-06
**Valid until:** 30 days (code-local; invalidated by changes to `pellmonsrv.py` shutdown paths or compose mounts)
