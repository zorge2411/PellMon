---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
plan: 01
status: complete
subsystem: docker
tags: [docker-compose, persistence, bind-mount]
requirements: [D-01, D-02, D-03, D-04, D-05, D-06]
key-files:
  modified: [docker-compose.yml, .env.example, .gitignore, tests/test_ci_docker_config.py]
  created: [.dockerignore]
---

# Phase 7 Plan 01: Host-persisted data and pellmon-init Summary

RRD data and logs are now host bind mounts under `${PELLMON_DATA_DIR:-./pellmon-data}`, with a one-shot root `pellmon-init` service that chowns data, logs and conf.d to 999:999 before `pellmonsrv` starts.

## Commits
- 70d81d3 test(07-01): failing tests (5 failed, 6 passed at that point, as intended)
- a2de1ff feat(07-01): compose bind mounts, pellmon-init, env/ignore entries

## Tests
- Baseline (before changes): 285 passed, 10 skipped.
- tests/test_ci_docker_config.py after: 11 passed. `docker compose config -q` returns 0.
- Full suite after: 291 passed, 10 skipped (baseline 285 + 6 new tests), no regressions.

## Deviations
- `.dockerignore` was untracked in the repo, so this commit adds it as a new tracked file (it already contained the previous entries plus `pellmon-data/`).
- PowerShell tool unavailable; WSL commands were run via Git Bash with `MSYS_NO_PATHCONV=1`.
- Edits were made with a Python script preserving CRLF line endings (not sed).

## Not verified
- Real `docker compose up`, chown behaviour and the daemon honouring `PELLMON_REQUIRE_DATADIR=1` (plan 07-02 implements it; manual check in 07-05).

## Self-Check: PASSED
