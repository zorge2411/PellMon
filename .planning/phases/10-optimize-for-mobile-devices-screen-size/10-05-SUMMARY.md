---
phase: 10-optimize-for-mobile-devices-screen-size
plan: 05
subsystem: testing
tags: [playwright, mobile, layout, browser-tests]
requires: [10-01, 10-03, 10-04]
provides:
  - Rendered overflow tests A1-A3 (6 pages x 390/768) and 1280 desktop smoke (D-07)
  - Rendered geometry/interaction tests B1-B7, C1-C3, D1-D2, E1-E3
key-files:
  created: [tests/browser/test_mobile_overflow.py, tests/browser/test_mobile_interactions.py]
  modified: [tests/browser/conftest.py]
requirements-completed: [D-02, D-03, D-04, D-05, D-06, D-07]
completed: 2026-09-24
---

# Phase 10 Plan 05: Browser acceptance tests Summary

Twelve overflow cases plus the 1280 desktop smoke, and eleven geometry/interaction tests, written against the UI-SPEC and RESEARCH thresholds. NONE of these browser assertions have been executed: the sandbox cannot call wsl.exe, so the orchestrator must run them in WSL.

## Commits
- 0202009: overflow tests A1-A3 + desktop smoke, wait helpers in conftest
- Task 2 commit: interaction tests (see git log)

## Run command (orchestrator, WSL)
`PELLMON_BROWSER_TESTS=1 PYTHONPATH=src $HOME/pellmon-browser-venv/bin/python -m pytest tests/browser -v -rs --allow-unix-socket`

## NOT executed (all browser assertions)
- test_mobile_overflow.py: test_no_horizontal_overflow x 12 (main, parameters-Overview, settings, consumptionview-consumption, logview-logView, auth-login at 390 and 768), test_desktop_smoke_1280.
- test_mobile_interactions.py: test_main_390_order_and_sizes (B1,B2,B4,B7), test_main_390_events_toggle (B3), test_main_390_graph_tap_targets (B5), test_main_390_navbar (B6), test_parameters_390_pills (C1), test_parameters_390_sections (C2), test_parameters_390_controls (C3), test_settings_390_gallery (D1,D2), test_main_768 (E1), test_parameters_768 (E2), test_settings_768 (E3).

Likely places for threshold mismatches to be fixed by the orchestrator: C1 pill widths/gaps (50% minus 8px is the plan's formula, exact CSS not verified), C3 (clicking `dt` reveals only one `.details` at a time, so the test opens param index 0 (select) then 1 (text form) and requires at least 3 checked controls), B2 image height (SVG object ratio), B6 tap target `.navbar-nav > li > a` including right-aligned list, D1 tile width range, and the desktop smoke using the nearest `[class*=col-]` ancestor for the D-07 columns. No assertion was weakened.

## Local verification (Windows)
- `pytest tests/browser --collect-only`: 21 items collected (13 overflow, 8 harness); interaction file collects 11 (total run includes them).
- Full suite (venv-py3, PYTHONPATH=src): 3 failed, 408 passed, 82 skipped. The 3 failures are the known baseline (test_conf_d_overrides_pellmon_conf, test_every_available_plugin_loads[consumption|silolevel]). Browser tests skip cleanly.
- `grep networkidle|time.sleep|wait_for_timeout tests/browser`: only a docstring mention in conftest.py.

## Screenshots
Written to tests/browser/_shots/ on the WSL run: overflow-<slug>-<width>, desktop-main-1280, desktop-parameters-1280, main-390-order, main-390-events-collapsed/-expanded, main-390-graph-targets, main-390-navbar-closed/-open, parameters-390-pills, parameters-390-sections-closed/-open, parameters-390-controls-0/-1, settings-390-gallery, main-768, parameters-768, settings-768. (Not generated here.)

## Deviations from Plan
- Worktree base differed; sanctioned `git reset --hard 9fcd5b3` performed at startup (clean tree).
- fake_dbus.py was not changed: its canned data (8 tags, 8 R/W items with enum and min/max, 4 commands) already covers the tests.
- No src/ changes were made or needed pending the WSL run.

## Known Stubs
None.

## Self-Check: PASSED
