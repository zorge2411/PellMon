# Phase 10 Discussion Log

**Date:** 2026-09-24
**Source:** `/gsd-discuss-phase 10`. For human reference only; not consumed by downstream agents.
See `10-CONTEXT.md` for the canonical decisions.

## Gray areas selected
All four: main page, graph usability, parameters/settings pages, verification.

## Main page on a phone
Options: single column current order; single column diagram-first with events collapsed; compact
header plus tabs. **Chosen:** single column, diagram first, events collapsed. Tabs redesign deferred.

## Graph on a phone
Options: responsive height and bigger tap targets; add touch pan/pinch; minimal fit-width.
**Chosen:** responsive height and bigger tap targets. Touch gestures deferred.

## Parameters and Settings pages
Options: stack controls; stack plus collapsible sections on Parameters; only fix overflow.
**Chosen:** stack controls plus collapsible sections on Parameters; Settings gallery 2 per row.

## Verification
Options: real phone plus structural tests; add automated screenshot checks; real phone only.
**Chosen:** add automated screenshot checks (390px and 768px, fail on horizontal overflow), on top
of structural tests and a real-phone human check.

## Claude-decided (not asked)
- Stay on Bootstrap 3 (framework upgrade is scope creep).
- Design widths 390px and 768px; desktop unchanged.

## Deferred
Touch graph gestures, tabbed phone redesign, PWA, dark mode, Bootstrap upgrade.

## Flagged for research
How to do headless screenshot/overflow checks in CI when the app needs D-Bus for real data.
