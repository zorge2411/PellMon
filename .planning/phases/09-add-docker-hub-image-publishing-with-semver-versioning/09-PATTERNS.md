# Phase 9: Add Docker Hub image publishing with semver versioning - Pattern Map

**Mapped:** 2026-09-22
**Files analyzed:** 7 (new: 4, modified: 3)
**Analogs found:** 6 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `VERSION` (new, repo root) | config | file-I/O (plain text, read by scripts + build) | `.env.example` (plain-text config-value file, root-level, documented by comments) | role-match |
| `scripts/bump-version.sh` (new) | utility (CLI script) | transform (git log → semver decision → file rewrite) | `setup-wsl.sh` (bash, `set -e`, step-numbered echo output, `git`/system calls) | role-match |
| `.github/workflows/publish.yml` (new) | config (CI workflow) | event-driven (triggered on tag push) | `.github/workflows/ci.yml` (same platform: GitHub Actions, `ubuntu-latest`, `actions/checkout@v4`) | exact |
| `configure.ac` (modified — `AC_INIT` version) | config (Autotools) | request-response (build-time substitution) | itself (existing `AC_INIT([PellMon], [0.7.0])` line) — no separate analog needed | exact (self) |
| `src/Pellmonsrv/version.py.in` (modified only if reconciling — otherwise unchanged) | config (Autotools `.in` template) | file-I/O (build-time substitution → `version.py`) | itself (existing `@VERSION@` placeholder pattern used throughout `directories.py.in`) | exact (self) |
| `DOCKER.md` or `DEPLOY-PI.md` (modified — document publish/versioning) | test/docs (documentation) | request-response (human-readable doc) | `DOCKER.md` (existing Quick Start style, fenced bash blocks, directory tree diagrams) | exact |
| `tests/test_version_bump.py` (new) | test | transform (unit test of bump script via subprocess/import) | `tests/test_backup_script.py` (tests a root-adjacent script via `importlib.util.spec_from_file_location`, `tmp_path` fixtures, no live hardware) | role-match |
| `tests/test_ci_docker_config.py` (modified — add publish.yml assertions) OR new `tests/test_publish_workflow.py` | test | transform (static string/regex assertions on YAML text) | `tests/test_ci_docker_config.py` (`test_github_actions_workflow` — exact same technique: read file text, assert substrings/regex, no YAML parser) | exact |

## Pattern Assignments

### `VERSION` (new, repo root)

**Analog:** `.env.example` (root-level plain-text config file with explanatory comments) — no code excerpt needed, this is a data file not code. Content should be a single line:
```
1.1.0
```
No `v` prefix, no trailing content, matching `docs/versioning-and-publish-reference.md`'s exact format (`MAJOR.MINOR.PATCH`, three dot-separated integers). Justify the reconciled number in a commit message / doc note: `configure.ac` currently says `0.7.0`, latest git tag is `v1.0.0` — since the app has shipped Docker deployments (Phase 6/7/8 work, `v1.0.0` tag already exists and is the higher, more recently-used number), start `VERSION` at `1.1.0` (bump from `1.0.0` for this phase's own feature work) rather than reverting to `0.7.0`. Do not silently pick `0.7.0`.

---

### `scripts/bump-version.sh` (new)

**Analog:** `D:\Antigravity\PellMon-master\setup-wsl.sh`

**Shebang + strict-mode pattern** (lines 1-5):
```bash
#!/bin/bash
# WSL 2 Development Environment Setup for PellMon Python 3 Migration
# Run this script in WSL to set up the complete development environment

set -e  # Exit on error
```
Apply the same `#!/bin/bash` + `set -e` + descriptive header-comment convention to `bump-version.sh`.

**Step-numbered echo output pattern** (lines 7-15, 44-49):
```bash
echo "=========================================="
echo "PellMon WSL 2 Development Environment Setup"
echo "=========================================="
echo ""

# Update package lists
echo "Step 1: Updating package lists..."
sudo apt-get update
```
Mirror this for bump-version.sh's steps ("Step 1: Reading VERSION", "Step 2: Scanning commits since last tag", etc.) — matches this repo's existing bash-script verbosity convention rather than a silent script.

