# Home Assistant dashboard for PellMon: research and design

**Researched:** 2026-10-11
**Inputs:** current HA docs (`home-assistant/home-assistant.io` at 3c049c1, 2026-10-11), ApexCharts card README/changelog (v2.2.3, last release 2025-08-21), PellMon `entities.py` and Scotte enumerations. Answers from the user interview: core cards plus a few HACS cards, responsive for phone and desktop, "balanced hero + detail", full controls including silo fill.

## 1. What the platform can do now (and what that means)

**Sections view is the right base.** It lays cards on a grid, supports section headings with entity badges, per-section background and theme, per-card resizing (`grid_options`), and visibility conditions by user, screen size, time or entity state. One view reflows from phone (1 column) to desktop (up to the max columns you set), so one dashboard serves both screens.

**The tile card does most of the work natively.** Its `features` cover exactly the PellMon shapes:
- `bar-gauge` (numeric sensor as a bar, min/max) for power %, silo level, oxygen.
- `trend-graph` (`hours_to_show`, `detail`) for sparklines inside the tile for temperatures.
- `numeric-input` (`slider` or `buttons`) for every `number` entity (setpoints, silo fill).
- `button` for `button` entities (reset alarm / reset ignition).
- `state_content` can show several things in the subtitle, and timestamp sensors render as relative time ("in 42 days") without templating.

**Other core cards worth using:** `gauge` (needle + coloured `segments`) for boiler temperature and days left; `statistics-graph` (`stat_types: change`, `period: day`) for daily deltas of `total_increasing` counters; `history-graph` for multi-sensor temperature curves; `heading` with entity badges as section headers; `conditional`/visibility for the alarm banner; `markdown` with templates for a one-line status sentence.

**Where core falls short (the reason for any HACS card):**
- Static `min`/`max` everywhere (gauge, bar-gauge): the silo gauge needs the silo capacity as a number.
- No forecast or projection line, no "now" marker, no per-day aggregation of a rolling value, no threshold colouring of a line.
- ApexCharts card covers all of that (`group_by` with `func: max/diff/delta`, `span.start: day`, `statistics` for long-term data, `data_generator` for a projected line, `now` marker, multi y-axis, `color_threshold` (experimental), `section_mode: true` + `grid_options` to sit on the sections grid).

**Risks to note**
- ApexCharts card v2.2.3 is from August 2025 (no release in 14 months at research time). It works in sections view, but it is a single-maintainer custom card; keep every ApexCharts card optional so the page degrades to a core card.
- Core cards show an error for an entity that does not exist (e.g. pelletcalc counters, chip-version-gated items), so the page must be generated from the entities that exist rather than hand-written for all 47.
- Long-term statistics only exist for sensors with a `state_class`; all numeric PellMon sensors have one except Light and Oxygen (no state class, so no statistics graph for them: use history-graph).

## 2. Entity inventory (47)

| Group | Sensors | Numbers / buttons |
|-------|---------|--------------------|
| Burner | Burner Mode (text), Alarm (text; `ok` or one of 9 alarm texts), Power %, Power kW, Feeder Time | Reset Alarm, Reset Ignition |
| Temperatures | Boiler, Chute, Smoke, Boiler Return, Hot Water, Outside, Indoor | Boiler Temp Setpoint, Boiler Temp Minimum, Boiler Diff Down/Up, Hot Water Setpoint, Hot Water Diff |
| Combustion | Oxygen, Desired Oxygen, Light (LDR), Water Flow | Chimney Draught |
| Fuel | Silo Days Left, Silo Level, Silo Empty Date, Magazine Content, Consumption Today / 7 Days / This Month | Silo Fill Level, Set Magazine Content, Feeder Capacity |
| Power limits and cleaning | | Min Power, Max Power, Cleaning Interval, Cleaning Time |
| Service | Ignition Count, Ignition Time, Motor Time, Electricity Time | |
| Feeder (pelletcalc counter mode, optional) | Feeder Revolutions, Feeder Speed, Revs per 6 min, Pellets per Revolution | |

Mode values (Scotte): Waiting, Starting 1/2, Running, Paused, Making hotwater, Stopped, Summer stop, Shut off, Running on battery, and several `Error - ...` strings. Alarm `ok` means no alarm.

