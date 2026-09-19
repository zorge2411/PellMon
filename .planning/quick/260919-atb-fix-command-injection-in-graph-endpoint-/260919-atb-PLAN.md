---
phase: quick-260919-atb
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/Pellmonweb/rrdcommand.py
  - src/Pellmonweb/pellmonweb.py
  - src/Pellmonweb/pellmonconf.py
  - src/pellmoncli.in
  - tests/Pellmonweb/test_rrd_command_injection.py
  - tests/Pellmonweb/test_pellmonconf_path_traversal.py
  - tests/test_pellmoncli_py3.py
autonomous: true
requirements: [SEC-Q1, SEC-Q2, PY3-Q3]

must_haves:
  truths:
    - "The /graph endpoint builds its rrdtool invocation as an argument list and runs it with shell=False"
    - "Shell metacharacters in bgcolor, legends, logtick, line name/color/ds_name, and numeric params cannot reach a shell or forge extra rrdtool arguments"
    - "pellmonconf source() and save() only read/write files whose request-supplied name is a key of self.dirs; anything else (absolute paths, ../ traversal, unknown names) is rejected"
    - "src/pellmoncli.in compiles under Python 3 and contains no py2-only constructs (print statement, raw_input, iteritems, except X, e)"
    - "pytest suite passes with no new failures beyond the known baseline"
  artifacts:
    - path: "src/Pellmonweb/rrdcommand.py"
      provides: "Importable, dbus-free rrdtool graph argv builder + validators"
      exports: ["build_graph_command"]
    - path: "tests/Pellmonweb/test_rrd_command_injection.py"
      provides: "Metacharacter/injection regression tests for the graph argv builder"
    - path: "tests/Pellmonweb/test_pellmonconf_path_traversal.py"
      provides: "Arbitrary file read/write regression tests for source()/save()"
    - path: "tests/test_pellmoncli_py3.py"
      provides: "Py3 compile + py2-construct scan gate for src/pellmoncli.in"
  key_links:
    - from: "src/Pellmonweb/pellmonweb.py"
      to: "src/Pellmonweb/rrdcommand.py"
      via: "import build_graph_command, called in graph()"
      pattern: "build_graph_command"
    - from: "src/Pellmonweb/pellmonweb.py graph()"
      to: "subprocess.Popen"
      via: "argv list, shell=False"
      pattern: "shell=False"
---

<objective>
Close two web-facing security holes and finish the Python 3 port of the CLI.

