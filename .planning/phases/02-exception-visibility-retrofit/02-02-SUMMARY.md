---
phase: 02-exception-visibility-retrofit
plan: 02
subsystem: plugin-loading
tags: [observability, logging, yapsy, tdd]
dependency-graph:
  requires:
    - "02-01 (before.xml baseline, junit-outcome-diff.py)"
  provides:
    - "OBS-01: loud plugin-load failures in Pellmonsrv.yapsy.PluginManager"
    - "tests/Pellmonsrv/test_plugin_manager_logging.py (caplog regression suite)"
  affects:
    - "Phase 3 IMPORT-01/IMPORT-02 work will now surface via a full traceback in
       the log instead of a swallowed one-liner when ScotteCom/NBEcom plugin
       modules fail to exec"
tech-stack:
  added: []
  patterns:
    - "logging.exception(...) inside except Exception: for plugin exec failures
       (auto-captures traceback, no manual exc_info bookkeeping needed)"
    - "logging.debug(..., exc_info=True) for expected-but-should-still-be-loud
       failures kept at DEBUG severity (descriptor parse)"
    - "except TypeError: with zero logging for hot-loop probes that fire on
       every normal non-matching iteration (issubclass probe)"
key-files:
  created:
    - tests/Pellmonsrv/test_plugin_manager_logging.py
  modified:
    - src/Pellmonsrv/yapsy/PluginManager.py
decisions: []
metrics:
  duration_minutes: 25
  completed: 2026-09-17
---

# Phase 2 Plan 02: Loud Plugin-Load Failures (OBS-01) Summary

Made yapsy's plugin-exec failure path emit a full ERROR-level traceback via `logging.exception(...)` instead of a swallowed `logging.debug` one-liner, while narrowing two adjacent bare `except:` clauses per their D-03 disposition (descriptor-parse stays DEBUG+traceback, subclass probe narrows to `except TypeError:` with no logging) — a strict TDD RED→GREEN cycle against a new caplog regression suite, with zero print() calls remaining in the file.

## What Was Built

### Task 1 (RED): `tests/Pellmonsrv/test_plugin_manager_logging.py`

Three caplog-based tests against `Pellmonsrv.yapsy.PluginManager`, using `tmp_path`-based fake plugin directories (no `daemon_module` fixture needed — this module imports cleanly today):

- `test_broken_plugin_exec_failure_logs_error_with_traceback` — writes a `broken.pellmon-plugin` descriptor + `broken.py` that raises `RuntimeError` at module-exec time; asserts an ERROR-level record with `exc_info is not None`, `exc_info[0] is RuntimeError`, and `"Unable to execute the code in plugin"` in the message; asserts `loadPlugins()` does not raise (broken plugin still skipped).
- `test_malformed_descriptor_logs_debug_with_traceback` — writes an unparseable `.pellmon-plugin` file; asserts a DEBUG-level record with `exc_info is not None` and `"Could not parse the plugin file"` in the message.
- `test_normal_plugin_scan_probe_stays_silent` — loads a valid plugin module with several non-class module-level symbols; asserts zero records mention `issubclass` and zero ERROR-level records.

All assertions read `record.levelno`, `record.exc_info`, and `record.getMessage()` — never `caplog.text` or captured stdout, per 02-RESEARCH.md Pitfall 5.

**RED result (commit `52cf8d7`):** `pytest tests/Pellmonsrv/test_plugin_manager_logging.py -v` → 2 failed (assertion errors on the exec-failure and descriptor-parse tests — both `assert []` for missing ERROR/DEBUG+exc_info records), 1 passed (probe-silence, since `except:` already only fires on `TypeError` in practice and adds no log call). No collection or import errors.

### Task 2 (GREEN): `src/Pellmonsrv/yapsy/PluginManager.py` — exactly three edits

1. **Descriptor parse** (`locatePlugins`): `except:` → `except Exception:`; `logging.debug("Could not parse the plugin file %s" % candidate_infofile)` → `logging.debug("Could not parse the plugin file %s", candidate_infofile, exc_info=True)` (lazy `%`-args + traceback attached, stays at DEBUG per D-03 since `logging.exception()` is hardcoded to ERROR).
2. **Plugin exec** (`loadPlugins`, the OBS-01 target): removed `print(candidate_filepath)` and `print(e)`; `except Exception as e:` → `except Exception:`; collapsed the two `logging.debug(...)` calls into one `logging.exception("Unable to execute the code in plugin: %s", candidate_filepath)`.
3. **Category subclass probe** (`loadPlugins` inner loop): `except:` → `except TypeError:`, no logging added — `issubclass()` only ever raises `TypeError` for a non-class argument, and this probe fires on every non-matching module-level symbol during a normal scan.

