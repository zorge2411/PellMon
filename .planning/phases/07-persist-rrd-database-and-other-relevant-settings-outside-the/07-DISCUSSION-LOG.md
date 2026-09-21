# Phase 7: Persist RRD database and other relevant settings outside the Docker container - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-21
**Phase:** 7-persist-rrd-database-and-other-relevant-settings-outside-the
**Areas discussed:** Where the data lives on the host, Ownership and first start, Config: read-only or editable from the web, Backup/restore and moving old data

---

## Where the data lives on the host

| Question | Options | Selected |
|----------|---------|----------|
| Location | Folder next to compose file, overridable / Fixed system path like /var/lib/pellmon / Keep Docker named volumes | Folder next to the compose file, overridable |
| Scope | RRD, settings database and logs / RRD and settings database only | RRD, settings database and logs |

**Notes:** The repo's `./data` is already used by build files copied into the image, so the folder is `./pellmon-data`.

---

## Ownership and first start

| Question | Options | Selected |
|----------|---------|----------|
| Ownership | Automatic one-shot init step in compose / Documented manual chown / Run containers as host user | Automatic one-shot init step |
| Unusable data folder | Fail loudly with a clear message / Fall back to temp folder with a warning | Fail loudly |

---

## Config: read-only or editable from the web

| Question | Options | Selected |
|----------|---------|----------|
| Config writability | Only conf.d writable, pellmon.conf read-only / All of config/ writable / Keep read-only | Only conf.d writable |
| Storage rule for GUI settings | Settings database / GUI writes back to config files | Settings database |

**Notes:** The rule applies project-wide (Phases 6 and 8).

---

## Backup, restore and moving old data

| Question | Options | Selected |
|----------|---------|----------|
| Backup | Script plus docs / Docs only / Web GUI backup button | Script plus docs |
| Old named-volume data | Documented one-time copy / Automatic migration / Start fresh | Documented one-time copy |

**Notes:** RRD files are not portable across machine types, so backups use `rrdtool dump`/`restore`.

---

## Claude's Discretion

- Init container image and compose syntax; backup script language/location/format; folder layout and permission bits; how the settings DB location is configured; test approach.

## Deferred Ideas

- Web GUI backup button; automatic volume migration; log rotation and RRD retention; Windows/WSL data layout; GUI forms replacing raw config editing.
