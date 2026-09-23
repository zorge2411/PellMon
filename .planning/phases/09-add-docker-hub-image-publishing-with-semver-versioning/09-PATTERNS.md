# Phase 9: Add Docker Hub image publishing with semver versioning - Pattern Map

**Mapped:** 2026-09-23
**Files analyzed:** 5
**Analogs found:** 5 / 5

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `VERSION` | config | file-I/O | *(none — new plain-text artifact, no code analog)* | n/a |
| `tools/version_bump.py` | utility (CLI script) | transform + event-driven (git-log driven decision) + file-I/O | `tools/pellmon_backup.py` | exact (role + shape) |
| `tests/test_version_bump.py` | test | unit (pure-function) | `tests/test_backup_script.py` | exact (test-harness shape) |
| `.github/workflows/ci.yml` (extended with a `publish` job, or new sibling `publish.yml`) | config (CI workflow) | event-driven (push-triggered) | `.github/workflows/ci.yml` (itself — existing `test` job) | exact (same file/family) |
| `tests/test_ci_docker_config.py` (extended with new assertions) | test | config-assertion | `tests/test_ci_docker_config.py` (itself — `test_github_actions_workflow`) | exact (same file, established idiom) |

## Pattern Assignments

### `tools/version_bump.py` (utility/CLI script, transform + file-I/O)

**Analog:** `tools/pellmon_backup.py`

**Header/license block** (lines 1-18) — every new file under this repo's Python packages/tools carries this GPL header verbatim per `CLAUDE.md`'s Comments convention:
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
```
(Note: `tools/pellmon_backup.py` uses this header with a tool-specific docstring below it — mirror that: keep the GPL block, replace the descriptive paragraph with `version_bump.py`'s own usage docstring, e.g. documenting `decide`/`--dry-run`/`--type` subcommands the way `pellmon_backup.py` documents `backup`/`restore`.)

**Imports pattern** (lines 43-58) — stdlib only, comma-free one-per-line where multi-purpose, no third-party deps:
```python
import argparse
import configparser
import datetime
import json
import logging
import os
import pathlib
import platform
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
```
For `version_bump.py` this trims down to what's actually needed: `argparse`, `re`, `subprocess`, `sys`, `os`/`pathlib`, and (per repo convention) `logging` with `logger = getLogger('pellMon')` if it logs at all — though note `pellmon_backup.py` uses its own `logging.getLogger('pellmon_backup')`, not the shared `'pellMon'` daemon logger, since it's a standalone `tools/` script outside the `Pellmonsrv`/`Pellmonweb` packages. Follow that same standalone-script convention (own named logger, not `'pellMon'`).

**Subprocess choke-point pattern** (lines 74-83) — single function all external commands go through, list argv, never `shell=True`:
```python
def _run(argv, stdout=None, check=True, capture=False):
    """Single choke point for external commands: list argv, never a shell."""
    logger.debug('run: %r', argv)
    kw = {}
    if capture:
        kw['stdout'] = subprocess.PIPE
        kw['stderr'] = subprocess.PIPE
    elif stdout is not None:
        kw['stdout'] = stdout
    return subprocess.run(argv, check=check, **kw)
```
Apply this exact shape for `version_bump.py`'s `git describe`/`git log`/`git tag`/`git push` calls — RESEARCH.md's `Pattern 2` example (`last_tag()`, `commits_since()`) already follows this idiom; treat that as the concrete target implementation, built on top of a `_run()` identical in spirit to the one above.

**Pure-function / I-O separation pattern** — `pellmon_backup.py` doesn't have a single pure decision function (its domain is inherently I/O), but its `build_manifest(cfg, rrd_version)` (lines 130-141) is the closest local precedent for a **pure, dict-in/dict-out function with zero I/O inside it**, callable and testable with plain data:
```python
def build_manifest(cfg, rrd_version):
    return {
        'format': 1,
        'created': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'rrd_filename': os.path.basename(cfg['database']),
        ...
    }
```
`decide_bump(commit_messages: list[str]) -> str | None` (per RESEARCH.md Pattern 1) should follow this same no-I/O, pure-transform shape — it's the direct analog for D-06's testability requirement.

**Validation / hard-fail-on-malformed-input pattern** (lines 116-124) — config-file-derived values are validated and raise `ValueError` with a descriptive message rather than silently coercing:
```python
    database = parser.get('conf', 'database', fallback=None)
    if not database:
        raise ValueError("no 'database' value found in %s or %s" %
                         (conf_file, resolved or '<no conf.d dir found>'))
    ...
    for key, value in (('database', database), ('settings_db', settings_db)):
        if value.startswith('-'):
            raise ValueError("%s value %r must not start with '-'" % (key, value))
