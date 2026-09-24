---
phase: 10-optimize-for-mobile-devices-screen-size
plan: 06
subsystem: ci
tags: [ci, playwright, github-actions, testing]
requires: [10-01]
provides: [mandatory-browser-layout-ci-step]
affects: [.github/workflows/ci.yml, tests/test_ci_docker_config.py, tests/README.md, .gitignore]
key-files:
  modified:
    - .github/workflows/ci.yml
    - tests/test_ci_docker_config.py
    - tests/README.md
    - .gitignore
decisions:
  - "Browser run is a step of the existing test job, so publish (needs: test) is blocked by layout failures with no guard edits"
  - "Uses --allow-unix-socket (Plan 01 spike result) as a CLI flag; pytest.ini keeps --disable-socket"
metrics:
  tasks: 2
  completed: 2026-09-24
---

# Phase 10 Plan 06: Mandatory browser layout tests in CI Summary

CI test job now installs Playwright Chromium, runs `pytest tests/browser -v -rs --allow-unix-socket` with `PELLMON_BROWSER_TESTS: "1"`, and uploads layout screenshots (`if: always()`, upload-artifact@v4, 7-day retention).

## Tasks

1. Guard test `test_ci_runs_mandatory_browser_layout_tests` (RED first), then three steps added to the `test` job. Commit 363c1cf.
2. `tests/README.md` section "Headless-browser layout tests (Phase 10)" and `.gitignore` entry for `tests/browser/_shots/`.

## Verification

- tests/test_ci_docker_config.py: 19 passed (existing tests untouched, only additions).
- Full suite on Windows: 3 failed (known baseline: test_backup_script::test_conf_d_overrides_pellmon_conf, test_plugin_loader consumption and silolevel), 391 passed, 58 skipped.
- YAML parse check skipped: PyYAML is not installed in venv-py3. The structure is validated by the guard tests (spaces only, step ordering).

## Deviations from Plan

None. The worktree base differed from the expected commit, so it was reset to a21f97a per the startup check.

## Known Stubs

None.

## Self-Check: PASSED
