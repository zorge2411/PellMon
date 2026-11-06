# Phase 12 Summary: scheduled backup to a NAS or other media

**Status:** code complete, pending verification on the real Pi with a real NAS/USB mount.

## Built
- `src/Pellmonsrv/backup_core.py` (12-01): archive creation in the `tools/pellmon_backup.py` format (rrdtool dump with retry, sqlite
  backup API, config copy, manifest), written as `.part`, verified by reading it back, then renamed; folder check incl. same-disk
  refusal and bounded waits (`call_with_timeout`); retention (`select_prune`/`prune`); schedule maths (`last_slot`, `next_slot`, `is_due`).
- `plugins/backup/` (12-02): `Backup` plugin (always loaded, idle until enabled), settings model with one validator, scheduler thread,
  run now / test folder, status; D-Bus `Get/SetBackupSettings`, `GetBackupStatus`, `StartBackup`, `TestBackupFolder`.
  The config object now remembers `conf_file` and `config_dir`.
- Web **Backup** page (12-03): settings form, Back up now, Test folder, status line, archive list, warnings.
- Compose (12-04): `${PELLMON_BACKUP_DIR:-./pellmon-backups}` mounted at `/backups` in pellmonsrv and the init service
  (non-recursive, failure-tolerant chown); `.env.example`, ignore files; `DEPLOY-PI.md` section with fstab examples (NFS, CIFS, USB),
  restore, security and a failure table (a test checks every reason is explained).

## Decisions that came up while building
- A missing NAS mount makes Docker bind-mount an empty folder on the SD card. The plugin refuses to back up when the folder is on the
  same disk as the database (setting on by default, `st_dev` comparison) and says so.
- The daemon's D-Bus thread must not block on a hung NFS mount: status reads and the folder test run in helper threads with a timeout
  (3 s and 10 s) and fall back to the last listing; backups run in their own thread.
- Reasons shown in the browser are fixed strings; paths and exception text never leave the daemon.
- Restore stays a host command (it must stop the daemon); a test proves archives extract with the restore tool's code.

## Not verified here
- Real `rrdtool` dump/restore round trip (no rrdtool in the dev container; a fake `rrdtool` script is used, CI/Pi has the real one).
- A real NAS mount (permissions as uid 999, `chown` behaviour, `st_dev` difference between the share and the SD card).
- The two browser-based suites need `gi` (CI).