**Error/precondition-check pattern** (lines 40-46):
```bash
if [ ! -d "$PELLMON_DIR" ]; then
    echo ""
    echo "ERROR: PellMon directory not found at $PELLMON_DIR"
    echo "Please adjust the PELLMON_DIR variable in this script."
    exit 1
fi
```
Use the same `if [ ... ]; then echo "ERROR: ..." >&2; exit 1; fi` shape for VERSION-file validation (missing file, malformed `MAJOR.MINOR.PATCH`), per RESEARCH.md's ported precondition-check snippet:
```bash
if [[ ! -f VERSION ]]; then
  echo "VERSION file missing" >&2
  exit 1
fi
version=$(tr -d '[:space:]' < VERSION)
IFS='.' read -r major minor patch <<< "$version"
if [[ -z "$major" || -z "$minor" || -z "$patch" ]] || ! [[ "$major$minor$patch" =~ ^[0-9]+$ ]]; then
  echo "VERSION must be MAJOR.MINOR.PATCH (three integers)" >&2
  exit 1
fi
```
(This exact snippet is from RESEARCH.md `## Code Examples`, already a bash port of the reference doc — reuse verbatim as the precondition block.)

**Core bump-decision algorithm** — reuse verbatim from RESEARCH.md `Pattern 2`:
```bash
last_tag=$(git describe --tags --abbrev=0 2>/dev/null || true)
range=${last_tag:+"$last_tag..HEAD"}
commits=$(git log ${range:-} --pretty=%B)

if echo "$commits" | grep -q "BREAKING CHANGE"; then
  bump=major
elif echo "$commits" | grep -qE '^feat(\(.+\))?:'; then
  bump=minor
elif echo "$commits" | grep -qE '^fix(\(.+\))?:'; then
  bump=patch
else
  echo "No release-triggering commits since ${last_tag:-repo start}."
  exit 0
fi
```
Caution flagged in RESEARCH.md: verify `grep -qE '^feat...'` against multi-line commit bodies (each line of `--pretty=%B` output, not just the subject) before trusting in CI — test with a synthetic multi-paragraph commit message.

**No `.py2bak` counterpart** — this is a brand-new file with no Python 2 predecessor; per CLAUDE.md migration-context guidance, do not create one.

---

### `.github/workflows/publish.yml` (new)

**Analog:** `D:\Antigravity\PellMon-master\.github\workflows\ci.yml`

**Trigger + job/runner scaffold pattern** (lines 1-20 of `ci.yml`):
```yaml
name: CI

on:
  push:
    branches:
      - master
      - python3-migration
  pull_request:
    branches:
      - master
      - python3-migration

jobs:
  test:
    name: Run Python Tests and Import Verification
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
```
Adapt the trigger block to tag-push-only (per D-03/RESEARCH.md Pattern 1) and reuse `actions/checkout@v4` (already the pinned version in this repo — match it, don't introduce a different pin):
```yaml
name: publish
on:
  push:
    tags:
      - 'v*'
jobs:
  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Login to Docker Hub
        uses: docker/login-action@v4
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - name: Set up QEMU
        uses: docker/setup-qemu-action@v4
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v4
      - name: Build and push
        uses: docker/build-push-action@v7
        with:
          platforms: linux/amd64,linux/arm/v7
          push: true
          tags: |
            peterscholer74/pellmon:latest
            peterscholer74/pellmon:${{ github.ref_name }}
```
(Image name locked by CONTEXT.md D-01: `peterscholer74/pellmon`.)

**Step-naming convention** (each `ci.yml` step has a `name:` field, e.g. `- name: Install Linux system packages`) — keep every `publish.yml` step named for parity with the existing workflow's readability in the Actions UI.

---

### `configure.ac` (modified)

**Current line to change** (line 1):
```
AC_INIT([PellMon], [0.7.0])
```
Per D-02, wire this to read the `VERSION` file rather than hardcoding a literal. Since `AC_INIT`'s version argument must be resolvable at `autoreconf`/`autoconf` time (not shell-runtime), the standard Autotools idiom is `m4_esyscmd` or `m4_esyscmd_s` reading the file at macro-expansion time:
```
AC_INIT([PellMon], m4_esyscmd_s([cat VERSION]))
```
This is a new pattern for this codebase (no existing `m4_esyscmd` usage found) — flag it clearly in the plan as a new Autotools technique, not a copy of an existing in-repo pattern. If the planner instead chooses option (b) from RESEARCH.md Pitfall 3 (keep `configure.ac` and `VERSION` independent), this file does not need to change at all — document that choice explicitly in `DOCKER.md`/`DEPLOY-PI.md` per D-02's requirement to flag the reconciliation decision, not silently skip it.

---

### `src/Pellmonsrv/version.py.in` (unchanged content, context only)

**Existing pattern** (both lines):
```python
# -*- coding: utf-8 -*-
__version__ = '@VERSION@'
```
No change needed to this file itself — `@VERSION@` is already substituted from `configure.ac`'s `AC_INIT` by the existing Autotools `AC_CONFIG_FILES` machinery (see `configure.ac` lines 35-60, though `version.py.in` is not currently listed there — verify it's actually wired into `AC_CONFIG_FILES` before assuming substitution happens; if it's missing from that list, that's a pre-existing gap unrelated to this phase but worth flagging to the planner).

---

### `DOCKER.md` (modified — document publish workflow + VERSION)

**Analog:** `D:\Antigravity\PellMon-master\DOCKER.md`

**Section + fenced-code-block style** (lines 1-30):
```markdown
# Docker Deployment Guide for PellMon

## Quick Start

\`\`\`bash
# 1. Copy and customize configuration
cp config/pellmon.conf.example config/pellmon.conf
cp .env.example .env
...
\`\`\`

## Configuration

### Required Files

\`\`\`
PellMon-master/
├── config/
│   ├── pellmon.conf      # Main config (required)
│   └── conf.d/           # Plugin configs (optional)
├── .env                   # Environment variables
├── docker-compose.yml
└── Dockerfile
\`\`\`
```
Add a new `## Publishing a Release` (or similar) section to `DOCKER.md` (or `DEPLOY-PI.md`, whichever the planner decides is the canonical deploy doc — `DEPLOY-PI.md` is referenced by `test_ci_docker_config.py::test_deploy_guide_documents_persistent_data` as the doc that gets content-checked by tests) using the same numbered-fenced-bash-block style: `bump-version.sh` usage, `git push --tags`, and a note that Docker Hub publish is CI-only (no local push credentials needed) per D-05.

---

### `tests/test_version_bump.py` (new)

**Analog:** `D:\Antigravity\PellMon-master\tests\test_backup_script.py`

**Script-under-test import pattern** (lines 17-20):
```python
_PATH = Path(__file__).resolve().parents[1] / "tools" / "pellmon_backup.py"
_spec = importlib.util.spec_from_file_location("pellmon_backup", _PATH)
pellmon_backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pellmon_backup)
```
`bump-version.sh` is bash, not Python, so this exact `importlib` technique does not apply directly — instead follow the *testing shape* (not the import mechanism): use `subprocess.run(["bash", "scripts/bump-version.sh"], cwd=tmp_path, ...)` against a throwaway git repo built in `tmp_path`, asserting on `VERSION` file contents and exit code afterward. This matches `test_backup_script.py`'s `tmp_path`-based isolation strategy (`_write()` helper, no real filesystem/hardware side effects) even though the script itself isn't Python.

**`tmp_path` fixture + helper-write pattern** (lines 27-31):
```python
def _write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path
```
Reuse this exact helper shape to seed a fake `VERSION` file and a fake git repo (`git init`, `git commit --allow-empty -m "feat: ..."`) inside `tmp_path` for each bump-classification test case (`feat:` → minor, `fix:` → patch, `BREAKING CHANGE` → major, none → no-op/exit 0, malformed `VERSION` → exit 1).

