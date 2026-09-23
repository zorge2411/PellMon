---
phase: 09-add-docker-hub-image-publishing-with-semver-versioning
plan: 01
subsystem: tooling
tags: [semver, ci, python, tdd]
requires: []
provides:
  - tools/version_bump.py (decide_bump/apply_bump/parse_version/format_version pure functions,
    last_tag/commits_since/_run git I/O wrappers, decide CLI subcommand)
  - VERSION file seeded at 1.0.0 (repo root)
affects:
  - .github/workflows/ci.yml (Plan 02 will add a publish job that shells out to this CLI)
tech-stack:
  added: []
  patterns:
    - "Pure decision function separated from I/O (mirrors tools/pellmon_backup.py's _run() choke point)"
key-files:
  created:
    - tools/version_bump.py
    - tests/test_version_bump.py
    - VERSION
  modified: []
decisions:
  - "VERSION seeded at 1.0.0 (D-09 bootstrap value, repo has zero git tags today)"
  - "configure.ac's AC_INIT([PellMon], [0.7.0]) left untouched per D-08, guarded by a dedicated test"
metrics:
  duration: ~25min
  completed: 2026-09-23
---

# Phase 9 Plan 1: Semver bump algorithm (tools/version_bump.py) Summary

Ported the reference `increment-version.ps1` bump-decision algorithm to a pure, pytest-covered
`decide_bump()` function plus thin git/file I/O wrappers in `tools/version_bump.py`, and seeded
the repo's `VERSION` file at `1.0.0`.

## What Was Built

- **`tools/version_bump.py`** — stdlib-only (`argparse`, `logging`, `os`, `re`, `subprocess`,
  `sys`) CLI tool following `tools/pellmon_backup.py`'s conventions (GPL header, `logger =
  logging.getLogger('version_bump')`, `%`-formatting, no f-strings, no type hints, `_run()`
  list-argv subprocess choke point, `main(argv=None)` try/except-and-return-1 idiom).
  - `decide_bump(commit_messages)` — pure function, zero I/O. Checks, in priority order:
    `'BREAKING CHANGE'` substring anywhere → `'major'`; `^feat(\(.+\))?:` line-start match →
    `'minor'`; `^fix(\(.+\))?:` line-start match → `'patch'`; else `None`. Priority is
    existence-based, not chronological.
  - `apply_bump(version_tuple, bump_type)`, `parse_version(text)` (hard-fails with `ValueError`
    on anything other than exactly 3 int-parseable dot-separated parts — no `v`-prefix
    stripping, no coercion), `format_version(version_tuple)`.
  - `read_version(path)` / `write_version(path, version_tuple)` — file I/O.
  - `last_tag()` — `git describe --tags --abbrev=0` with `check=False`, returns `None` on
    non-zero exit (the genuine first-run case: this repo has zero tags today).
  - `commits_since(tag)` — `git log {tag}..HEAD --pretty=%B` (or full history when `tag` is
    `None`), returns `result.stdout.splitlines()`.
  - CLI: `decide [--dry-run] [--type major|minor|patch] [--version-file VERSION]`. Emits
    `bump=<type|none>` and `version=<x.y.z>` to stdout and, when `$GITHUB_OUTPUT` is set,
    appends the same lines to that file for Plan 02's workflow to consume.
- **`tests/test_version_bump.py`** — 20 tests, all passing, no skip markers on the 16
  pure-function tests (D-06: run with no git/Docker present). 4 additional tests added in Task 3:
  two config-assertion guards (`VERSION` well-formedness, `configure.ac` untouched) and two
  git-backed integration tests (`pytest.mark.skipif(shutil.which('git') is None, ...)`) exercising
  the real "no tags yet" bootstrap path with a throwaway `tmp_path` git repo.
- **`VERSION`** — repo root, contains exactly `1.0.0\n` (verified via `open('VERSION','rb').read()
  == b'1.0.0\n'`).

## Task Execution (TDD RED/GREEN)

1. **RED** (`e4526fa`) — `tests/test_version_bump.py` with 16 named tests; collection fails with
   `FileNotFoundError` because `tools/version_bump.py` doesn't exist yet.
2. **GREEN** (`e605cbd`) — `tools/version_bump.py` implementing the full interface contract; all
   16 tests pass.
3. **Follow-up** (`ff7cf47`) — `VERSION` seeded at `1.0.0`, 4 more tests appended (D-08 guard,
   git-backed `last_tag`/`commits_since` bootstrap coverage). 20/20 pass.

## Verification

- `python -m pytest tests/test_version_bump.py -v` — 20/20 passed, 0 skipped (git is present in
  this dev environment).
- `python tools/version_bump.py decide --dry-run --type patch` → prints `bump=patch` /
  `version=1.0.1`, `VERSION` unchanged (byte-identical, confirmed via `git diff --stat VERSION`
  before commit and a raw-bytes read after).
- `python tools/version_bump.py --help` exits 0, lists the `decide` subcommand.
- `grep -c "shell=True" tools/version_bump.py` → 0.
- `grep -c "getLogger('version_bump')" tools/version_bump.py` → 1.
- `grep -c 'f"' tools/version_bump.py` → 0 (no f-strings).
- `grep -c "configure.ac\|version.py.in" tools/version_bump.py` → 0 (D-08 — reworded the
  docstring to avoid literal filename matches while still documenting the constraint).
- `git diff --stat configure.ac` — empty (D-08, `AC_INIT([PellMon], [0.7.0])` untouched).
- `python -m pytest tests/ -v` — no NEW failures. Pre-existing collection errors
  (`ModuleNotFoundError: cherrypy`, `ModuleNotFoundError: Crypto`) are Windows-dev-venv
  environment gaps unrelated to this plan (per `CLAUDE.md`: Windows is dev-only for syntax
  porting; `cherrypy`/`pycryptodome` are not installed in this worktree's Python 3.14 venv). Same
  8 collection errors present before and after this plan's changes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `tools/version_bump.py` docstring accidentally matched its own D-08 acceptance grep**
- **Found during:** Task 2, running the acceptance-criteria grep checks
- **Issue:** The initial module docstring explicitly named `configure.ac` and `version.py.in` to
  document the D-08 constraint, which caused `grep -c "configure.ac\|version.py.in"
  tools/version_bump.py` to return 1 instead of the required 0.
- **Fix:** Reworded the docstring line to say "any Autotools version file" instead of naming the
  files literally — same meaning, no literal string match.
- **Files modified:** `tools/version_bump.py`
- **Commit:** `e605cbd` (folded into Task 2's GREEN commit before it was created; no separate fix
  commit needed since this was caught before the initial commit).

No other deviations. Plan executed as written.

## Known Stubs

None.

## Threat Flags

None — this plan's threat register items (T-09-01, T-09-02, T-09-03) are exactly the file's
tested behavior (`_run()` list-argv, `parse_version` hard-fail, `last_tag()` no-tag tolerance);
no new untracked surface was introduced.

## Self-Check: PASSED

- `tools/version_bump.py` — FOUND
- `tests/test_version_bump.py` — FOUND
- `VERSION` — FOUND
- Commit `e4526fa` — FOUND
- Commit `e605cbd` — FOUND
- Commit `ff7cf47` — FOUND
