---
phase: quick-260919-olq
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/test_scotte_protocol_bugs.py
  - tests/test_burner_sim_pty.py
  - src/Scotteprotocol/protocol.py
  - tools/README-burner-sim.md
autonomous: true
requirements: [SCOTTE-CRLF-RETRY, SCOTTE-SETITEM-CONTRACT]

must_haves:
  truths:
    - "A CRLF-mode frame poll that needs a retry writes the retry frame terminated with exactly one CRLF (identical bytes to the first attempt)"
    - "Protocol.setItem never returns raw device reply bytes/characters (E0/E1/checksum bytes/garbage) to its callers"
    - "A successful write still returns 'OK' to scottecom.py and the D-Bus SetItem path"
    - "A rejected or unanswered write surfaces as a logged, typed error instead of a silent pseudo-success"
    - "Full pytest suite in WSL Debian is at or above the 240 passed / 5 skipped baseline"
  artifacts:
    - path: "tests/test_scotte_protocol_bugs.py"
      provides: "Failing-first regression tests for both bugs"
      contains: "crlf"
    - path: "src/Scotteprotocol/protocol.py"
      provides: "Fixed retry termination + documented setItem contract"
  key_links:
    - from: "src/Scotteprotocol/protocol.py"
      to: "src/Pellmonsrv/plugins/scottecom/scottecom.py"
      via: "setItem return/raise contract"
      pattern: "def setItem"
---

<objective>
Fix two known Scotte protocol bugs before real-burner testing:
1. `Protocol.run` GET retry path appends `'\r\n'` a second time in CRLF mode, sending `\r\n\r\n`.
2. `Protocol.setItem` returns raw device reply characters (`'E1'+checksum`, garbage, `'No answer'`) to callers.

Purpose: these are the last two known-correctness defects in the Scotte write/retry path; both are invisible to today's callers (see Context below), so they must be pinned by tests before hardware testing.
Output: failing-first regression tests, a minimal fix in `src/Scotteprotocol/protocol.py`, an updated pty test expectation, a documented contract decision in the SUMMARY.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/quick/260919-gpe-scotte-burner-emulator-for-integration-t/260919-gpe-SUMMARY.md
@.planning/quick/260919-jiz-fix-yapsy-plugin-loading-so-relative-imp/260919-jiz-SUMMARY.md
@src/Scotteprotocol/protocol.py
@src/Pellmonsrv/plugins/scottecom/scottecom.py
@tests/test_burner_sim_pty.py
@tools/burner_sim.py
@tools/README-burner-sim.md

<caller_analysis>
Already performed during planning — do NOT re-derive, but DO verify these line
references still hold before changing the contract:

- `src/Pellmonsrv/plugins/scottecom/scottecom.py:86-87` — `setItem` delegates
  straight to `Protocol.setItem`, returning whatever it gets.
- `src/Pellmonsrv/plugins/scottecom/scottecom.py:49` — the Scotte items are
  `Getsetitem(..., setter=lambda i,v: self.setItem(i,v))`.
- `src/Pellmonsrv/database.py:53-57` — `Getsetitem.value` setter calls
  `self.setter(name, value)` and **discards its return value**.
- `src/Pellmonsrv/database.py:138-140` — `Database.set_value` sets `.value` and
  then unconditionally `return 'OK'`.
- `src/Pellmonsrv/pellmonsrv.py:163-166` — D-Bus `SetItem` returns
  `conf.database.set_value(...)`, i.e. always `'OK'`.
- `src/Pellmonweb/pellmonweb.py:509-514` and `:566-569` — both `setItem` call
  sites are wrapped in bare `try/except` that substitutes `'error'`.
- `src/Pellmonsrv/plugin_categories.py:44` — base-class `setItem` stub.

**Consequence:** no production caller reads `Protocol.setItem`'s return value;
a failed write is reported to the web UI as `'OK'` today. Only tests and direct
`Protocol` users observe the raw bytes. Therefore raising on failure is the
compatible signalling mechanism: an exception propagates through the
`Getsetitem` setter, aborts `set_value`, becomes a D-Bus error, and both web
call sites already catch it and render `'error'`.

`Protocol.getItem` already raises `IOError(0, "GetItem failed")` on failure —
mirror that convention rather than inventing a new exception type.
</caller_analysis>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Baseline the suite, then write failing-first regression tests</name>
  <files>tests/test_scotte_protocol_bugs.py</files>
  <action>
First capture the baseline: run the full suite in WSL Debian
(`wsl -d Debian` with repo at /mnt/d/Antigravity/PellMon-master, using
`venv-wsl` read-only — do not pip install into it) and record the exact
pass/skip counts. Expected baseline: 240 passed, 5 skipped.

Then create `tests/test_scotte_protocol_bugs.py` following the conventions in
`tests/test_burner_sim_pty.py` (importlib-loaded `burner_sim`, `needs_pty`
skipif, `bounded()` executor timeout wrapper, the shared-`Frame` reset fixture)
and `tests/test_scotte_protocol_roundtrip.py` (transport-injected `Protocol`).
Do not copy the whole harness blindly — import/duplicate only what this file
needs, and keep the shared-Frame reset because `Scotteprotocol.frames` exposes
module-level `Frame` singletons.

Bug 1 test (CRLF retry) — use a recording fake transport, not a pty, because
`burner_sim` strips stray CR/LF from its input buffer and so cannot observe the
duplication:
  - Define a small fake transport object exposing `write(bytes)`,
    `read(n) -> b''`, `flushInput()`, `close()`, recording every `write` call's
    exact bytes.
  - Build `Protocol(None, '6.99', transport=fake, start_thread=False)`, set
    `protocol.frame_term_crlf = True`, keep checksums at their default.
  - Drive exactly one GET cycle without the infinite `run()` loop: put a
    `("FORCE_GET", <Frame>, responseQueue)` tuple on `protocol.q`, then run the
    thread body in a way that terminates (e.g. start the thread with
    `start_thread=True` on a second instance, or run `protocol.run` on a daemon
    worker thread via `bounded`-style timeout and read the recorded writes once
    two writes have been observed). Whatever mechanism is used, the test must
    not hang: bound every blocking wait.
  - Assert there are exactly 2 recorded writes, that both are byte-identical,
    and that each ends with exactly one `b'\r\n'` (`writes[i].count(b'\r\n') == 1`
    and no `b'\r\n\r\n'` anywhere). This test MUST fail before the fix.

Bug 2 tests (setItem contract) — pty tests against `tools/burner_sim.py`:
  - `--read-only` rejection: `BurnerSim(read_only=True)`; a
    `setItem('boiler_temp_set','65')` must not return any string containing the
    raw reply payload (`'E1'`, `'E0'`, or the checksum byte of either) and must
    not return a value other than `'OK'` silently — assert the post-fix contract
    (see Task 2) with `pytest.raises(IOError)`, and assert
    `sim.table['Z00'][10] == 60` (unchanged).
  - corrupt checksum on the write reply: `corrupt_checksum_rate = 1.0`; same
    assertion — no raw reply characters leak out of `setItem`.
  - no answer at all: `offline_after = sim.command_count`; `setItem` must raise
    rather than return the literal `'No answer'`.
  - a positive control: a normal write still yields exactly `'OK'`.
Mark these `@needs_pty` so Windows skips them.

Run the new file in WSL and confirm all four/five new tests FAIL (or error) for
the right reason before touching `src/`. Record the failure output in the
SUMMARY evidence.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc "cd /mnt/d/Antigravity/PellMon-master && ./venv-wsl/bin/python -m pytest tests/test_scotte_protocol_bugs.py -x -q; echo EXIT=$?"</automated>
  </verify>
  <done>Baseline counts recorded; new test file exists; every new test fails pre-fix, with the CRLF test failing specifically on a doubled `\r\n` and the setItem tests failing on raw reply characters / missing raise.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fix CRLF retry duplication and define the setItem contract</name>
  <files>src/Scotteprotocol/protocol.py, tests/test_burner_sim_pty.py, tools/README-burner-sim.md</files>
  <behavior>
    - CRLF-mode GET retry writes bytes identical to the first attempt (one CRLF).
    - Non-CRLF GET path byte stream is unchanged.
    - setItem success returns `'OK'`; dummyDevice still returns `'OK'`.
    - setItem never returns E0/E1/checksum/garbage/`'No answer'` text.
  </behavior>
  <action>
