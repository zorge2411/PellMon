---
status: complete
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
source: [07-VERIFICATION.md]
started: 2026-09-21T09:43:42Z
updated: 2026-09-21T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Build and run on a real Raspberry Pi (arm/v7 image), then `docker compose up -d`
expected: pellmon-init exits 0, both services healthy, data lands in ./pellmon-data owned 999:999. Set SERIAL_GID in .env before starting (stat -c %g /dev/ttyUSB0; 46 on the tester's adapter).
result: passed (Pi 3A+, arm/v7 image; stack up, data in pellmon-data owned 999:999; persistence across `docker compose down -v && up -d` confirmed, same inode)

### 2. Run with a real burner and SERIAL_GID set
expected: The Scotte serial port opens as uid 999 (log shows "serial port ok"), the main page shows no "No connection to the burner" banner, and values land in rrd.db under pellmon-data/data.
result: passed (serial port ok as uid 999, real burner values, rrd.db updating)

### 3. Open the dashboard in a browser (and the config editor if you run it separately)
expected: Graphs render from the persisted RRD. The standalone config editor (pellmonconf, port 8083, not part of the compose stack) shows a read-only message when saving pellmon.conf.
result: passed for graphs rendering from the persisted RRD (main, consumption, log pages). Standalone pellmonconf read-only message not exercised (not in the compose stack)

### 4. Backup and restore on the Pi
expected: python3 tools/pellmon_backup.py backup then restore --yes (from the repo root, as documented in DEPLOY-PI.md) restores graphs and settings; `docker compose restart pellmonweb` afterwards brings the web page back.
result: passed (backup, 0600 archive, restore --yes, restart pellmonweb, all services healthy, graphs intact)

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
