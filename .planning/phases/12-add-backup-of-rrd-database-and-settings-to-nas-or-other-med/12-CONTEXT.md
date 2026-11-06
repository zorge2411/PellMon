# Phase 12: Add backup of the RRD database and settings to a NAS or other media - Context

**Gathered:** 2026-11-05
**Status:** Ready for planning

<domain>
## Phase Boundary

PellMon backs up its RRD database and settings by itself, on a schedule, to a folder that the user has mounted
on the host (NAS share via NFS/SMB, USB drive, any disk), and keeps a limited number of old copies. It is
configured on a login-protected web page like the Home Assistant and Weather pages.

Today (Phase 7) only a manual host-side CLI exists (`tools/pellmon_backup.py backup|restore`). That tool stays the
way to **restore**; the archive format is unchanged so archives made by the new feature restore with it.

Out of scope: restore from the web GUI, SSH/SFTP/rsync or direct SMB targets, encryption, e-mail on failure,
downloading archives through the web page (they are on the NAS), cloud storage.
</domain>

<decisions>
- **D-01 (destination):** A mounted folder. Compose bind-mounts `${PELLMON_BACKUP_DIR:-./pellmon-backups}` at
  `/backups` in the `pellmonsrv` container. The user mounts the NAS or USB drive on the host and points
  `PELLMON_BACKUP_DIR` at it. The GUI chooses an optional sub-folder below `/backups`; it can never write outside it.
- **D-02 (runs inside the stack):** A new always-loaded daemon plugin `Backup` runs a scheduler thread in `pellmonsrv`
  (which has the RRD, the settings DB, the config and `rrdtool`), so no host cron or extra container is needed.
  It stays idle until enabled on the web page, like HomeAssistant and Openweathermap.
- **D-03 (archive):** Same layout as `tools/pellmon_backup.py` (`rrd.xml`, `pellmon_settings.db`, `config/`, `manifest.json`
  in one `.tar.gz`), file name `pellmon-backup-YYYYmmdd-HHMMSS.tar.gz`, mode 0600 where the medium allows. Written
  as a temporary name in the destination, verified (re-opened and read through), then renamed, so a half-written
  archive never looks complete. Plain, not encrypted.
- **D-04 (retention):** Keep the newest N archives plus the newest archive of each of the last M ISO weeks
  (defaults 14 and 8). Only files named `pellmon-backup-*.tar.gz` are ever deleted. The newest archive is never deleted.
- **D-05 (schedule):** Daily or weekly at a local time (and weekday for weekly). A missed slot (daemon was down) is run once
  after start; a failed run is retried hourly until the next slot. A first backup runs right after enabling.
- **D-06 (web page):** New **Backup** page (login required, same-origin check on POSTs): enable, sub-folder, frequency, time,
  weekday, keep-daily, keep-weekly; **Back up now**, **Test folder**; status line (off / waiting / running / ok / error with
  a stable reason) and the list of archives with size and time.
- **D-07 (errors are visible, never leak):** Reasons are fixed strings (folder missing: is the NAS mounted; folder not writable;
  out of space; rrdtool failed; settings database unreadable; unknown, see log). Paths and exception text are not sent
  to the browser. Failures are logged (they also reach the web log view).
- **D-08 (compatibility):** The archive must be accepted by `pellmon_backup.py restore` (tested). Documentation says: restore stays a
  host command because it must stop the daemon.
- **D-09 (security):** Archives hold password hashes and the MQTT/API secrets. Documented: protect the NAS folder. The web page
  never shows or returns secrets.
</decisions>
