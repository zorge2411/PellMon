---
phase: quick-260920-rpd
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/Pellmonsrv/pellmonsrv.py
  - src/Pellmonsrv/plugins/cleaning/__init__.py
  - src/Pellmonsrv/plugins/consumption/__init__.py
  - src/Pellmonsrv/plugins/silolevel/__init__.py
  - src/Pellmonweb/pellmonweb.py
  - tests/Pellmonsrv/test_rrdtool_bytes_handling.py
  - tests/Pellmonsrv/plugins/test_plugin_rrd_bytes.py
  - tests/Pellmonweb/test_export_bytes.py
autonomous: true
requirements: [PY3-RRD-01, PY3-RRD-02, DEPLOY-PI-01]

must_haves:
  truths:
    - "pellmonsrv starts with polling enabled and does not raise TypeError reading `rrdtool lastupdate` output"
    - "The Poller's failed-update log branch formats rrdtool stdout/stderr without raising TypeError"
    - "Cleaning, Consumption and SiloLevel parse rrdtool output as text and return real values (not silent '0'/None fallbacks)"
    - "The /export web endpoint parses rrdtool xport JSON output without raising TypeError"
    - "The /graph web endpoint still returns raw PNG bytes (unchanged)"
    - "Both daemons stay up >= 30 s in the WSL dry run with no tracebacks in either log"
    - "ScotteCom, SiloLevel, Consumption and Cleaning all appear in the daemon's `Activated plugins:` line"
  artifacts:
    - path: "tests/Pellmonsrv/test_rrdtool_bytes_handling.py"
      provides: "Bytes-output regression tests for pellmonsrv lastupdate + Poller update paths"
    - path: "tests/Pellmonsrv/plugins/test_plugin_rrd_bytes.py"
      provides: "Bytes-output regression tests for cleaning/consumption/silolevel rrdtool parsing"
    - path: "tests/Pellmonweb/test_export_bytes.py"
      provides: "Bytes-output regression test for the /export rrdtool xport parser"
  key_links:
    - from: "src/Pellmonsrv/pellmonsrv.py"
      to: "rrdtool lastupdate stdout"
      via: "decode before .split()"
      pattern: "decode\\("
    - from: "src/Pellmonweb/pellmonweb.py export()"
      to: "rrdtool xport stdout"
      via: "decode before re.sub/json.loads"
      pattern: "decode\\("
---

<objective>
Make the Docker/Raspberry-Pi deployment actually start and keep running by fixing the
Python 2 -> 3 bytes/str bugs on the daemon startup path and in the default-enabled
plugins, backed by failing-first unit tests and an end-to-end WSL dry run.

Purpose: `configparser` interpolation was the first Pi startup crash (already fixed,
02c83c8). The next one is `src/Pellmonsrv/pellmonsrv.py:567-568`, where
`subprocess.check_output(['rrdtool','lastupdate',conf.db])` returns `bytes` and
`s.split('\n')` raises `TypeError`. Polling is on by default, so this kills the daemon
at startup in every default deployment. The same bug class exists at five more rrdtool
call sites, three of them in plugins enabled by default
(`src/conf.d/enabled_plugins.conf`: SiloLevel, Consumption, Cleaning).

Output: minimal, per-call-site fixes; three new regression test files; a dry run in
which both daemons stay up with the default plugin set, RRD updates land, D-Bus reads
return simulator values, and the web UI serves a login page and a PNG graph.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@DEPLOY-PI.md
@src/conf.d/enabled_plugins.conf
@tests/Pellmonsrv/conftest.py
@tests/Pellmonsrv/test_pellmonsrv_logging.py
@tests/test_config_interpolation.py

**Branch discipline (non-negotiable):** work on the current branch
`fix/pi-startup-crashes`. Never switch branches, never commit to master, never push.
Stage only explicit file paths (`git add src/... tests/...`). Never `git add -A`,
`git add .`, `git stash`, `git restore`, or `git checkout --`. The untracked
`mqtt-*.json` file at repo root must never be staged.

