# Phase 11: Add silo days-left and additional numeric sensors to Home Assistant - Research

**Researched:** 2026-10-08
**Domain:** extending the Phase 6 MQTT discovery entity table (`plugins/homeassistant/entities.py`)
**Confidence:** HIGH on code facts (read from source); MEDIUM on which items matter to the user (needs a decision, see Open Questions)

## Summary

The bridge is data-driven: one `ENTITIES` tuple, filtered per connected burner by `present_entities(db.keys())`, with states read from `Database.snapshot()` (filled by the 2 s Database thread) and pushed on change plus a periodic refresh. Adding a numeric sensor is one `_s(...)` row. The hard parts are not the rows: they are (1) items whose value is expensive or non-numeric, (2) choosing device/state classes so HA statistics behave, (3) the hard-coded entity counts in tests/docs, and (4) the silo estimate's failure value.

## Findings

### Silo (the original ask)
- `silo_days_left` (days) and `silo_level` (kg) exist only when the `silolevel` plugin is enabled and activates (it raises at activate if `feeder_time`/`feeder_capacity` are not in the RRD item map).
- Both are `Getsetitem` getters that call `graphData()`: several `rrdtool` subprocesses, cached 300 s. Cost is paid on the Database thread at most once per 5 min; acceptable, but the first poll after start blocks that thread while rrdtool runs.
- Values are strings. `silo_days_left` is `None` until first compute (bridge skips `None`), `'365'` with no consumption data, `'0'` when the prediction raises. `'0'` reads as "empty today" in HA. Recommend: on exception set `None`/leave previous value, log once.
- Estimates jump when the method switches (last-week vs last-year vs last-month); not a bridge problem but worth a note in docs.

### Candidate additional numbers

Source: `scottecom/descriptions.py`, `Scotteprotocol/datamap.py` (version tuples), plugin item lists.

| Item | Unit | Source / availability | HA mapping suggestion | Verdict |
|------|------|-----------------------|-----------------------|---------|
| `silo_days_left` | d | silolevel plugin | `duration`, `measurement` | Include (required) |
| `silo_level` | kg | silolevel plugin | `weight`, `measurement` | Include (required) |
| `magazine_content` | kg | Scotte datamap 6.03+, R/W param (Z05) | `weight`, `measurement` | Include if present; value is a burner-side calc |
| `boiler_return_temp` | °C | Scotte 6.03+ | `temperature` | Include |
| `hotwater_temp` | °C | Scotte 6.03+ | `temperature` | Include |
| `outside_temp` | °C | Scotte 6.03+ | `temperature` | Include (note: owm/onewire may duplicate) |
| `indoor_temp` | °C | Scotte 6.03+ | `temperature` | Include |
| `flow` | l/s | Scotte 6.03+ | no standard class; `measurement` | Include, low value |
| `oxygen_desired` | % | Scotte all versions | none | Include (pairs with existing Oxygen Level) |
| `ignition_count` | times | Scotte 4.99+ | `total_increasing` | Include |
| `ignition_time` | s | Scotte all | `duration`, `total_increasing` | Include |
| `motor_time` / `el_time` | s | Scotte all | `duration`, `total_increasing` | Maybe: service-interval use |
| `alarm` | text | Scotte / pelletcalc state tracker | plain sensor (text) | Include: the useful "why is it stopped" signal; a state string, not a number |
| `feeder_rev`, `feeder_rpm`, `feeder_rev_capacity`, `feeder_rp6m` | various | pelletcalc counter mode (non-Scotte feeders) | counter `total_increasing` | Skip unless pelletcalc users ask; diagnostic only |
| `consumptionData24h/7d/8w/1y` | JSON bar charts | consumption plugin | NOT directly usable | Needs a derived scalar (kg burned today / this week) added to the plugin first; separate decision |
| `controller_online`, `controller_IP` | 0/1, text | NBE | out of scope (NBE over MQTT excluded in Phase 6) | Skip |
| `onewire`/`owfs`/`raspberrygpio`/`heatingcircuit`/`openweathermap`/`customalarms`/`calculate` items | various | user-defined names, not a fixed table | cannot go in a static `ENTITIES` table | Out of scope (Phase 6 excluded a general plugin bridge) |

