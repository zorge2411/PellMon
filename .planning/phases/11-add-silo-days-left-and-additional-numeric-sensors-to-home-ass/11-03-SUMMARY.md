# 11-03 Summary: consumption scalars

- Items `consumption_today`, `consumption_7d`, `consumption_month` (kg, one decimal, 300 s cache, `''` when rrdtool has no answer).
- Windows computed with `datetime` local midnight / first of month; tests run in UTC, Europe/Helsinki and America/New_York plus month and DST-change boundaries.
- Found, not fixed: `getItem` alignment code in the same file uses Python 2 integer division (`now/3600*3600`), so the bar charts are not hour/day aligned under Python 3. Filed as a follow-up.
