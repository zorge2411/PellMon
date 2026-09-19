---
phase: 05-security-ci-deployment-hardening
plan: 02
subsystem: ci-docker
tags: [ci, github-actions, docker, docker-compose, healthcheck, pytest]
dependency-graph:
  requires: []
  provides:
    - GitHub Actions CI workflow running pytest and import verification on Ubuntu (OPS-01)
    - Production Docker Compose and Dockerfile healthchecks with service_healthy readiness gate (OPS-03)
    - Automated configuration validation tests for CI workflow and Docker Compose
  affects:
    - .github/workflows/ci.yml
    - docker-compose.yml
    - Dockerfile
    - tests/test_ci_docker_config.py
tech-stack:
  added: []
  patterns:
    - GitHub Actions CI matrix with system D-Bus and GLib packages on Ubuntu runner
    - D-Bus Peer.Ping healthcheck over shared session socket in Docker Compose
    - Docker Compose service_healthy dependency ordering between pellmonweb and pellmonsrv
key-files:
  created:
    - .github/workflows/ci.yml
    - tests/test_ci_docker_config.py
  modified:
    - docker-compose.yml
    - Dockerfile
decisions: [D-03, D-05]
metrics:
  completed: 2026-09-18
---

# Phase 5 Plan 02: CI Workflow & Docker Deployment Hardening Summary

Established automated continuous integration and production Docker deployment healthchecks:
1. Created `.github/workflows/ci.yml` running pytest and import tests on an Ubuntu runner with system D-Bus, GLib, and RRDtool packages on push and pull requests to `master` and `python3-migration` (OPS-01).
2. Hardened `docker-compose.yml` with true service readiness healthchecks (`dbus-send` peer ping for `pellmonsrv` and `curl` HTTP check for `pellmonweb`) and enforced startup ordering with `condition: service_healthy` (OPS-03).
3. Standardized `Dockerfile` readiness healthcheck parameters.
4. Added automated validation test coverage in `tests/test_ci_docker_config.py`.

## What Was Built

### Task 1: Create GitHub Actions CI workflow (.github/workflows/ci.yml) (OPS-01)
- Triggered on `push` and `pull_request` against `master` and `python3-migration`.
- Executed on `ubuntu-latest` with Python 3.11 (`actions/setup-python@v5`).
- Installed system packages required for Linux D-Bus, GLib, and RRDtool:
  `python3-dbus`, `python3-gi`, `python3-gi-cairo`, `gir1.2-glib-2.0`, `librrd-dev`, `rrdtool`, `python3-rrdtool`.
- Installed Python dependencies from `requirements.txt` and testing packages (`pytest`, `pytest-mock`, `pytest-socket`).
- Executed `test-imports.py` and full test suite `pytest tests/ -v`.

### Task 2: Update Docker Compose and Dockerfile healthchecks (OPS-03)
- In `docker-compose.yml`:
  - Replaced process existence check (`pgrep`) with functional D-Bus session bus peer ping:
    `dbus-send --session --address=unix:path=/var/run/pellmon/bus_socket --dest=org.pellmon.int --print-reply /org/pellmon/int org.freedesktop.DBus.Peer.Ping > /dev/null 2>&1 || exit 1`.
  - Configured `pellmonweb` to wait for server readiness using `depends_on.pellmonsrv.condition: service_healthy`.
  - Updated `pellmonweb` healthcheck with `15s` interval, `5s` timeout, `3` retries, and `10s` start period.
- In `Dockerfile`:
  - Verified system packages `curl`, `procps`, and `dbus` are installed.
  - Aligned container `HEALTHCHECK` with standard 15s interval, 5s timeout, and 10s start period probing port 8081.

### Task 3: Add configuration verification tests (tests/test_ci_docker_config.py)
- Created unit tests verifying:
  - `test_github_actions_workflow`: Workflow triggers (push/PR on master and python3-migration), runner environment (ubuntu-latest, Python 3.11), required Linux system packages (D-Bus, GLib, RRDtool), and test execution commands (`pytest tests/`, `test-imports.py`).
  - `test_docker_healthchecks`: D-Bus peer ping test in `pellmonsrv`, `condition: service_healthy` dependency in `pellmonweb`, and HTTP port 8081 probe in `pellmonweb`.
  - `test_dockerfile_healthcheck`: `HEALTHCHECK` probing port 8081.

## Verification Results

1. Task 1 Verification:
```powershell
venv-py3/Scripts/python.exe -c "import os; assert os.path.isfile('.github/workflows/ci.yml'); content = open('.github/workflows/ci.yml').read(); assert 'test-imports.py' in content; assert 'pytest tests/' in content; assert 'python3-dbus' in content"
# Exit 0
```

2. Task 2 Verification:
```powershell
venv-py3/Scripts/python.exe -c "compose = open('docker-compose.yml').read(); assert 'service_healthy' in compose; assert 'dbus-send' in compose or 'org.pellmon.int' in compose; assert 'curl' in compose"
# Exit 0
```

3. Task 3 and Config Test Suite Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/test_ci_docker_config.py -v
# 3 passed in 0.03s
```

4. Full Test Suite Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/ -v
# 102 passed, 8 skipped, 2 warnings in 2.32s
```

## Deviations from Plan

None. Implementation strictly followed D-03, D-05, and plan specifications.

## Commits

- `7229d3d` ci(phase-5): add GitHub Actions CI workflow
- `17cf1e6` feat(phase-5): harden docker healthchecks and dependency ordering
- `d44c88d` test(phase-5): add automated verification for CI and Docker Compose config