Purpose: `/graph` passes an attacker-influenced string to `subprocess.Popen(..., shell=True)` (command injection), and `pellmonconf.source()/save()` open arbitrary request-supplied filenames (arbitrary file read/write as the web user, which the tool's own banner tells people to run as root). `src/pellmoncli.in` still contains Python 2 `print` statements and `raw_input`, so it is a hard SyntaxError under Python 3.

Output: a dbus-free `rrdcommand.py` argv builder wired into `graph()` with `shell=False`, an allowlist-based `source()/save()`, a Python 3 `pellmoncli.in`, and three new test modules.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@./CLAUDE.md
@.planning/STATE.md
@src/Pellmonweb/pellmonweb.py
@src/Pellmonweb/pellmonconf.py
@src/pellmoncli.in
@tests/conftest.py
@pytest.ini

<working_tree_constraint>
Execution runs on the MAIN tree (no worktree). `src/Pellmonweb/pellmonconf.py` and `src/pellmoncli.in` already carry pre-existing uncommitted user changes, and ~25 other files under `src/` have unrelated WIP.

- Stage ONLY the seven paths in `files_modified` — `git add <explicit path>` per file.
- NEVER `git add -A`, `git add .`, `git commit -a`, `git checkout -- <path>`, `git stash`, or `git restore` anything.
- Do not revert, reformat, or "clean up" the user's existing uncommitted edits in the files you touch — make your changes on top of the current working-tree content.
</working_tree_constraint>

<interfaces>
<!-- Current state the executor works against. No codebase exploration needed. -->

src/Pellmonweb/pellmonweb.py — module-level globals populated at config load (lines ~842-883):
  colorsDict : dict          # key -> color string, from config
  graph_lines : list[dict]   # each: {'name': str, 'color': str, 'ds_name': str, optional 'scale': 'off:gain'}
  logtick : str | None       # a ds_name, or None
  db : str                   # path to the .rrd file (from config, NOT request-supplied)

graph() request-derived values (lines ~255-368), each already int()-coerced or defaulted:
  timespan, graphtime, timeoffset : int-ish (graphtime/graphTimeStart/graphTimeEnd are str()'d)
  graphWidth : int, clamped <= 5000
  graphHeight : int, clamped <= 2000
  lines : list[str] | '__all__'   # from args['lines'].split(',') — UNVALIDATED request data
  legends : '' or ' --no-legend '
  bgcolor : ' ' or ' --color BACK#<raw args["bgcolor"]>'   # <-- hex check is bypassable: len != 6 skips int(,16)
  rightaxis : '' or '--right-axis 1:0' / '--right-axis <gain>:<offset>'

The safe reference pattern already exists in the same file — export() at lines 443-466 builds
a list and calls subprocess.Popen(RRD_command, shell=False, ...). Mirror it.

src/Pellmonweb/pellmonconf.py — Pellmonconf.__init__ builds:
  self.filelist : list[str]        # display names, e.g. 'pellmon.conf', 'conf.d/email.conf'
  self.dirs : dict[str, str]       # same display name -> directory to join with
source() currently joins only when `filename in self.dirs`, then falls through and opens the
RAW filename otherwise. save() never consults self.dirs at all.

Tests: pytest.ini sets `pythonpath = src`, `testpaths = tests`. pytest-socket blocks real sockets.
tests/conftest.py provides `cherrypy_request_ctx` (patches cherrypy.request/session/log).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Replace shell=True graph command with a validated argv builder</name>
  <files>src/Pellmonweb/rrdcommand.py, src/Pellmonweb/pellmonweb.py, tests/Pellmonweb/test_rrd_command_injection.py</files>
  <behavior>
    - build_graph_command returns a list whose first element is 'rrdtool' and second is 'graph'; no element contains an embedded shell metacharacter that originated from unvalidated input.
    - bgcolor='ff0000' produces the pair ['--color', 'BACK#ff0000'].
    - bgcolor='0; rm -rf /' , bgcolor='$(id)', bgcolor='aa`id`bb', bgcolor='ff0000 --imginfo /etc/passwd' are ALL rejected: no '--color' argument is emitted (and no argument contains 'rm', 'id', or '--imginfo').
    - legends='no' emits '--no-legend'; any other legends value emits no legend flag.
    - a graph_line whose 'name' is 'temp; id' or 'a b' or 'a:b' is skipped entirely (not emitted as DEF/LINE1).
    - a graph_line whose 'color' is '#00ff00' is emitted; color 'red; id', '00ff00 XPORT:x', and '#gggggg' are skipped.
    - a graph_line whose 'ds_name' contains ':' or ';' or whitespace is skipped.
    - logtick='badname;id' emits no tickmark DEF/TICK args; logtick='valid_ds' emits them.
    - width/height/timespan/offset inputs that are non-numeric strings raise ValueError or fall back to the documented default — they never appear verbatim in the argv.
    - Every element of the returned list is a str (rrdtool argv must not contain ints).
  </behavior>
  <action>
Create `src/Pellmonweb/rrdcommand.py` with the standard project GPL header (copy the header block from `src/Pellmonweb/pellmonconf.py`), `#!/usr/bin/env python3`, `# -*- coding: utf-8 -*-`, and `logger = getLogger('pellMon')`. This module must import ONLY stdlib (re, logging) so it is importable on the Windows dev box without dbus/gi/cherrypy.

Define module-level compiled validators and small helpers:
- `_HEX_COLOR = re.compile(r'\A[0-9A-Fa-f]{6}\Z')` and `valid_bgcolor(value)` returning bool. The current code's `if len(bgcolor) == 6` guard is the bug — the regex must be the only gate, applied unconditionally, with no length shortcut.
- `_RRD_NAME = re.compile(r'\A[A-Za-z0-9_]{1,64}\Z')` and `valid_name(value)` for DEF vnames, line names, and ds_names. rrdtool vnames are alphanumeric/underscore only; ':' is the rrdtool field separator and is the primary forgery vector, so it must never pass.
- `_LINE_COLOR = re.compile(r'\A#?[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?\Z')` and `valid_color(value)` (optional leading '#', 6 hex digits, optional 2-digit alpha). Normalize the return so the emitted argument always has exactly one leading '#'.
- `_coerce_int(value, default, minimum=None, maximum=None)` that returns `default` on TypeError/ValueError and clamps to the bounds.

Define `build_graph_command(db, graph_lines, lines, logtick=None, legends=None, bgcolor=None, width=440, height=400, graphtime=None, time_start='', time_end='', right_axis=None)` returning `list[str]`.

Semantics, translated from the current string construction at pellmonweb.py:370-389 (preserve rrdtool behavior exactly — this is a security fix, not a feature change):
- Start with `['rrdtool', 'graph', '-', '--disable-rrdtool-tag', '--border', '0']`.
- If `legends == 'no'`, append `'--no-legend'`. Ignore any other value.
- If `bgcolor` passes `valid_bgcolor`, append `'--color'` then `'BACK#' + bgcolor`. Otherwise append nothing and `logger.warning('rejected bgcolor argument: %r', bgcolor)`.
- Append `'--lower-limit', '0'`.
- If `right_axis` is provided, append `'--right-axis'` then the `'gain:offset'` string built from floats by the caller — coerce both halves through `float()` inside this function and re-render with `'%s:%s'`, so a malicious `scale` config string cannot pass through. Always append `'--right-axis-format', '%1.0lf'`.
- Append `'--full-size-mode'`, `'--width', str(width)`, `'--height', str(height)` using `_coerce_int` (width max 5000, height max 2000, both min 1).
- Append `'--end', '%s-%ss' % (graphtime, time_end)` and `'--start', '%s-%ss' % (graphtime, time_start)`, with graphtime/time_start/time_end each passed through `_coerce_int` first. Note: the existing string version interpolates these values with the trailing 's' suffix already present in `graphTimeEnd`/`graphTimeStart` usage — emit exactly one 's' suffix per argument; verify against the export() form at pellmonweb.py:444, which is the known-correct list version.
- If `logtick` is truthy AND `valid_name(logtick)`, append `'DEF:tickmark=%s:%s:AVERAGE' % (db, logtick)` and `'TICK:tickmark#E7E7E7:1.0'`. If truthy but invalid, skip and log a warning.
- For each `line` in `graph_lines` where `lines == '__all__' or line['name'] in lines`: validate `line['name']`, `line['ds_name']` with `valid_name` and `line['color']` with `valid_color`. If any fails, `logger.warning` and `continue` — skip that line rather than aborting the whole graph. Then append `'DEF:%s=%s:%s:AVERAGE' % (name, db, ds_name)`. If `'scale'` in line, split on ':' and `float()` both halves inside a try/except (falling back to gain=1, offset=0 exactly as today), then append the `CDEF:%s_s=%s,%d,+,%d,/` and `LINE1:%s_s%s:%s` arguments; else append `LINE1:%s%s:%s`. IMPORTANT: the LINE1 legend text must NOT be wrapped in literal `"` quotes — those quotes were only needed because the old string went through a shell. With shell=False, embedded quotes would appear verbatim in the rendered legend.
- Finally, assert/ensure every element is a `str` before returning.

In `src/Pellmonweb/pellmonweb.py`: add `from Pellmonweb.rrdcommand import build_graph_command` alongside the existing imports (match the file's existing import style for sibling modules). Replace the block at lines ~369-390 — delete the `RRD_command = "rrdtool graph - ..."` string construction and the per-line string concatenation, and call `build_graph_command(...)` with the already-computed `db`, `graph_lines`, `lines`, `logtick`, `graphWidth`, `graphHeight`, `graphtime`, `graphTimeStart`, `graphTimeEnd`, and the raw `args.get('legends')` / `args.get('bgcolor')`. Keep the existing `legends`/`bgcolor` local-variable derivation OUT of the command path — pass the raw request values to the builder and let the builder validate; delete the now-dead pre-formatting at lines 315-330 (the `' --no-legend '` and `' --color BACK#'` string fragments) so there is exactly one validation site. Similarly, pass the right-axis gain/offset as a `gain:offset` string rather than a pre-built `--right-axis ...` fragment.
Then call `subprocess.Popen(RRD_command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)`, mirroring export() at line 466. Leave the response headers and `cmd.communicate()[0]` return behavior unchanged.

Create `tests/Pellmonweb/test_rrd_command_injection.py` with a module docstring explaining that these are regression tests for the shell=True command injection in `/graph`. Import `build_graph_command` and the validators directly from `Pellmonweb.rrdcommand` — do NOT import `Pellmonweb.pellmonweb` (it pulls in dbus/gi, unavailable on Windows). Cover every bullet in `<behavior>`, and add a parametrized case sweeping the metacharacter set `; | & $ ` > < \n \\ ' " ( ) { } *` through bgcolor, logtick, line name, line color, and ds_name, asserting the payload substring appears in NO element of the returned argv. Add one test asserting `all(isinstance(a, str) for a in cmd)`.
Also add a source-level guard test that reads `src/Pellmonweb/pellmonweb.py` and asserts `'shell=True'` does not appear anywhere in it (use pathlib from the repo root, same style as `tests/test_no_ad_hoc_print.py`).
  </action>
  <verify>
    <automated>python -m pytest tests/Pellmonweb/test_rrd_command_injection.py -q</automated>
  </verify>
  <done>All new tests pass; `grep -n "shell=True" src/Pellmonweb/pellmonweb.py` returns nothing; graph() calls build_graph_command and Popen with shell=False.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Restrict pellmonconf source()/save() to the known config-file allowlist</name>
  <files>src/Pellmonweb/pellmonconf.py, tests/Pellmonweb/test_pellmonconf_path_traversal.py</files>
  <behavior>
    - source('pellmon.conf') on an instance whose self.dirs contains that key reads the resolved file and returns JSON with 'data'.
    - source('/etc/passwd'), source('C:\\Windows\\win.ini'), source('../../etc/passwd'), source('conf.d/../../../etc/passwd'), source(None), source('') all return JSON containing an 'error' key and no 'data' key, and never open a file.
    - save() with a filename not in self.dirs returns {'success': False, 'error': ...} and writes nothing (assert the target path does not exist / open was never called).
    - save() on a non-POST request still returns the existing 'only POST' error shape (unchanged).
    - save() with an allowed filename on a POST request writes to the resolved path under self.dirs and returns {'success': True}.
    - The resolved path is confirmed to still live under its mapped directory after normalization (defense in depth against a crafted self.dirs entry).
  </behavior>
  <action>
Add a private helper `_resolve(self, filename)` to the `Pellmonconf` class that returns the absolute on-disk path for an allowed `filename`, or raises `ValueError` otherwise. Rules, in order:
1. If `filename` is not a `str` or is empty -> raise `ValueError('no filename')`.
2. If `filename not in self.dirs` -> raise `ValueError('not an allowed config file')`. This is the core allowlist: `self.dirs` keys are exactly the display names built in `__init__` from `pellmon.conf` plus the discovered `conf.d/*.conf` files. Do NOT normalize-then-check, and do NOT attempt to sanitize traversal sequences — membership in `self.dirs` is the only gate, so `../` payloads simply fail the lookup.
3. Build `path = os.path.realpath(os.path.join(self.dirs[filename], filename))` and confirm `os.path.commonpath([path, os.path.realpath(self.dirs[filename])]) == os.path.realpath(self.dirs[filename])`; raise `ValueError('path escapes config directory')` if not.

Rewrite `source(self, filename=None)` to call `self._resolve(filename)` inside the existing try block and open the returned path. Remove the current `if filename in self.dirs: filename = os.path.join(...)` fall-through, which is what allows an unknown name to be opened raw. Keep the existing response shape: on success `json.dumps({'filename': filename, 'data': data, 'line': 1, 'linesep': linesep})` — return the ORIGINAL display name in the `'filename'` field, not the resolved absolute path, so the on-disk layout is not leaked to the client. On `ValueError`/`OSError`, keep returning `json.dumps({'error': str(e)})`.

Rewrite `save(self, filename='', data=None)` so the POST branch calls `self._resolve(filename)` before opening, and catches `(ValueError, OSError)` (widen from the current `IOError`-only catch) returning `{'success': False, 'error': str(e)}`. Leave the non-POST branch exactly as-is.

Log each rejection with `logger.warning('rejected config file access: %r', filename)` using the module's existing `logger`. Match the file's existing `%`-formatting and indentation style; do not add type hints (the codebase has none) and do not reformat untouched code.

Create `tests/Pellmonweb/test_pellmonconf_path_traversal.py`. `Pellmonweb.pellmonconf` imports cherrypy/mako/configparser but NOT dbus, so it is directly importable. Construct the instance without running the real `__init__` file walk: instantiate `Pellmonconf(config_file=str(tmp_path / 'pellmon.conf'), lookup=None)` after writing a real `pellmon.conf` into `tmp_path`, then assert/adjust `inst.dirs` to the expected mapping. Use the `cherrypy_request_ctx` fixture for the save() tests and set `cherrypy.request.method` to `'POST'` / `'GET'` as needed. Cover every bullet in `<behavior>`, and parametrize the rejection cases over the traversal/absolute-path payload list. For the "never opens a file" assertions, use `mocker.patch('codecs.open')` and assert it was not called.
  </action>
  <verify>
    <automated>python -m pytest tests/Pellmonweb/test_pellmonconf_path_traversal.py -q</automated>
  </verify>
  <done>All new tests pass; source() and save() both route through _resolve(); no code path opens a raw request-supplied filename.</done>
</task>

<task type="auto">
  <name>Task 3: Port src/pellmoncli.in to Python 3 and gate it with a compile test</name>
  <files>src/pellmoncli.in, tests/test_pellmoncli_py3.py</files>
  <action>
Port `src/pellmoncli.in` to Python 3. Known py2 constructs:
- line 66: `print getItem(item)` -> `print(getItem(item))`
- line 69: `print setItem(args.item, args.value)` -> `print(setItem(args.item, args.value))`
- line 73: `print "\n".join(l)` -> `print("\n".join(l))`
- line 90: `a=raw_input(">")` -> `a=input(">")`
- line 98: `print item, getItem(item)` -> `print(item, getItem(item))`
- line 104: `print getItem(l[1])` -> `print(getItem(l[1]))`
- line 106: `print "dbus error"` -> `print("dbus error")`
- line 108: `print l[1]+" is not a data/parameter name "` -> `print(l[1]+" is not a data/parameter name ")`
- line 112: `print setItem(l[1], ' '.join(l[2:]))` -> `print(setItem(l[1], ' '.join(l[2:])))`
- line 114: `print l[1]+" is not a parameter/command name"` -> `print(l[1]+" is not a parameter/command name")`
Then scan the whole file for any remaining py2-only construct: `except X, e:`, `iteritems`/`iterkeys`/`itervalues`, `has_key`, `unicode(`, `basestring`, `xrange`, `<>`, backtick repr, `raise X, y`, octal `0755` literals, `from string import maketrans`. Fix any found; also fix the tab-indented `return` at line 51 (`\treturn notify.GetItem(...)` inside `getItem`) to 8 spaces — mixed tabs/spaces is a TabError risk under Python 3.

These `print()` calls are the CLI's intended user-facing output and are exempt from the OBS-03 no-print sweep (which only covers `src/Pellmonsrv` and `src/Pellmonweb` — `src/pellmoncli.in` is outside both, so `tests/test_no_ad_hoc_print.py` needs no change; confirm this before touching that test).

Note `getItem` at line 129 is called at module scope inside `__main__` before `notify` is bound as a global — it works because `notify` is assigned at module level first. Do not restructure; this port is syntax-only.

Create `tests/test_pellmoncli_py3.py` modeled on `tests/test_no_ad_hoc_print.py` (pathlib from `REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]`). It must NOT import the module (it imports `gi`, unavailable on Windows). Instead:
1. Read `src/pellmoncli.in` as text and assert `compile(source, 'pellmoncli.in', 'exec')` succeeds — this is the primary gate and fails loudly on any py2 print/syntax.
2. Walk the resulting AST and assert no `ast.Name` with id in `{'raw_input', 'unicode', 'basestring', 'xrange', 'long'}` is loaded.
3. Regex-assert the source contains no `\.iteritems\(|\.iterkeys\(|\.itervalues\(|\.has_key\(` and no `except\s+\w+\s*,\s*\w+\s*:`.
4. Assert the file contains no literal tab character in its indentation.
  </action>
  <verify>
    <automated>python -m pytest tests/test_pellmoncli_py3.py -q</automated>
  </verify>
  <done>src/pellmoncli.in compiles under Python 3; the new gate test passes and would fail if any py2 construct were reintroduced.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Browser -> CherryPy `/graph` query args | Untrusted `bgcolor`, `legends`, `lines`, `width`, `height`, `time*` cross here into a subprocess invocation |
| Browser -> CherryPy pellmonconf `/source`, `/save` | Untrusted `filename` and `data` cross here into filesystem read/write |
| Config file -> `graph_lines` / `logtick` | Semi-trusted; a compromised or sloppy `conf.d/*.conf` currently reaches the shell verbatim |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-Q1-01 | Elevation of Privilege | `Root.graph()` `subprocess.Popen(shell=True)` (pellmonweb.py:390) | mitigate | Task 1: argv list + `shell=False`; regex allowlists for bgcolor/name/ds_name/color; ints coerced and clamped |
| T-Q1-02 | Tampering | rrdtool argument forgery via `:` in line/ds names (e.g. `x:AVERAGE --imginfo /etc/passwd`) | mitigate | Task 1: `_RRD_NAME` permits only `[A-Za-z0-9_]`; invalid lines are skipped and logged, never emitted |
| T-Q1-03 | Information Disclosure | `Pellmonconf.source()` arbitrary file read (pellmonconf.py:93-102) | mitigate | Task 2: `_resolve()` allowlist keyed on `self.dirs`; plus realpath containment check |
| T-Q1-04 | Tampering | `Pellmonconf.save()` arbitrary file write, tool documented to run as root (pellmonconf.py:104-115) | mitigate | Task 2: same `_resolve()` gate applied before `codecs.open(..., 'w')` |
| T-Q1-05 | Information Disclosure | `source()` echoing the resolved absolute path back to the client | mitigate | Task 2: return the display name in the `filename` field, not the on-disk path |
| T-Q1-06 | Denial of Service | Oversized `width`/`height` driving rrdtool memory use | accept | Existing clamps (5000 x 2000) retained in `_coerce_int`; authenticated-surface, low value |
| T-Q1-SC | Tampering | npm/pip/cargo installs | mitigate | Not applicable — this plan adds no new dependencies (stdlib `re`/`ast` only) |
</threat_model>

<verification>
1. `python -m pytest tests/ -q` — no new failures beyond the documented known-red baseline; capture the baseline BEFORE making changes so the comparison is meaningful.
2. `grep -n "shell=True" src/Pellmonweb/pellmonweb.py` — no output.
3. `grep -n "raw_input\|print \"" src/pellmoncli.in` — no output.
4. `python -c "compile(open('src/pellmoncli.in').read(),'x','exec')"` — exits 0.
5. `git status --short` — confirm only the seven planned files are modified/added by this work; the pre-existing WIP diff on other `src/` files is untouched.
</verification>

<success_criteria>
- `/graph` runs rrdtool via an argv list with `shell=False`; no attacker-controlled string can introduce a shell command or an extra rrdtool argument.
- `pellmonconf.source()`/`save()` reject every filename that is not a key of `self.dirs`, including absolute paths and traversal payloads.
- `src/pellmoncli.in` is valid Python 3 with no py2-only constructs, guarded by an automated test.
- Three new test modules pass; full suite shows no regressions.
- Commit stages only the seven files in `files_modified`; the user's unrelated uncommitted changes remain intact.
</success_criteria>

<output>
Create `.planning/quick/260919-atb-fix-command-injection-in-graph-endpoint-/260919-atb-SUMMARY.md` when done.
</output>
