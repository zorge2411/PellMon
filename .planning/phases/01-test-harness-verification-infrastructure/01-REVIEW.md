---
phase: 01-test-harness-verification-infrastructure
reviewed: 2026-09-17T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - pytest.ini
  - requirements-dev.txt
  - tests/conftest.py
  - tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py
  - tests/Pellmonsrv/test_database.py
  - tests/Pellmonweb/test_auth.py
  - tests/test_plugin_imports.py
  - tests/test_socket_guardrail.py
  - tests/README.md
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-09-17
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the new pytest harness (`pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`, and the five test modules plus `tests/README.md`). The suite is unusually well-documented: fixtures and tests carry precise line-number references back into the source they exercise (`database.py:153-156`, `auth.py:147,150`, etc.), and those references were spot-checked against the current source (`src/Pellmonsrv/database.py`, `src/Pellmonweb/auth.py`, `src/Pellmonsrv/plugins/nbecom/__init__.py`) and found accurate. The `known_broken` marker mechanism, the `--disable-socket` guardrail, and the two hardware-mock fixtures (`loop_serial`, `mocked_udp_socket`) all behave as documented and are self-verifying (removing `--disable-socket` would make `test_socket_guardrail.py` fail on its own, not silently pass).

No critical/security issues were found in the test code itself. Two warnings are worth fixing: one test's name overstates what it actually verifies and as a result fails to catch a real latent bug in the code it's supposed to characterize (`database.py`'s `writeval`/`confval` path binds the wrong value to the `value` column), and the marker-based green/red gate has no `--strict-markers` protection against a future typo silently breaking the `known_broken` filtering this whole harness design depends on.

## Warnings

### WR-01: `test_writeval_with_confval_sets_both_columns` doesn't actually verify both columns, masking a real bug in the code path it exercises

**File:** `tests/Pellmonsrv/test_database.py:60-74`
**Issue:** The test name and docstring claim to exercise the "nested bare except: upsert path" in `Keyval_storage.writeval` (`database.py:198-200`) and to confirm it "sets both columns." It only asserts on `confvalue`:
```python
store.writeval("ckey", value="v1", confval="c1")
...
cursor.execute("SELECT confvalue FROM keyval WHERE id=?", ("ckey",))
confvalue, = next(cursor)
...
assert confvalue == "c1"
```
It never reads back the `value` column. That matters because both the primary branch (`database.py:196`) and the fallback branch this test targets (`database.py:199`) contain the same bug — they bind `(item, confval, confval)` instead of `(item, value, confval)`:
```python
cursor.execute("INSERT OR REPLACE INTO keyval (id, value, confvalue) VALUES (?,?,?)", (item, confval, confval))
```
So after this test runs, the `value` column for `ckey` actually contains `"c1"`, not the `"v1"` the test wrote — the opposite of "sets both columns" correctly. Because the test never checks `value`, it gives false confidence that this path is correct and would not catch a regression (or catch the existing defect) if/when `database.py` is touched in a later phase.
**Fix:** Add an assertion on the `value` column so the test documents current (buggy) behavior explicitly, e.g.:
```python
cursor.execute("SELECT value FROM keyval WHERE id=?", ("ckey",))
value, = next(cursor)
conn.close()

assert confvalue == "c1"
# database.py:196/199 currently bind confval into the value column too --
# this documents the existing defect (owner: a later phase) rather than
# silently ignoring it.
assert value == "c1"  # NOTE: expected "v1"; tracks a known database.py bug
```
Or, preferably, promote this into an explicit `known_broken`-marked test that asserts `value == "v1"` and is expected to fail until the underlying `writeval` bug is fixed — consistent with how `test_plugin_imports.py` handles other known, still-unfixed defects.

### WR-02: No `--strict-markers`, so a typo in `known_broken` would silently break the green/red baseline split

**File:** `pytest.ini:1-6`
**Issue:** The entire harness design (per `tests/README.md`) depends on `@pytest.mark.known_broken` reliably separating the "green baseline gate" (`pytest -m "not known_broken"`) from the full-truth run. Without `--strict-markers` in `addopts`, pytest accepts any marker name silently — a future contributor mistyping `@pytest.mark.know_broken` or `@pytest.mark.knwon_broken` on a new expected-red test would not raise a `PytestUnknownMarkWarning`-as-error; the mistyped test would simply be included in the "green" gate and, if it's a genuinely still-broken migration defect, would break CI without any indication that the marker was the problem.
**Fix:** Add `--strict-markers` to `addopts`:
```ini
[pytest]
pythonpath = src
testpaths = tests
addopts = --disable-socket --strict-markers
markers =
    known_broken: documents a confirmed, still-unfixed Python 3 defect; expected to FAIL until the phase named in the test docstring fixes it
```

## Info

### IN-01: `requirements-dev.txt` uses ceiling pins, inconsistent with the project's documented floor-only convention

**File:** `requirements-dev.txt:2-5`
**Issue:** CLAUDE.md documents that `requirements.txt` intentionally "uses `>=` version floors only" so builds aren't over-constrained, and notes there's no lockfile. `requirements-dev.txt` instead pins upper bounds (`pytest>=9.0,<10`, etc.) for every dependency. This isn't wrong for dev/test tooling, but it's an unexplained deviation from the stated project convention and could surprise a future contributor who assumes the same floor-only policy applies everywhere.
**Fix:** Add a one-line comment in `requirements-dev.txt` explaining the ceiling-pin rationale (protecting the test harness from breaking pytest major-version changes), or align with the floor-only convention if that wasn't a deliberate choice.

### IN-02: Sqlite connections opened in test bodies aren't closed on assertion-failure paths

**File:** `tests/Pellmonsrv/test_database.py:16-34, 60-74`
**Issue:** `test_init_fallback_path_when_table_missing` and `test_writeval_with_confval_sets_both_columns` open a raw `sqlite3.connect(dbfile)` and only call `conn.close()` after multiple `cursor.execute()`/`next()` calls that could themselves raise. If one of those calls raises (e.g., during a future regression), the connection is left open when the test fails. Since `CLAUDE.md` specifically calls out Windows as a primary dev platform (`venv-py3`), an open sqlite3 handle can hold an OS-level file lock on the `tmp_path`-backed `.db` file, which is more likely to cause a leaked/locked-file surprise on Windows than on Linux during a later cleanup or retry.
**Fix:** Use a `with sqlite3.connect(dbfile) as conn:` block, or wrap the assertions in `try/finally: conn.close()`, so the connection is always released even when the test itself is failing.

---

_Reviewed: 2026-09-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
