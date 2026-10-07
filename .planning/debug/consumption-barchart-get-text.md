---
status: investigating
trigger: "DATA_START Web log shows repeating errors: (1) 'error generating barchartdata' with TypeError: 'NoneType' object is not subscriptable at plugins/consumption/__init__.py line 195 in barchartdata: lastbar = float(self.rrd_total(start, now, cache=False)[1:][:-1]); during handling, AttributeError: 'Getsetitem' object has no attribute 'get_text' at pellmonsrv.py line 129 in run: value = item.get_text(item.value). (2) Every 5 min: 'INFO - silolevel prediction error: Expecting value: line 1 column 1 (char 0)'. DATA_END"
created: 2026-10-07
updated: 2026-10-07
---

## Current Focus
hypothesis: (1) rrd_total returns None (rrdtool fetch failing/py3 port issue); (2) Getsetitem lacks get_text (py3 migration / Database thread calls get_text on wrong class); (3) silolevel prediction fetches a URL/file returning empty/non-JSON
next_action: gather initial evidence

## Symptoms
expected: No errors in log; consumption bar chart data generated; daemon Database thread polls items cleanly; silolevel prediction works
actual: Errors repeat in web log view (barchartdata every ~5 min, silolevel prediction every 5 min)
errors: see trigger
reproduction: Run pellmonsrv in Docker (/app/src/...); errors appear in log view
started: Python 3 port (Docker deployment), 2026-10-07 observed

## Eliminated

## Evidence

## Resolution
root_cause:
fix:
verification:
files_changed:
