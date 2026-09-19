---
phase: quick-260919-gpe
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tools/burner_sim.py
  - tools/README-burner-sim.md
  - tests/test_burner_sim_pty.py
autonomous: false
requirements: [SIM-01, SIM-02, SIM-03]

must_haves:
  truths:
    - "On Linux/WSL, `python3 tools/burner_sim.py` opens a pty pair and prints the slave device path to stdout"
    - "Scotteprotocol.Protocol opened against that pty path reads plausible values for power, boiler_temp, mode, version without hanging"
    - "Protocol.setItem('boiler_temp_set', N) returns 'OK' and a subsequent getItem returns N (write round-trip)"
    - "The simulator logs the exact bytes of every received command and every sent response"
    - "Fault-injection flags --drop-rate, --corrupt-checksum-rate, --delay, --offline-after and --read-only change simulator behaviour"
    - "Tests exercising dropped and checksum-corrupted frames fail on timeout rather than blocking forever"
    - "Tests skip cleanly on Windows (no pty) and pass under WSL Debian"
    - "Every spec-vs-code disagreement found is written down in tools/README-burner-sim.md DISCREPANCIES and in the SUMMARY"
    - "No file under src/ is modified"
  artifacts:
    - path: "tools/burner_sim.py"
      provides: "Scotte burner emulator over a pty, with drifting value table, write handling and fault injection"
      contains: "openpty"
      min_lines: 250
    - path: "tests/test_burner_sim_pty.py"
      provides: "pty-based integration tests of Scotteprotocol.Protocol against the simulator"
      contains: "skipif"
    - path: "tools/README-burner-sim.md"
      provides: "Usage instructions (pellmonsrv debug wiring) plus DISCREPANCIES section"
      contains: "DISCREPANCIES"
  key_links:
    - from: "tests/test_burner_sim_pty.py"
      to: "tools/burner_sim.py"
      via: "importlib.util.spec_from_file_location (no sys.path mutation)"
      pattern: "spec_from_file_location"
    - from: "tools/burner_sim.py"
      to: "src/Scotteprotocol/frames.py frame layout"
      via: "frame field-width table derived from spec and cross-checked against code"
      pattern: "Z00"
    - from: "tools/README-burner-sim.md"
      to: "src/conf.d/plugins/scottecom.conf"
      via: "serialport = <pty slave path>"
      pattern: "serialport"
---

<objective>
Build a Scotte/Bio Comfort pellet burner emulator so PellMon's `scottecom` plugin and the
`Scotteprotocol` library can be exercised end-to-end without physical hardware.

Purpose: the project's core value claim is "the daemon must actually talk to real burner
hardware" — today that claim is untestable. A pty-backed emulator makes the real serial
code path (`Protocol.__init__` with a device name, the poll thread, `Frame.parse`,
`setItem`) runnable in CI and by hand via `pellmonsrv debug`.

Output: `tools/burner_sim.py`, `tests/test_burner_sim_pty.py`, `tools/README-burner-sim.md`.

Non-goal: fixing production code. If a genuine bug in `src/` blocks the tests, report it
in the SUMMARY and mark the test `@pytest.mark.known_broken` (the marker already exists in
`pytest.ini`) rather than silently patching `src/`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@scotte_protocol_spec.md
@src/Scotteprotocol/protocol.py
@src/Scotteprotocol/frames.py
@src/Scotteprotocol/datamap.py
@src/Scotteprotocol/enumerations.py
@src/Scotteprotocol/transformations.py
@src/Pellmonsrv/plugins/scottecom/scottecom.py
@src/conf.d/plugins/scottecom.conf
@tests/conftest.py
@tests/test_scotte_protocol_roundtrip.py
@pytest.ini

<sensitive_file_handling>
`mqtt-e117...-Scotte Pellet Burner-....json` at the repo root is a Home Assistant
diagnostics export (top-level keys: `home_assistant`, `custom_components`,
`integration_manifest`, `setup_times`, `data`, `issues`). It is untracked and contains
device identifiers.

Rules, no exceptions:
- READ ONLY, for value structure/plausible ranges. Never write to it.
- Never copy any identifier, serial, MAC, token, unique_id, entity_id containing a serial,
  hostname or coordinate from it into `tools/burner_sim.py`, the tests, the README, the
  SUMMARY, or a commit message. Extract shapes and magnitudes only, then paraphrase.