**Shell rules:** the dry run is a bash script under WSL Debian. Invoke it from
PowerShell as
`wsl -d Debian -- bash /mnt/c/.../scratchpad/dryrun.sh`
— NOT from Git Bash (it mangles `/mnt` paths). Do not pipe PowerShell output into
`tail`; use `Select-Object -Last N`.

<interfaces>
<!-- The six rrdtool call sites in scope. All currently treat bytes as str. -->

src/Pellmonsrv/pellmonsrv.py:567-576 (MyDaemon.run, startup, polling enabled)
  s = subprocess.check_output(['rrdtool', 'lastupdate', conf.db])
  l = s.split('\n'); items = l[0].split(); values = l[2].split()
  conf.lastupdate_time = int(values[0].strip(':'))   # ValueError already caught
  conf.lastupdate = dict(zip(items, values))

src/Pellmonsrv/pellmonsrv.py:293-299 (Poller.run, every poll interval)
  cmd = subprocess.Popen(RRD_command, stdout=PIPE, stderr=PIPE)
  out, err = cmd.communicate()
  ... logger.info('... %s, %s'%(out.rstrip('\n'), err.rstrip('\n')))  # bytes.rstrip(str)

src/Pellmonsrv/plugins/cleaning/__init__.py:85-89 (rrd_total)
  total = str(int(float(cmd.communicate()[0].splitlines()[1].strip('"'))))
  except Exception: total = '0'      # bug is currently MASKED -> always '0'

src/Pellmonsrv/plugins/consumption/__init__.py:221-239 (rrd_total)
  total = cmd.communicate()[0].splitlines()[1]      # bytes
  ... return total.replace(',', '.')                # bytes.replace(str,str) -> TypeError
  except Exception: total = None                    # bug currently MASKED -> None

src/Pellmonsrv/plugins/silolevel/__init__.py:186-211 (graphData)
  out = cmd.communicate()[0]; return int(out)                       # int(bytes) -> TypeError
  out = cmd.communicate()[0]; out = re.sub(str_pattern, r'...', out) # str pat on bytes -> TypeError

src/Pellmonweb/pellmonweb.py:430-439 (export)
  out, err = cmd.communicate()
  out = re.sub(r'...', r'...', out, flags=re.M)     # str pattern on bytes -> TypeError
  out = json.loads(out)

src/Pellmonweb/pellmonweb.py:354-357 (graph) -- CORRECT AS-IS.
  returns cmd.communicate()[0] as image/png bytes. DO NOT decode this one.

Existing repo decode convention (src/Pellmonsrv/plugins/exec/__init__.py:88):
  .decode('utf-8', errors='replace')
</interfaces>

<test_fixtures>
Realistic rrdtool outputs the tests must feed as BYTES:

`rrdtool lastupdate <db>` on a fresh db (note: blank line 2, data on line 3):
  b"feeder_time boiler_temp power\n\n1758300000: U U U\n"
and on a populated db:
  b"feeder_time boiler_temp power\n\n1758300060: 12 73.5 30\n"

`rrdtool graph ... PRINT:s:"%lf"` (cleaning/consumption): line 0 is the graph size,
line 1 is the printed value:
  b'0x0\n"123.456789"\n'          (cleaning, %lf)
  b'0x0\n"123,46"\n'              (consumption, %.2lf, comma decimal locale)

`rrdtool last <db>` (silolevel): b"1758300060\n"

`rrdtool xport --json ...` (silolevel + web export) -- rrdtool emits unquoted keys and
single quotes, which is exactly why the code runs two `re.sub` passes first:
  b"{ about: 'RRDtool graph JSON output',\n  meta: { start: 1758300000, step: 60,\n"
  b"  end: 1758300060, rows: 1, columns: 1, legend: [ 'level' ] },\n"
  b"  data: [ [ 1.0e+02 ] ]\n}\n"
