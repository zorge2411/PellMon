# Scotte burner emulator (`tools/burner_sim.py`)

A pty-backed emulator of a Scotte / Bio Comfort pellet burner. It lets the real
`Scotteprotocol.Protocol` serial code path (open device, poll thread,
`Frame.parse`, `setItem`) and the `scottecom` plugin run without hardware.

## Requirements

Linux or WSL only (needs `os.openpty`). No extra pip packages (stdlib only).
On Windows `python tools/burner_sim.py --help` works but starting the
simulator exits with "requires Linux/WSL".

## Quickstart

```bash
python3 tools/burner_sim.py --seed 1
# pty: /dev/pts/N
```

The pty path changes on every run. Point the plugin at it in
`src/conf.d/plugins/scottecom.conf` (or your own conf.d copy):

```ini
[plugin_ScotteCom]
serialport = /dev/pts/N
chipversion = auto      ; or pin e.g. 6.99
```

then run `pellmonsrv debug` (see `src/debugsrv.sh`) and watch drifting values
instead of the dummy `1234`. Every received command and every sent response is
logged to stderr as `RX b'...'` / `TX b'...'`.

Note: see DISCREPANCIES item 12 - at the time of writing the yapsy plugin
loader cannot load the `scottecom` plugin, so `pellmonsrv debug` will not get
that far until that is fixed. `Scotteprotocol.Protocol` itself works against
the simulator (see the tests).

## Flags

| Flag | Effect |
| --- | --- |
| `--seed N` | deterministic random drift |
| `--chip-version STR` | version reported in Z04 index 1 (default `" 6.99"`) |
| `--no-checksum` | emulate chips without checksums |
| `--crlf` | terminate responses with CRLF (with `--no-checksum`, writes get no answer, as `Protocol.run` assumes for such chips) |
| `--drop-rate F` | fraction (0.0-1.0) of responses silently dropped |
| `--corrupt-checksum-rate F` | fraction of responses sent with a wrong checksum byte |
| `--delay S` | sleep S seconds before every response |
| `--offline-after N` | answer N commands, then stop answering |
| `--read-only` | answer `E1` to every write, table untouched |
| `--freeze` | disable value drift (constant table; used by tests) |

Library use: `BurnerSim(**opts)`, `start()` -> slave path, `stop()`,
`received_commands`, `sent_responses`, `table`, `tick(dt)`. Fault-injection
attributes (`drop_rate`, ...) may be changed at runtime.

## Tests

`tests/test_burner_sim_pty.py` loads the simulator in-process via
`importlib.util.spec_from_file_location` and drives a live `Protocol` over the
pty. Every blocking call runs under a hard timeout so a hang fails instead of
blocking. pty tests skip on Windows; table-consistency tests (simulator vs
`src/Scotteprotocol`) run everywhere.

## DISCREPANCIES

Spec = `scotte_protocol_spec.md`; code = `src/Scotteprotocol/` and the
scottecom plugin. "Sim" is what the simulator implements. Magnitudes of
plausible values came from a real-burner telemetry export (values only).

1. **Frames Z07/Z08.** Spec documents Z00-Z06. Code also defines Z07 (40x5) and
   Z08 (25x5); Z08 is used (`oxygen_mid`, `E06`), Z07 is unused by the
   datamap. Sim: implements both as in code. Spec is incomplete, not a bug.
2. **E0/E1 error responses.** Spec omits them; `Frame.parse` recognises
   `addCheckSum('E1')` (no such data) and `addCheckSum('E0')` (checksum
   fail). Sim: sends E0 on bad inbound checksum, E1 on unknown frame/address.
   Spec gap.
3. **Data map coverage.** Spec lists ~10 settings; datamap has ~80 entries
   (alarm, model, ignition_time, Z02 counters, ignition_count, Z06 temperatures,
   version, timers, oxygen/regulator/cleaning parameters ...). For the 10 that
   spec lists (frame, index, decimals, write address, min/max) NO discrepancy
   found. Sim: full datamap write-address table (cross-checked by a test).