**GREEN result (commit `cec7ed1`):** `pytest tests/Pellmonsrv/test_plugin_manager_logging.py -v` → 3 passed. Full suite `pytest tests/Pellmonsrv/test_plugin_manager_logging.py tests/ -q -m "not known_broken"` → 32 passed, 8 skipped, 2 deselected, exit 0.

## Verification

- `grep -n "print(" src/Pellmonsrv/yapsy/PluginManager.py` → no matches.
- `grep -c "logging.exception" src/Pellmonsrv/yapsy/PluginManager.py` → 1.
- `grep -n "except TypeError:" src/Pellmonsrv/yapsy/PluginManager.py` → exactly 1 match (the `issubclass` probe).
- `grep -vn "^\s*#" src/Pellmonsrv/yapsy/PluginManager.py | grep -c "except:\s*$"` → 0 (both bare-except sites removed).
- Full-truth run diffed against `before.xml` via `junit-outcome-diff.py`: `BEFORE 39 / AFTER 42`, `CHANGED: 0`, `DISAPPEARED: 0`, `ADDED: 3` (the three new tests, informational only) → `IDENTICAL pass/fail/skip status before and after`. Confirms the two known-red Phase 3 failures (`scottecom`, `nbecom` deferred-import) are unchanged and no other test outcome shifted.
- `git diff` of the PluginManager.py commit shows exactly the three targeted `except` blocks changed and exactly two `print()` calls removed — no other line differs.

## TDD Gate Compliance

RED gate: commit `52cf8d7` (`test(02-02): add caplog regression test...`) — 2 failed / 1 passed against unmodified source, assertion errors not collection errors. GREEN gate: commit `cec7ed1` (`feat(02-02): make yapsy plugin-load failures loud...`) — all 3 tests pass immediately after. No REFACTOR commit was needed (the GREEN edit was already minimal and matched the plan's exact target diff).

## Deviations from Plan

### Auto-fixed Issues

None — no bugs, blockers, or missing critical functionality encountered during execution.

### Informational note (not a deviation, no action taken)

The plan's `<interfaces>` block and 02-PATTERNS.md both state "this file does NOT use `getLogger('pellMon')`. It calls the `logging` module-level functions directly." On re-verification, `PluginManager.py` line 30 (pre-existing, untouched by this plan) actually reads `logging = getLogger('pellMon')` — the module-level name `logging` is rebound to the shared `pellMon` Logger instance rather than the stdlib `logging` module. Functionally this makes no difference to the required behavior: `logging.exception(...)` and `logging.debug(..., exc_info=True)` both resolve to `Logger.exception`/`Logger.debug` bound methods on the shared logger, which is exactly what the acceptance criteria require (all 3 caplog tests pass using `caplog`, which attaches to the root logger hierarchy regardless of this aliasing). No code change was made in response to this — it is pre-existing, already-correct behavior, not something this plan's scope touches. Flagged here only because the literal acceptance-criteria grep `grep -n "getLogger" src/Pellmonsrv/yapsy/PluginManager.py` returns 1 match (line 25 `from logging import getLogger` + line 30 usage) rather than 0, contradicting the plan's stale assumption; the underlying intent of that criterion — "do not introduce a new/different logger convention" — is satisfied since nothing was added or changed at that line.

## Known Stubs

None.

## Threat Flags

None — this plan only changes log verbosity/severity on an existing exec/parse failure path. The one interpolated value (`candidate_filepath`) is a filesystem path, never a credential, matching the plan's `<threat_model>` (N/A, no information-disclosure risk introduced).

## Self-Check: PASSED

- `tests/Pellmonsrv/test_plugin_manager_logging.py` — FOUND
- `src/Pellmonsrv/yapsy/PluginManager.py` — FOUND
- Commit `52cf8d7` (RED: caplog regression test) — FOUND in `git log --oneline --all`
- Commit `cec7ed1` (GREEN: PluginManager.py edits) — FOUND in `git log --oneline --all`
