---
phase: quick-261011-idv
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/Pellmonsrv/plugins/consumption/__init__.py
  - tests/Pellmonsrv/plugins/test_consumption_alignment.py
autonomous: true
requirements: [QUICK-261011-idv]
status: done
---

<objective>
Fix Python 2 integer division left in `Consumption_plugin.getItem` so the consumption bar charts
(`consumptionData24h`, `7d`, `8w`, `1y`) are aligned to the hour, local midnight, week and month
boundaries again.
</objective>

<problem>
Found 2026-10-11 while implementing Phase 11 plan 11-03. In `src/Pellmonsrv/plugins/consumption/__init__.py`
`getItem` computes the `start` argument of `barchartdata` with `/` where Python 2 meant floor division:

- 24h: `align=now/3600*3600`
- 7d: `align=int(now)/86400*86400-(time.localtime(now).tm_hour-int(now)%86400/3600)*3600`
- 8w: `align=int(now+4*86400)/(86400*7)*(86400*7)-(time.localtime(now).tm_hour-int(now)%86400/3600)*3600 -4*86400`
- 1y: `align1y=now/int(31556952/12)*int(31556952/12)-(time.localtime(now).tm_hour-int(now)%86400/3600)*3600`

Under Python 3 `/` is true division, so `now/3600*3600 == now` (a float): the divide-then-multiply
rounding is a no-op, and in the 7d/8w/1y lines `int(now)%86400/3600` becomes a fractional UTC hour,
so the local-offset correction is also wrong. Result: bars end at "now" instead of at the hour/day/
week/month boundary, every bar is shifted, and the "current" bar is empty. Nothing raises, so it
went unnoticed. `Pellmonsrv/plugins/consumption` has no tests today.

Related, not in scope: the silolevel estimate reads `consumptionData7d/8w/1y` (bar `data[i][1]`
positions), so it is skewed by the same bug; it should improve after this fix, but its thresholds
were tuned on Python 2 behaviour, so compare before/after on a real RRD.
</problem>

<tasks>
<task type="auto" tdd="true">
  <name>Task 1: Characterise the intended alignment</name>
  <action>
    Add `tests/Pellmonsrv/plugins/test_consumption_alignment.py`. Patch `time.time`/`time.localtime`
    (or the plugin's `_now()` helper added in Phase 11) and capture the `start` passed to a patched
    `barchartdata`. Expected values come from evaluating the original expressions with Python 2
    semantics (`//`), in UTC, Europe/Helsinki and America/New_York (set TZ + `time.tzset()`), including a
    DST-change day and a month/year boundary. Tests must fail on the current code.
  </action>
</task>
<task type="auto">
  <name>Task 2: Use floor division</name>
  <files>src/Pellmonsrv/plugins/consumption/__init__.py</files>
  <action>
    Replace `/` with `//` in the four `align*` expressions (including the inner `int(now)%86400//3600`).
    Prefer extracting `align_for(itemName, now)` as a small pure method so the tests call it directly
    rather than going through the cache. Do not change periods, bar counts, cache times or the Phase 11
    scalar items. Keep `%`-formatting and the surrounding style.
  </action>
  <verify>pytest tests/Pellmonsrv/plugins -q; then compare `consumptionData24h` output before/after against a copy of the real RRD on the Pi (last bar should end on the full hour).</verify>
</task>
<task type="auto">
  <name>Task 3: Sweep for the same pattern</name>
  <action>
    `grep -rn "[a-z)0-9]/[0-9(]" src --include=*.py` (skip `.py2bak`) for other `x/N*N` rounding or
    integer-expected divisions in plugins and protocol code (none other than this file found in the
    Phase 11 spot check). Fix any real finds in this task with a test each; list the rest in the summary.
  </action>
</task>
</tasks>

<success_criteria>
- Alignment tests pass in the three time zones, fail on the pre-fix code.
- `start` passed to `barchartdata` is an int on the hour / local midnight / week / month boundary.
- Full pytest suite green.
</success_criteria>
