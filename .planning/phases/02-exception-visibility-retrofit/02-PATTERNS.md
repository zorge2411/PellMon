# Phase 2: Exception Visibility Retrofit - Pattern Map

**Mapped:** 2026-09-17
**Files analyzed:** 16 (3 D-02 bare-except targets + 13 D-04 print-sweep targets; some overlap)
**Analogs found:** 16 / 16 (this phase edits existing files only — every "analog" is the file's own already-established local convention; no genuinely new files are created except test files, which have a strong analog in Phase 1's `tests/test_plugin_imports.py`)

This phase is unusual for pattern mapping: there are no new source files. Every task is a **local, in-file substitution** (bare `except:` / broad `except Exception as e: print(e)` → `except Exception:` + `logger.exception(...)`), so the "closest analog" for each file is either (a) that same file's own dominant existing pattern (e.g. `pellmonsrv.py`'s `except Exception as e: logger.info(...)` blocks are the template for its own bare-except conversions), or (b) a sibling plugin file that already has the shared-logger pattern wired up correctly, for files that need a logger added (`database.py`). Concrete line numbers below are freshly re-verified against current source (2026-09-17), not copied blind from RESEARCH.md.

## File Classification

| File to Modify | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/Pellmonsrv/yapsy/PluginManager.py` | service (plugin loader) | event-driven (discovery/load) | itself — `logging.debug(...)` pattern already used at lines 192, 195, 204 | exact (self-consistent) |
| `src/Pellmonsrv/pellmonsrv.py` | daemon entry / controller | event-driven + batch (poll loop) | itself — `logger.info('%s plugin error: %s'%(...))` at line 103, `logger.info(...)` at 266/268/284/289 | exact (self-consistent) |
| `src/Pellmonsrv/plugins/calculate/__init__.py` | plugin (service) | request-response (`getItem`/`setItem`) | itself — `logger.info(calc_item+' error: '+str(e))` at lines 331, 357; `logger.info(str(e))` at 296, 317 | exact (self-consistent) |
| `src/Pellmonsrv/database.py` | model / persistence | CRUD (SQLite key-val + in-memory dict) | `src/Pellmonsrv/plugins/consumption/__init__.py` (has `from logging import getLogger` + module logger, same shared-logger convention) | role-match (logger-add pattern) |
| `src/Pellmonsrv/daemon.py` | utility (daemonizer) | file-I/O (stdio redirect) | `src/Pellmonsrv/pellmonsrv.py` (`logger.exception`/`logger.error` conventions once retrofitted) | role-match |
| `src/Pellmonsrv/plugins/consumption/__init__.py` | plugin | request-response | itself — already has `logger = getLogger('pellMon')`; only swap `print(e)`→`logger.exception(...)` | exact |
| `src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py` | utility (protocol frame codec) | transform | `src/Pellmonsrv/plugins/nbecom/__init__.py` (sibling module, same package, needs same treatment) | exact (sibling) |
| `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py` | service (protocol state machine) | event-driven (retry/reconnect) | `src/Pellmonsrv/plugins/nbecom/__init__.py` | exact (sibling) |
| `src/Pellmonsrv/plugins/nbecom/__init__.py` | plugin | request-response + event-driven | itself / `plugins/consumption/__init__.py` for logger convention | role-match |
| `src/Pellmonsrv/plugins/onewire/__init__.py` | plugin | request-response | `plugins/consumption/__init__.py` | role-match |
| `src/Pellmonsrv/plugins/owfs/__init__.py` | plugin | request-response | `plugins/consumption/__init__.py` | role-match |
| `src/Pellmonsrv/plugins/testplugin/__init__.py` | plugin (test fixture) | request-response | `plugins/consumption/__init__.py` | role-match |
| `src/Pellmonweb/pellmonconf.py` | controller (standalone CLI tool) | request-response | `src/Pellmonweb/pellmonweb.py` (`Dbus_handler`, same package, has `logger`) | role-match |
| `src/Pellmonweb/pellmonweb.py` | controller (CherryPy app) | request-response | itself — establish local convention | exact (self-consistent) |
| `tests/Pellmonsrv/test_plugin_manager_logging.py` (new) | test | event-driven (caplog assertion) | `tests/test_plugin_imports.py` (Phase 1) | exact |
| `tests/Pellmonsrv/test_pellmonsrv_logging.py` (new) | test | event-driven (caplog assertion) | `tests/test_plugin_imports.py` (Phase 1) | exact |
| `tests/Pellmonsrv/plugins/test_calculate_logging.py` (new) | test | event-driven (caplog assertion, with maketrans shim) | `tests/test_plugin_imports.py` (Phase 1, especially its `ModuleNotFoundError`/skip-handling structure) | exact |

## Pattern Assignments

### `src/Pellmonsrv/yapsy/PluginManager.py` (service, event-driven)

**Analog:** itself (`logging.debug` calls already present at lines 192/195/204 establish the module-level `import logging` + bare-function-call convention — this file does NOT use `getLogger('pellMon')`, it calls the `logging` module functions directly, e.g. `logging.debug(...)`)

**Current state, verified 2026-09-17 (lines 207-212, descriptor parse):**
```python
try:
    config_parser.read(candidate_infofile)
