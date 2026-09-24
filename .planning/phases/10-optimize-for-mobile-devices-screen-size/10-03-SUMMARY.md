---
phase: 10-optimize-for-mobile-devices-screen-size
plan: 03
subsystem: ui
tags: [mako, bootstrap3, responsive, mobile, a11y]
requires: [10-02]
provides:
  - Responsive dashboard grid (col-xs-12 col-md-N, integer N)
  - Collapsible events widget with delegated toggle
  - CSS-sized graph and six plugin chart sources
affects: [10-05, 10-07]
tech-stack:
  added: []
  patterns: [delegated jQuery handler with .text(), CSS-class sizing instead of inline height]
key-files:
  created: [tests/Pellmonweb/test_mobile_dashboard.py]
  modified:
    - src/Pellmonweb/html/index.html
    - src/Pellmonweb/html/events
    - src/Pellmonweb/html/graph
    - src/Pellmonweb/html/layout.html
    - src/Pellmonweb/html/consumption.html
    - src/Pellmonweb/media/js/index.js
    - src/Pellmonsrv/plugins/consumption/__init__.py
    - src/Pellmonsrv/plugins/silolevel/__init__.py
    - src/Pellmonsrv/plugins/consumption/templates/consumption24h
    - src/Pellmonsrv/plugins/consumption/templates/consumption7d
    - src/Pellmonsrv/plugins/consumption/templates/consumption8w
    - src/Pellmonsrv/plugins/consumption/templates/consumption1y
key-decisions:
  - "events toggle aria-controls points at #events-wrap (the element whose state changes)"
  - "navbar aria-expanded sync lives in layout.html so it works on every page"
requirements-completed: [D-01, D-03, D-04, D-06, D-07]
metrics:
  completed: 2026-09-24
---

# Phase 10 Plan 03: Responsive Dashboard Markup Summary

Fixed the Python 3 `col-md-6.0` column bug (`12 // len(row)`), made the dashboard single-column on phones, added a collapsible events widget, and moved all chart heights from inline 400px to CSS classes.

## Tasks

1. Dashboard grid, events toggle, graph controls, navbar aria - commit 4100f5d
2. CSS-sized charts in six plugin sources, stacking Consumption page - commit abd5875

## Deviations from Plan

None. Task 1 commit includes the Task 2 tests (single test file written up front for RED), so that commit has 3 intentionally failing tests until abd5875.

## Deployment note

Plugin templates are served by the daemon over D-Bus and cached by the web process (RESEARCH Pitfall 9): both containers must be recreated to pick up the chart class change.

## Verification

Full suite (venv-py3, PYTHONPATH=src): 400 passed, 58 skipped, 3 failed - exactly the known baseline (test_conf_d_overrides_pellmon_conf, test_every_available_plugin_loads[consumption|silolevel]). Browser-level checks skipped locally by design.

## Known Stubs

None.

## Self-Check: PASSED