**Bug 1 — `Protocol.run`, GET branch (currently lines ~284-320).** Build the
on-the-wire frame exactly once, before the first write:
compute `sendFrame = self.addCheckSum(frame.pollFrame)`, then derive a single
terminated value (e.g. `wire = sendFrame + '\r\n' if self.frame_term_crlf else
sendFrame`) and use that same value for both the first write and the retry.
Remove the second `if self.frame_term_crlf: sendFrame += '\r\n'` inside the
retry block. Do not touch `frame.getLength` (the known CRLF/getLength
discrepancy stays as-is, SUMMARY-only). Do not touch the PUT branch's
termination, which already applies CRLF once.

**Bug 2 — `Protocol.setItem` (lines ~184-227).** Implement this contract and
document it in the method docstring:
  - Success (device replied with checksummed `OK`, or CRLF-era assumed-OK, or
    `dummyDevice`) → return the string `'OK'`.
  - Local validation failure (value not a number, value outside
    `dataparam.min..max`, item has no `address` / is not a setting) → raise
    `ValueError` with the existing human-readable message text
    (`"not a number"`, `"Expected value X..Y"`, `"Not a setting value"`). Log at
    `warning`.
  - Device rejected or did not answer (anything that is not the checksummed
    `OK`, including `E0`, `E1`, wrong length, garbage, `'No answer'`) → log at
    `warning`/`error` including `repr()` of the raw reply for diagnosis, then
    raise `IOError(0, '<short reason>')`, mirroring `getItem`'s
    `IOError(0, "GetItem failed")` convention. The raw reply must appear in the
    log only, never in the raised message or a return value.
  - Keep the existing `except (KeyError, ValueError, TypeError, IndexError)` /
    `except Exception` structure but re-raise as the contract types instead of
    `return str(e)` — no code path may return a diagnostic string any more.
Use `%`-style logging and the existing `logger = getLogger('pellMon')`, per
project conventions. Do NOT change wire behaviour: same bytes written, same
number of reads, no new reply read in CRLF mode.

**Caller compatibility.** Verify (re-read if needed) that
`scottecom.setItem` needs no change (it delegates, so the exception propagates)
and that `Database.set_value`/`Getsetitem.value` propagate rather than swallow.
If any production caller would now crash the daemon instead of logging, make
the minimal adjustment at that caller and note it in the SUMMARY — do not
weaken the contract to avoid touching it.

**Update the one existing test this contract breaks:**
`tests/test_burner_sim_pty.py::test_read_only_mode_rejects_writes` currently
asserts `result != "OK"`; change it to assert the raise and keep the
`sim.table['Z00'][10] == 60` assertion. Leave every other test untouched.

**Docs:** in `tools/README-burner-sim.md`, amend DISCREPANCIES entries 6 and 7
to note that the raw-error-reply leak and the CRLF retry duplication are now
fixed, leaving the remaining spec-vs-code discrepancies recorded as-is.

Out of scope, leave untouched: `setDaemon` at `protocol.py:77`, the shared
`Frame` singletons, and the checksum/CRLF write-reply spec discrepancies.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc "cd /mnt/d/Antigravity/PellMon-master && ./venv-wsl/bin/python -m pytest tests/test_scotte_protocol_bugs.py tests/test_burner_sim_pty.py tests/test_scotte_protocol_roundtrip.py -q; echo EXIT=$?"</automated>
  </verify>
  <done>All new regression tests pass; the three Scotte-related test files are green; `git diff` on `src/` is limited to `Protocol.run`'s GET branch and `Protocol.setItem`.</done>
</task>

<task type="auto">
  <name>Task 3: Full-suite verification, optional end-to-end, SUMMARY and commit</name>
  <files>.planning/quick/260919-olq-fix-scotte-crlf-retry-duplication-and-se/260919-olq-SUMMARY.md</files>
  <action>
