# 11-02 Summary: silolevel

- `silo_days_left` is unknown after a prediction error (internal `None`, exposed as `''` so D-Bus marshalling stays safe and the HA guard skips it). Error is logged once per distinct message at warning level and re-armed after a success.
- New `silo_empty_date` item (ISO 8601 with offset, `''` when unknown).
- Web template no longer prints "null days to empty".
- First tests for the plugin (9): all estimate branches, '365', error, recovery, empty date, fill-level stamping.
