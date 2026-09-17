# Phase 2: Exception Visibility Retrofit - Research

**Researched:** 2026-09-17
**Domain:** Python 3 exception handling / stdlib `logging` retrofit (no new dependencies)
**Confidence:** HIGH (all claims below are grounded in direct reads of the actual source files and, where relevant, live interpreter runs against `venv-wsl` — not training-data guesses)

## Summary

This phase touches existing code paths only — no new libraries, no new architecture. The work is: (1) convert specific bare/broad `except:` clauses in exactly three files to `except Exception:` + `logger.exception(...)`, (2) replace ad hoc `print()` calls with the existing shared `logger = getLogger('pellMon')` across `src/Pellmonsrv/` and `src/Pellmonweb/`, and (3) prove via Phase 1's pytest suite that pass/fail/skip status is byte-identical before and after.

Two findings materially change how the planner should scope and verify this phase, both confirmed by direct execution against this repo's `venv-wsl` interpreter (not assumed):

1. **`src/Scotteprotocol/protocol.py` is unreachable today, on every dev platform in this repo, for a *different* reason than Windows/grp masking.** `import Scotteprotocol.protocol` fails at `Scotteprotocol/__init__.py:2` (`from protocol import Protocol` → `ModuleNotFoundError: No module named 'protocol'`) before `protocol.py`'s own broken `from enumerations import dataEnumerations` (line 25) is ever reached. This is a pure Python-2-style implicit-relative-import bug, independent of platform (`grp`/`dbus` masking does not apply here — the failure is confirmed on Linux/WSL directly). This explains and validates CONTEXT.md's D-02 decision to *exclude* `Scotteprotocol/protocol.py` from the 3-file conversion scope even though ROADMAP's phase success criterion 3 literally names it. See Open Questions for the exact recommended resolution.