</test_fixtures>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Failing-first bytes/str regression tests for every rrdtool call site</name>
  <files>tests/Pellmonsrv/test_rrdtool_bytes_handling.py, tests/Pellmonsrv/plugins/test_plugin_rrd_bytes.py, tests/Pellmonweb/test_export_bytes.py</files>
  <behavior>
    - pellmonsrv lastupdate: with `subprocess.check_output` monkeypatched to return the
      fresh-db BYTES fixture, the startup parsing logic populates `conf.lastupdate_time`
      (int) and `conf.lastupdate` (dict of DS name -> value str) without raising TypeError.
    - pellmonsrv lastupdate, populated db: `conf.lastupdate_time == 1758300060` and
      `conf.lastupdate['boiler_temp'] == '73.5'`.
    - pellmonsrv lastupdate, truncated/empty output (b"" and b"header\n"): does not raise
      IndexError; falls back to a time-based `lastupdate_time` and an empty/partial dict.
    - Poller failure branch: fake Popen with returncode 1 and BYTES stdout/stderr
      (b"ERROR: ...\n") logs one message containing the decoded stderr text, no TypeError.
    - cleaning.rrd_total: with fake Popen returning b'0x0\n"123.456789"\n', returns "123"
      (currently returns "0" because the TypeError is swallowed by the bare except).
    - consumption.rrd_total: with fake Popen returning b'0x0\n"123,46"\n', returns a str
      containing "." and not "," (currently returns None).
    - silolevel getLastUpdateTime: with b"1758300060\n", returns int 1758300060.
    - silolevel siloLevelData: with the xport BYTES fixture, returns a dict whose
      ["data"] is a list (no TypeError from re.sub on bytes).
    - pellmonweb export: with fake Popen returning the xport BYTES fixture and
      returncode 0, JSON parsing succeeds and `out["data"]` is reachable.
  </behavior>
  <action>
    Write the three test files. Follow existing conventions: the fake-manager /
    monkeypatch style of tests/Pellmonsrv/test_pellmonsrv_logging.py, the `daemon_module`
    fixture from tests/Pellmonsrv/conftest.py for anything importing
    Pellmonsrv.pellmonsrv, and the plugin-import style of tests/test_plugin_loader.py and
    tests/Pellmonsrv/plugins/test_calculate_hardening.py.

    Never invoke a real rrdtool binary: monkeypatch `subprocess.check_output` and
    `subprocess.Popen` in the module under test. Use a small `_FakePopen` helper exposing
    `communicate()` returning a `(stdout_bytes, stderr_bytes)` tuple and a `returncode`
    attribute, shared per file.

    For the pellmonsrv startup lastupdate logic: the parsing currently lives inline inside
    `MyDaemon.run()`, which cannot be called in a test. Do NOT restructure it in this task
    — instead write the test against the helper function that Task 2 will extract
    (`read_lastupdate(db_path)` at module level in pellmonsrv.py, returning
    `(lastupdate_time, lastupdate_dict)`). The test therefore fails on AttributeError
    until Task 2 lands, which is the intended RED state. Document this in the module
    docstring the same way test_pellmonsrv_logging.py documents its RED state.

    Tests must run on Windows where possible: no real subprocess, no dbus/gi import
    outside the `daemon_module` fixture, no filesystem paths outside tmp_path. Only skip
    for genuinely missing dbus/gi (reuse the existing skip patterns, do not invent new ones).

    Run the new tests and CONFIRM THEY FAIL before touching src/. Record the failure
    output in the SUMMARY evidence.

    Commit (tests only, explicit paths):
    `test(quick-260920-rpd): add failing bytes/str regression tests for rrdtool parsing`
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc 'cd /mnt/d/Antigravity/PellMon-master &amp;&amp; venv-wsl/bin/python -m pytest tests/Pellmonsrv/test_rrdtool_bytes_handling.py tests/Pellmonsrv/plugins/test_plugin_rrd_bytes.py tests/Pellmonweb/test_export_bytes.py -q -p no:cacheprovider'</automated>
  </verify>
  <done>All three test files exist and every new test FAILS (TypeError / AttributeError / wrong-value assertion), with no errors caused by the test harness itself (no import errors, no accidental real-rrdtool invocation). Baseline suite re-run recorded: 252 passed, 6 skipped before these files were added.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fix the six rrdtool bytes/str call sites, one commit per logical fix</name>
  <files>src/Pellmonsrv/pellmonsrv.py, src/Pellmonsrv/plugins/cleaning/__init__.py, src/Pellmonsrv/plugins/consumption/__init__.py, src/Pellmonsrv/plugins/silolevel/__init__.py, src/Pellmonweb/pellmonweb.py</files>
  <behavior>
    Every test written in Task 1 turns GREEN, and the existing suite stays at its
    252 passed / 6 skipped baseline (plus the new passing tests).
  </behavior>
  <action>
    Minimal, surgical fixes. Decode with `.decode('utf-8', errors='replace')` to match the
    existing repo convention in src/Pellmonsrv/plugins/exec/__init__.py:88. Match
    surrounding indentation exactly; do not reformat blocks; use `%`-formatting for log
    messages; no type hints. Keep GPL headers untouched.

    1. src/Pellmonsrv/pellmonsrv.py startup lastupdate (currently lines 566-576): extract
       the parsing into a module-level `read_lastupdate(db_path)` returning
       `(lastupdate_time, lastupdate_dict)`. Inside it, decode `check_output` stdout before
       `.split('\n')`, and guard short/empty output (fewer than 3 lines) by returning
       `(int(time.time()), {})` instead of raising IndexError. Keep the existing ValueError
       fallback behaviour. Replace the inline block in `MyDaemon.run()` with a call that
       assigns `conf.lastupdate_time` and `conf.lastupdate`.
       Commit: `fix(pellmonsrv): decode rrdtool lastupdate output before parsing`

    2. src/Pellmonsrv/pellmonsrv.py Poller (lines 294-299): decode `out` and `err` before
       the `.rstrip('\n')` in the failed-update log message.
       Commit: `fix(pellmonsrv): decode rrdtool update stdout/stderr before logging`

    3. src/Pellmonsrv/plugins/cleaning/__init__.py:85-89: decode `communicate()[0]` before
       `.splitlines()[1].strip('"')`. Leave the existing except/'0' fallback in place.
       Commit: `fix(cleaning): decode rrdtool graph PRINT output before parsing total`

    4. src/Pellmonsrv/plugins/consumption/__init__.py:221-239: decode `communicate()[0]`
       before `.splitlines()[1]`, so the cached `Bardata` holds a str and the
       `total.replace(',', '.')` at the end works.
       Commit: `fix(consumption): decode rrdtool graph PRINT output before caching total`

    5. src/Pellmonsrv/plugins/silolevel/__init__.py:188-189 and 206-207: decode before
       `int(out)` (strip whitespace) and before the two `re.sub` passes feeding
       `json.loads`.
       Commit: `fix(silolevel): decode rrdtool last/xport output before parsing`

    6. src/Pellmonweb/pellmonweb.py export() at 430-439: decode `out` and `err` before the
       `re.sub`/`json.loads` and before the `cherrypy.log` failure message.
       DO NOT TOUCH graph() at 354-357 — it correctly returns PNG bytes. Add a one-line
       comment there stating the bytes return is intentional, so a future audit does not
       "fix" it.
       Commit: `fix(pellmonweb): decode rrdtool xport output in export endpoint`

    Then audit the rest of the startup / first-poll path for remaining py2-isms and record
    findings (do not fix anything outside this path — it goes in the SUMMARY as a finding):
    str/bytes at socket, dbus and sqlite boundaries; `dict.keys()`/`map()`/`filter()` being
    indexed or len()'d; integer vs true division; `unicode(`. `setDaemon` is deprecated but
    functional — LEAVE IT. Use targeted greps over src/ excluding *.py2bak.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc 'cd /mnt/d/Antigravity/PellMon-master &amp;&amp; venv-wsl/bin/python -m pytest tests -q -p no:cacheprovider'</automated>
  </verify>
  <done>All Task 1 tests pass; full suite shows 252 + new tests passed, 6 skipped, 0 failed; six separate commits exist on fix/pi-startup-crashes, each touching only its own file(s) by explicit path; `git status --short` still shows mqtt-*.json as untracked and unstaged.</done>
</task>

<task type="auto">
  <name>Task 3: Iterate the WSL dry run until both daemons run clean for >= 30 s</name>
  <files>scratchpad/dryrun2.sh (scratchpad only — NOT committed), plus any src/ files needing further real fixes</files>
  <action>
    Copy the existing dry-run script from
    `C:/Users/peter/AppData/Local/Temp/claude/D--Antigravity-PellMon-master/63772f98-a473-45cf-9c73-f8fadf45d20e/scratchpad/dryrun.sh`
    into your own scratchpad as `dryrun2.sh` and adapt it. Keep its existing structure:
    conf.d built exactly as DEPLOY-PI.md step 4a with `@localstatedir@` pointed at a temp
    dir, `tools/burner_sim.py` on a pty, both daemons under `dbus-run-session`, config
    derived from `config/pellmon.conf.example`. All throwaway config lives OUTSIDE the repo
    (under /tmp inside WSL). Run every python process with `python3 -u`. Wrap the whole
    session in `timeout`.

    Adaptations required:
    - Set a short `pollinterval` (~5 s) in the generated config.
    - Extend the run so both daemons are alive >= 30 s after start; assert liveness with
      `kill -0` at the 30 s mark, not just at the end.
    - Add D-Bus reads: `dbus-send --session --print-reply --dest=org.pellmon.int /org/pellmon/int org.pellmon.int.GetItem string:boiler_temp` (and `power`), asserting the returned values match what the simulator serves.
    - Assert the RRD file is created and receives >= 1 update after the short poll
      interval: `rrdtool lastupdate <db>` timestamp advances between two samples taken
      ~10 s apart; also capture `rrdtool info <db>` last_update.
    - `curl -s -o /dev/null -w "%{http_code}"` on `/` must be 200 or a 3xx redirect to
      login — never 500.
    - Login with the generated test hash (the script already creates one via
      `Pellmonweb.auth.hash_password`); assert the authenticated request succeeds.
    - Fetch the graph endpoint for the default graph lines and assert the response starts
      with the PNG magic bytes `\x89PNG` (`head -c4 | xxd`).
    - First check `which rrdtool` in WSL Debian. If it is missing, DO NOT `apt install`
      without reporting — report exactly which checks could not be performed and continue
      with the rest.

    Success gate for the daemon log: `Activated plugins:` lists ScotteCom, SiloLevel,
    Consumption and Cleaning, and neither `srv.log` nor `web.log` contains `Traceback`.
    If a plugin fails to activate, FIX THE REAL CAUSE — do not disable the plugin and do
    not edit enabled_plugins.conf.

    Iterate: each further real crash found on this startup/first-poll path gets its own
    minimal fix plus, where unit-testable, a test added to the Task 1 files, and its own
    commit (explicit paths only). Anything outside this path is recorded as a SUMMARY
    finding, not fixed.

    Cleanup is mandatory on every run: kill pellmonsrv, pellmonweb, burner_sim and the
    dbus-daemon spawned by dbus-run-session; finish with
    `pgrep -af "burner_sim|Pellmonsrv|Pellmonweb|dbus-daemon"` and assert it reports none.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash /mnt/c/Users/peter/AppData/Local/Temp/claude/D--Antigravity-PellMon-master/63772f98-a473-45cf-9c73-f8fadf45d20e/scratchpad/dryrun2.sh</automated>
  </verify>
  <done>Dry run output shows: both daemons alive at the 30 s mark; `Activated plugins:` includes ScotteCom, SiloLevel, Consumption, Cleaning; zero `Traceback` lines in srv.log and web.log; GetItem returns simulator values for boiler_temp and power; RRD lastupdate timestamp advanced at least once; `/` returned 200 or a login redirect; authenticated login succeeded; graph response begins with the PNG magic bytes; final pgrep reports no leftover processes.</done>