except:
    logging.debug("Could not parse the plugin file %s" % candidate_infofile)					
    continue
```
**Target (per CONTEXT.md D-03 — stays debug level, but attaches traceback via `exc_info=True` since `logging.exception()` is hardcoded to ERROR and has no debug equivalent):**
```python
try:
    config_parser.read(candidate_infofile)
except Exception:
    logging.debug("Could not parse the plugin file %s", candidate_infofile, exc_info=True)
    continue
```

**Current state (lines 273-281, plugin load/exec — THE critical OBS-01 target):**
```python
candidate_globals = {"__file__":candidate_filepath+".py"}
try:
    print(candidate_filepath)
    with open(candidate_filepath+".py") as f:
        exec(compile(f.read(), candidate_filepath+".py", 'exec'), candidate_globals)
except Exception as e:
    print(e)
    logging.debug("Unable to execute the code in plugin: %s" % candidate_filepath)
    logging.debug("\t The following problem occured: %s %s " % (os.linesep, e))
```
**Target (both `print()` calls removed per D-04; collapses to one `logging.exception` at ERROR level per D-05):**
```python
candidate_globals = {"__file__":candidate_filepath+".py"}
try:
    with open(candidate_filepath+".py") as f:
        exec(compile(f.read(), candidate_filepath+".py", 'exec'), candidate_globals)
except Exception:
    logging.exception("Unable to execute the code in plugin: %s", candidate_filepath)
```

**Current state (lines 287-290, subclass probe inside hot inner loop):**
```python
try:
    is_correct_subclass = issubclass(element, self.categories_interfaces[category_name])
except:
    continue
```
**Target (D-03 — narrow to the one exception type `issubclass()` can raise for a non-class arg; no logging, this fires on every non-matching symbol and is expected):**
```python
try:
    is_correct_subclass = issubclass(element, self.categories_interfaces[category_name])
except TypeError:
    continue
```

---

### `src/Pellmonsrv/pellmonsrv.py` (daemon entry/controller)

**Analog:** itself — the file's own `logger = getLogger('pellMon')` (declared module-level, confirmed via imports at line 24 `import logging`, module attaches logger elsewhere in file) and existing `except Exception as e: logger.info(...)` blocks are the direct template; this phase just upgrades the log call, not the except type where it's already `Exception`.

**Imports already present (lines 20-40, no changes needed here):**
```python
import signal, os, errno, queue, threading
import dbus, dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib, GObject
import logging
import logging.handlers
...
```

**Category A — plugin activation loop, verified lines 93-103 (steady-state failure path, convert to loud):**
```python
# CURRENT:
try:
    plugin = plugins[plugin_name]
    plugin.plugin_object.activate(conf.plugin_conf[plugin.name], globals(), self)
    self.protocols.append(plugin)
    activated_plugins.append(plugin.name)
