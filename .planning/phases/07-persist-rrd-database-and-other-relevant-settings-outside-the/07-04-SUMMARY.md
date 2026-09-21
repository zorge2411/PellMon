---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
plan: 04
status: complete
requirements: [D-10]
key-files:
  created: [tools/pellmon_backup.py, tests/test_backup_script.py]
---

# Phase 7 Plan 04: Backup/restore tool Summary

`tools/pellmon_backup.py` backs up and restores the RRD (as an XML dump), the settings DB (SQLite backup API) and the config folder in one 0600 tar.gz, in docker-compose mode or `--local`.

## Commits
- 50f8948 test(07-04): failing tests (collection error on the missing tool, as intended)
- f0e1618 feat(07-04): tool, both local and docker modes

## Tests
Baseline before: 303 passed, 10 skipped. After: 313 passed, 10 skipped (10 new tests, no regressions). rrdtool exists in WSL Debian (/usr/bin/rrdtool), so the local round-trip test actually ran and passed.

## Deviations
- Tasks 2 and 3 were implemented in one file write and committed together (no NotImplementedError stubs were needed).
- `backup` does not delete a pre-existing `--out` file on failure (avoids destroying a user's earlier archive); on the missing-database path nothing is written.
- `_run` gained a `capture` flag (used for `rrdtool --version`).

## Not verified
- Docker mode was verified only with a faked `_run` (argv assertions). No real `docker compose` backup/wipe/restore was run (manual step in plan 07-05).
- Manual `--local` run from the repo root resolved the RRD path to `/var/lib/pellmon/rrd.db` via the host conf.d fallback, then failed as expected because that file does not exist on this machine.