</task>

<task type="auto">
  <name>Task 4: Final suite verification and SUMMARY with findings</name>
  <files>.planning/quick/260920-rpd-fix-bytes-str-bugs-so-docker-config-star/260920-rpd-SUMMARY.md</files>
  <action>
    Re-run the full suite in WSL Debian and compare against the 252 passed / 6 skipped
    baseline. Then run the dbus/gi-dependent functional tests that skip under venv-wsl with
    the system python3:
    `PYTHONPATH=src:venv-wsl/lib/python3.13/site-packages python3 -m pytest <file> -q -p no:cacheprovider`
    for each file that reported a dbus/gi skip, and record their results separately.

    Write the SUMMARY covering: each call site fixed and the commit hash for it; the RED
    evidence from Task 1 (the actual failure messages); the dry-run evidence for every gate
    in Task 3's done criteria; any check that could not be performed (e.g. rrdtool missing)
    stated explicitly; and a `## Findings (not fixed)` section listing every py2-ism or bug
    found outside the startup / first-poll path, with file:line and why it was out of scope.

    Do not push. Confirm the branch is still `fix/pi-startup-crashes` and that
    `git status --short` shows no staged mqtt-*.json.
  </action>
  <verify>
    <automated>wsl -d Debian -- bash -lc 'cd /mnt/d/Antigravity/PellMon-master &amp;&amp; venv-wsl/bin/python -m pytest tests -q -p no:cacheprovider &amp;&amp; git status --short --porcelain | grep -c "^A" ; git branch --show-current'</automated>
  </verify>
  <done>Full suite passes with no regressions against the 252/6 baseline; dbus/gi functional tests run under system python3 and their results recorded; SUMMARY.md written with per-fix commit hashes, RED evidence, dry-run evidence, unperformed checks, and a Findings section; branch is fix/pi-startup-crashes, nothing pushed, nothing staged.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| rrdtool subprocess -> daemon/web process | Untrusted-ish external process output parsed as JSON/floats |