except Exception as e:
    failed_plugins.append(plugin.name)
    if conf.command == 'debug':
        raise
    else:
        logger.info('%s plugin error: %s'%(plugin_name, str(e))   )

# TARGET (keep the debug-mode raise branch untouched; only the else-branch log call changes):
except Exception:
    failed_plugins.append(plugin.name)
    if conf.command == 'debug':
        raise
    else:
        logger.exception('%s plugin error'%plugin_name)
```

**Category A — Poller data-read paths, verified lines 258-268:**
```python
# CURRENT:
except IOError as e:
    try:
        conf.database['oxygen_regulation'].value
    except Exception as e:
        logger.info('error in retry %s'%str(e) )
except Exception as e:
    logger.debug('error polling %s: %s'%(data['name'], str(e)) )

# TARGET:
except IOError:
    try:
        conf.database['oxygen_regulation'].value
    except Exception:
        logger.exception('error in retry for %s'%data['name'])
except Exception:
    logger.exception('error polling %s'%data['name'])
```

**Category A — whole-poll-iteration catch-all, verified line 288-289:**
```python
# CURRENT:
except Exception as e:
    logger.info('error in polling %s'%str(e) )

# TARGET:
except Exception:
    logger.exception('error in polling')
```

**Category A — `plugin_dirs` config parse, print-sweep target (D-04). Note: line numbers 744-752 from RESEARCH.md were not re-read this session (outside the 245-295/85-134 ranges directly verified); re-confirm exact line numbers before editing, but the transformation is unambiguous from the pattern already seen:**
```python
# Pattern to apply (matches RESEARCH.md's captured before/after):
except configparser.NoSectionError as e:
    logger.debug('no plugin_dirs section: %s'%str(e))   # narrow — expected/absent-section case, no print, no exception-level log
    pass
except Exception:
    logger.exception('invalid setting for plugin_dirs')  # drop the print(e) call entirely
```

**Category B — leave untouched (do NOT convert, per D-03's own "only hidden bugs should be loud" reasoning applied consistently):**
Config-default-fallback bare excepts inside `config.__init__` (confirmed pattern already present at line 256 `except: pass` for the RRD-counter-wrap guard, and the ~24 similar occurrences RESEARCH.md enumerates in `config.__init__`/`drop_privileges`). Leave these as bare `except:` (out of scope) or narrow to the specific expected type (`KeyError`/`ValueError`/`configparser.NoOptionError`) without adding any logging call. Flag this disposition explicitly in the plan.

---

### `src/Pellmonsrv/plugins/calculate/__init__.py` (plugin, request-response)

**Analog:** itself — `logger.info(calc_item+' error: '+str(e))` (line 331, 357) and `logger.info(str(e))` (line 296, 317) are the file's own established call sites; this phase only changes the log level/call, not the surrounding try/except structure except where D-02/D-03 narrow the except type.

**Category A — the OBS-02 smoking gun, verified lines 345-358 (`setItem`, `unicode()` is a Python-2-only builtin that ALWAYS raises `NameError` under Python 3, currently silently swallowed):**
```python
# CURRENT:
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

# TARGET (logic/return values UNCHANGED — still returns 'error', still masks the
# NameError from the caller — only the log call changes):
        except Exception:
            logger.exception('%s error'%calc_item)
            return 'error'
    except:
        ...   # outer bare except at line 359 is Category B, leave alone (see below)
```

**Category A — `activate()`'s two re-raising blocks, verified lines 295-297 and 316-318:**
```python
# CURRENT (line 295-297, outer activate() exception):
except Exception as e: 
    logger.info(str(e))
    raise e

