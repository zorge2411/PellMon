# Phase 11: Add silo days-left and additional numeric sensors to Home Assistant - Context

**Gathered:** 2026-10-11
**Status:** Ready for planning (writable-extras list needs one-line confirmation, see D-08)

<domain>
## Phase Boundary

Extend the Phase 6 Home Assistant MQTT device with the pellet silo estimate and further PellMon
items, keeping every existing topic, unique id and entity unchanged. Burner is a Scotte, chip
version **6.34**, so all version-gated items (>= 4.99, >= 6.03) exist; `oxygen_mid` (6.50) does not.

In scope: new `ENTITIES` rows, one new derived consumption item in the consumption plugin, an
"empty date" value, a numeric-state guard in the bridge, silolevel error value, tests, docs.
Out of scope: NBE items, plugin-defined/user-named items (1-Wire, GPIO, calculate, customalarms,
heatingcircuit, openweathermap), burner ON/OFF (Phase 6 D-07), blower/oxygen tuning writes.
</domain>

<decisions>
- **D-01 (silo):** Add sensors `silo_days_left` (d, duration, measurement) and `silo_level`
  (kg, weight, measurement). Published only when the silolevel plugin is active.
- **D-02 (empty date):** Add a timestamp sensor (`device_class: timestamp`) = now + `silo_days_left`
  days, as a new item in the silolevel plugin (e.g. `silo_empty_date`, ISO 8601 with offset).
  Unknown while days-left is unknown.
- **D-03 (silo error value):** On prediction failure `silo_days_left` becomes unknown (None, last
  good value not republished as `0`), logged once with the correct level. `'365'` (no data) stays
  but is documented.
- **D-04 (Scotte read-only sensors, all present on 6.34):** `magazine_content` (kg), `boiler_return_temp`,
  `hotwater_temp`, `outside_temp`, `indoor_temp` (degC), `flow` (l/s), `oxygen_desired` (%),
  `ignition_count` and `ignition_time` (s), `motor_time` and `el_time` (s; `total_increasing`
  for the counters), and text sensor `alarm` (no unit/class).
- **D-05 (pelletcalc feeder counters):** `feeder_rev` (total_increasing), `feeder_rpm`,
  `feeder_rp6m`, `feeder_rev_capacity`; published only when the pelletcalc counter mode is active.
- **D-06 (consumption scalar):** Add derived numeric items to the consumption plugin
  (kg burned today / last 7 days / this calendar month; names decided in planning) computed from the
  existing RRD data the bar charts use, plus HA sensors (`weight`, kg, `measurement`; plain
  measurement not total_increasing because the windows roll). Must not make the 2 s Database thread
  slow: cache like silolevel (>= 300 s).
- **D-07 (bridge guard):** For numeric entities, publish only values that parse as a finite float;
  skip `''`, `'-'`, `'None'`, `'nan'`. Text sensors (`mode`, `alarm`) unchanged. Existing entities
  keep today's behaviour except for this guard.
- **D-08 (writable extras, proposed, confirm):** New numbers, all behind the existing "Allow commands"
  switch and Phase 6 rate-limit/readback: `hotwater_temp_set` (0-80), `hotwater_temp_diff` (0-20),
  `magazine_content` (0-9999 kg, set after refuelling), `silo_reset_level` (0-50000 kg, the
  "I refilled" action; plugin stamps `silo_reset_time`). Ranges are intersected with the item's own
  min/max as in Phase 6 D-02. Blower, oxygen and regulator settings are NOT exposed.
- **D-09 (compatibility):** No existing `object_id`, unique id, topic or name changes (Phase 6 D-01/D-03/D-19).
  New entities appear on upgrade without user action; if their item vanishes the retained config is
  cleared. Commands off => the new numbers are removed like the existing ones.
- **D-10 (tests/docs):** Replace hard-coded entity counts in the entity/docs/page/browser tests with
  values derived from `ENTITIES`; document the new entities, the silo semantics and the HA unit
  choices in the HA docs page. Verify device_class/unit pairs against current HA MQTT docs during planning.
</decisions>

<canonical_refs>
- `.planning/phases/06-*/06-CONTEXT.md` (D-01..D-19) and `11-RESEARCH.md`, `11-SEED.md`
- `src/Pellmonsrv/plugins/homeassistant/{entities,bridge}.py`
- `src/Pellmonsrv/plugins/silolevel/__init__.py`, `consumption/__init__.py`, `pelletcalc/__init__.py`
- `src/Scotteprotocol/datamap.py` (version-gated items and param ranges)
</canonical_refs>
