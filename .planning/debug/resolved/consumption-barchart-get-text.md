---
status: resolved
trigger: "DATA_START Web log shows repeating errors: (1) 'error generating barchartdata' with TypeError: 'NoneType' object is not subscriptable at plugins/consumption/__init__.py line 195 in barchartdata: lastbar = float(self.rrd_total(start, now, cache=False)[1:][:-1]); during handling, AttributeError: 'Getsetitem' object has no attribute 'get_text' at pellmonsrv.py line 129 in run: value = item.get_text(item.value). (2) Every 5 min: 'INFO - silolevel prediction error: Expecting value: line 1 column 1 (char 0)'. DATA_END"
created: 2026-10-07
updated: 2026-10-07T00:00:00Z
---

## Current Focus
hypothesis: CONFIRMED (see Resolution).
next_action: none

## Symptoms
expected: No errors in log; consumption bar chart data generated; daemon Database thread polls items cleanly; silolevel prediction works
actual: Errors repeat in web log view (barchartdata every ~5 min, silolevel prediction every 5 min)
errors: see trigger
reproduction: Run pellmonsrv in Docker (/app/src/...); errors appear in log view
started: Python 3 port (Docker deployment), 2026-10-07 observed

## Eliminated
- 'Getsetitem has no attribute get_text' is not a bug: pellmonsrv.py:129 tries get_text first (only nbecom items have it), the except AttributeError fallback reads item.value. The traceback only appears because logger.exception in barchartdata prints the chained exception context.
- RRD missing data sources: eliminated. rrd.db has feedertime/feedercapacity/logtick, matching [rrd_ds_names]; the plugin's rrdtool graph call returns a value on the Pi.

## Evidence
- consumption/__init__.py: per-bar rrd_total calls were wrapped in try/except, but the current-bar call (lastbar) was not. rrd_total returns None when rrdtool prints nothing; None[1:] raised TypeError, barchartdata returned str(e) (not JSON).
- silolevel/__init__.py json.loads() of consumptionData1y received that string -> 'Expecting value: line 1 column 1'.
- On the Pi after pulling the fix, log shows none of the three errors over 15 min; rrdtool graph with real DS names printed 4.51.

## Resolution
root_cause: Unguarded rrd_total call for the current bar in barchartdata; any transient rrdtool failure (None result) made barchartdata return a non-JSON error string, which silolevel then failed to parse every 5 min.
fix: Wrapped the lastbar computation in try/except falling back to 0 (commit a438501, released as v2.4.1).
verification: Verified on the Pi (stoker-pi): error lines absent from pellmonsrv logs after update. Underlying transient rrdtool failure cause not identified.
files_changed: [src/Pellmonsrv/plugins/consumption/__init__.py]
