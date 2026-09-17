---
phase: 02-exception-visibility-retrofit
plan: 05
subsystem: observability
tags: [logging, print-sweep, nbecom, database, pellmonweb, pellmonconf]
dependency-graph:
  requires:
    - "02-01 (JUnit outcome baseline, junit-outcome-diff.py)"
  provides:
    - "39 in-scope print() calls converted to shared-pellMon-logger calls across 11 files"
    - "Five new module loggers: database.py, daemon.py, nbeprotocol/frames.py, pellmonweb.py, pellmonconf.py"
  affects:
    - "02-06 (the plan that turns the repo-wide print() grep into an enforced pytest gate)"
tech-stack:
  added: []
  patterns:
    - "logger = getLogger('pellMon') module-scope shared logger (D-01), copied from plugins/consumption/__init__.py"
    - "logger.exception(<fixed message>) inside except blocks, dropping manual repr(e)/str(e) interpolation since exception() attaches the traceback"
key-files:
  created: []
  modified:
    - src/Pellmonsrv/database.py
    - src/Pellmonsrv/daemon.py
    - src/Pellmonsrv/plugins/consumption/__init__.py
    - src/Pellmonsrv/plugins/onewire/__init__.py
    - src/Pellmonsrv/plugins/owfs/__init__.py
    - src/Pellmonsrv/plugins/testplugin/__init__.py
    - src/Pellmonsrv/plugins/nbecom/__init__.py
    - src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py
    - src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py
    - src/Pellmonweb/pellmonweb.py
    - src/Pellmonweb/pellmonconf.py
decisions: []
metrics:
  duration_minutes: 55
  completed: 2026-09-17
---

# Phase 2 Plan 05: Print-to-Logger Sweep (Daemon Core, NBE Protocol, Web Process) Summary

Converted all 39 in-scope `print()` calls across eleven `src/Pellmonsrv/` and `src/Pellmonweb/` files to shared-`pellMon`-logger calls at appropriate severity levels, added the shared-name module logger to the five files that had none, and left `pellmonconf.py`'s three-line CLI startup banner untouched (annotated as the intentional D-04 carve-out).

## What Was Built

### Task 1: Daemon core and simple plugins (6 files, 8 print sites)

- `src/Pellmonsrv/database.py` — added `from logging import getLogger` + `logger = getLogger('pellMon')` (file had no logger). Converted `Getsetitem`'s value-setter `print(e)` and `Keyval_storage.readval`'s `print(e)` to `logger.exception(...)`, narrowing both `except Exception as e:` clauses to `except Exception:`. Only 2 print sites existed (no third site in `writeval`, contrary to the plan's speculative note — `writeval`'s `except Exception as e: raise` had no print).
- `src/Pellmonsrv/daemon.py` — added the same logger pair (file had no logger). The plan's read_first pointed at a "stderr-redirect fallback" at ~line 131, but the actual print site is in `stop()`'s `OSError` handler (last-resort path when killing the daemon process fails for a reason other than "No such process"). Converted `print(str(err))` to `logger.exception('error stopping daemon process %s'%pid)`.
- `plugins/consumption/__init__.py` (logger already present) — `barchartdata`'s `except Exception as e: print(e); return str(e)` converted to `logger.exception('error generating barchartdata')`, keeping `as e` since `str(e)` is still used in the return value.
- `plugins/onewire/__init__.py` (logger already present) — the `activate()` catch-all already had `logger.debug(...)` one line above the print; added a second `logger.exception('Onewire activate failed')` call (full traceback, distinct from the existing debug-level `str(e)` summary) and removed the redundant print.
- `plugins/owfs/__init__.py` (logger already present) — all three `print(exc_type, exc_value)` sites (in `getItem`, `setItem`, `counter_thread`) converted to `logger.exception(...)` naming the enclosing operation and the relevant item/counter. Per plan instruction, left the `exc_type, exc_value, exc_traceback = sys.exc_info()` assignments and the subsequent `traceback.print_tb(..., file=sys.stdout)` calls untouched — those are out of this plan's explicit `print(` scope and still exist as prior stdout output (not addressed here).
- `plugins/testplugin/__init__.py` (logger already present) — the setter's debug trace `print('testplugin set: ', name, value)` converted to `logger.debug('testplugin set: %s %s', name, value)`.

Verified: `grep -rn "print("` across all six files returns no matches; `getLogger('pellMon')` count is 1 for both `database.py` and `daemon.py`; `getLogger(__name__)` count is 0 repo-wide (D-01 preserved); full suite still `29 passed, 8 skipped`.

### Task 2: NBE protocol package (3 files, 23 print sites)

`plugins/nbecom/nbeprotocol/protocol.py` (17 sites, logger already present) — assigned levels by reading each site's surrounding context:

| Line (pre-edit) | Site | Level assigned |
|---|---|---|
| 75 | `get_rsakey` retry trace | `logger.debug` |
| 81 | `get_rsakey` except-Exception repr | `logger.exception` |
| 106 | `set()` "use rsa for xtea set" trace | `logger.debug` |
| 115 | `set()` "set error: %s" before raising `protocol_error` | `logger.debug` |
| 119 | `set()` `except protocol_error:` retry trace | `logger.debug` |
| 122 | `set()` xtea-key-delete trace | `logger.debug` |
| 132 | `set()` "no more set retry" (give up) | `logger.warning` |
| 149 | `get()` `except:` retry trace | `logger.debug` |
| 151 | `get()` "no more get retry" (give up) | `logger.warning` |
| 197 | `find_controller` `except seqnum_error as e:` | `logger.exception` |
| 200 | `find_controller` `except Exception as e:` (per-retry) | `logger.exception` |
| 219 | `find_controller` "lost conn" (connection-lost) | `logger.warning` (merged with the adjacent pre-existing `logger.info('Lost connection to controller')` into a single warning-level call, since both fired on the same branch) |
| 233 | `find_controller` outer `except Exception as e:` ("don't ever die in this thread") | `logger.exception` |
| 309 | `make_request` `except seqnum_error as e:` | `logger.exception` |
| 314 | `make_request` `except socket.timeout as e:` | `logger.exception` |
| 317 | `make_request` `except Exception as e:` | `logger.exception` |
| 332 | `xtea_refresh_thread` success trace after xtea-key reset | `logger.debug` |

`plugins/nbecom/__init__.py` (5 sites, logger already present):
- Line 92 `print('wait controller')` (state trace) -> `logger.debug('wait controller')`.
- Line 99 `except Exception as e: print(repr(e), 'direrror')` -> `logger.exception('error requesting directory list')`.
- Line 127 `except Exception as e: print(repr(e), 'exc in getgroup', name, time.time())` -> `logger.exception('exc in getgroup for %s', name)` (retains the `name` per plan instruction).
- Line 250 (`eventlogger` loop) and line 267 (`alarm_poller` loop), both `except Exception as e: print(repr(e))` -> `logger.exception('error in eventlogger loop')` / `logger.exception('error in alarm_poller loop')` respectively.

`plugins/nbecom/nbeprotocol/frames.py` — added `from logging import getLogger` + `logger = getLogger('pellMon')` (file had no logger). Converted `print('ERRROR chiphertext too short', len(h))` to `logger.error('ciphertext too short: %d', len(h))`, correcting both typos (`ERRROR` -> nothing, `chiphertext` -> `ciphertext`) as explicitly sanctioned by the plan.

Verified: `grep -rn "print("` under `plugins/nbecom/` returns no matches; `getLogger('pellMon')` count is 1 in `frames.py`; `ciphertext too short` present, `ERRROR`/`chiphertext` absent; `git diff src/Pellmonsrv/plugins/nbecom/` contains no changed `import`/`if`/`while`/`for`/`return`/`raise` line and no changed exception class name (only `except X as e:` -> `except X:` bindings where `e` became unused); `tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import` still fails with `ModuleNotFoundError: No module named 'frames'` (confirmed via direct pytest run); full suite `29 passed, 8 skipped`.

### Task 3: Web process, preserving the pellmonconf CLI banner (2 files, 4 print sites converted + 3 preserved)

`src/Pellmonweb/pellmonweb.py` — added `from logging import getLogger` to the import block and `logger = getLogger('pellMon')` at module scope (file had no logger; this is a separate process from the daemon, sharing the logger *name* per D-01, not a shared handler/stream). Converted:
- `Dbus_handler.start()`'s `print('server not running')` -> `logger.info('D-Bus server not running')`.
- `Dbus_handler.start()`'s `print('server is running')` -> `logger.info('D-Bus server is running')`.
- The per-page-view `print(parameterlist)` -> `logger.debug('parameterlist: %s', parameterlist)`.

No `cherrypy.log(...)` call was touched (confirmed via `git diff`).

`src/Pellmonweb/pellmonconf.py` — added the same logger pair (file had no logger). Converted the config-path print `print(config_file)` -> `logger.debug('config file: %s', config_file)`. Left the three-line CLI startup banner (`Open http://...`, `Run as root...`, `Quit with CTRL-C`) as bare `print()` calls, unchanged, per D-04's intentional-CLI-output carve-out, and added a `#` comment immediately above the banner recording that it is deliberately excluded from the OBS-03 sweep.

Verified: `grep -c "print("` on `pellmonweb.py` returns 0; `grep -n "print("` on `pellmonconf.py` returns exactly 3 matches (all three banner lines); the annotation comment is present above them; `getLogger('pellMon')` count is 1 in each file; `tests/Pellmonweb/test_auth.py` — 6/6 passed, unchanged; full suite `29 passed, 8 skipped`.

## Overall Verification