4. **`chimney_draught` is version-bounded** (`'0000'..'6.85'`) in code; spec
   shows it unconditionally. On the default 6.99 it is absent from the
   `Protocol` database, so `G00` is unreachable via `setItem`. Sim: accepts
   `G00` regardless. Looks intentional (chip change), spec gap.
5. **4-digit value padding.** Spec says "usually 4 digits"; code uses
   `"{:0>4.0f}".format(value * 10**decimals)`, which can exceed 4 characters.
   Checked against every `param` in the datamap: the largest scaled value is
   9999 (`E03`), so no discrepancy today; nothing in code guards a future entry.
   Sim: requires exactly 4 digits, else E1.
6. **Write response.** Spec: `OK` "or `OK` + checksum". Code: expects exactly
   `addCheckSum('OK')` (3 bytes) with checksums, 2 bytes without. FIXED
   (quick-260919-olq): `setItem` no longer returns the raw reply on failure; it
   returns `'OK'` on success, raises `ValueError` for local validation errors
   and `IOError` for a rejected/unanswered write (raw reply only in the log).
   Sim: `OK`/`E1`/`E0` with checksum.
7. **CRLF era.** Spec: older chips have no terminator, newer chips "may" use
   CRLF. Code: CRLF mode is the last auto-detect fallback after checksums are
   switched off (treated as the oldest chips) and writes are assumed to succeed
   with no read. Contradictory era assignment. Sim: `--crlf` appends CRLF to
   responses; with `--no-checksum` it never answers writes (code's assumption).
8. **CRLF + checksum.** With checksums on, `Frame.getLength` returns
   `frameLength + 1` and ignores CRLF, so a chip sending checksum AND CRLF
   leaves 2 unread bytes (cleared by the next `flushInput`). Works only by
   accident. Possible protocol bug, needs real hardware to judge. Sim: supports
   the combination.
9. **Version frame.** Spec never mentions Z04 index 1 as an ASCII version
   string (e.g. `" 6.99"`, leading space), used by `chipversion = auto`
   (`getItem('version').lstrip()`). Sim: implements it.
10. **Spec worked example.** Spec's checksum example still contains a
    "Wait, let's verify" scratch note; the arithmetic itself is right
    (`Z000000` -> checksum byte `Z`, matches code and existing tests).
    No functional discrepancy.
11. **Serial parameters.** Spec: 9600 8N1, no flow control. Code sets 9600,
    parity N, no flow control, timeout 1 s; 8 data bits / 1 stop bit come from
    pyserial defaults. Consistent; no discrepancy.
12. **Real src bug (not spec-vs-code): plugin cannot load under yapsy.**
    `Pellmonsrv/yapsy/PluginManager.py:273-276` execs plugin `__init__.py`
    with globals `{"__file__": ...}` only; `plugins/scottecom/__init__.py`
    does `from .scottecom import scottecom`, which raises
    `KeyError: "'__name__' not in globals"`. Observed running
    `python3 -m Pellmonsrv.pellmonsrv debug` under WSL: the ScotteCom plugin
    fails to load (logged, not fatal), so no `boiler_temp` etc. items exist.
    Plain `import` of the plugin package (as `tests/test_plugin_imports.py`
    does) succeeds, which is why it went unnoticed. Not fixed here (src/ is
    out of scope).
13. **Other src observations** (see the quick-task SUMMARY): the retry path in
    `Protocol.run` used to append CRLF twice in CRLF mode (FIXED in
    quick-260919-olq: first attempt and retry now send identical bytes);
    `self.setDaemon(True)`
    (protocol.py:77) is deprecated; `Frame` objects are module-level
    singletons so `readtime`/`indexWriteTime` are shared by every `Protocol`
    instance (tests reset them in a fixture).
