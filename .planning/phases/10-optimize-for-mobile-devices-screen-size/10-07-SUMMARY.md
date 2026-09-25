---
phase: 10-optimize-for-mobile-devices-screen-size
plan: 07
status: complete
requirements: [D-02, D-06, D-07]
---

# Phase 10 Plan 07: Final checks and real-device verification Summary

Status: complete. Automated gates were run by the orchestrator, the human-verify checkpoint was approved by the user.

## Automated gates (2026-09-24)

- Windows `pytest tests/`: 408 passed, 82 skipped, 3 failed (the known pre-existing baseline:
  `test_backup_script::test_conf_d_overrides_pellmon_conf`,
  `test_plugin_loader::test_every_available_plugin_loads[consumption|silolevel]`).
- WSL Chromium headless shell, `PELLMON_BROWSER_TESTS=1 pytest tests/browser --allow-unix-socket`:
  32 passed.
- PR #22 CI: green, including the mandatory browser step, Playwright install and screenshot upload
  (first real run on ubuntu-latest). Merge triggered release `v2.1.0` (amd64, arm64, arm/v7).

## What the browser tests caught

The structural tests could not see one real defect that the browser layout tests found on their
first run: at 390px the Parameters command buttons stretched to 510px (Bootstrap `.btn-group` is
inline-block and shrinks to its widest child; `.btn` does not wrap), causing sideways scroll and,
through the widened emulated layout viewport, two tap-test timeouts. Fixed with a `command-group`
hook class (no `:has()`, older phones must work) making the group block-level and wrapping the
button text on phones. A Settings tile-width lower bound was also loosened from 150 to 140px (real
width about 150; the two-column assertion is unchanged). Commit `efa4cc7`.

## Human verification (D-06c, D-07)

Operator deployed `v2.1.0` on the Pi (pull, up, restart of both containers so the cached plugin
chart templates reload) and checked the real pages on a phone via `https://stoker.schoeler.pro/`
and the desktop layout. Reply: **"approved"** (2026-09-25).

## Deviations

- The plan-01 socket spike could not run in the executor sandbox (wsl.exe blocked); the
  orchestrator ran it and recorded the result in 10-01-SUMMARY.md (`--allow-unix-socket` works).
- Plan 10-05's first executor died on an API spend limit before writing anything; retried cleanly.
- Executors could not run the browser tests; the orchestrator ran and fixed them in WSL.
