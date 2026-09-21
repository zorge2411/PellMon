---
status: partial
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
source: [07-VERIFICATION.md]
started: 2026-09-21T09:43:42Z
updated: 2026-09-21T09:43:42Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Build and run on a real Raspberry Pi (arm/v7 image), then `docker compose up -d`
expected: pellmon-init exits 0, both services healthy, data lands in ./pellmon-data owned 999:999. Set SERIAL_GID in .env before starting (stat -c %g /dev/ttyUSB0; 46 on the tester's adapter).
result: [pending]

### 2. Run with a real burner and SERIAL_GID set
expected: The Scotte serial port opens as uid 999 (log shows "serial port ok"), the main page shows no "No connection to the burner" banner, and values land in rrd.db under pellmon-data/data.
result: [pending]

### 3. Open the dashboard in a browser (and the config editor if you run it separately)
expected: Graphs render from the persisted RRD. The standalone config editor (pellmonconf, port 8083, not part of the compose stack) shows a read-only message when saving pellmon.conf.
result: [pending]

### 4. Backup and restore on the Pi
expected: python3 tools/pellmon_backup.py backup then restore --yes (from the repo root, as documented in DEPLOY-PI.md) restores graphs and settings; `docker compose restart pellmonweb` afterwards brings the web page back.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
