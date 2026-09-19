---
phase: quick-260919-gpe
plan: 01
status: incomplete
one-liner: "pty-backed Scotte burner emulator + pty integration tests; Protocol works against it, but pellmonsrv debug could not load the ScotteCom plugin (src yapsy bug)"
key-files:
  created:
    - tools/burner_sim.py
    - tools/README-burner-sim.md
    - tests/test_burner_sim_pty.py
completed: 2026-09-19
---

# Quick 260919-gpe: Scotte burner emulator Summary

`status: incomplete` only because the plan's task-4 end-to-end check
(`pellmonsrv debug` reading values from the plugin) could not be completed:
the ScotteCom plugin fails to load under the vendored yapsy loader (a src/
bug, reported below, not fixed). Tasks 1-3 are done and committed.

## What was built
- `tools/burner_sim.py`: pty emulator; frame layouts Z00-Z08, full write-address
  table, drifting seeded values, E0/E1/OK replies, fault flags
  (`--drop-rate`, `--corrupt-checksum-rate`, `--delay`, `--offline-after`,
  `--read-only`) plus extras `--freeze`, `--no-checksum`, `--crlf`,
  `--chip-version`. Importable API (`BurnerSim`, `start`, `stop`,
  `received_commands`).
- `tests/test_burner_sim_pty.py`: 14 tests (4 pure, 10 pty). Every blocking
  call is bounded by a ThreadPoolExecutor timeout.
- `tools/README-burner-sim.md`: usage, flag reference, DISCREPANCIES.

Commit: e614928 (three files, explicit paths). Nothing pushed.

## Test results
- WSL Debian (venv-wsl, Python 3.13.5): new file 14 passed (stable over
  repeated runs); full suite 208 passed, 3 skipped.
- Windows (Python 3.14 venv): new file 4 passed, 10 skipped (pty tests skip).
- pytest-socket `--disable-socket` does NOT interfere with ptys (test asserts
  a real read works while `socket.socket()` still raises SocketBlockedError).
- pytest-timeout is not installed; hang protection is via executor timeouts.

## Manual verification in WSL (task 4 checkpoint)
Verified:
- Simulator run as a subprocess printed `pty: /dev/pts/N`;
  `Protocol(path, 'auto')` detected version 6.99 with checksums on, read
  power=64, boiler_temp~58 (drifting: 58.3 -> 58.0 after 9 s), chute_temp=27,
  mode=Running, version=' 6.99', feeder_time counter advancing;
  `setItem('boiler_temp_set','62')` -> `OK`, read back 62.
NOT verified:
- `pellmonsrv debug` end to end. Ran `python3 -m Pellmonsrv.pellmonsrv -C
  <temp conf> -D SESSION debug` under `dbus-run-session` (system python3 +
  read-only venv-wsl site-packages, temp config outside the repo). The daemon
  started and served D-Bus, but the ScotteCom plugin failed to load (bug 1),
  so GetItem returned KeyError for every item. The human-verify step (visual
  confirmation, README review) is left to the user.

## DISCREPANCIES (spec vs code)
Full text in `tools/README-burner-sim.md`. Short list:
1. Spec omits frames Z07/Z08 (code defines both; Z08 used by `oxygen_mid`).
2. Spec omits E0/E1 error responses (code handles them).
3. Spec lists ~10 params, datamap ~80; for the 10 listed, no discrepancy.
4. `chimney_draught` version-bounded (<6.85) in code, unconditional in spec.
5. 4-digit padding: no discrepancy today (max scaled value 9999), no guard.
6. Write response: spec "OK or OK+checksum"; code needs exactly checksummed OK;
   error replies are returned raw (e.g. 'E1'+checksum byte) by `setItem`.
7. CRLF era: spec says newer chips, code treats CRLF as oldest-chip fallback
   and assumes writes succeed without reading.
8. CRLF with checksum on: `getLength` ignores CRLF (works only via flushInput).
9. Spec omits Z04/1 ASCII version string used by `chipversion=auto`.
10. Spec's checksum example has a leftover "Wait, let's verify" note (math OK).
11. Serial parameters: consistent, no discrepancy.

## src/ bugs found (NOT fixed; src/ untouched, `git diff HEAD -- src` empty)
1. **Plugin cannot load under yapsy** (blocks core value): 
   `src/Pellmonsrv/yapsy/PluginManager.py:273-276` execs plugin `__init__.py`
   with `candidate_globals = {"__file__": ...}` only, so
   `src/Pellmonsrv/plugins/scottecom/__init__.py:4`
   (`from .scottecom import scottecom`) raises
   `KeyError: "'__name__' not in globals"`. Plain imports (test_plugin_imports)
   pass, masking it. Other plugins using relative imports (e.g. nbecom) likely
   affected too (not checked). Needs a decision on the loader (Rule 4-ish);
   not fixed because src/ edits are out of scope.
2. `src/Scotteprotocol/protocol.py` `Protocol.run` retry path: in CRLF mode
   `sendFrame += '\r\n'` is applied again on retry, sending `\r\n\r\n`.
3. `src/Scotteprotocol/protocol.py:77` `self.setDaemon(True)` is deprecated
   (DeprecationWarning on 3.13); the transport path already uses `.daemon`.
4. `Frame` instances in `src/Scotteprotocol/frames.py` are module-level
   singletons: `readtime`/`indexWriteTime` are shared across `Protocol`
   instances (one Protocol per process only). Tests reset them in a fixture;
   without that a second Protocol silently serves stale cache for 8 s.
5. `setItem` returns raw error bytes (`'E1'` + checksum char) to callers.

## Deviations from plan
- Added `--freeze` flag (deterministic tests) and extra tests (datamap/frame
  cross-check, in-process E0/E1, auto-version, delay, offline-after, command
  write). No known_broken markers were needed.
- `--crlf --no-checksum`: simulator sends no write reply (mirrors the code's
  assumption); the plan said always reply OK.
- Simulator tolerates stray CRLF after inbound commands regardless of flags.
- No `.py2bak` created; no `pytest.ini` change.

## Sensitive file
The mqtt-*.json export was read only for value magnitudes and never staged.
No identifier, credential, serial or filename-specific id from it appears in
any committed file, this SUMMARY or a commit message.
