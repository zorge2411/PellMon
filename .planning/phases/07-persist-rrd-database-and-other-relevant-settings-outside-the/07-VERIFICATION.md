---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
verified: 2026-09-21T00:00:00Z
status: human_needed
score: 12/12 decisions verified (D-08 partial by design, see below)
overrides_applied: 0
gaps: []
human_verification:
  - test: "Build and run on a real Raspberry Pi (arm/v7 image), then `docker compose up -d`"
    expected: "pellmon-init exits 0, both services healthy, data lands in ./pellmon-data owned 999:999"
    why_human: "Smoke test ran on x86_64 Docker Desktop, not arm/v7"
  - test: "Run with real burner and SERIAL_GID set"
    expected: "Scotte serial port opens as uid 999 and values land in rrd.db"
    why_human: "No serial hardware; the smoke daemon ran without a connection"
  - test: "Open the dashboard and the config editor in a browser"
    expected: "Graphs render from persisted RRD. Read-only save error is shown for pellmon.conf"
    why_human: "Only HTTP 200 was checked; the config editor (port 8083) is not in the compose stack"
---

# Phase 7 Verification Report

**Goal:** RRD DB, settings DB and logs persist on the host (`./pellmon-data`, override `PELLMON_DATA_DIR`) with auto ownership, loud failure, config rules, GUI-settings-to-DB rule, scripted backup/restore.
**Status:** human_needed (all automated and smoke checks pass; hardware and browser items remain)

## Decisions

| ID | Status | Evidence |
|----|--------|----------|
| D-01 host folder, default `./pellmon-data`, `PELLMON_DATA_DIR` override | VERIFIED | docker-compose.yml `${PELLMON_DATA_DIR:-./pellmon-data}/data` and `/logs` mounts; .env.example last block. Smoke: with `PELLMON_DATA_DIR=./pd` data appeared in `pd/data` |
| D-02 bind over `/var/lib/pellmon` (RRD + settings DB) and logs | VERIFIED | compose pellmonsrv volumes; smoke: `rrd.db` (11530592 B) and `pellmon_settings.db` present in `pd/data` |
| D-03 `pellmon-run` stays a named volume | VERIFIED | compose `volumes: pellmon-run`, only named volume |
| D-04 web data mount read-only | VERIFIED | pellmonweb `.../data:/var/lib/pellmon:ro` |
| D-05 `pellmon-data/` in .gitignore | VERIFIED | .gitignore last line (`*.db` also present) |
| D-06 one-shot init fixes ownership | VERIFIED | `pellmon-init` `user: root`, chown 999:999. Smoke: init exit 0, `pd/data`, `pd/logs` = 999:999, `depends_on: service_completed_successfully` |
| D-07 loud failure on unusable folder | VERIFIED | pellmonsrv.py:893-925 `check_data_dirs`. Smoke: data mount read-only, init skipped, `exit=1`, message names `/var/lib/pellmon`, rrd.db and settings DB |
| D-08 only conf.d writable, pellmon.conf read-only | PARTIAL (deliberate) | pellmon.conf `:ro` in both services. `conf.d` is `:ro` for pellmonsrv and rw mount for pellmonweb, but not chowned to 999 (WR-03), so it is not actually writable by uid 999, and no editor runs in the stack. Smoke: `config/conf.d` stayed 1000:1000. pellmonconf.py:130-141 maps EROFS/EACCES to a read-only message. Consistently documented in compose comments and DEPLOY-PI.md:153-164 |
| D-09 GUI settings go to settings DB | VERIFIED | Keyval_storage in database.py:151-175 in the data folder; DEPLOY-PI.md:143; pellmon.conf.example comment. File mode 0600 confirmed (smoke `600`) |
| D-10 backup/restore script + docs | VERIFIED | tools/pellmon_backup.py (489 lines), DEPLOY-PI.md ~250-355 |
| D-11 documented manual named-volume migration | VERIFIED | DEPLOY-PI.md:259 "Moving data off the old named volume (one time)" |
| D-12 no web backup button | VERIFIED | none in code; DEPLOY-PI.md:354 says deferred |

Plan-level must_haves were checked through these decisions and the tests below. No plan truth is contradicted. The other deliberate deviations (init has no `build:` and uses `pull_policy: never`; `PELLMON_REQUIRE_DATADIR=1` gate set in compose; uid/gid 999 pinned at Dockerfile:42) are consistent in compose, Dockerfile, tests and docs.

## Test results (run by verifier)

| Command | Result |
|---------|--------|
| full suite, venv-wsl | 332 passed, 10 skipped |
| dbus/gi subset, system python3 | 230 passed |

## Smoke test (scratch copy of HEAD on WSL ext4, project `pmverify`, image `pmverify-img:latest`)

| Step | Observed | Status |
|------|----------|--------|
| clean `up -d --build` | Build succeeded once, init "Exited" 0. First attempt: pellmonsrv crash-looped with `KeyError: 'feeder_time'` in silolevel. **Cause was my scratch prep**: I left `database.conf.in` unconverted. Redone exactly as DEPLOY-PI step 4a, then no error | VERIFIED (after prep fix) |
| health | pellmonsrv and pellmonweb both `(healthy)`; web `200` on :19081 | VERIFIED |
| ownership | `pd/data`, `pd/logs`, files = 999:999; `config/conf.d` stayed 1000:1000; `pellmon_settings.db` 0600, `rrd.db` 0644 | VERIFIED |
| `down -v` then `up -d` | `rrd.db` same size and inode (11530592, 201396), settings DB intact, both healthy | VERIFIED |
| unusable data dir | `exit=1`, message names folder and files | VERIFIED |
| backup `--verbose` | resolved `/var/lib/pellmon/rrd.db`, wrote `pellmon-backup-...tar.gz`, mode 600 | VERIFIED |
| wipe then `restore --yes` | dir empty, then `rrd.db` + `pellmon_settings.db` (0600) restored, 999:999, `rrdtool info` OK | VERIFIED |
| second restore | `rrd.db.pre-restore` and `pellmon_settings.db.pre-restore` created, mode 0600 | VERIFIED |
| corrupt archive restore | tool printed "Compressed file ended before the end-of-stream marker"; `rrd.db` md5 unchanged before and after (`159729ed...`) | VERIFIED (settings DB md5 not readable as non-root; only rrd.db compared) |
| restart pellmonweb | web `200`, both healthy | VERIFIED |

Cleanup: `docker ps -a` and `docker image ls` before showed only `pellmon:latest` and the github-mcp-server image; after, same. `pellmon:latest` untouched. First rm of root-owned scratch dirs failed (container ran as uid 999 and the image was already removed), so I removed `~/pmverify` with `wsl -u root`. Nothing left behind.

## Anti-patterns

Grep for `shell=True|TODO|FIXME|XXX|TBD` over phase files (backup tool, pellmonsrv.py, pellmonconf.py, compose, Dockerfile, DEPLOY-PI.md, phase tests): no matches. No hard-coded secrets found. Tests are non-trivial (332/230 pass, including backup and persistence tests).

## Observations (not gaps)

- Daemon logs `rrdtool` "start should be less than end" errors during the smoke run (WSL clock skew / demo mode). Not related to persistence.
- The failed-restore check compared only `rrd.db` because the settings DB is 0600 and owned by 999.
- `pellmonconf` (port 8083) is not in the compose stack, so the D-08 writable path is untested end to end. This is documented.

## Gaps

None.