2. **`src/Pellmonsrv/plugins/calculate/__init__.py` is *also* currently unimportable on every dev platform, for two independent reasons that mask each other by platform.** On Windows, `import os, grp, pwd` (line 24) fails first with `ModuleNotFoundError` for `grp` (caught and `pytest.skip`-ped by `tests/test_plugin_imports.py`'s `PLATFORM_UNAVAILABLE` allowlist). On Linux/WSL, `grp` imports fine, so execution proceeds to line 28 — `from string import maketrans` — which raises **`ImportError`** (not `ModuleNotFoundError`; `string.maketrans` was removed in Python 3, moved to `str.maketrans`). Confirmed live: `venv-wsl/bin/python -c "import Pellmonsrv.plugins.calculate"` raises this exact error. Critically, `tests/test_plugin_imports.py`'s `except ModuleNotFoundError as exc:` catch clause does **not** catch a plain `ImportError` — so on Linux/WSL/CI, `test_plugin_module_imports[calculate]` is a genuine, currently-undocumented **failure**, not the "skip on missing grp" that 01-VALIDATION.md documents (that documentation was written from a Windows-only verification run). This is a pre-existing bug, not something Phase 2 introduces or is responsible for fixing — but the planner must know it exists so the before/after comparison is interpreted correctly and isn't misattributed to this phase's changes.

**Primary recommendation:** Do the conversion work as file-level text edits guided by the per-block dispositions below (not a mechanical "every bare except in these 3 files becomes `logger.exception`" pass — several bare excepts in `pellmonsrv.py`'s `config.__init__` and in `calculate/__init__.py`'s `Calc` class are intentional control-flow/default-fallback patterns, and making them loud would flood the log on every normal startup/item access). Verify `PluginManager.py` and `pellmonsrv.py` changes via real import/activation (both modules import cleanly today). Verify `calculate/__init__.py` changes via a **test-only** `string.maketrans` shim (monkeypatch, not a production fix) since the module cannot be imported unmodified today. Treat `Scotteprotocol/protocol.py` as out of this phase's edit scope, matching CONTEXT.md's D-02 — recommend a one-line note in VERIFICATION.md explaining why ROADMAP's literal mention of that file is satisfied by proxy (see Open Questions).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Plugin discovery/activation error visibility | Daemon process (`Pellmonsrv/yapsy/PluginManager.py`, `pellmonsrv.py`) | — | Plugin loading and activation both happen entirely inside the `pellmonsrv` daemon process; no cross-process boundary involved |
| Protocol/database write-failure visibility | Daemon process (`pellmonsrv.py` `Poller.run`, `database.py`) | — | RRD polling and SQLite writes are daemon-internal; D-Bus is not involved in this failure path |
| Calculate-plugin failure visibility | Daemon process, plugin tier (`plugins/calculate/__init__.py`) | — | Plugin subclasses `protocols` and runs inside the daemon; no web-tier involvement |
| Print-to-logging sweep | Daemon process + Web process (`src/Pellmonsrv/`, `src/Pellmonweb/`) | — | Both processes share the observability goal; each keeps its own `getLogger('pellMon')` instance (two separate log streams per D-01, not a shared logger across processes) |

This phase makes no cross-tier or cross-process changes — every edit is a local, in-process logging-call substitution.

## Standard Stack

No new dependencies. This phase uses only the Python 3 stdlib `logging` module, already imported via `from logging import getLogger` / `import logging` in every touched file.

**Installation:** N/A — nothing to install.

## Package Legitimacy Audit

Not applicable. This phase installs zero external packages; it only edits existing `except`/`print` call sites. Skip the slopcheck/registry-verification gate.

## Architecture Patterns

### Exception-visibility data flow (before -> after)

```
BEFORE (current):
  [failure occurs: bad plugin descriptor / exec error / protocol parse / db write]
        |
        v
  bare `except:`  or  `except Exception as e: print(e)` / `logger.info(str(e))`
        |
        v
  failure silently discarded or logged as a one-line message with no traceback
        |
        v
  caller proceeds as if nothing happened (plugin just "isn't in the list",
  polled value silently becomes 'U', calculated item silently returns 'error')

AFTER (this phase):
  [same failure occurs -- control flow and return values are UNCHANGED]
        |
        v
  `except Exception:` (or narrowed type where the except is genuine
  control-flow, e.g. `except KeyError:`)
        |
        v
  logger.exception("<same or clarified message>")  -- captures sys.exc_info()
  automatically, writes full traceback to the shared 'pellMon' logger
        |
        v
  caller proceeds EXACTLY as before (same return value / same swallow) --
  only the log stream gained a traceback; no behavior changed
```

### Recommended per-file disposition

Not a generic pattern — these are the actual occurrences read from the three D-02-scoped files plus the D-04-scoped print sweep, each disposed individually.

#### 1. `src/Pellmonsrv/yapsy/PluginManager.py` (per CONTEXT.md D-03, already fully specified — implement exactly as follows)

```python
# Line 208-212 (descriptor parse) -- BEFORE:
try:
    config_parser.read(candidate_infofile)
except:
    logging.debug("Could not parse the plugin file %s" % candidate_infofile)
    continue

# AFTER:
try:
    config_parser.read(candidate_infofile)
except Exception:
    logging.debug("Could not parse the plugin file %s", candidate_infofile, exc_info=True)
    continue
```
(Stays at `debug` level per D-03 — "low severity" — but must still carry the traceback via `exc_info=True` since D-03 says "stays at logger.debug but with logger.exception for the traceback"; use `logging.debug(..., exc_info=True)` here rather than `logging.exception()` because `logging.exception()` is hardcoded to ERROR level in the stdlib — there is no `debug`-level equivalent of `logger.exception()`. This is the one occurrence in this phase where `exc_info=True` is the correct idiom instead of literally calling `.exception()`.)

```python
# Line 273-281 (plugin load/exec -- THE critical OBS-01 target) -- BEFORE:
candidate_globals = {"__file__":candidate_filepath+".py"}
try:
    print(candidate_filepath)
    with open(candidate_filepath+".py") as f:
        exec(compile(f.read(), candidate_filepath+".py", 'exec'), candidate_globals)
except Exception as e:
    print(e)
    logging.debug("Unable to execute the code in plugin: %s" % candidate_filepath)
    logging.debug("\t The following problem occured: %s %s " % (os.linesep, e))

# AFTER:
candidate_globals = {"__file__":candidate_filepath+".py"}
try:
    with open(candidate_filepath+".py") as f:
        exec(compile(f.read(), candidate_filepath+".py", 'exec'), candidate_globals)
except Exception:
    logging.exception("Unable to execute the code in plugin: %s", candidate_filepath)
```
(Both `print()` calls removed per D-04; the two `logging.debug` lines collapse into one `logging.exception` call at ERROR level per D-05 — this is the literal fix ROADMAP success criterion 2 asks for: a broken ScotteCom/NBEcom module load now produces a full traceback in the daemon log instead of a swallowed one-liner.)

```python
# Line 287-290 (subclass probe, hot inner loop) -- BEFORE:
try:
    is_correct_subclass = issubclass(element, self.categories_interfaces[category_name])
except:
    continue

# AFTER (per D-03 -- narrow, no logging, since non-class symbols are expected/normal):
try:
    is_correct_subclass = issubclass(element, self.categories_interfaces[category_name])
except TypeError:
    continue
```

#### 2. `src/Pellmonsrv/pellmonsrv.py`

The file has 27 bare `except:` occurrences (confirmed by direct grep) plus several `except Exception as e:` blocks that already log via `.info`. **Do not convert all 27 mechanically.** Two clearly distinct categories exist in this file:

**Category A — steady-state failure paths (convert to loud, matches OBS-01/OBS-02):**

| Line(s) | Current | Recommended AFTER | Why loud |
|---|---|---|---|
| 93-103 (`try: plugin.plugin_object.activate(...) except Exception as e:`) | `logger.info('%s plugin error: %s'%(plugin_name, str(e)))` | `logger.exception('%s plugin error'%plugin_name)` (keep the `if conf.command == 'debug': raise` branch unchanged) | This is the daemon-side half of OBS-01 — a plugin whose `activate()` raises must produce a full traceback, not a one-line message |
| 258-268 (Poller data-read: `except IOError as e:` / `except Exception as e:`) | `logger.info('error in retry %s'%str(e))` / `logger.debug('error polling %s: %s'%(data['name'], str(e)))` | `logger.exception('error in retry for %s'%data['name'])` / `logger.exception('error polling %s'%data['name'])` | Directly the OBS-02 "protocol-parsing... in pellmonsrv.py" target — this is where per-item RRD polling reads fail |
| 288 (`except Exception as e:` wrapping the whole poll iteration) | `logger.info('error in polling %s'%str(e))` | `logger.exception('error in polling')` | The OBS-02 "database-write failure" catch-all for the RRD update subprocess path |
| 346 (`db_copy_thread`, bare `except: pass`) | swallows everything from `copy_db()` silently, even though `copy_db()` already logs internally | `except Exception: logger.exception('unexpected error in db_copy_thread')` | `copy_db()`'s own try/except (325-328, 336-338) already logs known failures at `.info`; this outer bare except is a dead-code safety net that would hide anything `copy_db()` didn't anticipate (e.g. a future refactor bug) — upgrading it is cheap and closes a real gap |
| 744-752 (`except configparser.NoSectionError as e: print('noconf', e); pass` / `except Exception as e: print(e); logger.info('invalid setting for plugin_dirs')`) | prints + `.info` | drop both `print()` calls (D-04); upgrade the `except Exception as e:` branch to `logger.exception('invalid setting for plugin_dirs')`; leave the `NoSectionError` branch as `logger.debug(...)` (it's an expected "section absent" case, not a bug) | Direct print-sweep target; the second except's message is currently the only signal an operator gets when `plugin_dirs` config is malformed |

**Category B — intentional config-default fallbacks (leave narrow/untouched, out of functional scope):**

Lines 448, 526, 537, 544, 554, 562, 565, 585, 636, 643, 649, 654, 659, 690, 694, 699, 703, 711, 718, 722, 727, 731, 736, 739, 775 are all `try: <read one optional config value> except: <assign a hardcoded default>` inside `config.__init__` (startup-time config parsing) or `drop_privileges` (line 775, "can live without it for testing purposes"). These are **not** the "protocol-parsing or database-write failure" paths ROADMAP's success criterion 3 targets — they're expected-missing-key fallback logic that runs on every single daemon start. Converting all 25 of these to `logger.exception` would:
- Produce 10-20+ tracebacks in the log on every normal startup where optional config sections are simply absent (the common case for a minimal `pellmon.conf`)
- Contradict the "no logic altered, purely observability" framing — mass-logging expected-missing-config as errors materially changes what a normal startup log looks like, which is itself an observable behavior change beyond what OBS-01/02/03 ask for
- Not match CONTEXT.md's own stated philosophy for `PluginManager.py` line 289 (D-03): "only exception types that indicate a hidden bug should be loud"

**Recommendation for the planner:** leave Category B bare excepts as bare `except:` (out of scope, same as the ~140+ deferred occurrences elsewhere in `src/` per D-02's deferred note) — or, if the plan-checker wants every bare except in the 3 named files touched, narrow them to `except (configparser.NoOptionError, configparser.NoSectionError, KeyError, ValueError):` without adding logging, which satisfies "no bare except left" without adding startup log spam. Do not add `logger.exception` calls to these lines. Flag this disposition explicitly in the plan so a future reviewer doesn't assume it was missed.

#### 3. `src/Pellmonsrv/plugins/calculate/__init__.py`

Same two-category split as `pellmonsrv.py`, at smaller scale (8 bare `except:` found by direct grep, CONCERNS.md's "7" is a slight undercount — line 359 has trailing whitespace after `except:` which likely wasn't matched by a stricter grep).

**Category A — the actual OBS-02 target (convert to loud):**

```python
# Line 345-358, setItem() -- BEFORE (this is the smoking gun: `unicode(value)`
# at line 351 is a Python-2-only builtin removed in Python 3 -- it ALWAYS
# raises NameError, and today that NameError is silently caught and
# degraded to a generic 'error' string with only logger.info(str(e))):
def setItem(self, itemname, value):
    try:
        item = itemList[self.name2index[itemname]]
        calc_item = item['calc_item']
        prog = self.getItem(calc_item)
        try:
            stack = [unicode(value)]
            calc = Calc(prog, self.db, stack=stack)
            calc.run()
            return 'OK'
        except Exception as e:
            calc = Calc(prog, self.db)
            logger.info(calc_item+' error: '+str(e))
            return 'error'
    except:
        ...

# AFTER (logic/return values UNCHANGED -- still returns 'error', still
# masks the NameError from the caller's perspective -- only the log call
# changes, which is exactly the phase boundary: "makes existing failures
# visible... does NOT fix any underlying bugs"):
def setItem(self, itemname, value):
    try:
        item = itemList[self.name2index[itemname]]
        calc_item = item['calc_item']
        prog = self.getItem(calc_item)
        try:
            stack = [unicode(value)]
            calc = Calc(prog, self.db, stack=stack)
            calc.run()
            return 'OK'
        except Exception:
            logger.exception('%s error'%calc_item)
            return 'error'
    except:
        ...
```
This is the single most illustrative example of this phase's value: after this change, every write to a calculated item logs `NameError: name 'unicode' is not defined` with a full traceback instead of a bare `error` string with no diagnostic — exactly what OBS-02 asks for, and exactly why PROTO-02 (Phase 4) exists to actually fix it.

Also convert the `activate()` method's two `except Exception as e: logger.info(str(e)); raise [e]` blocks (lines 292-293's inner one intentionally re-raises unchanged; lines 295-297 and 316-318 outer ones) from `.info` to `.exception`, keeping the `raise`/`raise e` behavior identical.

**Category B — control-flow bare excepts (leave alone, do NOT add logging):**

Lines 54, 151, 169, 181, 191, 333, 340, 359 all use bare `except:` as **expected control flow**, not error suppression:
- Lines 54/181/191 (`Calc.execute`/`next`/`skip`): catch `IndexError` from `self.calc[self.IP]` running past the end of the token list, immediately re-raised as a domain-specific `ValueError('Expected operand')` etc. — this is how the stack-based mini-interpreter detects "end of program reached unexpectedly." Every syntactically-invalid calc program hits this in normal use.
- Lines 151/169 (`rcl`/`grcl` ops): catch `KeyError` from a dict lookup on an undefined variable name, re-raised as `ValueError('no variable named %s')`. Normal user-error path (typo'd variable name in a calc program), not a code bug.
- Lines 333/340 (`getItem`): catch `KeyError` when an item has no `calc_item` key (plain static items don't), falling back to returning the raw stored value. This runs on **every single non-calculated item read** — it is the dominant code path, not an edge case.
- Line 359 (`setItem` outer): catches the `KeyError`/lookup failure for items with no `calc_item`, falling back to `store_setting`. Same normal-path reasoning.

Converting any of these to `except Exception: logger.exception(...)` would log a full traceback on essentially every `getItem`/`setItem` call in the plugin — the opposite of "purely observability, no logic altered" since it would make the log stream unusable. **Recommendation: leave these 8 bare, or narrow the type to the specific expected exception (`IndexError`/`KeyError`) without adding a log call.** This mirrors D-03's own reasoning for `PluginManager.py` line 289 and should be applied the same way here — CONTEXT.md's D-02 names the *file*, not "every occurrence in the file," and the file-level scoping is satisfied by fixing the genuine OBS-02 target (`setItem`'s `unicode()` swallow) plus narrowing the rest for type-safety without indiscriminate logging.

#### 4. `src/Scotteprotocol/protocol.py` — excluded from this phase (see Open Questions)

19 bare/broad excepts confirmed present (per CONCERNS.md), but this file is **not** in CONTEXT.md's D-02 list and is confirmed unreachable under Python 3 today (see Summary finding #1). Do not edit this file in Phase 2.

### Print-statement sweep (D-04) — full file list

Confirmed by direct grep across `src/Pellmonsrv/` and `src/Pellmonweb/` (excluding `.py2bak`), 41 `print()` call sites across 13 files (beyond the 2 already covered in `PluginManager.py` above):

| File | Lines | Disposition |
|---|---|---|
| `src/Pellmonsrv/daemon.py` | 131 | `print(str(err))` inside daemonizer stderr-redirect fallback → `logger.exception` or at minimum `logger.error(str(err))` — this is the last-resort error path before stdio is redirected away, so logging (not printing) is the whole point |
| `src/Pellmonsrv/database.py` | 113, 170 | `print(e)` fallbacks explicitly called out by CONVENTIONS.md as inconsistent → `logger.exception(...)`. **Note:** `database.py` has no `logger = getLogger('pellMon')` at module scope today — add one (D-01: use the shared name, not `__name__`) |
| `src/Pellmonsrv/pellmonsrv.py` | 748, 751 | See Category A table above — drop both, fold into the `logger.exception` call |
| `src/Pellmonsrv/plugins/consumption/__init__.py` | 209 | `print(e)` → `logger.exception(...)` (module already has `logger = getLogger('pellMon')`) |
| `src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py` | 88 | `print('ERRROR chiphertext too short', len(h))` → `logger.error('ciphertext too short: %d', len(h))` (fix the typo while touching the line is acceptable — it's a log message string, not logic) |
| `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py` | 75, 81, 106, 115, 119, 122, 132, 149, 151, 197, 200, 219, 233, 309, 314, 317, 332 (17 occurrences) | All debug-trace prints in the NBE protocol retry/reconnect state machine → convert to `logger.debug(...)`/`logger.warning(...)` per severity (retries = debug, "no more retry" = warning, exception reprs = `logger.exception` where inside an `except` block). **Caveat:** this module is part of the NBEcom deferred-import chain (`known_broken`-adjacent, IMPORT-02/Phase 3) — it imports today (unlike Scotteprotocol) but its runtime behavior is unverified without hardware; keep changes to logging calls only |
| `src/Pellmonsrv/plugins/nbecom/__init__.py` | 92, 99, 127, 250, 267 | Same pattern, convert to `logger.debug`/`logger.exception` |
| `src/Pellmonsrv/plugins/onewire/__init__.py` | 85 | `print(e)` → `logger.exception(...)` |
| `src/Pellmonsrv/plugins/owfs/__init__.py` | 159, 193, 234 | `print(exc_type, exc_value)` (3x, inside `except:` blocks) → `logger.exception(...)` |
| `src/Pellmonsrv/plugins/testplugin/__init__.py` | 64 | `print('testplugin set: ', name, value)` → `logger.debug(...)` (this is a test-fixture plugin used by `tests/`, not real hardware — confirm no test asserts on its stdout before changing) |
| `src/Pellmonweb/pellmonconf.py` | 125 | `print(config_file)` — debug leftover, no argparse/CLI intent → `logger.debug(config_file)` |
| `src/Pellmonweb/pellmonconf.py` | 154, 155, 156 | `print('Open http://...')`, `print('Run as root...')`, `print('Quit with CTRL-C')` — **keep as `print()`**. Confirmed by direct read: this is a startup banner for a manually-invoked standalone tool (`pellmonconf` — the web-based config editor's entry point), directly analogous to the "intentional CLI output" carve-out ROADMAP's own success-criteria wording uses for `pellmoncli`. Converting to `logger.info` would suppress this banner by default (module logger typically defaults to WARNING+ if no handler is attached when run standalone), degrading UX for zero observability gain |
| `src/Pellmonweb/pellmonweb.py` | 132, 138 | `print('server not running')` / `print('server is running')` — D-Bus connectivity state-change debug leftovers inside `Dbus_handler.start()` → `logger.info(...)` (genuinely useful operational signal, not CLI banner) |
| `src/Pellmonweb/pellmonweb.py` | 556 | `print(parameterlist)` — clear debug leftover dumping full parameter list on every page view → `logger.debug(...)` |

**Verification command for "no remaining ad hoc print() calls":**
```bash
grep -rn "print(" src/Pellmonsrv src/Pellmonweb --include="*.py" | grep -v "\.py2bak"
```
Expected clean result after this phase: **only** `src/Pellmonweb/pellmonconf.py:154`, `:155`, `:156` remain (the confirmed-intentional CLI banner). Any other line appearing in this grep's output after the sweep is a regression. Root-level `test-imports.py`, `convert-to-py3.py`, and `src/pellmoncli.in` are outside this grep's search roots already (excluded by D-04, no extra filtering needed).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Capturing exception traceback in a log record | Manual `traceback.format_exc()` + string concatenation into a log message | `logger.exception(msg)` (implicitly calls `sys.exc_info()` and attaches it to the LogRecord) | Idiomatic, matches D-05, and lets `dbus_signal_handler` (the existing custom `logging.Handler` in `pellmonsrv.py`) receive the full traceback as part of the record rather than a pre-flattened string |
| A new exception hierarchy for "plugin load failed" vs "plugin activate failed" | New custom exception classes | Keep using bare `Exception` catches at these call sites — the existing `protocol_error`/`seqnum_error` hierarchy in `nbeprotocol/protocolexceptions.py` already exists for protocol-specific errors and this phase does not touch that boundary | Introducing new exception types would be a logic change, explicitly out of scope ("no logic altered") |

**Key insight:** This phase's entire value is substitutional (swap the logging call inside an existing `except` block) — any task that proposes adding new exception classes, new control flow, or new retry logic has drifted out of phase scope into Phase 3/4 territory.

## Common Pitfalls

### Pitfall 1: Treating `ModuleNotFoundError` handling as equivalent to `ImportError` handling
**What goes wrong:** `tests/test_plugin_imports.py`'s `except ModuleNotFoundError as exc:` does not catch the `calculate` plugin's `ImportError: cannot import name 'maketrans' from 'string'` on Linux/WSL, so that test fails (not skips) on Linux, contradicting 01-VALIDATION.md's documented Windows-only "skip on missing grp" baseline.
**Why it happens:** `ModuleNotFoundError` is a *subclass* of `ImportError`; catching the subclass does not catch instances of the (broader) parent raised by a different underlying cause (`ImportError` raised directly by `from string import maketrans` failing to find the *attribute*, not the *module*).
**How to avoid:** Run this phase's before/after comparison on the **same interpreter/platform Phase 1 documented** (`venv-py3/Scripts/python.exe` per 01-VALIDATION.md's "Interpreter" row) so the baseline and the post-Phase-2 run are directly comparable. If the executor ever runs on WSL/Linux instead, expect one *additional* pre-existing failure (`test_plugin_module_imports[calculate]`) that exists independently of anything this phase changes — do not treat it as a Phase 2 regression, and do not attempt to fix it (that's Phase 4 PROTO-02 territory, and PROTO-02's current wording only names the line-351 `unicode()` bug, not this line-28 import-time bug — flag as a REQUIREMENTS.md gap, see Open Questions).
**Warning signs:** Before/after diff shows `test_plugin_module_imports[calculate]` changing status between runs when it shouldn't have (it's untouched by this phase's edits) — almost certainly means the two runs used different platforms/interpreters, not that the changes broke something.

### Pitfall 2: Converting every bare `except:` mechanically, producing log spam
**What goes wrong:** `pellmonsrv.py` has 27 bare excepts and `calculate/__init__.py` has 8; roughly two-thirds of these (in `config.__init__`'s optional-config-value parsing, and in `calculate`'s dict-lookup control flow) are intentional "use default on missing key" patterns that fire on every normal run. Logging all of them at `.exception` level turns a clean startup log into 10-20+ tracebacks and turns every `getItem`/`setItem` call in the Calculate plugin into a logged traceback.
**Why it happens:** CONTEXT.md's D-02 scopes the conversion to *files*, not to *every occurrence within those files* — but it's easy to over-read "convert bare excepts in these 3 files" as "convert every bare except found by grep."
**How to avoid:** Apply the per-line disposition tables above (Category A = loud, Category B = narrow-but-silent). When in doubt, ask: "would this exception firing represent a hidden bug an operator needs to know about, or is it the designed behavior for a missing optional setting / expected lookup miss?"
**Warning signs:** A code review that touches more than ~10-12 lines total across `pellmonsrv.py` + `calculate/__init__.py` for the D-02 conversion is very likely over-converting — the genuine "hidden bug" targets are a small, specific set (plugin activation, RRD poll/write, `setItem`'s `unicode()` call).

### Pitfall 3: Attempting to verify `calculate/__init__.py` changes via a real import
**What goes wrong:** `import Pellmonsrv.plugins.calculate` fails today (before *and* after this phase's changes) on any interpreter that reaches line 28, because `from string import maketrans` is broken under Python 3 — this is unrelated to this phase's logging edits and won't be fixed by them.
**Why it happens:** The module-level import failure happens before any of the `setItem`/`getItem`/`activate` code this phase touches ever executes.
**How to avoid:** Verify the logging changes with a **test-only** monkeypatch that restores `string.maketrans` before import, e.g.:
```python
# tests/... (test-only shim, NOT a production fix)
import string
if not hasattr(string, "maketrans"):
    string.maketrans = str.maketrans
import Pellmonsrv.plugins.calculate as calculate_module
```
This unblocks import purely for test purposes without touching `src/` (which would be an out-of-scope logic fix belonging to Phase 4 / PROTO-02-adjacent). Document in the test file's docstring that this shim exists solely to make the module importable for exception-visibility testing and must be removed once Phase 4 fixes the underlying bug for real.
**Warning signs:** A task or test that edits `plugins/calculate/__init__.py`'s `from string import maketrans` line — that's the Phase 4 fix, not Phase 2's.

### Pitfall 4: Assuming `Scotteprotocol/protocol.py`'s 19 bare excepts are this phase's responsibility
**What goes wrong:** ROADMAP.md's phase success criterion 3 literally names `Scotteprotocol/protocol.py`, but CONTEXT.md's D-02 (the user-locked decision) does not include it in the 3-file scope, and the module is confirmed unreachable under Python 3 today (independent of the `calculate` maketrans issue — this is a pure broken-relative-import bug at `Scotteprotocol/__init__.py:2`).
**Why it happens:** Success-criterion wording was written before the CONTEXT.md discussion session read the actual files and discovered the reachability problem.
**How to avoid:** Do not edit `Scotteprotocol/protocol.py` in this phase. See Open Questions for the recommended resolution language for `/gsd:verify-work`.
**Warning signs:** A plan task targeting `Scotteprotocol/protocol.py` — should not exist in this phase's plan.

### Pitfall 5: pytest log capture changing "output" in a way that looks like a behavior diff
**What goes wrong:** pytest's default behavior captures `logging` calls per-test and can print a "Captured log call" section in verbose/failure output; if the before/after comparison naively diffs raw console text (not structured pass/fail status), a `.info` → `.exception` change will show up as a text diff even though no test assertion changed.
**Why it happens:** `logger.exception()` writes more content (the traceback) to the log stream than `logger.info(str(e))` did.
**How to avoid:** Compare **structured test outcomes only** (pass/fail/error/skip per test ID via `--junitxml`), never raw stdout/console text. See the exact commands under Validation Architecture below. Confirmed safe: `tests/Pellmonweb/test_auth.py` (01-02-02) explicitly asserts only on return values, never on `cherrypy.log` content, per 01-VALIDATION.md — no existing test in this repo asserts on log message text, so this is a theoretical risk, not a confirmed one, but the comparison mechanism should be robust to it regardless.

## Code Examples

See the per-file "Architecture Patterns" section above — every code example there is a verified before/after pair read directly from this repository's current source, not a generic pattern.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `except Exception as e: logger.info(str(e))` or bare `except: pass` / `print(e)` | `except Exception: logger.exception(msg)` | This phase | Traceback now visible in daemon log for genuine failure paths; return values/control flow unchanged |

Not applicable beyond this phase's own before/after — there is no external ecosystem "state of the art" shift here (stdlib `logging.exception()` has behaved identically since Python 2.x).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pellmonconf.py:154-156` prints are intentional CLI banner output and should be excluded from the D-04 sweep | Print-statement sweep table | Low — if wrong, planner just converts 3 extra lines to `logger.info`; easily reversible, no functional risk either way |
| A2 | `nbeprotocol/protocol.py` and `nbecom/__init__.py`'s print-to-logger conversions are safe to make without hardware verification, since they're logging-call-only changes inside code paths already gated by `TEST-01`'s mocked-transport testing philosophy | Print-statement sweep table | Low-Medium — these files are only reachable at runtime with real/mocked hardware; if a print-format assumption (e.g. `%s` vs positional logging args) is wrong, it would only surface when NBEcom actually runs, which is unverified either way per CONCERNS.md |

**All other claims in this research are `[VERIFIED]` by direct code read and/or live interpreter execution against this repository (`venv-wsl`), not `[ASSUMED]` or `[CITED]`** — there is no external library/API surface in this phase to verify against Context7 or official docs; the entire research surface is this codebase's own source.

## Open Questions

1. **How should `/gsd:verify-work` interpret ROADMAP's success criterion 3 naming `Scotteprotocol/protocol.py`, given CONTEXT.md's D-02 excludes it and it's confirmed unreachable?**
   - What we know: `Scotteprotocol/protocol.py` cannot be imported today (confirmed via live `venv-wsl` execution: fails at `Scotteprotocol/__init__.py:2`, a different, unrelated bare-relative-import bug, before `protocol.py`'s own line-25 bug is ever reached). CONTEXT.md's D-02 (user-locked) explicitly lists only `PluginManager.py`, `pellmonsrv.py`, `plugins/calculate/__init__.py`.
   - What's unclear: Whether the plan/verification should (a) silently satisfy the criterion via the other two files' conversions, (b) explicitly amend ROADMAP.md's Phase 2 success criterion 3 wording to drop the `Scotteprotocol/protocol.py` mention (deferring its 19 bare excepts to Phase 3, after IMPORT-01 makes the module reachable), or (c) still touch `Scotteprotocol/protocol.py`'s bare excepts blind (unverifiable by real import, verified only by static/text inspection) just to literally satisfy the wording.
   - Recommendation: Option (b) — amend ROADMAP.md's Phase 2 success criterion 3 to read "...in `pellmonsrv.py` or `plugins/calculate/__init__.py`" (drop the Scotteprotocol mention) and add a one-line note that `Scotteprotocol/protocol.py`'s exception-visibility work is deferred to Phase 3 (naturally bundled with IMPORT-01's relative-import fix, since you cannot meaningfully verify "loud exceptions" in a module that cannot be imported). This is the cleanest resolution and matches what CONTEXT.md's D-02 already implicitly decided. Flag this as a **ROADMAP amendment recommendation** for the planner/orchestrator to action (e.g. via `/gsd:evolve-roadmap` or an inline plan note), not a silent scope change.

2. **Should the `calculate/__init__.py` `maketrans` import bug (blocking ALL verification of this phase's changes to that file) be fixed now as a one-line, purely-mechanical part of Phase 2, or strictly deferred to Phase 4?**
   - What we know: `from string import maketrans` → `from string import ...` doesn't exist; the mechanical fix (`stack = [unicode(value)]` → `stack = [str(value)]` and drop the `maketrans` import, using `str.maketrans` inline at its one use site around line 252 `value.translate({...})`) is exactly the kind of 1:1 Python-2→3 mechanical substitution CONVENTIONS.md documents as the established "migration diff signature" — arguably not "new logic," just finishing an already-started mechanical port.
   - What's unclear: CONTEXT.md's phase boundary is explicit: "does NOT fix any underlying bugs... It is a purely observability change." REQUIREMENTS.md's PROTO-02 explicitly owns the `unicode()` fix in Phase 4. Fixing `maketrans` now would be scope creep even if trivial, and would make Phase 2 harder to review as "log calls only."
   - Recommendation: **Do not fix it in Phase 2.** Use the test-only monkeypatch shim (Pitfall 3, above) to verify the logging changes in isolation. Flag to STATE.md/PROJECT.md that PROTO-02's Phase 4 scope should be widened to include the `from string import maketrans` line-28 import-time bug alongside the already-known line-351 `unicode()` bug — both are needed to make `plugins/calculate/__init__.py` actually importable on Python 3, and REQUIREMENTS.md currently only names one of the two.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest + plugins (pytest-mock, pytest-socket, pytest-cov) | Before/after comparison | Confirmed installed in `venv-py3` per 01-VALIDATION.md (Phase 1 deliverable) | pytest `>=9.0,<10` | — |
| `venv-py3/Scripts/python.exe` | Only interpreter with both `cherrypy` and `pyserial` (per 01-VALIDATION.md) | Assumed present (Phase 1 artifact, not re-verified live in this session) | — | If missing, re-run Phase 1's environment spike before starting Phase 2 |
| `venv-wsl` (WSL Python 3.13) | Used in this research session to empirically confirm the `Scotteprotocol`/`calculate` import failures | Confirmed present and functional (used directly above) | Python 3.13 (system, via `venv-wsl/bin/python`) | Not required for Phase 2 execution itself — Windows `venv-py3` is the documented execution environment per 01-VALIDATION.md |

**Missing dependencies with no fallback:** None identified.
**Missing dependencies with fallback:** None identified — all tooling needed for this phase already exists from Phase 1.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest `>=9.0,<10` (already installed, Phase 1 deliverable) |
| Config file | `pytest.ini` (repo root, created in Phase 1) |
| Quick run command | `venv-py3/Scripts/python.exe -m pytest tests/ -x -q -m "not known_broken"` |
| Full suite command | `venv-py3/Scripts/python.exe -m pytest tests/ -v` |

### Exact before/after comparison mechanism

Do **not** diff raw pytest console text (see Pitfall 5). Compare structured per-test outcomes via JUnit XML:

```bash
# BEFORE any Phase 2 edits:
venv-py3/Scripts/python.exe -m pytest tests/ -v \
  --junitxml=.planning/phases/02-exception-visibility-retrofit/before.xml

# ... apply all Phase 2 changes ...

# AFTER Phase 2 edits:
venv-py3/Scripts/python.exe -m pytest tests/ -v \
  --junitxml=.planning/phases/02-exception-visibility-retrofit/after.xml
```

Then diff outcomes only (pass/fail/error/skip per test ID), ignoring captured log/stdout content entirely:

```python
import xml.etree.ElementTree as ET

def outcomes(path):
    tree = ET.parse(path)
    result = {}
    for tc in tree.iter('testcase'):
        test_id = f"{tc.get('classname')}::{tc.get('name')}"
        if tc.find('failure') is not None:
            result[test_id] = 'fail'
        elif tc.find('error') is not None:
            result[test_id] = 'error'
        elif tc.find('skipped') is not None:
            result[test_id] = 'skip'
        else:
            result[test_id] = 'pass'
    return result

before, after = outcomes('before.xml'), outcomes('after.xml')
diff = {k: (before.get(k), after.get(k)) for k in set(before) | set(after) if before.get(k) != after.get(k)}
assert not diff, f"Outcome changed for: {diff}"
print("IDENTICAL pass/fail/skip status before and after" if not diff else "REGRESSION DETECTED")
```

This is the ROADMAP Phase 2 success criterion 1 verification, made concrete and executable. Expected result: `diff == {}` (empty) — the two known Expected-Red-Baseline failures (`test_plugin_module_imports[scottecom]`, `test_nbecom_deferred_protocol_import`) remain failing with the identical failure *type* before and after, since this phase does not touch import statements in any file that affects them.

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-01 | Plugin activation failure in `PluginManager.loadPlugins` produces `logger.exception` traceback | unit | `pytest tests/Pellmonsrv/test_plugin_manager_logging.py -v` | ❌ Wave 0 — new file |
| OBS-01 | Plugin `activate()` failure in `pellmonsrv.py`'s `Database.__init__` plugin-activation loop produces `logger.exception` traceback | unit | `pytest tests/Pellmonsrv/test_pellmonsrv_logging.py -v` | ❌ Wave 0 — new file |
| OBS-02 | `calculate/__init__.py`'s `setItem()` `unicode()` `NameError` produces `logger.exception` traceback (via the test-only `maketrans` shim) | unit | `pytest tests/Pellmonsrv/plugins/test_calculate_logging.py -v` | ❌ Wave 0 — new file |
| OBS-02 | `pellmonsrv.py`'s `Poller.run` data-read/RRD-write failure produces `logger.exception` traceback | unit | `pytest tests/Pellmonsrv/test_pellmonsrv_logging.py -v` (same file as above) | ❌ Wave 0 — new file |
| OBS-03 | No `print()` calls remain in `src/Pellmonsrv/`/`src/Pellmonweb/` outside the confirmed `pellmonconf.py:154-156` CLI banner | enforcement | `grep -rn "print(" src/Pellmonsrv src/Pellmonweb --include="*.py" \| grep -v "\.py2bak"` (assert output is exactly 3 lines, all `pellmonconf.py`) | ❌ Wave 0 — could be a pytest-wrapped grep test or a standalone shell check task |
| Phase success criterion 1 | Before/after test suite parity | integration | See "Exact before/after comparison mechanism" above | ❌ Wave 0 — new comparison script |

### Sampling Rate
- **Per task commit:** quick run command (`-x -q -m "not known_broken"`)
- **Per wave merge:** full suite command + the before/after JUnit XML diff
- **Phase gate:** full suite green (matching Phase 1's documented 2-failure red baseline exactly) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/Pellmonsrv/test_plugin_manager_logging.py` — uses `caplog` fixture to assert a broken plugin `.py` file (or a monkeypatched `open()`/`compile()` failure) triggers a `logging.exception`-level record with `record.exc_info is not None`, for the `PluginManager.py:273-281` change
- [ ] `tests/Pellmonsrv/test_pellmonsrv_logging.py` — covers both the plugin-activation loop (line 93-103) and `Poller.run`'s failure paths (258-268, 288) via `caplog`
- [ ] `tests/Pellmonsrv/plugins/test_calculate_logging.py` — includes the test-only `string.maketrans` shim (Pitfall 3) before importing the module, then asserts `setItem()` still returns `'error'` (logic unchanged) AND that a `logger.exception` record with a `NameError` traceback was emitted
- [ ] A before/after JUnit-XML comparison script (either a standalone script invoked as a manual verification step, or wrapped as `tests/test_no_regression.py` if the plan prefers a single pytest-native gate — but note this test necessarily needs to run *twice*, once per git state, so it's more naturally a wave-boundary manual/scripted step than a single pytest test)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V7 Error Handling and Logging | Yes | This phase directly implements ASVS V7's "log security-relevant events" intent for the daemon's failure paths. Standard control: ensure `logger.exception()` messages never interpolate secrets (passwords, XTEA keys, RSA keys) into the log line |
| V2/V3/V4/V5/V6 | No | This phase touches no authentication, session, access-control, input-validation, or cryptography code paths — it is a pure logging-call substitution inside existing `except` blocks |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sensitive data (SMTP password, D-Bus payloads, XTEA session keys) leaking into logs via a newly-verbose `logger.exception()` call | Information Disclosure | Audit each converted `except` block's *message* argument (not the auto-captured traceback, which is fine) to confirm it does not string-format in `password`/`key`/credential variables. Confirmed audit: `sendmail_thread`'s existing `except Exception as e: logger.info('error trying to send email'); logger.info(str(e))` (pellmonsrv.py:426-428) is **not** touched by this phase's Category A/B tables (it's not one of the flagged targets) — if a future task does touch it, `str(e)` from an `smtplib` auth failure can, in some SMTP server implementations, echo back partial credential info in the exception message; recommend leaving this specific block out of scope or explicitly scrubbing it if touched |

This phase does not introduce new attack surface — it only makes existing failures more visible in an existing, already-privileged log stream (the daemon log, which per SEC findings elsewhere already contains a plaintext-password logging bug in `Pellmonweb/auth.py`, owned by Phase 5/SEC-01 — unrelated to this phase's edits).

## Sources

### Primary (HIGH confidence — direct code reads and live interpreter execution, this session)
- `D:\Antigravity\PellMon-master\src\Pellmonsrv\yapsy\PluginManager.py` (lines 195-300) — read directly
- `D:\Antigravity\PellMon-master\src\Pellmonsrv\plugins\calculate\__init__.py` (full file) — read directly
- `D:\Antigravity\PellMon-master\src\Scotteprotocol\protocol.py` (lines 1-40) — read directly
- `D:\Antigravity\PellMon-master\src\Pellmonsrv\pellmonsrv.py` (lines 85-134, 245-789) — read directly
- `D:\Antigravity\PellMon-master\src\Pellmonsrv\database.py` (lines 100-205) — read directly
- `D:\Antigravity\PellMon-master\src\Pellmonweb\pellmonconf.py` (lines 110-160) — read directly
- `D:\Antigravity\PellMon-master\src\Pellmonweb\pellmonweb.py` (lines 120-145, 545-560) — read directly
- `D:\Antigravity\PellMon-master\tests\test_plugin_imports.py` (full file) — read directly
- Live execution: `venv-wsl/bin/python -c "import Pellmonsrv.plugins.calculate"` → confirmed `ImportError: cannot import name 'maketrans' from 'string'`
- Live execution: `venv-wsl/bin/python -c "import Scotteprotocol.protocol"` → confirmed `ModuleNotFoundError: No module named 'protocol'` at `Scotteprotocol/__init__.py:2`
- Live execution: `grep -rn "print(" src/Pellmonsrv src/Pellmonweb --include="*.py"` and `grep -rn "^\s*except:\s*$"` on the 3 D-02-scoped files — confirmed full occurrence lists

### Secondary (MEDIUM confidence)
- `.planning/codebase/CONCERNS.md` — bare-except occurrence counts (27/19/7 — confirmed 27 and 19 match direct grep exactly; the "7" for calculate is a slight undercount vs. the 8 confirmed by direct grep, likely a whitespace-tolerant regex miss on `except:  ` with trailing spaces at line 359)
- `.planning/codebase/CONVENTIONS.md` — shared logger convention, `%`-formatting style, `print(e)` inconsistency callout

### Tertiary (LOW confidence)
None — this research required no external/library documentation lookups; the entire surface is this repository's own source code, verified directly.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, stdlib `logging` only
- Architecture: HIGH — every before/after example is a direct read of current source, not inferred
- Pitfalls: HIGH — both major pitfalls (Scotteprotocol unreachability, calculate maketrans bug) confirmed via live interpreter execution, not assumed from documentation

**Research date:** 2026-09-17
**Valid until:** Effectively indefinite for the code-reading findings (they describe the current state of a static codebase that won't drift without further commits) — but re-verify the exact line numbers if any other phase/plan touches `pellmonsrv.py`, `PluginManager.py`, or `calculate/__init__.py` before Phase 2 executes, since line numbers will shift with any intervening edit.
