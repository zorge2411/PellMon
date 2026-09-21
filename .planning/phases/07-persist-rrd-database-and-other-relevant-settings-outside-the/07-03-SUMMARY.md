---
phase: 07-persist-rrd-database-and-other-relevant-settings-outside-the
plan: 03
status: complete
requirements: [D-08]
key-files:
  modified: [src/Pellmonweb/pellmonconf.py, src/Pellmonweb/media/js/source.js]
  created: [tests/Pellmonweb/test_pellmonconf_readonly.py]
---

# Phase 7 Plan 03: Read-only config save message Summary

`Pellmonconf.save` now returns "<file> is read-only (...)" for EROFS/EACCES/EPERM instead of a raw OSError string; the editor JS renders errors with `.text()` instead of `.html()`.

## Tests
- Baseline (full suite, WSL venv): 297 passed, 10 skipped. After: 303 passed, 10 skipped (+6 new). No regressions.
- `tests/Pellmonweb` with system python3 + venv site-packages: 100 passed.
- Failing-first confirmed: 3 read-only cases failed (raw message lacked filename) before implementation.

## Deviations
None. The test commit and feature commit are separate; the JS file has LF endings, pellmonconf.py CRLF, both preserved.

## Scope note
The editor is the standalone `pellmonconf` tool on port 8083, not mounted by Pellmonweb and not started by the compose stack. This change is verified by unit tests only; D-08 is not exercised by `docker compose up`.

## Not verified
No end-to-end check of the message in a browser or container.