# CURRENT (line 316-318, top-level activate() exception):
except Exception as e:
    logger.info( str(e))
    raise

# TARGET (keep raise/raise e behavior identical, only upgrade .info -> .exception):
except Exception:
    logger.exception('calculate plugin activation error')
    raise e   # or raise, matching whichever the original block used
```
Also `getItem`'s inner block at line 330-332 follows the identical pattern (`logger.info(calc_item+' error: '+repr(e))` → `logger.exception('%s error'%calc_item)`), same disposition as `setItem` above — confirm during implementation whether this exact line is in the D-02 file scope (it is — `calculate/__init__.py` is one of the three named files) even though RESEARCH.md's Category A table only explicitly walks through `setItem`; `getItem`'s block is the same class of "hidden bug masked by generic error string" and should receive the same treatment for consistency within the file.

**Category B — leave untouched, do NOT add logging (control-flow bare excepts, verified structurally present at lines 333, 340, 359 — `getItem`/`setItem`'s outer `except:` blocks catching `KeyError` from missing `calc_item` key, which is the normal/dominant path for plain non-calculated items):**
```python
# Lines 333, 340 (getItem) and 359 (setItem) — leave bare or narrow to `except KeyError:`
# WITHOUT adding a log call. These fire on every read/write of a non-calculated item.
```

---

### `src/Pellmonsrv/database.py` (model/persistence — needs a logger ADDED)

**Analog for adding the logger:** `src/Pellmonsrv/plugins/consumption/__init__.py` lines 1-30 (verified) — this is the pattern to copy for the *import* + *instantiation* of the shared logger, since `database.py` currently has **no logger at all** (confirmed: only `from weakref import WeakValueDictionary`, `import time`, `import sqlite3, threading` at lines 17-19).

**Imports pattern to copy (from `plugins/consumption/__init__.py:28`):**
```python
from logging import getLogger
...
logger = getLogger('pellMon')   # module-level, per D-01 — shared name, not __name__
```

**Current state, verified lines 111-113 (`Getsetitem.value` setter, `print(e)` fallback flagged by CONVENTIONS.md):**
```python
except Exception as e:
   print(e)
```
**Target:**
```python
except Exception:
    logger.exception('error setting value for %s'%self.name)
```

**Current state, verified lines 168-171 (`Keyval_storage.readval`, `print(e)` fallback):**
```python
except Exception as e:
    print(e)
    return 'error'
```
**Target:**
```python
except Exception:
    logger.exception('error reading value for %s'%item)
    return 'error'