```
Apply the same pattern to `VERSION` file parsing (Pitfall 3 in RESEARCH.md): strip/trim, split on `.`, assert exactly 3 int-parseable parts, `raise ValueError('...')` with a clear message on any deviation — do not silently coerce a malformed `VERSION`.

**argparse subcommand CLI shape** (lines 439-459):
```python
def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Back up / restore PellMon persistent data')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('backup', 'restore'):
        s = sub.add_parser(name)
        s.add_argument('--config', default='./config/pellmon.conf')
        ...
    return p.parse_args(argv)
```
`version_bump.py`'s `main()`/`parse_args()` should mirror this `add_subparsers(dest='command', required=True)` shape (RESEARCH.md's CLI shape example — `decide` subcommand with `--dry-run`/`--type` — already matches this idiom; treat `pellmon_backup.py`'s `parse_args` as the concrete precedent to copy structurally).

**Top-level error handling / exit-code pattern** (lines 462-489):
```python
def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        stream=sys.stderr, format='%(asctime)s %(message)s')
    try:
        ...
    except (ValueError, OSError, EOFError, sqlite3.Error,
            subprocess.CalledProcessError, tarfile.TarError) as e:
        sys.stderr.write('error: %s\n' % e)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
```
Copy this exact `main(argv=None)` / catch known-exception-types / `sys.stderr.write('error: %s\n' % e)` / `return 1` / `sys.exit(main())` idiom for `version_bump.py` — it is this codebase's established "CLI tool reports errors cleanly, no raw traceback" convention. Adjust the caught-exception tuple to what `version_bump.py` can actually raise (`ValueError` for VERSION-parse/malformed-bump-type, `subprocess.CalledProcessError` for failed git calls).

---

### `tests/test_version_bump.py` (test, unit/pure-function)

**Analog:** `tests/test_backup_script.py`

**Module-loading pattern for a `tools/` script with no package `__init__.py`** (lines 1-20):
```python
"""Tests for tools/pellmon_backup.py (D-10): backup/restore of RRD + settings DB + config."""

import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sqlite3
import sys
import tarfile
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "tools" / "pellmon_backup.py"
_spec = importlib.util.spec_from_file_location("pellmon_backup", _PATH)
pellmon_backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pellmon_backup)
```
For `test_version_bump.py`, use exactly this pattern, pointed at `tools/version_bump.py`:
```python
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "tools" / "version_bump.py"
_spec = importlib.util.spec_from_file_location("version_bump", _PATH)
version_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(version_bump)
```
(This is also given directly in RESEARCH.md's "Test conventions to mirror" section — treat that as the concrete boilerplate to use, sourced from this same analog.)

**Conditional-skip marker pattern** (lines 22-24) — external-tool availability gated with a `pytest.mark.skipif`:
```python
needs_rrdtool = pytest.mark.skipif(shutil.which('rrdtool') is None,
                                   reason='rrdtool not installed')
posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX modes')
```
`version_bump.py`'s tests are pure-function (D-06: no git/Docker needed for `decide_bump()`), so this pattern applies only if any test in the file needs a real `git` binary (e.g. an integration-style test of `last_tag()`/`commits_since()`); the core `decide_bump()` tests need no skip markers at all — keep them unconditional, per D-06's explicit "no live git repo... in the test run" requirement.

**Direct call + assert pattern for a pure function** — closest local precedent (still I/O-adjacent but structurally similar, dict-in/values-out) at lines 42-48:
```python
def test_conf_d_overrides_pellmon_conf(tmp_path):
    conf = _write(tmp_path / 'pellmon.conf',
                  '[conf]\ndatabase = /x/pellmon.rrd\nconfig_dir = %s\n' % (tmp_path / 'conf.d'))
    _write(tmp_path / 'conf.d' / 'database.conf', '[conf]\ndatabase = /y/rrd.db\n')
    cfg = pellmon_backup.read_effective_config(str(conf))
    assert cfg['database'] == '/y/rrd.db'
    assert cfg['settings_db'] == '/y/pellmon_settings.db'