**Skip-if-tool-missing pattern** (line 22-24):
```python
needs_rrdtool = pytest.mark.skipif(shutil.which('rrdtool') is None,
                                   reason='rrdtool not installed')
```
Apply the same idiom for a `needs_bash = pytest.mark.skipif(shutil.which('bash') is None, reason='bash not installed')` guard if running under a bash-less environment is a real concern (Windows dev box without Git Bash) — matches this repo's existing environment-availability guard convention.

---

### `tests/test_ci_docker_config.py` (extend) or new test file for `publish.yml`

**Analog:** `D:\Antigravity\PellMon-master\tests\test_ci_docker_config.py::test_github_actions_workflow`

**Text-assertion-on-YAML pattern** (lines 18-37):
```python
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
    assert "ubuntu-latest" in content, "CI runner must be ubuntu-latest"
```
Apply the identical technique (no YAML parser dependency, plain substring/regex assertions + tab-character guard) to a new `test_publish_workflow()` covering `publish.yml`: assert `tags:` trigger (not `branches:`), pinned action versions (`docker/build-push-action@v7`, `docker/setup-qemu-action@v4`, `docker/setup-buildx-action@v4`, `docker/login-action@v4` — and explicitly assert `@main`/`@master` are absent, per RESEARCH.md's anti-pattern warning), `linux/amd64,linux/arm/v7` platform string, and that `secrets.DOCKERHUB_TOKEN`/`secrets.DOCKERHUB_USERNAME` are referenced (never a literal credential).

## Shared Patterns

### Bash script header/strict-mode/step-echo convention
**Source:** `setup-wsl.sh` (also present in `install-2to3.sh`, `reinstall.sh`)
**Apply to:** `scripts/bump-version.sh` (and any local `publish-image.sh` wrapper if the planner adds one per CONTEXT.md's Claude's-Discretion note)
```bash
#!/bin/bash
set -e
echo "=========================================="
echo "<Script Title>"
echo "=========================================="
echo ""
echo "Step 1: <description>..."
```

### GitHub Actions workflow scaffold (checkout + named steps + `ubuntu-latest`)
**Source:** `.github/workflows/ci.yml`
**Apply to:** `.github/workflows/publish.yml`
```yaml
runs-on: ubuntu-latest
steps:
  - name: Checkout repository
    uses: actions/checkout@v4
```

### Static text/regex assertions on config files (no parser dependency)
**Source:** `tests/test_ci_docker_config.py`
**Apply to:** `tests/test_version_bump.py`, any new/extended test covering `publish.yml`, `VERSION`, or `configure.ac` changes
```python
content = (REPO_ROOT / "<file>").read_text(encoding="utf-8")
assert "<required-substring>" in content, "<failure message>"
```

### Root-level plain-text/INI config file with explanatory header comment
**Source:** `.env.example`
**Apply to:** `VERSION` (though `VERSION` itself should stay comment-free/single-line per the reference doc's exact format — the *documentation* of what it means belongs in `DOCKER.md`/`DEPLOY-PI.md`, not inline in the file, since `bump-version.sh`'s parser expects exactly `MAJOR.MINOR.PATCH` with nothing else)

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `configure.ac`'s `m4_esyscmd_s([cat VERSION])` substitution (if D-02 option (a) is chosen) | config | file-I/O | No existing `m4_esyscmd`/dynamic-version Autotools usage anywhere in this repo's `configure.ac`/`Makefile.am` files to copy from — this would be new Autotools territory; RESEARCH.md's own Pitfall 3 flags this as the single most-open decision. If the planner picks option (b) (keep `configure.ac` and `VERSION` independent), this row is moot. |

## Metadata

**Analog search scope:** repo root (`*.sh`, `configure.ac`, `.env.example`, `DOCKER.md`), `.github/workflows/`, `src/Pellmonsrv/version.py.in`, `tests/` (`test_ci_docker_config.py`, `test_backup_script.py`), `docs/versioning-and-publish-reference.md`, `Dockerfile`, `docker-compose.yml`
**Files scanned:** ~15 (targeted reads, no full-repo scan needed — file list was small and explicit from CONTEXT.md/RESEARCH.md)
**Pattern extraction date:** 2026-09-22
