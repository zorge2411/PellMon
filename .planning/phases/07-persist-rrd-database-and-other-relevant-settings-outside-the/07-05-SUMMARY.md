---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
plan: 05
status: complete
requirements: [D-01, D-05, D-08, D-10, D-11, D-12]
key-files:
  modified: [DEPLOY-PI.md, HARDWARE-BRINGUP.md, config/pellmon.conf.example, tests/test_ci_docker_config.py]
---

# Phase 7 Plan 05: Docs, example config and real smoke test

Documented the host data folder, init ownership (sudo for conf.d edits), backup/restore run from the repo root, and the one-time named-volume copy; removed the conflicting `database =` from `pellmon.conf.example`; ran a real docker compose smoke test on WSL ext4.

## Commits
- 0fc649b test(07-05): failing doc checks
- b66d09a docs(07-05): docs and conf example
- 746d5a6 docs(07-05): note pellmonweb restart needed after restore

## Tests
Baseline before Task 2 commit (Task 2 docs present, uncommitted): 315 passed, 10 skipped. Prior baseline 313 passed, 10 skipped (the 2 new Task 1 tests now pass). No regressions.

## Review of the interrupted docs
Checked against 07-05-PLAN and the tool's argparse (`--config`, `--host-config-dir`, `--verbose`, `--yes`, `--out`). All correct; no fixes needed. One addition after the smoke test: a sentence that `docker compose restart pellmonweb` is needed after a restore.

## Smoke test (WSL Debian ext4, `~/pmsmoke`, project `pmsmoke`, ports 18081/18082, image tagged `pmsmoke-img` via sed on the scratch compose file so the existing `pellmon:latest` was not overwritten)

| Step | Result |
|---|---|
| Image build (amd64) | verified (first parallel build failed with "image already exists" tag race between two build targets; second `build pellmonsrv` succeeded) |
| pellmon-init exits 0; srv and web healthy | verified: `Exited (0)`, srv/web `(healthy)` |
| data/logs owned 999:999; rrd.db, pellmon_settings.db present | verified (`999 999`) |
| settings DB mode 0600 | verified (`600`) |
| `down -v` then `up -d` keeps data | verified (rrd.db 11530592 bytes before/after; mtime advanced only after daemon restart polling) |
| Loud failure with read-only data folder (docker run, init skipped, PELLMON_REQUIRE_DATADIR=1) | verified: `pellmonsrv: data directory /var/lib/pellmon, .../rrd.db, .../pellmon_settings.db is not writable by uid 999...`, exit code 1 (an earlier run showing exit 0 was my shell pipe artefact, rerun without pipes gave exit=1). Done with `:ro` mount, not `chmod 500`, because sudo needs a password |
| backup `--verbose` resolved path | verified: `conf.d: config_dir /etc/pellmon/conf.d not on host, using .../config/conf.d`, `effective database: /var/lib/pellmon/rrd.db` |
| archive mode | verified `-rw-------` |
| wipe (as root in container), restore `--yes` | verified: files back, settings DB 0600 owned 999:999 |
| `rrdtool info` after restore | verified: filename `/var/lib/pellmon/rrd.db`, step 30, DS defs present |
| Web serves after restore | partly: 500 "DbusNotConnected: server not running" until `docker compose restart pellmonweb`, then 200. Cause: restore restarts the daemon, which recreates the D-Bus socket. Pre-existing architecture; documented in DEPLOY-PI.md, tool not changed |
| Negative no-guess (`--config` with only `[conf]`) | verified: exit 1, `error: no 'database' value found in /tmp/empty.conf or <no conf.d dir found>`, no archive created |
| pellmonweb: touch pellmon.conf fails, conf.d writable | verified: `Permission denied` (not "Read-only file system" wording), conf.d touch succeeded and was removed |
| D-08 editor message | not run (editor not in compose; covered by 07-03 unit tests) |
| Web UI graphs in browser | NOT RUN (only curl HTTP 200 after web restart) |

Cleanup: `down -v --remove-orphans`, `pmsmoke-img` removed, scratch copy removed (root cleanup via a temporary `debian:bookworm-slim` pull, also removed). `docker ps -a` empty and `docker image ls` (github-mcp-server, pellmon:latest) identical before and after. Note: pre-existing `pellmon:latest` is an arm/v7 image and cannot run on this host.

## Deviations
- Rule 3: used `pmsmoke-img` tag and container names to avoid touching the existing image.
- Extra doc sentence about restarting pellmonweb after restore.

## Not verified
Real burner hardware; browser rendering; Pi/arm64 build; D-08 message in a running editor.