Writable numbers beyond the existing 10 (all Scotte params with min/max in the datamap) such as `hotwater_temp_set`, `blower_*`, `oxygen_*` are possible but widen the command surface that Phase 6 deliberately limited. Not recommended without an explicit decision.

### Constraints inherited from Phase 6
- D-01/D-03: topic layout, device identifiers and unique IDs are fixed; new entities only add `object_id`s, they must not rename any. `uid_prefix`/`node_id` come from settings.
- D-05: entities are published only when the item exists (`present_entities`), so version-dependent items (6.03+, 4.99+) are safe.
- Phase 6 fixed the list at a known size ("same entities as the existing device"). Extending it is a conscious scope change; record it in 11-CONTEXT.md.
- Stale retained configs: when an item disappears `_remove_stale_config` clears it; confirm it handles newly added ids on upgrade (it should, verify in a test).

### Technical details for planning
- Row format: `_s(name, object_id, item, unit, device_class, state_class)`. HA rejects some unit/device_class combos (e.g. `duration` accepts `d,h,min,s,ms`; `weight` accepts `kg,g,...`; `total_increasing` only with numeric states). Text sensors (`alarm`, `mode`) must have no unit, device_class or state_class.
- Counters (`ignition_count`, `ignition_time`, motor/el time) use `state_class: total_increasing`; they reset on burner counter reset (`reset_ignition`), which HA handles as a new cycle.
- States are published as plain strings; non-numeric values (`'-'`, empty, `'None'`) on a numeric sensor make HA log errors. The bridge only skips Python `None`. Add numeric guard for numeric entities (skip or publish nothing when `float()` fails) unless it already exists; check `_state_value`.
- Tests to update: `tests/Pellmonsrv/plugins/test_homeassistant_entities.py` hard-codes 21 / 20 / 19 / `20 + 2` and "12 command entities"; the HA docs page and `test_homeassistant_docs.py`, plus any entity table in `tests/Pellmonweb/test_homeassistant_*` and browser tests (grep `Burner Mode`). Prefer deriving counts from `ENTITIES` instead of new literals.
- `Database.get_text` is called from the Database thread for every item every 2 s; new Scotte items are cached protocol reads (as existing ones), silo items are the only expensive one.

## Recommended scope for planning
1. Silo: `silo_days_left`, `silo_level`; change error value from `'0'` to unknown.
2. Scotte read-only numbers: `magazine_content`, `boiler_return_temp`, `hotwater_temp`, `outside_temp`, `indoor_temp`, `oxygen_desired`, `ignition_count`, `ignition_time`, plus text `alarm`.
3. Numeric guard in the bridge for non-numeric states.
4. Test/doc updates with derived counts.
5. Deferred: consumption scalar sensors, extra writable numbers, plugin-defined items.

## Open Questions (need user decision before planning)
1. Which Scotte version is the real burner (affects whether the 6.03+/4.99+ items will appear at all)?
2. Include `flow`, `motor_time`, `el_time`, pelletcalc feeder counters, or keep to the list above?
3. Do you want a consumption scalar (kg today / week) as a new plugin item plus HA sensor in this phase?
4. Publish `silo_days_left` as days (integer) only, or also an "empty date" timestamp sensor?
5. Any writable extras (e.g. `hotwater_temp_set`)?

## Sources
- Code read: `plugins/silolevel/__init__.py`, `plugins/homeassistant/{entities,bridge}.py`, `plugins/scottecom/descriptions.py`, `Scotteprotocol/datamap.py`, `plugins/pelletcalc`, `consumption`, `nbecom`, `pellmonsrv.py` Database thread.
- `.planning/phases/06-*/06-CONTEXT.md` (D-01..D-19).
- Not verified: HA device-class/unit compatibility tables were not fetched in this session; confirm against current Home Assistant MQTT sensor docs before implementing.
