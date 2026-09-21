---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
plan: 02
status: complete
requirements: [D-07, D-09]
key-files:
  modified: [src/Pellmonsrv/pellmonsrv.py, src/Pellmonsrv/database.py]
  created: [tests/Pellmonsrv/test_data_dir_check.py, tests/test_data_persistence.py]
---

# Phase 7 Plan 02: Data dir guard and settings DB hardening Summary

`check_data_dirs(conf)` runs in `run()` before any fork or thread: with `PELLMON_REQUIRE_DATADIR=1` an unusable data folder logs an error naming the path and exits 1, otherwise it warns. The settings DB path is now derived from `conf.db` (no `/tmp` fallback via the `nvdb` AttributeError), logfile failures are logged at warning level, and `Keyval_storage` chmods the file 0600.

## Tests
- Baseline: 291 passed, 10 skipped. After: 297 passed, 10 skipped. No regressions.
- Failing-first confirmed: 6 new tests failed before implementation (missing `check_data_dirs`, `/tmp` path, mode 0644).

## Deviations
- Test assertion `'/tmp' not in keyval_db` was wrong because pytest's tmp_path lives under /tmp; changed to `!= '/tmp/pellmon_settings.db'`.
- Edits done with Python scripts preserving CRLF.

## Not verified
- Real Docker run with unwritable mount (manual check in 07-05); tests using dbus/gi under system python3 not run separately (daemon_module stubs cover them in venv-wsl).