```
For `decide_bump()`, RESEARCH.md already gives the concrete equivalent (no `tmp_path` fixture needed since it's pure list-in/value-out):
```python
def test_breaking_change_wins_priority_over_feat_and_fix():
    lines = ['fix: something', 'feat: new thing', 'oops BREAKING CHANGE here']
    assert version_bump.decide_bump(lines) == 'major'


def test_no_match_returns_none():
    assert version_bump.decide_bump(['chore: tidy up', 'docs: update readme']) is None


def test_feat_must_be_at_line_start():
    assert version_bump.decide_bump(['this is a feat: not really']) is None
```
Use these as-is; add the mirror-image `fix:`-only and `BREAKING CHANGE`-substring-anywhere-in-a-line cases for full priority-order coverage per D-03.

**Error-path / exit-code assertion pattern** (lines 89-99):
```python
def test_missing_database_is_an_error(tmp_path, capsys):
    conf = _write(tmp_path / 'pellmon.conf',
                  '[conf]\nconfig_dir = %s\n' % (tmp_path / 'conf.d'))
    (tmp_path / 'conf.d').mkdir()
    out = tmp_path / 'out.tgz'
    rc = pellmon_backup.main(['backup', '--local', '--config', str(conf), '--out', str(out)])
    err = capsys.readouterr().err
    assert rc != 0
    assert str(conf) in err and 'database' in err
```
Apply the same `rc = module.main([...]); err = capsys.readouterr().err; assert rc != 0; assert '<message fragment>' in err` idiom for `version_bump.py`'s malformed-`VERSION` and unknown-`--type` error paths.

---

### `.github/workflows/ci.yml` (extended) or new `publish.yml` (config, event-driven)

**Analog:** `.github/workflows/ci.yml`'s existing `test` job (this same file — no separate CI-workflow analog exists elsewhere in the repo)

**Trigger block pattern** (lines 3-11):
```yaml
on:
  push:
    branches:
      - master
      - python3-migration
  pull_request:
    branches:
      - master
      - python3-migration
```
A new `publish` job must trigger only on `push` to `master` (not `python3-migration`, not `pull_request` — see RESEARCH.md Anti-Patterns), so if added as a second job in the same file, gate it with an explicit `if:`:
```yaml
  publish:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/master'
    runs-on: ubuntu-latest
    permissions:
      contents: write
```

**Checkout step pattern** (lines 19-20):
```yaml
      - name: Checkout repository
        uses: actions/checkout@v4
```
The publish job needs the same `uses: actions/checkout@v4` action, but with `fetch-depth: 0` added (full history required for `git describe`/`git log`) — this is a deviation from the `test` job's shallow default, document it explicitly as an intentional difference, not an oversight.

**Step-naming / named-steps-with-`run:` convention** (lines 22-58) — every step has a descriptive `name:`, multi-line shell blocks use YAML `|` block scalars:
```yaml
      - name: Install Linux system packages
        run: |
          sudo apt-get update
          sudo apt-get install -y --no-install-recommends \
            python3-dbus python3-gi python3-gi-cairo gir1.2-glib-2.0 \
            librrd-dev rrdtool python3-rrdtool python3-venv
```
Mirror this `name:` + `run: |` shape for the publish job's steps (`Decide version bump`, `Commit and tag version bump`, etc. — see RESEARCH.md Pattern 3/4 for the exact step bodies to use).

**Explicit note — do NOT reuse the `test` job's venv/system-site-packages mechanics** (lines 32-46): the publish job does not need `dbus`/`gi`/`rrdtool` system bindings (RESEARCH.md's "Established Patterns" section is explicit about this) — use a plain runner-default `python3` (or `actions/setup-python`, which `ci.yml`'s `test` job deliberately avoids for import-binding reasons that don't apply here) for the stdlib-only `version_bump.py` script.

---

### `tests/test_ci_docker_config.py` (extended, config-assertion)

**Analog:** this same file's existing `test_github_actions_workflow()` (lines 18-68)

**Plain-text/regex assertion pattern against workflow YAML** (lines 18-46, representative excerpt):
```python
REPO_ROOT = Path(__file__).resolve().parent.parent