| burner serial/pty -> daemon | Simulator stands in for hardware during the dry run |
| HTTP client -> pellmonweb | /export and /graph args reach the rrdtool argv builder |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-rpd-01 | Tampering | rrdtool xport output -> `json.loads` in pellmonweb export() and silolevel | mitigate | Decode with `errors='replace'` (no crash on malformed bytes); parsing stays inside the existing try/except so a malformed payload cannot kill the request thread |
| T-rpd-02 | Denial of Service | `read_lastupdate` on a fresh/truncated RRD file | mitigate | Guard short output and fall back to `int(time.time())` + empty dict instead of raising IndexError at daemon startup |
| T-rpd-03 | Information disclosure | Decoded rrdtool stderr written to logs | accept | Contains only DS names and file paths already present in config; no secrets |
| T-rpd-04 | Elevation of privilege | Dry-run config and RRD files | mitigate | All throwaway state under /tmp outside the repo; no privileged flags; every spawned process killed and verified with pgrep |
| T-rpd-SC | Tampering | npm/pip/cargo installs | mitigate | No new dependencies are installed by this plan; `apt install` is forbidden without first reporting |
</threat_model>

<verification>
- `wsl -d Debian -- bash -lc 'cd /mnt/d/Antigravity/PellMon-master && venv-wsl/bin/python -m pytest tests -q'` — no regressions vs 252 passed / 6 skipped.
- `grep -rn "communicate()\|check_output" src/ --include=*.py | grep -v py2bak` — every hit either decodes its output or is the intentional PNG-bytes return in pellmonweb graph().
- Dry run (Task 3) green on all gates.
- `git log --oneline fix/pi-startup-crashes` shows one commit per logical fix, none on master, nothing pushed.
</verification>

<success_criteria>
- pellmonsrv starts with polling enabled and no TypeError from the lastupdate path.
- All six rrdtool call sites handle bytes correctly; graph() still returns PNG bytes.
- Cleaning/Consumption/SiloLevel return real values instead of masked '0'/None fallbacks.
- Failing-first tests exist for every fixed call site, confirmed RED then GREEN.
- Both daemons run >= 30 s clean in the dry run with the four default plugins activated,
  RRD updating, D-Bus reads working, web root and PNG graph served.
- Out-of-path issues are documented as findings, not fixed.
</success_criteria>

<output>
Create `.planning/quick/260920-rpd-fix-bytes-str-bugs-so-docker-config-star/260920-rpd-SUMMARY.md` when done
</output>
</content>
</invoke>