## 3. Design

**Principles:** three levels of hierarchy (hero, section, detail); colour only carries meaning (green running, blue idle/starting, orange attention, red alarm); one unit style; no duplicated data; charts only where trend matters; destructive or rare controls (resets, fill) are tucked in a Controls section.

**View: one Sections view, max 3 columns.**

```
┌ Header badges: Mode · Boiler °C · Silo days left ───────────────────┐
│ [ALARM BANNER, visible only when alarm != ok]                       │
├─ Burner now ───────────┬─ Fuel ───────────────┬─ Heating & water ───┤
│ Power tile (bar-gauge) │ Silo days-left gauge │ Boiler gauge        │
│ Power kW + Feeder time │ Silo level (bar)     │ Return / hot water  │
│ Boiler/Chute/Smoke     │ Empty date (relative)│ Outside / indoor    │
│  tiles w/ trend graph  │ Consumption today,7d,│ Flow                │
│ Oxygen vs desired      │  month (3 tiles)     │ Temps history graph │
├─ Silo history + forecast (full width, ApexCharts) ──────────────────┤
├─ Daily consumption (bars) ──────────┬─ Burner runtime (changes) ────┤
├─ Controls (admin only) ─────────────┴───────────────────────────────┤
│ numeric-input tiles: setpoints, power limits, cleaning, hot water,   │
│ chimney draught, feeder capacity, magazine content, Silo Fill Level  │
│ buttons: Reset Alarm, Reset Ignition (with confirmation)             │
├─ Service ────────────────────────────────────────────────────────────┤
│ Ignition count/time, Motor time, Electricity time, Light, feeder     │
│ counters (only if present)                                           │
└──────────────────────────────────────────────────────────────────────┘
```

**Signature elements**
1. *Silo forecast chart:* ApexCharts area of `silo_level` from long-term statistics (`span` last 60 days) plus a dashed projection from "now" to 0 at the `silo_empty_date` using `data_generator` (two points), with a `now` marker. This is the single most "designed" element and the reason ApexCharts is worth it.
2. *Days-left gauge:* needle gauge with `segments` red under 7, orange under 21, green above; shown next to the empty date as a relative time.
3. *Daily consumption:* column chart, `consumption_today` grouped per day with `func: max` (the rolling value resets at midnight, so the daily max is the daily total).
4. *Alarm banner:* a conditional card, hidden when alarm is `ok`, red tile with the alarm text and the Reset Alarm button.
5. *Tile colour by state:* boiler/chute/smoke tiles coloured by threshold using the setpoint; mode tile icon and colour mapped from the mode text with a small template.

**Mobile vs desktop:** sections reflow to one column; hero row first on mobile; wide ApexCharts hidden below a screen-width condition and replaced by the tile trend graphs; Controls and Service sections collapsed behind headings (tap action) on mobile.

**Safety:** numbers only work with "Allow commands" on in PellMon; the page should still confirm Reset Alarm / Reset Ignition (`tap_action` with `confirmation`) and gate the Controls section to admin users via a visibility condition.

## 4. Delivery options

| Option | What | Verdict |
|--------|------|---------|
| A | Hand-written YAML in the repo | Fast, but breaks on absent entities and drifts from the entity table |
| B (recommended) | `tools/ha_dashboard.py` generates the YAML from `ENTITIES`, takes the user's real entity ids, omits absent entities, switches ApexCharts cards to core fallbacks with a flag | Stays in sync, testable (golden YAML, every referenced id exists, no entity used twice by accident) |
| C | Bundle as a Home Assistant blueprint or HACS dashboard | Not possible for dashboards via MQTT discovery; out of scope |

## 5. Open questions for the user (blocking the build)
1. **Entity ids.** The MQTT payloads carry names but no `object_id`, and the device was taken over, so the real ids are unknown. Needed: the list of ids (Developer tools > Template: `{% for e in integration_entities('mqtt') %}{{ e }} | {{ state_attr(e, 'friendly_name') }}{% endfor %}`).
2. **Silo capacity (kg)** for the silo gauge/bar max.
3. **Which optional sensors are physically connected** (return, hot water, outside, indoor, flow, pelletcalc counters), so the page does not show dead tiles.
4. Dashboard name/path and whether to render a preview mockup first.