```
Note: RESEARCH.md cites a second `print(e)` occurrence at line 170 inside what it describes as a separate site — on this read, the two flagged `print(e)` occurrences are lines 113 and 170 exactly as enumerated in CONTEXT.md D-04; confirmed both present and both fit this same before/after shape. `writeval`'s equivalent write-path (visible starting line 173 in this read) should be checked for a third `print(e)`/bare-except during implementation since it wasn't fully in the read window — grep `print(` in this file before finalizing the task.

---

### `src/Pellmonsrv/plugins/consumption/__init__.py` (plugin, request-response)

**Analog:** itself — already has `logger = getLogger('pellMon')` wired correctly (line 28 import, confirmed). Only the `print(e)` call site (RESEARCH.md line 209, not directly re-read this session but the module's logger convention is confirmed present) needs `logger.exception(...)`.

**Imports (lines 20-30, verified — use this exact import style if any new module in this phase needs to add a logger):**
```python
from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Item, Getsetitem
from threading import Thread, Timer
from configparser import ConfigParser
from os import path
import os, grp, pwd
import time
from datetime import datetime
from logging import getLogger
from time import mktime
from datetime import datetime
```

---

### NBE protocol package (`plugins/nbecom/__init__.py`, `plugins/nbecom/nbeprotocol/protocol.py`, `plugins/nbecom/nbeprotocol/frames.py`)

**Analog:** each other (sibling modules in the same package) plus `plugins/consumption/__init__.py` for the shared-logger convention if any of the three lacks a module-level logger. Not re-read line-by-line this session (RESEARCH.md's line numbers — `protocol.py`: 75,81,106,115,119,122,132,149,151,197,200,219,233,309,314,317,332; `__init__.py`: 92,99,127,250,267; `frames.py`: 88 — were confirmed by direct grep in the research session and are treated as reliable, but re-grep before editing since this is a 17-occurrence file and line drift risk is nonzero).

**Pattern to apply (debug-trace prints → severity-appropriate logger calls):**
```python
# retry/reconnect trace prints -> logger.debug(...)
# "no more retry" / give-up prints -> logger.warning(...)
# prints inside an except block showing an exception repr -> logger.exception(...)
```
**Typo fix while touching the line (`frames.py:88`, acceptable per RESEARCH.md — it's a log string, not logic):**
```python
# CURRENT:
print('ERRROR chiphertext too short', len(h))
# TARGET:
logger.error('ciphertext too short: %d', len(h))
```
**Caveat:** this package is part of the NBEcom deferred-import chain (Phase 3 territory) — keep changes to logging calls only, do not touch import statements or control flow.

---

### `plugins/onewire/__init__.py`, `plugins/owfs/__init__.py`, `plugins/testplugin/__init__.py`

**Analog:** `plugins/consumption/__init__.py` (shared logger convention).

```python
# onewire/__init__.py:85 -- print(e) -> logger.exception(...)
# owfs/__init__.py:159,193,234 -- print(exc_type, exc_value) inside except: -> logger.exception(...)
# testplugin/__init__.py:64 -- print('testplugin set: ', name, value) -> logger.debug(...)
#   CAUTION: this is a test-fixture plugin used by tests/ -- confirm no test asserts on its stdout before changing
```

---

### `src/Pellmonsrv/daemon.py`

**Analog:** `src/Pellmonsrv/pellmonsrv.py` (once retrofitted) for the `logger.exception`/`logger.error` idiom — this is the daemonizer's last-resort stderr-redirect fallback, so logging (not printing) is the point.

```python
# daemon.py:131 -- print(str(err)) -> logger.exception(...) or at minimum logger.error(str(err))
```

---

### `src/Pellmonweb/pellmonconf.py` and `src/Pellmonweb/pellmonweb.py`

**Analog:** `src/Pellmonweb/pellmonweb.py`'s own `Dbus_handler` class establishes the web-process logger convention (separate `getLogger('pellMon')` instance per D-01 — two processes, two log streams, same logger *name*).

```python
# pellmonconf.py:125 -- print(config_file) -> logger.debug(config_file)
# pellmonconf.py:154,155,156 -- KEEP AS print() -- confirmed intentional CLI startup banner
#   for a manually-invoked standalone tool; converting would silently suppress the banner
#   for zero observability gain. Do not touch these three lines.
# pellmonweb.py:132,138 -- print('server not running')/print('server is running') -> logger.info(...)
# pellmonweb.py:556 -- print(parameterlist) -> logger.debug(...)
```

---

### New test files (`tests/Pellmonsrv/test_plugin_manager_logging.py`, `tests/Pellmonsrv/test_pellmonsrv_logging.py`, `tests/Pellmonsrv/plugins/test_calculate_logging.py`)

**Analog:** `tests/test_plugin_imports.py` (Phase 1 deliverable) — read for structure conventions (test IDs, `ModuleNotFoundError`/skip handling, `PLATFORM_UNAVAILABLE` allowlist pattern). Not re-read line-by-line this session since Phase 1's PATTERNS/VALIDATION already documents its shape in detail and RESEARCH.md's Pitfall 1/3 sections quote its exact catch-clause behavior directly.

**Core pattern to copy:** use pytest's built-in `caplog` fixture to assert a `logging.exception`-level record was emitted with `record.exc_info is not None`, rather than asserting on message text (per RESEARCH.md's Pitfall 5 — never assert on captured-log console text, only structured record attributes).

```python
# tests/Pellmonsrv/plugins/test_calculate_logging.py -- test-only maketrans shim,
# NOT a production fix, must precede the import:
import string
if not hasattr(string, "maketrans"):
    string.maketrans = str.maketrans
import Pellmonsrv.plugins.calculate as calculate_module
```

## Shared Patterns

### Shared logger convention (D-01)
**Source:** `src/Pellmonsrv/plugins/consumption/__init__.py:28` (`from logging import getLogger`) + module-level `logger = getLogger('pellMon')` instantiation used across 15+ files per CONVENTIONS.md.
**Apply to:** Every file in this phase that logs, including `database.py` which currently has none. Do NOT switch to `getLogger(__name__)` — this is a locked decision (D-01).

### Exception-visibility substitution (the whole phase's core pattern)
**Source:** `src/Pellmonsrv/pellmonsrv.py:93-103` is the best "already half-right" example in the codebase — bare `except Exception as e: logger.info(...)` upgraded to `except Exception: logger.exception(...)`.
```python
try:
    <risky call>
except Exception:
    logger.exception("<same or clarified message, no %s manual interpolation of e>")
    <same fallback/return value as before -- control flow UNCHANGED>
```
**Apply to:** All Category-A blocks across `PluginManager.py`, `pellmonsrv.py`, `plugins/calculate/__init__.py`, plus every `print(e)`-in-`except` site in the D-04 sweep list.

### Narrow-but-silent exception typing (D-03's "hidden bug vs. expected control flow" test)
**Source:** `PluginManager.py:287-290` (subclass probe → `except TypeError:`), mirrored for `calculate/__init__.py` lines 333/340/359 (`except KeyError:` for missing `calc_item`) and `pellmonsrv.py`'s `config.__init__` optional-value fallbacks.
**Apply to:** Any bare `except:` in the three D-02 files that fires on every normal iteration/call (Category B) — narrow the type, do not add a log call, do not convert to `logger.exception`.

## No Analog Found

None. Every file in this phase's scope already has an internally-consistent existing pattern (either its own established `logger.info`/`logging.debug` call sites, or a sibling file in the same package with the shared-logger convention already wired up) to copy from — this is expected for a pure observability-retrofit phase touching only existing files.

## Metadata

**Analog search scope:** `src/Pellmonsrv/`, `src/Pellmonsrv/yapsy/`, `src/Pellmonsrv/plugins/*/`, `src/Pellmonweb/`, `tests/` (Phase 1 artifact)
**Files scanned/read directly this session:** `src/Pellmonsrv/database.py` (lines 1-40, 100-180), `src/Pellmonsrv/yapsy/PluginManager.py` (lines 190-295), `src/Pellmonsrv/pellmonsrv.py` (lines 1-40, 85-134, 245-295), `src/Pellmonsrv/plugins/calculate/__init__.py` (lines 280-360), `src/Pellmonsrv/plugins/consumption/__init__.py` (lines 1-30)
**Files relied on from RESEARCH.md without independent re-read this session (line numbers treated as reliable but should be re-grepped immediately before each edit task, since RESEARCH.md itself flags line-drift risk):** `daemon.py:131`, `plugins/nbecom/__init__.py` (5 sites), `plugins/nbecom/nbeprotocol/protocol.py` (17 sites), `plugins/nbecom/nbeprotocol/frames.py:88`, `plugins/onewire/__init__.py:85`, `plugins/owfs/__init__.py` (3 sites), `plugins/testplugin/__init__.py:64`, `Pellmonweb/pellmonconf.py` (125, 154-156), `Pellmonweb/pellmonweb.py` (132, 138, 556), `pellmonsrv.py:744-752` (plugin_dirs config parse)
**Pattern extraction date:** 2026-09-17