- `grep -rn "print("` across all eleven of this plan's files (outside `pellmonconf.py`'s banner) returns zero matches.
- `grep -n "print("` on `pellmonconf.py` returns exactly the 3 banner lines.
- Repo-wide `grep -rn "print(" src/Pellmonsrv src/Pellmonweb --include="*.py" | grep -v "\.py2bak"` shows only the 3 pellmonconf.py banner lines plus sites in `pellmonsrv.py` and `yapsy/PluginManager.py` — both owned by plans 02/03, not this plan's scope.
- Full-truth run: `venv-py3/Scripts/python.exe -m pytest tests/ -v --junitxml=...` -> `2 failed, 29 passed, 8 skipped, 39 testcases` — identical to `before.xml`.
- `junit-outcome-diff.py before.xml <after>` -> `CHANGED: 0, DISAPPEARED: 0, ADDED: 0` -> `IDENTICAL pass/fail/skip status before and after`. The temporary after-XML used for this comparison was deleted after the check (not a committed deliverable).
- ASVS V7 watch-list check: none of the new log interpolations in `nbecom`/`nbeprotocol` render `password`, `pincode`, `xtea_key`, or RSA key material — only function/path/item/counter names and status codes are interpolated. `pellmonweb.py`'s new logging calls interpolate `parameterlist` (item data, not session/credential state) and static strings only.

## Deviations from Plan

**1. [Rule 1 - clarification] daemon.py's actual print site differs from the plan's `<read_first>` description**
- **Found during:** Task 1
- **Issue:** The plan's read_first pointed at "lines 110-145 for the stderr-redirect fallback `print(str(err))`", implying the print sits in the stdio-redirect section of `daemonize()`. The actual and only print site in the file is in `stop()`'s `OSError` handler when killing the daemon process fails for a reason other than "No such process" — a different code path with the same characteristic (last-resort path where printing to a possibly-closed stdout is unreliable).
- **Fix:** Converted the actual site found by grep, using a message naming the operation (`'error stopping daemon process %s'%pid`) instead of the plan's suggested message.
- **Files modified:** `src/Pellmonsrv/daemon.py`
- **Commit:** `abdd61a`

**2. [Rule 1 - minor cleanup] onewire/__init__.py had a redundant `logger.debug` already logging the same exception one line above the print**
- **Found during:** Task 1
- **Issue:** The single print site at `plugins/onewire/__init__.py` sat directly beneath an existing `logger.debug('Onewire activate failed: %s'%str(e))` call, meaning any conversion of the print alone would either duplicate the debug-level message or drop the traceback entirely.
- **Fix:** Kept the existing debug-level summary line and added a `logger.exception('Onewire activate failed')` call (attaches full traceback, a strict improvement over the print which had none) in place of the print.
- **Files modified:** `src/Pellmonsrv/plugins/onewire/__init__.py`
- **Commit:** `abdd61a`

**3. [Rule 1 - minor cleanup] nbeprotocol/protocol.py's "lost conn" print sat directly above an existing `logger.info` with the same message**
- **Found during:** Task 2
- **Issue:** `find_controller`'s connection-lost branch had both a `print('-------------------lost conn')` and, on the very next line, `logger.info('Lost connection to controller')` — firing on the exact same condition. Converting the print alone while leaving the info call would produce two log records (one info, one converted) for a single event.
- **Fix:** Merged the two into a single `logger.warning('Lost connection to controller')` call, matching the plan's stated severity guidance ("connection-lost prints -> `logger.warning`") and removing the duplicate `logger.info`.
- **Files modified:** `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`
- **Commit:** `2b65d0f`

No architectural changes, no auth gates, no fix-attempt-limit issues.

## Known Stubs

None.

## Threat Flags

None — this is a pure logging-call substitution; the ASVS V7 credential-interpolation check (per this plan's `<threat_model>`) was applied at every converted `nbecom`/`nbeprotocol` and `pellmonweb` site and found no secret material interpolated into any new log message.

## Self-Check: PASSED

- `src/Pellmonsrv/database.py` — FOUND, contains `getLogger('pellMon')`
- `src/Pellmonsrv/daemon.py` — FOUND, contains `getLogger('pellMon')`
- `src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py` — FOUND, contains `getLogger('pellMon')`
- `src/Pellmonweb/pellmonweb.py` — FOUND, contains `getLogger('pellMon')`
- `src/Pellmonweb/pellmonconf.py` — FOUND, contains `getLogger('pellMon')` and the 3-line banner with its annotation comment
- Commit `abdd61a` (Task 1) — FOUND in `git log --oneline`
- Commit `2b65d0f` (Task 2) — FOUND in `git log --oneline`
- Commit `8bd3041` (Task 3) — FOUND in `git log --oneline`
- `venv-py3/Scripts/python.exe -m pytest tests/ -q -m "not known_broken"` — 29 passed, 8 skipped (matches pre-change baseline)
- `junit-outcome-diff.py` self-comparison against `before.xml` — IDENTICAL pass/fail/skip status
