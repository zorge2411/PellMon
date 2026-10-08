# Phase 11 seed notes (pre-research)

Captured 2026-10-08 from a code analysis; input for /gsd-research-phase 11.

## How silo days-left works today
- `src/Pellmonsrv/plugins/silolevel/__init__.py`: items `silo_reset_level` (R/W kg), `silo_reset_time`, `silo_level` (R kg), `silo_days_left` (R days).
- Level = reset level minus kg burned, from `rrdtool xport` over `feeder_time * feeder_capacity / 360000`.
- Days left (first match wins): (1) level < 3 weeks of last-week use: linear burn at last week's rate; (2) usage a year ago: replay last year's curve; (3) else last month (or last week x 4) scaled by `month_weights`; no data -> `'365'`; exception -> `'0'`.
- Read path: `graphData()` is cached 300 s; value is a string, `None` until first compute.

## How the HA bridge publishes
- `plugins/homeassistant/entities.py` `ENTITIES` table is the only list; `present_entities()` drops entities whose item is missing.
- States come from `Database.snapshot()` (Database thread polls every item each 2 s) and change callbacks; `None` values are skipped.
- Known minimum change: add `silo_days_left` (d, duration) and `silo_level` (kg, weight) sensors; update hard-coded entity counts in the entity tests (21/20/19, `20 + 2`) and HA docs/tests.

## Research questions
1. Which other numeric items are worth exposing? Candidates seen: `feeder_rpm`, `feeder_rev`, `feeder_rev_capacity`, `feeder_rp6m`, `alarm`, consumption plugin data (JSON bar charts, probably needs a derived daily/total kg number), heatingcircuit, onewire/owfs, openweathermap, NBE items.
2. Per item: unit, device_class/state_class (total_increasing for counters), update frequency, whether `get_text` is cheap on the Database thread.
3. Should `silo_days_left` publish `unknown` instead of `'0'` on error? Should an "empty date" timestamp sensor be added?
4. Do any new entities change the Phase 6 unique-id/topic compatibility rules (D-19)?