- Never `git add` it. Stage only the three files this plan creates, by explicit path.
</sensitive_file_handling>

<interfaces>
Contracts the simulator must satisfy — already established by `src/Scotteprotocol/`, do not
re-derive from scratch, but DO cross-check them against `scotte_protocol_spec.md`.

Protocol framing (src/Scotteprotocol/protocol.py):
- `addCheckSum(s)` -> `s + chr(XOR of all ord(c))`, latin-1 encoded on the wire.
- `checkCheckSum(s)` -> 0 when the trailing checksum byte is correct.
- Read request: `addCheckSum(frame.pollFrame)`, e.g. `Z000000` + `Z` (8 bytes).
- Read response: exactly `frame.getLength(protocol)` bytes — `frameLength + 1` when
  `checksum` is on, `frameLength + 2` when `frame_term_crlf` is on, else `frameLength`.
- Write request: `addCheckSum(address + "{:0>4.0f}".format(value * 10**decimals))`,
  e.g. `B010060` + checksum.
- Write response: `addCheckSum('OK')` -> 3 bytes read when checksum on, 2 when off.
- Error responses recognised by `Frame.parse`: `addCheckSum('E1')` (no such data) and
  `addCheckSum('E0')` (checksum fail).
- `serial.Serial` settings used for a real device: 9600 8N1, `timeout = 1`.

Frame field widths (src/Scotteprotocol/frames.py) — the simulator's response layout:
- Z00 `[5]*7 + [10,10] + [5]*9`  (18 fields, 100 chars)
- Z01 `[5]*46` (230), Z02 `[10]*4` (40), Z03 `[5]*20` (100), Z04 `[5]*2` (10),
  Z05 `[5]*39` (195), Z06 `[5]*18` (90), Z07 `[5]*40` (200), Z08 `[5]*25` (125)

Datamap facts the simulator must honour (src/Scotteprotocol/datamap.py):
- `version` = Z04 index 1, `decimals = -1` (raw string, e.g. `' 6.99'`); the plugin's
  `chipversion = auto` path calls `getItem('version').lstrip()` first, with checksums ON.
- Named tuples: `data(frame,index,decimals)`, `param(frame,index,decimals,address,min,max)`,
  `command(address,min,max)`. Every write address in the map (`A00`..`V02`) must be accepted.
- `dataEnumerations` in `enumerations.py` bound plausible `mode` (0-20), `alarm` (0-9) and
  `model` (0-4) values.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Derive the wire protocol, then build tools/burner_sim.py</name>
  <files>tools/burner_sim.py</files>
  <action>
Step A — derive first, cross-check second. Build the authoritative frame/address model in
this order, recording every disagreement as you go into a running notes list (scratchpad
file, not the repo):
  1. `scotte_protocol_spec.md` — frame table, checksum algorithm, write format, OK/E0/E1
     responses, 4-digit value padding.
  2. The mqtt diagnostics JSON — read only, for realistic value magnitudes and which
     parameters a real burner actually reports. Paraphrase magnitudes; copy no identifiers.
  3. Only then `src/Scotteprotocol/{protocol,frames,datamap,enumerations,transformations}.py`
     and `src/Pellmonsrv/plugins/scottecom/scottecom.py`.