Run the full pytest suite in WSL Debian (same invocation as the baseline) and
compare against the recorded baseline (240 passed, 5 skipped). Any regression
must be fixed, not explained away.

Optional end-to-end (ONLY if it can be done quickly; skip and say so otherwise)
— follow the exact recipe in
`.planning/quick/260919-jiz-*/260919-jiz-SUMMARY.md`: system `python3` with
`venv-wsl` site-packages on `PYTHONPATH`, `dbus-run-session`, `python3 -u`,
throwaway config OUTSIDE the repo, a scottecom-only plugin dir of symlinks in
/tmp, hard timeouts on every command, and kill every spawned process
(`burner_sim.py` included) afterwards. Exercise: one `SetItem` write plus a
read-back, and one `--read-only` write rejection. Report precisely what was and
was not verified — do not claim hardware verification.

Write the SUMMARY at
`.planning/quick/260919-olq-fix-scotte-crlf-retry-duplication-and-se/260919-olq-SUMMARY.md`
covering: the failing-first evidence for both bugs; **the setItem contract
decision and its rationale**, including the finding that
`Getsetitem.value`/`Database.set_value` discard the setter's return value so a
failed write previously reported `'OK'` to the web UI, and why raising is the
compatible signal; the exact diff scope in `src/`; before/after suite counts;
the end-to-end result or the reason it was skipped; and the still-open
spec-vs-code discrepancies plus the explicitly out-of-scope items (`setDaemon`,
`Frame` singletons) carried forward.

Commit only the touched files by explicit path
(`src/Scotteprotocol/protocol.py`, `tests/test_scotte_protocol_bugs.py`,
`tests/test_burner_sim_pty.py`, `tools/README-burner-sim.md`, and the planning
dir files in a separate docs commit). Never `git add -A`/`.`, never stash,
never `git restore`/`checkout --`. The untracked `mqtt-*.json` export must never
be staged or referenced. Do not push.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc "cd /mnt/d/Antigravity/PellMon-master && ./venv-wsl/bin/python -m pytest -q 2>&1 | tail -5"</automated>
  </verify>
  <done>Full suite at or above baseline (240 passed, 5 skipped); SUMMARY written with the contract rationale; commits contain only the explicitly listed paths; nothing pushed.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| burner hardware/sim → `Protocol.run` reads | Untrusted bytes from a serial device are decoded and parsed |
| `Protocol.setItem` return → D-Bus → web UI | Device-controlled text previously flowed toward the UI |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-olq-01 | Information disclosure | `Protocol.setItem` return value | mitigate | Contract in Task 2: raw device reply appears only in logs (`repr()`), never in return values or exception messages reaching the web UI |
| T-olq-02 | Spoofing/Tampering | Device write reply | mitigate | Only a checksum-valid `OK` counts as success; everything else raises |
| T-olq-03 | Denial of service | Retry path | accept | Retry count is unchanged (1 retry, then give up); CRLF fix reduces, not increases, bytes written |
| T-olq-SC | Tampering | package installs | mitigate | No new dependencies are installed by this plan; `venv-wsl` is used read-only |
</threat_model>

<verification>
- `grep -n "frame_term_crlf" src/Scotteprotocol/protocol.py` shows the GET branch applying CRLF exactly once (no occurrence inside the retry block).
- `grep -vn '^\s*#' src/Scotteprotocol/protocol.py | grep -c "return str(e)"` is 0 within `setItem`.
- `git diff --stat` lists only the five files in `files_modified` plus planning docs.
</verification>

<success_criteria>
- Both regression tests failed before the fix and pass after it.
- CRLF retry writes byte-identical, singly-terminated frames.
- `setItem` returns `'OK'` on success and raises `ValueError`/`IOError` otherwise, leaking no raw reply text.
- Full WSL suite at or above 240 passed / 5 skipped.
- SUMMARY documents the contract decision, rationale, and exactly what was/wasn't verified.
</success_criteria>

<output>
Create `.planning/quick/260919-olq-fix-scotte-crlf-retry-duplication-and-se/260919-olq-SUMMARY.md` when done
</output>
