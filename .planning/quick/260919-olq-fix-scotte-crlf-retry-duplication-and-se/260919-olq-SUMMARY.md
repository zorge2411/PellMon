---
status: complete
phase: quick-260919-olq
plan: 01
requirements: [SCOTTE-CRLF-RETRY, SCOTTE-SETITEM-CONTRACT]
commits: [03bc51e]
---

# Quick 260919-olq: Scotte CRLF retry duplication and setItem contract

## Result
- Bug 1 fixed: in `Protocol.run` the GET frame is CRLF-terminated once, before the first write; first attempt and retry send identical bytes.
- Bug 2 fixed: `Protocol.setItem` never returns device reply text.

## setItem contract (final)
- Success (checksummed OK, CRLF-era assumed OK, dummyDevice): returns `'OK'`.
- Local validation (not a number, out of range, not a setting): `ValueError` with the old message text; logged at warning.
- Device rejected (E0/E1/garbage/wrong length) or no answer: logged at warning with `repr(raw reply)`, then `IOError(0, 'SetItem failed: ...')`. Raw reply is only in the log.
- Unexpected internal error: logged with traceback, `IOError`.
- Unknown param still raises `KeyError` (unchanged).

Rationale: `Getsetitem.value` (database.py:53-57) discards the setter's return and `Database.set_value` always returns `'OK'`, so failed writes were reported to the web UI as OK. Raising is the compatible signal: it propagates through the setter, aborts `set_value`, becomes a D-Bus error, and both pellmonweb call sites (509-514, 566-569) already catch it and show `'error'`. Mirrors `getItem`'s `IOError`.

## Caller safety check (no daemon thread breaks)
- scottecom.py delegates; only its own poll threads call `getItem`, never `setItem`.
- calculate plugin `set` op (`db.set_value`) runs inside `run()`/thread bodies wrapped in `except Exception` with `logger.exception` (calculate/__init__.py:194-219, 375-381).
- D-Bus `SetItem` raises a D-Bus error to the caller; daemon verified alive afterwards (end-to-end).
- No production change was needed outside protocol.py.

## src diff scope
`src/Scotteprotocol/protocol.py` only: `setItem` body/docstring, and in `run` the GET branch (CRLF appended once before first write; two in-block appends removed). Wire behavior otherwise unchanged. Side effect: `indexWriteTime` is now stamped only after validation passes (previously before the range check).

## Deviation
- [Rule 1] `tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_set_item_unexpected_error_logs_exception` (not in the plan's file list) called `setItem` expecting a swallowed error; wrapped the call in `pytest.raises(IOError)`, assertions on the logged exception unchanged.

## Failing-first evidence (WSL Debian, before touching src)
`tests/test_scotte_protocol_bugs.py`: 5 failed, 1 passed (the positive control).
- CRLF: `AssertionError: assert b'Z000000Z\r\n' == b'Z000000Z\r\n\r\n'` (retry doubled the terminator).
- read-only / corrupt-checksum / no-answer setItem: `DID NOT RAISE OSError` (raw reply / 'No answer' was returned).
- local validation: `DID NOT RAISE ValueError`.

## Suite counts (WSL Debian, venv-wsl)
- Baseline: 240 passed, 5 skipped (with the new file present pre-fix: 241 passed, 5 failed, 5 skipped).
- After: 246 passed, 5 skipped (240 + 6 new tests, no regressions).

## End-to-end (WSL, scottecom-only plugin dir in /tmp, throwaway config, sim on a pty)
Verified: `pellmonsrv debug` + `burner_sim.py --seed 1 --freeze` under `dbus-run-session`.
- Normal sim: D-Bus `SetItem boiler_temp_set 65` returned `'OK'`, sim received `B010065@`, `GetItem` returned `65`.
- `--read-only` sim: `SetItem` produced a D-Bus error (OSError), `GetItem` still `60`, daemon log had `setItem boiler_temp_set rejected or unanswered, raw reply 'E1t'`, daemon stayed alive and answered later GetItem calls.
Not verified: no real burner hardware; CRLF mode not exercised end-to-end (covered only by the recording-transport unit test); web UI rendering of the error not exercised (relies on the existing try/except in pellmonweb, read not run). All spawned processes killed, /tmp artifacts removed.

## Still open / carried forward
- Spec-vs-code discrepancies in tools/README-burner-sim.md other than the two fixed (entries 6 and 13 updated) remain, incl. CRLF era assignment and `Frame.getLength` ignoring CRLF with checksums.
- Out of scope, untouched: `setDaemon(True)` at protocol.py:77; shared module-level `Frame` singletons.