Where the spec and the code disagree, implement the behaviour that the CODE expects (the
simulator's job is to be a stand-in for hardware that PellMon talks to), and record the
disagreement — do not silently normalise it away. Expected candidates, to be confirmed or
refuted rather than assumed: spec documents only Z00-Z06 while `frames.py` also defines
Z07/Z08; spec omits the E0/E1 error responses; spec omits the version-bounded
`chimney_draught` mapping (`'0000'..'6.85'`); spec's flat "4-digit padding" vs the code's
`"{:0>4.0f}".format(value * 10**decimals)` which can exceed 4 characters.

Step B — write `tools/burner_sim.py` per CLAUDE.md conventions: `#!/usr/bin/env python3`,
`# -*- coding: utf-8 -*-`, the GPL header block copied from `src/Scotteprotocol/protocol.py`,
`%`-formatting for log/error messages, no type hints, no `.py2bak` counterpart. Structure:

  - `BurnerSim` class holding a value table keyed by `(frame_id, index)` with the frame
    layouts above. Seed it with plausible values derived in Step A: burner running,
    boiler_temp ~65.5 C (raw `00655`, decimals 1), chute/smoke temps, oxygen ~8-12%,
    power 0-100, mode index in range of `dataEnumerations['mode']`, alarm 0 ('ok'),
    monotonic counters in Z02 (motor_time, el_time and the two `_perm` totals),
    and Z04 index 1 = the version string (default `' 6.99'`, overridable via
    `--chip-version`). Unmapped indices render as a plausible zero-ish padded number.
  - `tick()` / drift: temperatures random-walk within physical bounds, counters increase
    monotonically with elapsed wall time, power/oxygen wobble. Drift must be deterministic
    under a `--seed` flag so tests can assert on it.
  - `render_frame(frame_id)` -> fixed-width right-aligned ASCII string of exactly the
    frame's `frameLength`, then checksum appended (unless `--no-checksum`), and `\r\n`
    appended when `--crlf` is set.
  - Command loop: read bytes from the pty master, accumulate, and dispatch. Commands are
    7 payload chars (+1 checksum byte, +2 optional CRLF). Payloads starting `Z` are frame
    polls; anything else is a write of `AAA` + 4-digit value. Verify the inbound checksum;
    on mismatch reply `addCheckSum('E0')`. On an unknown frame or unknown write address
    reply `addCheckSum('E1')`.
  - Writes: store the raw 4-digit value back into the table at the `(frame, index)` the
    datamap associates with that address (so a write is observable by the next read),
    reply `addCheckSum('OK')`, and log the exact received and sent byte sequences with
    `repr()` of the latin-1 bytes. Command addresses (`V00`, `V01`, `V02`, `D04`) have no
    backing index — apply their side effect on the `mode`/`alarm` fields instead and
    still reply `OK`.
  - Fault injection flags, all independent: `--drop-rate F` (0.0-1.0, silently send no
    response), `--corrupt-checksum-rate F` (send a response with a deliberately wrong
    checksum byte), `--delay SECONDS` (sleep before responding), `--offline-after N`
    (answer N commands, then stop responding entirely), `--read-only` (reply `E1` to any
    write and leave the table untouched).
  - `main()`: `os.openpty()`, set raw termios on the slave fd so no ECHO/ONLCR mangles the
    protocol bytes (`termios`/`tty.setraw`), print the slave path via
    `os.ttyname(slave_fd)` on a line of the form `pty: /dev/pts/N`, then serve until
    SIGINT. Guard the pty/termios imports so `python tools/burner_sim.py --help` still
    works on Windows and exits with a clear "requires Linux/WSL" message when run there.
  - Expose the serving core as an importable API — `BurnerSim(**opts)`, `start()` returning
    the slave device path, `stop()`, and a `received_commands` list — so tests can drive it
    in-process on a daemon thread without spawning a subprocess.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc "cd /mnt/d/Antigravity/PellMon-master && ./venv-wsl/bin/python -c \"import importlib.util,sys; s=importlib.util.spec_from_file_location('bs','tools/burner_sim.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); b=m.BurnerSim(seed=1); p=b.start(); print('pty',p); import time; time.sleep(0.2); b.stop(); print('ok')\""</automated>
  </verify>
  <done>Simulator imports and starts on WSL, prints a /dev/pts path, stops cleanly; no file under src/ modified.</done>
</task>

<task type="auto">
  <name>Task 2: pty integration tests driving Scotteprotocol against the simulator</name>
  <files>tests/test_burner_sim_pty.py</files>
  <action>
Create `tests/test_burner_sim_pty.py` matching the existing test style in
`tests/test_scotte_protocol_roundtrip.py` (module docstring, plain asserts, fixtures).

Import rules: `tools/` is NOT on `pythonpath` (see `pytest.ini`) and `sys.path` mutation is
gated by `tests/test_no_sys_path_shims.py` — load the simulator with
`importlib.util.spec_from_file_location` from a path derived via
`pathlib.Path(__file__).resolve().parents[1] / "tools" / "burner_sim.py"`. Do not edit
`pytest.ini`.

Module-level guard: `pytest.mark.skipif(not hasattr(os, "openpty") or sys.platform == "win32", reason="pty unavailable on Windows")`.

Fixture `burner_sim`: start a `BurnerSim` with a fixed `--seed`, yield `(sim, pty_path)`,
and always `stop()` in teardown so a failed test cannot leave a thread or fd behind.

Anti-hang requirement — every test must be able to FAIL rather than block:
- Construct `Protocol(pty_path, '6.99')` (the real serial path, which the existing
  `loop://` tests never exercise) and rely on pyserial's `timeout = 1`.
- Wrap any call that could block (`getItem`, `setItem`) so the whole test body is bounded:
  run it on a `concurrent.futures.ThreadPoolExecutor` with a hard `result(timeout=...)`,
  or assert on wall-clock elapsed time. A hang must surface as a failed assertion/TimeoutError.

Tests to write:
1. `test_read_roundtrip` — read `power`, `boiler_temp`, `mode`, `version` through a live
   `Protocol` over the pty; assert the values match what the simulator's table says
   (deterministic under the fixed seed) and that `mode` decodes through `dataEnumerations`.
2. `test_write_roundtrip` — `setItem('boiler_temp_set', '60')` returns `'OK'`, the simulator
   recorded the exact expected command bytes (`B010060` + checksum) in `received_commands`,
   and a follow-up `getItem('boiler_temp_set')` returns `'60'`. Note that `getItem` forces a
   re-poll for ~4s after a write (`protocol.py` `time.time()-writeTime < 4.0`), so budget
   the timeout accordingly.
3. `test_dropped_frames_do_not_hang` — `--drop-rate 1.0`: a read must raise `IOError`
   (Protocol's "GetItem failed") or return within a bounded time; assert the bound.
4. `test_corrupt_checksum_handled` — `--corrupt-checksum-rate 1.0`: `Frame.parse` rejects
   the response, `Protocol` retries once and then fails without hanging.
5. `test_read_only_mode_rejects_writes` — `--read-only`: `setItem` does not return `'OK'`
   and the simulator's stored value is unchanged.
6. `test_pytest_socket_guardrail_not_triggered` — assert the pty path works with
   `--disable-socket` active (ptys are file descriptors, not sockets); if pytest-socket
   does interfere, do NOT weaken the guardrail — record it in the SUMMARY.

If any test reveals a genuine defect in `src/`, mark it `@pytest.mark.known_broken` with a
docstring naming the defect and report it in the SUMMARY. Do not edit `src/`.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc "cd /mnt/d/Antigravity/PellMon-master && timeout 300 ./venv-wsl/bin/python -m pytest tests/test_burner_sim_pty.py -v --timeout=60 2>&1 | tail -30 || timeout 300 ./venv-wsl/bin/python -m pytest tests/test_burner_sim_pty.py -v 2>&1 | tail -30"</automated>
  </verify>
  <done>All new tests pass under WSL Debian, the full suite still passes, and the whole file collects-and-skips on Windows.</done>
</task>

<task type="auto">
  <name>Task 3: tools/README-burner-sim.md with usage and DISCREPANCIES</name>
  <files>tools/README-burner-sim.md</files>
  <action>
Write `tools/README-burner-sim.md` covering:

  - What it is and why (hardware-free integration testing of the Scotte path).
  - Requirements: Linux/WSL only (pty), no extra pip packages.
  - Quickstart: `python3 tools/burner_sim.py --seed 1`, note the printed `pty: /dev/pts/N`,
    set `serialport = /dev/pts/N` in `src/conf.d/plugins/scottecom.conf` (and
    `chipversion = auto` or a pinned version), then run `pellmonsrv debug` and watch the
    values appear. Mention that the pty path changes on every run.
  - Full flag reference: `--seed`, `--chip-version`, `--no-checksum`, `--crlf`,
    `--drop-rate`, `--corrupt-checksum-rate`, `--delay`, `--offline-after`, `--read-only`.
  - How the tests use it (`tests/test_burner_sim_pty.py`, in-process via importlib).
  - A `## DISCREPANCIES` section listing every disagreement found in Task 1 between
    `scotte_protocol_spec.md` and `src/Scotteprotocol/` + the scottecom plugin. One row or
    bullet per item, each stating: what the spec says, what the code does, which behaviour
    the simulator implements, and whether it looks like a real protocol bug worth filing.
    If a check came out clean, say so explicitly rather than omitting it — "no discrepancy
    found in X" is useful information. Do not reference the mqtt diagnostics file by
    filename or quote anything identifying from it; cite it as "a real-burner telemetry
    export" if a magnitude came from there.

Then stage and commit ONLY the three files this plan created, by explicit path:
`git add tools/burner_sim.py tools/README-burner-sim.md tests/test_burner_sim_pty.py`.
Never `git add -A`/`git add .`, never add the mqtt JSON, never `git stash`,
`git restore` or `git checkout --`. Do not push.
  </action>
  <verify>
    <automated>cd /d/Antigravity/PellMon-master && grep -q "DISCREPANCIES" tools/README-burner-sim.md && grep -q "serialport" tools/README-burner-sim.md && git status --porcelain | grep -E "^(A|M) " </automated>
  </verify>
  <done>README exists with usage and a populated DISCREPANCIES section; exactly the three new files are staged; the mqtt JSON is still untracked and unmodified.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>A pty-backed Scotte burner emulator (`tools/burner_sim.py`), pty integration tests, and a README documenting usage plus spec-vs-code discrepancies.</what-built>
  <how-to-verify>
1. In WSL: `wsl -d Debian`, then `cd /mnt/d/Antigravity/PellMon-master`.
2. Run `./venv-wsl/bin/python tools/burner_sim.py --seed 1` and note the printed `pty: /dev/pts/N`.
3. In a second shell, point `serialport` in `src/conf.d/plugins/scottecom.conf` at that path
   and run `pellmonsrv debug` (or the equivalent `src/debugsrv.sh`); confirm boiler/chute
   temps and mode show plausible drifting values rather than dummy `1234`.
4. Review the `## DISCREPANCIES` section of `tools/README-burner-sim.md` — confirm the
   listed spec-vs-code disagreements look real and that none of them were resolved by
   editing `src/`.
5. Confirm `git status` shows the mqtt JSON still untracked and unstaged.
  </how-to-verify>
  <resume-signal>Type "approved" or describe issues</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| pty slave -> Scotteprotocol | Untrusted, attacker-shaped serial bytes reach `Frame.parse`; the simulator is the first tool able to feed malformed frames into the real code path |
| repo -> git history | The mqtt diagnostics export contains device identifiers that must never be committed |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gpe-01 | Information Disclosure | mqtt-*.json diagnostics export | mitigate | Read-only use for value shapes; explicit-path `git add` only; no identifiers copied into any committed file, SUMMARY or commit message |
| T-gpe-02 | Denial of Service | `Protocol.run` poll thread vs. dropped/corrupt frames | mitigate | Tests bound every blocking call with an explicit timeout so a hang fails the test instead of wedging the suite |
| T-gpe-03 | Tampering | `src/` production code | mitigate | Plan forbids editing `src/`; genuine defects are reported in the SUMMARY and marked `known_broken` instead |
| T-gpe-04 | Information Disclosure | `/dev/pts/N` created by the simulator | accept | Dev-only tool on a developer machine; pty is owned by the invoking user and torn down on exit |
| T-gpe-SC | Tampering | package installs | accept | No new dependencies — stdlib only (`os`, `pty`, `termios`, `argparse`, `random`, `threading`); `venv-wsl` used read-only |
</threat_model>

<verification>
- `wsl -d Debian -- bash -lc "cd /mnt/d/Antigravity/PellMon-master && ./venv-wsl/bin/python -m pytest -q"` — full suite green (or only pre-existing `known_broken` failures).
- `git diff --stat HEAD -- src/` is empty.
- `git status --porcelain` shows the mqtt JSON still as `??`, unmodified.
</verification>

<success_criteria>
- `tools/burner_sim.py` serves the Scotte protocol over a pty and satisfies a live
  `Scotteprotocol.Protocol` for both reads and writes.
- Fault-injection flags demonstrably change behaviour and are covered by tests that cannot hang.
- `tools/README-burner-sim.md` documents `pellmonsrv debug` wiring and a populated
  DISCREPANCIES section.
- Zero changes under `src/`; any defect found is reported, not patched.
- Only the three new files are committed; nothing pushed.
</success_criteria>

<output>
Create `.planning/quick/260919-gpe-scotte-burner-emulator-for-integration-t/260919-gpe-SUMMARY.md` when done.
Include in the SUMMARY: the full DISCREPANCIES list, any `src/` bugs found (with file:line
and why they were not fixed), and confirmation that no identifier from the diagnostics
export was reproduced anywhere.
</output>
