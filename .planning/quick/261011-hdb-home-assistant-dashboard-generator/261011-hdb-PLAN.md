---
phase: quick-261011-hdb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tools/ha_dashboard.py
  - tests/test_ha_dashboard.py
  - config/ha-dashboard.example.yaml
  - DEPLOY-PI.md
  - tests/test_homeassistant_docs.py
  - .github/workflows/ci.yml
  - requirements-dev.txt
autonomous: true
requirements: [QUICK-261011-hdb]
status: done
---

<objective>
Generate a Home Assistant dashboard (Sections view YAML) from the Phase 6/11 entity table, following
`.planning/research/ha-dashboard-design.md` and the approved mockup: burner now, fuel with silo forecast,
heating and water, daily consumption, service, and a separate Controls view.
</objective>

<decisions>
- Stdlib-only generator that imports `entities.ENTITIES`, so the page follows the integration; a test
  fails when an entity is added without a place on the page.
- Entity ids come from a pasted Home Assistant template output (friendly names), matched exactly then by
  suffix, longest name first, per domain. Absent entities are left off.
- Core cards for everything; ApexCharts card only for the silo forecast and the daily consumption chart,
  each with a core `statistics-graph` fallback (`--no-apexcharts`).
- Optional sensors (outside, indoor, flow, feeder counters) off unless `--include`.
- Controls live in a second view (optionally limited with `--admin-user`), not in the main view.
- YAML keys checked against the HA docs (docs repo 3c049c1) and frontend source (3280113) for
  `max_columns`, `column_span`, `visible`.
</decisions>