def test_github_actions_workflow():
    """Verify .github/workflows/ci.yml configuration integrity."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.is_file(), f"CI workflow file not found at {ci_path}"

    content = ci_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Verify basic YAML syntax (no tabs, proper key-value structure)
    for idx, line in enumerate(lines, 1):
        assert "\t" not in line, f"Tab character found in line {idx} of ci.yml"

    # Verify triggers and target branches
    assert "push:" in content, "Workflow should trigger on push"
    ...
```
This is a plain-text-content-assertion style (no YAML parser used anywhere in this test file, confirmed) — new tests for the publish job/workflow must follow the exact same idiom: `content = path.read_text(...)`, then `assert "<literal snippet>" in content, "<message>"`. RESEARCH.md's own Phase Requirements → Test Map table already names the two functions to add:

```python
def test_publish_workflow_permissions_and_skip_ci():
    """D-04: publish job has contents: write, fetch-depth: 0, and the [skip ci] marker."""
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "contents: write" in content
    assert "fetch-depth: 0" in content
    assert "[skip ci]" in content


def test_publish_workflow_multiarch_and_tags():
    """D-01/D-02: publish job targets peterscholer74/pellmon, multi-arch, :latest + version tag."""
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "peterscholer74/pellmon" in content
    assert "linux/amd64,linux/arm64" in content
    assert "peterscholer74/pellmon:latest" in content
```
(Adjust the file path read if the publish job ends up in a separate `publish.yml` instead of `ci.yml` — same `read_text`/`assert "<literal>" in content` idiom either way.)

**Helper-function reuse** (lines 111-115) — `_service_block(content, name)` is specific to `docker-compose.yml` service extraction and does not apply to workflow-YAML assertions (which use flat `in content` checks, not per-block regex slicing) — no need to build an equivalent helper for the publish-workflow tests; follow the simpler flat-`assert` style of `test_github_actions_workflow()` instead.

---

## Shared Patterns

### GPL header block on every new source file
**Source:** `tools/pellmon_backup.py:1-18` (and consistently across `src/Pellmonsrv/`)
**Apply to:** `tools/version_bump.py` only (not `VERSION`, not test files — `tests/test_backup_script.py` has no GPL header, so `tests/test_version_bump.py` should match that convention: no header, just a one-line module docstring).

### Subprocess choke-point (`_run()`), list argv, never shell=True
**Source:** `tools/pellmon_backup.py:74-83`
**Apply to:** `tools/version_bump.py` — every `git`/`docker` shell-out.

### `main(argv=None)` / catch known exceptions / `sys.stderr.write('error: %s\n' % e)` / `return 1` / `sys.exit(main())`
**Source:** `tools/pellmon_backup.py:462-489`
**Apply to:** `tools/version_bump.py`'s CLI entry point.

### `importlib.util.spec_from_file_location` module loading for `tools/` scripts under test
**Source:** `tests/test_backup_script.py:17-20`
**Apply to:** `tests/test_version_bump.py`.

### Plain-text/regex content assertions against workflow YAML (no YAML parser)
**Source:** `tests/test_ci_docker_config.py:18-68`
**Apply to:** New assertions covering the publish job in `tests/test_ci_docker_config.py`.

### `%`-style string formatting, not f-strings, inside non-test project code
**Source:** repo-wide convention (`CLAUDE.md` Code Style; confirmed throughout `tools/pellmon_backup.py`, e.g. `'%s value %r must not start with %r'`)
**Apply to:** `tools/version_bump.py` internals. Note: `tests/test_ci_docker_config.py` itself uses f-strings in assertion messages (`f"CI workflow file not found at {ci_path}"`) — CLAUDE.md explicitly carves out an exception for f-strings in "new top-level tooling scripts"; test files in this repo already use f-strings freely, so f-strings are fine in `tests/test_version_bump.py` and new assertions in `tests/test_ci_docker_config.py`, but `tools/version_bump.py` itself should prefer `%`-formatting for logger/error messages to match `pellmon_backup.py`.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `VERSION` | config | file-I/O | No existing plain-text single-value config file in the repo to model against (closest concept, `configure.ac`'s `AC_INIT([PellMon], [0.7.0])`, is Autotools syntax, explicitly not to be touched per D-08) — content format ("MAJOR.MINOR.PATCH\n", no `v` prefix, seeded literally at `1.0.0` per D-09) comes directly from CONTEXT.md/RESEARCH.md, not from a codebase analog. |

## Metadata

**Analog search scope:** `tools/`, `tests/`, `.github/workflows/` (entire repo root for `VERSION`-equivalent config files — none found)
**Files scanned:** `tools/pellmon_backup.py`, `tools/burner_sim.py` (checked, not read in full — `pellmon_backup.py` is the stronger analog per RESEARCH.md), `tests/test_backup_script.py`, `tests/test_ci_docker_config.py`, `.github/workflows/ci.yml`
**Pattern extraction date:** 2026-09-23
