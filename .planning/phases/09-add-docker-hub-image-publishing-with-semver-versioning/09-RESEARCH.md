# Phase 9: Add Docker Hub image publishing with semver versioning - Research

**Researched:** 2026-09-23
**Domain:** GitHub Actions CI/CD, semver automation from Conventional Commits, Docker Buildx multi-arch publishing
**Confidence:** HIGH (workflow mechanics, Python stdlib patterns, existing repo conventions) / MEDIUM (exact current major-version pins for `docker/*` GitHub Actions, branch-protection unknowns)

## Summary

Phase 9 ports two PowerShell scripts (`increment-version.ps1`, `publish.ps1`) into one Python
tool (`tools/version_bump.py`, matching the `tools/pellmon_backup.py` precedent) driven from a
new GitHub Actions job that triggers on push to `master`. The job: (1) computes the semver bump
from Conventional Commits messages since the last `v*` tag using the exact three-rule priority
order from the reference doc, (2) commits `VERSION` + creates/pushes an annotated tag using the
built-in `GITHUB_TOKEN` (requires `contents: write` permission and a mandatory `[skip ci]`
commit-message marker to avoid a trigger loop), and (3) builds+pushes a multi-arch
(`linux/amd64`,`linux/arm64`) image to `peterscholer74/pellmon` on Docker Hub tagged `:latest`
and `:{version}`, using `docker/setup-qemu-action` + `docker/setup-buildx-action` +
`docker/login-action` + `docker/build-push-action`. A no-bump commit range is a clean no-op:
exit 0, nothing built, nothing pushed.

The single largest deviation from the reference algorithm that the planner must document
explicitly (not silently drop) is push semantics: the reference script pushes `:latest` and
`:{version}` as two independent `docker push` calls, failing fast on the first failure without
attempting the second. `docker/build-push-action` (and `docker buildx build --push` generally)
pushes all `tags:` in one atomic manifest-list push per platform combination — there is no
per-tag independent success/failure in the buildx-driven flow. This is an intentional, disclosed
deviation, not a bug.

**Primary recommendation:** Implement `tools/version_bump.py` as a pure `decide_bump(commit_messages: list[str]) -> str | None` function plus thin subprocess/file I/O wrappers (mirroring `pellmon_backup.py`'s `_run()` choke-point pattern), call it from a new GitHub Actions job (`publish`, in a separate workflow file `publish.yml` or as a second job in `ci.yml` gated with `needs: test` and `if: github.ref == 'refs/heads/master'`), and use the official `docker/*` composite actions for the multi-arch build+push rather than hand-rolling `docker buildx` shell commands in the workflow YAML.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Bump-decision logic (parse commit messages -> major/minor/patch/none) | CI / Tooling script (`tools/version_bump.py`) | — | Pure function, must be unit-testable without git/Docker (D-06); belongs in a standalone script, not inline YAML `run:` blocks |
| Git log/tag inspection | CI / Tooling script (subprocess wrapper) | GitHub Actions step (checkout with full history) | `git describe`/`git log` need real repo history; the workflow step's job is only to supply a full-depth checkout (`fetch-depth: 0`) |
| VERSION file read/write | CI / Tooling script | Repo root (source of truth artifact) | Matches reference doc: `VERSION` is a plain-text file, single source of truth, updated in-place |
| Git commit/tag/push of the bump | GitHub Actions workflow step | `tools/version_bump.py` (optional `--tag` helper) | D-04 deviates from the reference (which never commits) — this is new CI-only responsibility; needs `contents: write` and bot git identity config, best done as explicit `git` CLI steps in the workflow, not buried in the Python script, so failures are visible in the Actions log |
| Docker image build (multi-arch) | GitHub Actions workflow (docker/build-push-action) | — | Buildx + QEMU cross-compilation is an Actions-runner concern (emulation setup), not something a Python script should shell out to independently — reuse the maintained composite action |
| Docker Hub authentication | GitHub Actions workflow (docker/login-action) + repo secrets | — | Secrets (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`) are GitHub-native; login-action is the standard, audited way to feed them to the Docker CLI without echoing them to logs |
| Test gating before publish | GitHub Actions workflow (`needs: test` job dependency) | — | Must not publish an image built from code that fails the existing pytest/import-check gate (`ci.yml`'s `test` job) |

## User Constraints (from CONTEXT.md)

<user_constraints>
### Locked Decisions

- **D-01:** Docker Hub namespace/image is `peterscholer74/pellmon`. Published tags:
  `peterscholer74/pellmon:latest` and `peterscholer74/pellmon:{version}`. One Docker Hub
  repository, matching the existing `pellmon:latest` local convention in `docker-compose.yml`.
- **D-02:** Build multi-arch: `linux/amd64` and `linux/arm64`, via
  `docker buildx build --platform linux/amd64,linux/arm64 --push` (QEMU emulation for the arm64
  leg). Deviates from the reference script (native-arch only) because Raspberry Pi is a named
  production target in `CLAUDE.md`.
- **D-03:** Fully CI-automated on push to `master`. Reads Conventional Commit messages since the
  last `v*` tag (or full history if no tag exists yet), applies the exact priority order: any
  commit containing `BREAKING CHANGE` (substring, case-sensitive) anywhere in range -> major;
  else any commit line starting `^feat(\(.+\))?:` -> minor; else any commit line starting
  `^fix(\(.+\))?:` -> patch; else no-op (exit success, nothing built/pushed/committed).
- **D-04:** Unlike the reference script (never commits `VERSION` itself), this CI **does** commit
  the bump and push the tag: writes new `VERSION`, commits as
  `chore: bump version to {version} [skip ci]` (the `[skip ci]` marker is mandatory — without it
  the bump commit re-triggers the same workflow), creates annotated tag `v{version}`, pushes both
  commit and tag to `master`, THEN builds and pushes the image tagged with that version. Requires
  `contents: write` token permission (GitHub Actions -> repo Settings -> Actions -> General ->
  Workflow permissions -> "Read and write permissions" must be enabled once by the developer —
  cannot be set from code; plan must document this as a manual one-time setup step).
- **D-05 (Claude's discretion, stated so the planner doesn't re-derive it):** Port the
  bump-decision and publish logic as a **Python script** (`tools/version_bump.py`-style),
  consistent with `tools/pellmon_backup.py`/`tools/burner_sim.py` precedent — no PowerShell or
  Bash for this logic anywhere in the project. Must run standalone (local dry-run/manual
  override) and as a CI step.
- **D-06:** The bump-decision function (parse commit messages -> major/minor/patch/none) must be
  a pure, unit-testable function separable from git/Docker I/O shell-outs — real `pytest`
  coverage without a live git repo or Docker daemon, mirroring Phase 1's test-harness philosophy.
- **D-07:** Docker Hub push auth uses two new GitHub Actions repo secrets:
  `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (a Docker Hub access token, not the account
  password). Added once by the developer in repo Settings -> Secrets — plan must document the
  exact secret names but cannot create them itself.
- **D-08:** `configure.ac`'s `AC_INIT([PellMon], [0.7.0])` and any Autotools version references
  are legacy/superseded — this phase does NOT sync them with the new `VERSION` file. `VERSION`
  becomes the sole source of truth for the Docker image tag only. No changes to
  `configure.ac`/`version.py.in` are in scope.

### Claude's Discretion

- Exact GitHub Actions job/workflow structure (new workflow file vs. extending `ci.yml`) — keep
  the existing PR-gating `ci.yml` test job intact and either add a dependent job/workflow that
  only runs after tests pass on `master`, or reuse call.
- Whether the version-bump script also supports a `--dry-run`/local CLI mode for developers who
  want to preview the next version before pushing — reasonable convenience, not required.
- Exact commit message wording, as long as it includes the mandatory `[skip ci]` marker on the
  bump commit (D-04).

### Deferred Ideas (OUT OF SCOPE)

- A `restart-container.ps1`-equivalent auto-redeploy-on-publish step — explicitly out of scope.
  `docker compose pull && docker compose up -d` (per `DEPLOY-PI.md`) stays the operator action;
  auto-triggering a redeploy from CI would need reaching the Pi/host from GitHub Actions (webhook,
  SSH, watchtower, etc.), not decided here. Candidate for a future phase.
- GHCR or other secondary registry mirroring — Docker Hub only for this phase.
- Pinning/locking `requirements.txt` versions to a specific Docker base image digest — already
  covered by Phase 5's OPS-04 (and `requirements.txt` is already `==`-pinned, confirmed by
  reading the file during this research pass).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| D-01 | Docker Hub target `peterscholer74/pellmon`, single image, `:latest` + `:{version}` tags | See "Docker Hub / build-push-action config" below — `tags:` input takes a multiline list; both go in one `build-push-action` invocation |
| D-02 | Multi-arch `linux/amd64` + `linux/arm64` via buildx | See "Multi-arch build job" — `setup-qemu-action` + `setup-buildx-action` + `platforms:` input |
| D-03 | CI-automated bump-decision algorithm, exact priority order | See "Bump-decision algorithm (ported)" — regex/substring rules transcribed 1:1 from reference doc, Python equivalents given |
| D-04 | CI commits VERSION + pushes tag, `contents: write`, `[skip ci]` | See "Git write-back from a workflow" — permissions block, bot identity, `[skip ci]` semantics, one-time repo setting |
| D-05 | Python port, not Bash/PowerShell, `tools/version_bump.py`-style | See "Existing project conventions to mirror" — `tools/pellmon_backup.py` shape adopted directly |
| D-06 | Pure `decide_bump()` function, pytest-covered, no live git/Docker needed | See "Testable function design" and "Test conventions to mirror" (`tests/test_backup_script.py` pattern) |
| D-07 | `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` secrets, Docker Hub access token | See "Docker Hub access token" — manual setup step, scope guidance |
| D-08 | `VERSION` is sole source of truth; `configure.ac`/`version.py.in` untouched | Confirmed via `grep AC_INIT configure.ac` -> `AC_INIT([PellMon], [0.7.0])`; no code changes needed here, just a planner constraint to not touch it |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib only (`subprocess`, `re`, `argparse`, `pathlib`) | 3.13/3.14 (repo's pinned runtimes) | Bump-decision logic, VERSION read/write, git shell-outs | `[VERIFIED: codebase]` — no third-party dependency needed; matches `tools/pellmon_backup.py`'s stdlib-only approach (`argparse`, `configparser`, `subprocess`, `tarfile`, no pip deps beyond what's already in `requirements.txt`) |
| `actions/checkout@v4` | v4 | Checkout with full git history (`fetch-depth: 0`) | `[CITED: docs.github.com/actions]` — already used in `ci.yml`; must add `fetch-depth: 0` for the new job since `git describe --tags` and `git log {tag}..HEAD` need full history, not the default shallow clone |
| `docker/setup-qemu-action` | v3 `[ASSUMED — see note]` | Registers QEMU binfmt handlers so the amd64 runner can emulate arm64 during buildx build | `[CITED: github.com/docker/setup-qemu-action]` — official Docker org action, standard companion to buildx multi-arch builds |
| `docker/setup-buildx-action` | v3 `[ASSUMED — see note]` | Creates a buildx builder instance with the `docker-container` driver (required for multi-platform output and registry push) | `[CITED: github.com/docker/setup-buildx-action]` |
| `docker/login-action` | v3 `[ASSUMED — see note]` | Authenticates the Docker CLI against Docker Hub using `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets without echoing them | `[CITED: github.com/docker/login-action]` |
| `docker/build-push-action` | v6 `[ASSUMED — see note]` | Buildx build + multi-tag push in one step, replacing the reference script's `docker build`/`docker tag`/`docker push` sequence | `[CITED: github.com/docker/build-push-action]` |

**Version pin note:** WebSearch (not Context7 — no MCP docs tool returned results for these
GitHub Marketplace actions) surfaced `docker/build-push-action` major `v6`/`v7`,
`docker/setup-qemu-action` major `v3`/`v4`, `docker/setup-buildx-action` major `v3`/`v4` as
current across different sources dated at different points; sources disagreed on the exact
latest major (v6 vs v7 for build-push-action, v3 vs v4 for the setup actions). **Do not hardcode
an exact major version in the plan without the implementer checking each action's current
release tag at execution time** (`gh api repos/docker/build-push-action/releases/latest` or the
Marketplace page) — pin to a specific major (e.g. `docker/build-push-action@v6`) and let
Dependabot/manual review bump it later, rather than trusting this research's version number as
gospel. This entire row is `[ASSUMED]` pending that verification — see Assumptions Log.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` (already a dev dependency per `ci.yml`) | already pinned via CI's `pip install pytest pytest-mock pytest-socket` | Unit tests for `decide_bump()` | Standard — matches `tests/test_backup_script.py` |
| `git` CLI (pre-installed on `ubuntu-latest`) | runner default | `git describe --tags --abbrev=0`, `git log {range} --pretty=%B`, `git tag -a`, `git push` | No action needed; already present on GitHub-hosted runners |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `docker/build-push-action` composite action | Hand-rolled `docker buildx build --platform ... --push` shell step | Slightly more control over exact push-failure-per-tag semantics (closer to the reference script's independent-tag-check behavior), but loses the action's maintained caching (`cache-from`/`cache-to` GHA cache), summary annotations, and structured outputs (`digest`, `imageid`). Recommend the action; document the atomic-push deviation instead of hand-rolling to preserve an edge-case behavior nobody has asked for. |
| Python `semver` / `python-semantic-release` package | Hand-written `decide_bump()` | The reference doc's algorithm is intentionally simple (3 rules, first-match-wins) and D-06 requires it be a small pure function with direct pytest coverage — pulling in `python-semantic-release` (a much larger opinionated tool with its own changelog/release-note generation, GitHub Release creation, etc.) would replace, not port, the reference algorithm, and risks behavior drift from the documented priority order. Not recommended; would also need slopcheck/registry verification as a new external dependency, adding process overhead for no requirement this phase actually has. |
| Single workflow file (extend `ci.yml`) | Separate `publish.yml` workflow file | See "Workflow structure" section below — both are viable; recommendation given there. |

**Installation:**
```bash
# No new pip packages — tools/version_bump.py uses only Python stdlib.
# GitHub Actions dependencies are declared as `uses:` steps in the workflow YAML, not installed via pip.
```

**Version verification:** No new PyPI/npm packages are introduced by this phase (confirmed:
`tools/version_bump.py` needs only `subprocess`, `re`, `argparse`, `pathlib`, all stdlib). The
only "packages" involved are GitHub Marketplace Actions (`docker/*`), which are not
pip/npm-registry artifacts and are out of scope for `npm view`/`pip index versions`/slopcheck —
see Package Legitimacy Audit below for why that gate is N/A here, and the version-pin note above
for how the plan should still gate on verifying the current release tag.

## Package Legitimacy Audit

**Not applicable — no external Python/pip packages are installed by this phase.**
`tools/version_bump.py` uses only Python stdlib modules already available in every environment
this project targets (Windows dev venv, WSL dev venv, Debian bookworm-slim container). The
`docker/*` GitHub Actions referenced above are GitHub Marketplace Actions (git-ref-pinned
composite actions from the verified `docker` GitHub organization), not registry packages — the
slopcheck/`npm view`/`pip index versions` protocol does not apply to them. The planner should
still have the implementer verify each action's current major-version tag at execution time
(see the Version pin note above) since this research's specific version numbers came from
WebSearch with disagreeing sources, not an authoritative single source.

**Packages removed due to slopcheck [SLOP] verdict:** none (no packages installed)
**Packages flagged as suspicious [SUS]:** none (no packages installed)

## Architecture Patterns

### System Architecture Diagram

```text
Push to master (feat:/fix:/chore: commit, or a merged PR)
        |
        v
[ci.yml : test job]  (existing, unchanged)
  - apt-get system deps, venv --system-site-packages, pip install -r requirements.txt
  - test-imports.py
  - pytest tests/
        | (on success, same workflow file OR triggered dependent workflow)
        v
[publish job/workflow]  <-- NEW
  1. actions/checkout@v4  (fetch-depth: 0 -- full history needed for git describe/git log)
  2. Set up Python (stdlib only, no pip installs needed for the script itself)
  3. Run: python tools/version_bump.py decide
       -> reads VERSION, runs `git describe --tags --abbrev=0` (tolerates "no tags yet")
       -> runs `git log {range} --pretty=%B`
       -> applies decide_bump(commit_lines) -> "major"|"minor"|"patch"|None
       -> IF None: exit 0, print "no release needed", END WORKFLOW (no-op)
       -> IF a bump: writes new VERSION, prints new version to stdout/GITHUB_OUTPUT
  4. IF a bump happened:
       a. git config user.name/user.email (bot identity)
       b. git add VERSION && git commit -m "chore: bump version to {version} [skip ci]"
       c. git tag -a "v{version}" -m "Release {version}"
       d. git push origin master && git push origin "v{version}"
  5. docker/setup-qemu-action@vN
  6. docker/setup-buildx-action@vN
  7. docker/login-action@vN  (DOCKERHUB_USERNAME / DOCKERHUB_TOKEN secrets)
  8. docker/build-push-action@vN
       context: .
       platforms: linux/amd64,linux/arm64
       push: true
       tags: |
         peterscholer74/pellmon:latest
         peterscholer74/pellmon:{version}
        |
        v
Docker Hub: peterscholer74/pellmon:latest, peterscholer74/pellmon:{version}
        |
        v
(Manual, operator-triggered, out of scope for this phase)
docker compose pull && docker compose up -d   [per DEPLOY-PI.md]
```

### Recommended Project Structure
```
tools/
├── version_bump.py       # NEW: decide_bump() pure function + CLI (decide/apply/--dry-run)
├── pellmon_backup.py      # existing precedent for shape/conventions
tests/
├── test_version_bump.py   # NEW: pytest coverage for decide_bump(), mirrors test_backup_script.py
├── test_ci_docker_config.py  # existing: extend or add sibling assertions for the new workflow
VERSION                    # NEW at repo root: plain text, "MAJOR.MINOR.PATCH", no v prefix
.github/workflows/
├── ci.yml                 # existing test-gate workflow, unchanged (or lightly extended)
├── publish.yml             # NEW (recommended) OR a new job inside ci.yml — see discussion below
```

### Pattern 1: Pure decision function separated from I/O (D-06)
**What:** `decide_bump(commit_messages: list[str]) -> str | None` takes plain strings in,
returns `"major"|"minor"|"patch"|None` out — no subprocess calls, no file I/O inside it.
**When to use:** Always, for the bump-decision core — this is what makes it testable per D-06
without a live git repo.
**Example:**
```python
# Source: ported from D:\Antigravity\Kombikode tool\docs\versioning-and-publish-reference.md
# (reference doc's exact regex/substring semantics — do not invent new patterns)
import re

_FEAT_RE = re.compile(r"^feat(\(.+\))?:")
_FIX_RE = re.compile(r"^fix(\(.+\))?:")


def decide_bump(commit_messages):
    """Return 'major' | 'minor' | 'patch' | None from a list of commit message lines.

    Mirrors increment-version.ps1's algorithm exactly:
    - ANY line in ANY commit containing the substring 'BREAKING CHANGE' -> major
      (bare substring, case-sensitive, not anchored to line start)
    - else ANY line starting with 'feat:' or 'feat(scope):' -> minor
    - else ANY line starting with 'fix:' or 'fix(scope):' -> patch
    - else None (no-op; caller must not touch VERSION or build anything)

    Priority is existence-based, not chronological: if the range contains both a
    fix: commit and a BREAKING CHANGE mention (anywhere, in any order), the result
    is 'major'.
    """
    if any('BREAKING CHANGE' in line for line in commit_messages):
        return 'major'
    if any(_FEAT_RE.match(line) for line in commit_messages):
        return 'minor'
    if any(_FIX_RE.match(line) for line in commit_messages):
        return 'patch'
    return None


def apply_bump(version_tuple, bump_type):
    major, minor, patch = version_tuple
    if bump_type == 'major':
        return (major + 1, 0, 0)
    if bump_type == 'minor':
        return (major, minor + 1, 0)
    if bump_type == 'patch':
        return (major, minor, patch + 1)
    raise ValueError('unknown bump_type: %r' % bump_type)
```

**Critical porting detail — line-by-line, not whole-message matching:** The reference doc is
explicit that PowerShell's `-match` applied to an array of lines (the output of
`git log --pretty=%B`, which is itself the full multi-line body of every commit in range) checks
"does ANY element (line) match", not "does the whole message match as one string". In Python,
`git log {range} --pretty=%B` returns one big string; **you must split it into lines before
calling `decide_bump()`** (e.g. `output.splitlines()`), not pass the whole capture as a single
string, or a multi-line commit body's `feat:` line buried after a summary line won't be detected
by `^feat(\(.+\))?:` (Python's `re.match` without `re.MULTILINE` only anchors `^` to the start of
the whole string, not the start of each line). Either split first, or compile with `re.MULTILINE`
and use `re.search` — splitting first (matching the PowerShell array semantics 1:1) is the safer
port since it also makes the bare-substring `BREAKING CHANGE` check behave identically either
way. `[VERIFIED: reference doc, cross-checked against Python re semantics]`

### Pattern 2: Subprocess I/O wrapper choke point (mirrors `pellmon_backup.py`)
**What:** All external `git`/`docker` calls go through one function, never `shell=True`, always
a list argv — matches this repo's established `_run()` pattern.
**When to use:** For every git/docker shell-out in `version_bump.py`.
**Example:**
```python
# Source: pattern from D:\Antigravity\PellMon-master\tools\pellmon_backup.py:74-80
import subprocess


def _run(argv, check=True, capture=False):
    """Single choke point for external commands: list argv, never a shell."""
    kw = {}
    if capture:
        kw['stdout'] = subprocess.PIPE
        kw['stderr'] = subprocess.PIPE
        kw['text'] = True
    return subprocess.run(argv, check=check, **kw)


def last_tag():
    """Return the most recent v* tag, or None if the repo has no tags yet."""
    result = _run(['git', 'describe', '--tags', '--abbrev=0'], check=False, capture=True)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def commits_since(tag):
    rng = '%s..HEAD' % tag if tag else 'HEAD'
    result = _run(['git', 'log', rng, '--pretty=%B'], capture=True)
    return result.stdout.splitlines()
```

### Pattern 3: Git write-back from a workflow (D-04)
**What:** A workflow step commits `VERSION` and pushes a tag using the default `GITHUB_TOKEN`.
**When to use:** Only after `decide_bump()` returns a non-None result.
**Example:**
```yaml
# Source: standard GitHub Actions pattern for bot-authored commits
# https://docs.github.com/en/actions/security-guides/automatic-token-authentication
permissions:
  contents: write   # required at job or workflow level; default GITHUB_TOKEN is read-only otherwise

steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0        # full history: git describe/git log need it, default shallow clone breaks this
      # token: ${{ secrets.GITHUB_TOKEN }} is implicit; persist-credentials defaults to true,
      # which is what lets the later `git push` step reuse the checkout's auth

  - name: Decide version bump
    id: bump
    run: |
      python tools/version_bump.py decide >> "$GITHUB_OUTPUT"
      # script should print e.g. "bump=minor" and "version=1.4.0" as GITHUB_OUTPUT-format lines,
      # or "bump=none" if decide_bump() returned None

  - name: Commit and tag version bump
    if: steps.bump.outputs.bump != 'none'
    run: |
      git config user.name "github-actions[bot]"
      git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
      git add VERSION
      git commit -m "chore: bump version to ${{ steps.bump.outputs.version }} [skip ci]"
      git tag -a "v${{ steps.bump.outputs.version }}" -m "Release ${{ steps.bump.outputs.version }}"
      git push origin HEAD:master
      git push origin "v${{ steps.bump.outputs.version }}"
```

**`[skip ci]` semantics — verify before relying on it:** GitHub's built-in skip-ci behavior
triggers when the phrase `[skip ci]` (or `[ci skip]`, `[no ci]`, `[skip actions]`,
`[actions skip]`) appears in **the commit message of the push/PR HEAD commit that would trigger
the workflow**. `[CITED: github.blog/changelog/2021-02-08-github-actions-skip-pull-request-and-push-workflows-with-skip-ci]`
This should correctly prevent the bot's own `chore: bump version ... [skip ci]` commit from
re-triggering `ci.yml`'s `push: branches: [master]` trigger. **However**, if the publish job
lives in a *separate* workflow file from `ci.yml` and that file's trigger is `workflow_run`
(triggered by `ci.yml`'s completion) rather than a raw `push:` trigger, `[skip ci]` does not
apply in the same way — `workflow_run` triggers are keyed to the *triggering* workflow's run,
and the bot's push would need its own guard (e.g. checking the actor is `github-actions[bot]` and
short-circuiting, or simply relying on the fact that a `chore:` commit contains no
`feat:`/`fix:`/`BREAKING CHANGE` and so `decide_bump()` naturally no-ops on the *next* run even if
one is triggered — a second layer of protection worth keeping regardless). **Recommend the
planner treat this as an explicit verification task during implementation** (push a test commit,
confirm no second workflow run fires) rather than assuming `[skip ci]` alone is sufficient if a
`workflow_run`-triggered structure is chosen.

### Pattern 4: Multi-arch build+push (D-02)
**What:** QEMU + Buildx + login + build-push-action chain, replacing `publish.ps1`'s
`docker build`/`docker tag`/`docker push` sequence.
**When to use:** After the version bump (or immediately, using the just-written `VERSION` file,
if no bump — though per D-03 a no-bump means the whole job should skip this too, since "no
release needed" means nothing should be pushed).
**Example:**
```yaml
# Source: standard pattern documented at https://docs.docker.com/build/ci/github-actions/multi-platform/
- name: Set up QEMU
  uses: docker/setup-qemu-action@v3   # verify current major tag at implementation time

- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3  # verify current major tag at implementation time

- name: Log in to Docker Hub
  uses: docker/login-action@v3
  with:
    username: ${{ secrets.DOCKERHUB_USERNAME }}
    password: ${{ secrets.DOCKERHUB_TOKEN }}

- name: Build and push
  uses: docker/build-push-action@v6   # verify current major tag at implementation time
  with:
    context: .
    platforms: linux/amd64,linux/arm64
    push: true
    tags: |
      peterscholer74/pellmon:latest
      peterscholer74/pellmon:${{ steps.bump.outputs.version }}
```

**Disclosed deviation — atomic multi-tag push vs. reference's independent per-tag push:** The
reference doc's `publish.ps1` calls `docker push` twice, once per tag, and treats a `:latest`
push failure as fatal *before* even attempting the `:{version}` push (fail-fast, independently
checked). `docker/build-push-action` (and `docker buildx build --push` generally) builds once and
pushes **all** tags supplied to `tags:` as part of a single buildx operation — there is no
"push `:latest`, stop on failure, then push `:{version}`" two-step in the buildx model; it is
effectively all-or-nothing for the whole multi-platform manifest list. `[CITED: docs.docker.com/build/ci/github-actions/multi-platform]`
This is an acceptable, disclosed deviation (D-02 already accepts moving to buildx for multi-arch
support, which structurally forces this atomicity), but the plan should state it explicitly
rather than imply per-tag failure isolation still exists.

### Anti-Patterns to Avoid
- **Passing the raw `git log --pretty=%B` string (not split into lines) into `decide_bump()`:**
  Silently breaks multi-line commit body detection for `^feat:`/`^fix:` line-start anchoring —
  see Pattern 1 above.
- **Hand-writing `docker buildx build` as a raw `run:` shell step instead of using the
  maintained actions:** Loses GHA layer caching support, structured step outputs, and makes QEMU
  binfmt setup a manual (and easy to get wrong) `docker run --privileged --rm tonistiigi/binfmt
  --install all` step instead of the one-line `setup-qemu-action`.
- **Forgetting `permissions: contents: write` at the job/workflow level:** The default
  `GITHUB_TOKEN` for a `push` trigger has narrower default permissions in newer GitHub Actions
  configurations (particularly if the repo/org has `Restrict` set as the default workflow
  permission) — without this the `git push` step fails with a 403, not a helpful error about
  missing scope.
- **Forgetting `fetch-depth: 0` on the checkout step:** `actions/checkout@v4`'s default is a
  shallow clone (`fetch-depth: 1`), which makes `git describe --tags --abbrev=0` and
  `git log {tag}..HEAD` unreliable/wrong (missing history, tags may not resolve at all).
- **Running the publish job on `pull_request` events:** Only `push: branches: [master]` should
  trigger the bump+publish job — PRs must never push tags or Docker images (this is implicit in
  D-03 "on push to master" but worth an explicit workflow-trigger guard, e.g.
  `if: github.event_name == 'push' && github.ref == 'refs/heads/master'`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-arch Docker builds (QEMU binfmt registration, buildx builder lifecycle) | Manual `docker run --privileged tonistiigi/binfmt` + `docker buildx create --use` shell steps | `docker/setup-qemu-action` + `docker/setup-buildx-action` | Maintained by Docker Inc., handles builder cleanup/caching, avoids re-solving binfmt edge cases per-runner-image-update |
| Conventional-Commits parsing at scale (changelog generation, GitHub Release notes) | A bigger regex/parsing layer beyond the 3 documented rules | Nothing — the reference doc's 3-rule algorithm is intentionally minimal and is what D-03 locks in; do not add `docs:`/`chore:`/scope-aware extra logic that isn't in the reference doc | Scope creep risk: this phase is explicitly "port the algorithm exactly", not "build a better one" |
| Docker Hub credential handling in the shell | Manually `echo $TOKEN \| docker login --password-stdin` in a `run:` step | `docker/login-action` | Avoids accidental secret echoing in logs, handles registry-URL defaulting correctly |

**Key insight:** Every piece of this phase already has a maintained, first-party GitHub Action
or stdlib pattern — the only genuinely new code is the ~20-line `decide_bump()` function and its
thin I/O wrapper, which is exactly what D-05/D-06 scope it down to.

## Common Pitfalls

### Pitfall 1: `[skip ci]` commit re-triggering the workflow anyway
**What goes wrong:** The bot's own `chore: bump version ... [skip ci]` push still kicks off a
new `ci.yml`/`publish.yml` run, potentially causing an infinite loop of empty bump attempts (each
one no-ops on `decide_bump()` since a `chore:` commit matches none of the three rules — so the
loop is not infinite in *effect*, but it does waste CI minutes and clutters the Actions log every
release).
**Why it happens:** `[skip ci]` only works when placed correctly on the triggering commit and
the workflow uses a directly-triggered `push:` event; `workflow_run`-chained or `paths-ignore`
misconfigurations can bypass the built-in skip logic.
**How to avoid:** Use a plain `push: branches: [master]` trigger (not `workflow_run`) for the
simplest, most reliable `[skip ci]` behavior; verify with a real test push during implementation.
**Warning signs:** Two workflow runs appear back-to-back in the Actions tab for what should be
one release; the second run's `decide_bump()` step logs "no release needed" (harmless but a
signal the skip marker isn't being honored).

### Pitfall 2: Branch protection blocking the bot's own push (open risk — flagged, not resolved)
**What goes wrong:** If `master` has branch protection rules requiring PR review or status
checks before any push (including from `GITHUB_TOKEN`), the `git push origin HEAD:master` step
in Pattern 3 fails outright.
**Why it happens:** GitHub's default `GITHUB_TOKEN`, even with `contents: write`, is still
subject to branch protection rules unless the repo's protection settings include an exception for
`github-actions[bot]` or "Allow specified actors to bypass required pull requests."
**How to avoid:** This research **could not verify from the repo alone** whether `master` has
branch protection configured (that's a GitHub repo Settings value, not something in the checked-
out tree) — **flagged as an explicit open risk the plan must handle**, e.g. by documenting a
manual check ("Settings -> Branches -> confirm no protection rule blocks
`github-actions[bot]`, or add a bypass") as a one-time setup step alongside the `contents: write`
permission toggle already required by D-04. If protection is later added and blocks this, the
fallback is a fine-grained PAT stored as a secret and used in place of `GITHUB_TOKEN` for the
checkout/push steps.
**Warning signs:** `git push` step fails with `! [remote rejected] master -> master (protected
branch hook declined)` or similar 403/422 errors.

### Pitfall 3: `VERSION` file format drift breaking the parser
**What goes wrong:** A stray trailing newline, extra whitespace, or a `v` prefix accidentally
committed to `VERSION` causes the "exactly 3 dot-separated integers" parse to fail.
**Why it happens:** The reference doc is explicit: `VERSION`'s content, after `.Trim()`, must
split on `.` into exactly 3 integer parts — anything else (missing file, `1.2`, `1.2.3.4`,
non-numeric, or a `v1.2.3` prefix) is a hard error (exit 1).
**How to avoid:** Port this validation exactly in `version_bump.py` (strip/trim before parsing,
assert exactly 3 int-parseable parts, hard-fail with a clear message otherwise) — do not silently
coerce or guess.
**Warning signs:** `ValueError`/parse exception on a workflow run that previously worked; check
`VERSION`'s exact bytes (`cat -A VERSION` equivalent) for stray whitespace or line endings.

### Pitfall 4: First-run "no tags yet" case mishandled
**What goes wrong:** `git describe --tags --abbrev=0` exits non-zero (with output to stderr) when
the repo has no tags at all — a naive `check=True` subprocess call raises `CalledProcessError`
instead of falling through to "use full history".
**Why it happens:** This repo currently has **no `v*` tags** (confirmed: this phase introduces
tagging for the first time) — the very first workflow run after this phase ships *is* the
first-run case, not a hypothetical edge case to defer.
**How to avoid:** Explicitly catch the non-zero exit (`check=False`, inspect `returncode`) and
treat it as "no tag" -> use `git log --pretty=%B` (whole history) as the reference doc specifies,
not an error.
**Warning signs:** The very first publish-workflow run fails outright instead of computing a bump
from full history.

### Pitfall 5: Docker Hub repository must already exist
**What goes wrong:** `docker push` (or the equivalent buildx push) fails with
`insufficient_scope: authorization failed` or `repository does not exist` if
`peterscholer74/pellmon` hasn't been created on Docker Hub yet, even with valid credentials.
**Why it happens:** Docker Hub does not auto-create repositories on first push for access-token
auth in all account tiers/settings; this varies but is a very common first-publish failure mode
per the reference doc's own note ("Push failures are the overwhelmingly common failure mode in
practice").
**How to avoid:** Document as a manual pre-flight step: create the `peterscholer74/pellmon`
repository on Docker Hub (public or private per preference) before the first CI run, alongside
the access-token creation step.
**Warning signs:** First publish run's push step fails with an auth/scope error despite correct
secrets.

## Code Examples

### CLI shape for `tools/version_bump.py` (dry-run support, Claude's discretion item)
```python
# Source: pattern adapted from tools/pellmon_backup.py's argparse subcommand structure
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='Semver bump decision + VERSION file management')
    sub = parser.add_subparsers(dest='command', required=True)

    decide = sub.add_parser('decide', help='Compute and apply the next version bump')
    decide.add_argument('--dry-run', action='store_true',
                         help='Print the computed bump/version without writing VERSION')
    decide.add_argument('--type', choices=['major', 'minor', 'patch'],
                         help='Force a specific bump, skipping commit analysis (mirrors -Type)')

    args = parser.parse_args(argv)
    # ... dispatch to decide_bump()/apply_bump(), read/write VERSION, print GITHUB_OUTPUT-format
    #     lines ("bump=minor\nversion=1.4.0\n") when running under CI (os.environ.get('GITHUB_OUTPUT'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

### Test conventions to mirror (`tests/test_version_bump.py`)
```python
# Source: pattern from D:\Antigravity\PellMon-master\tests\test_backup_script.py
# (importlib.util module loading, no package __init__.py needed for a tools/ script)
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "tools" / "version_bump.py"
_spec = importlib.util.spec_from_file_location("version_bump", _PATH)
version_bump = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(version_bump)


def test_breaking_change_wins_priority_over_feat_and_fix():
    lines = ['fix: something', 'feat: new thing', 'oops BREAKING CHANGE here']
    assert version_bump.decide_bump(lines) == 'major'


def test_no_match_returns_none():
    assert version_bump.decide_bump(['chore: tidy up', 'docs: update readme']) is None


def test_feat_must_be_at_line_start():
    assert version_bump.decide_bump(['this is a feat: not really']) is None


def test_feat_with_scope_matches():
    assert version_bump.decide_bump(['feat(ui): new button']) == 'minor'
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Single-arch `docker build`/`docker push` (reference `publish.ps1`) | `docker buildx build --platform ... --push` via `docker/build-push-action` | Buildx has been GA/default in Docker CLI since ~2021-2022; this is not a recent change, just not what the Windows-only reference script used | Enables Raspberry Pi arm64 support (D-02) which the reference script structurally could not do |
| Manually scripted git tag + `git push --tags` after a human runs `increment-version.ps1` | GitHub Actions job runs the whole decide -> commit -> tag -> build -> push chain automatically on every master push | This phase (D-03/D-04) | Zero-touch releases; also introduces new failure modes (branch protection, `[skip ci]` correctness) that a human-run script never had to handle |

**Deprecated/outdated:** Nothing in this research is itself deprecated — the reference doc's
underlying algorithm is small and stable; only the *execution environment* (PowerShell on
Windows -> Python in Linux CI) changes.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Current major version tags for `docker/setup-qemu-action`, `docker/setup-buildx-action`, `docker/login-action`, `docker/build-push-action` are v3/v3/v3/v6 (or v4/v4/v3/v7 per a conflicting source) | Standard Stack, Pattern 4 | Low-medium: using a stale major tag still generally works (these actions are backward compatible within a major version) but the plan should not hardcode an unverified exact tag as if confirmed; implementer should check the Marketplace page or `gh api .../releases/latest` before writing the final workflow YAML |
| A2 | GitHub's default `GITHUB_TOKEN` with `contents: write` can push directly to `master` without hitting branch protection | Pitfall 2 | Medium: if branch protection exists and blocks this, D-04's entire commit/tag/push design fails at runtime; plan must include a verification step and a PAT fallback note |
| A3 | `docker/build-push-action`'s multi-tag push is atomic (all tags in one push operation, no independent per-tag failure) rather than looping `docker push` per tag internally | Pattern 4 deviation note | Low: this is documented Docker/buildx behavior, but if the action's internals differ, the "disclosed deviation" framing in the plan could be imprecise — worth a quick confirmation read of the action's README during implementation |
| A4 | `[skip ci]` on a plain `push:`-triggered workflow reliably prevents the bot's own bump commit from re-triggering the same workflow | Pitfall 1 | Low-medium: this is documented GitHub behavior (CITED), but the plan should still include an explicit test-push verification step rather than assuming it silently |

## Open Questions

1. **Should the publish job live in a new `publish.yml` or as a second job inside `ci.yml`?**
   - What we know: Both are structurally viable. A separate job inside `ci.yml` gated by
     `needs: test` and `if: github.ref == 'refs/heads/master' && github.event_name == 'push'`
     avoids duplicating the checkout/dependency-install steps' *intent* (though the publish job
     needs a different, much lighter checkout — no system deps/venv needed) and keeps the whole
     CI/CD pipeline visible in one workflow run. A separate `publish.yml` triggered on
     `workflow_run` (keyed to `ci.yml` completing successfully on `master`) more cleanly separates
     "test gate" from "release automation" concerns and makes it trivial to re-run just the
     publish half without re-running tests, but requires careful `workflow_run` trigger
     conditions (branch, conclusion) to avoid firing on PR-only `ci.yml` runs, and complicates
     `[skip ci]` semantics as noted in Pattern 3.
   - What's unclear: This repo's existing convention only has one workflow file so far; no
     precedent either way. CONTEXT.md explicitly leaves this to Claude's discretion.
   - Recommendation: **Same-file second job in `ci.yml`** (`needs: test`, branch/event `if:`
     guard) — simpler `[skip ci]` semantics (plain `push:` trigger, not `workflow_run`), one file
     to maintain, and the existing `test_ci_docker_config.py` test-of-the-workflow-file pattern
     can be extended in place rather than needing a second config-assertion test file.

2. **Exact current major-version tags for the four `docker/*` actions.**
   - What we know: All four are official, actively maintained Docker-org actions; WebSearch
     results disagreed on the precise current major (v3 vs v4 for the setup actions, v6 vs v7 for
     build-push-action) — normal for a moving target and not resolvable further without
     Context7/MCP access to these specific Marketplace pages (unavailable in this session).
   - What's unclear: The single correct "latest" tag as of implementation date.
   - Recommendation: Implementer pins to a specific major (e.g. `@v3`/`@v6`) at plan-execution
     time by checking `https://github.com/docker/<action>/releases` directly, rather than trusting
     this research's specific number.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `git` CLI | Bump-decision, commit/tag/push | ✓ (GitHub-hosted `ubuntu-latest` runner ships git) | runner default | — |
| Docker Buildx | Multi-arch build | ✓ via `docker/setup-buildx-action` on `ubuntu-latest` (Docker Engine + buildx plugin pre-installed) | runner default | — |
| QEMU (arm64 emulation) | Cross-arch build leg | ✓ via `docker/setup-qemu-action` | action-managed | — |
| Docker Hub account + `peterscholer74/pellmon` repository | Push target | Unknown from repo alone — must be confirmed/created manually (D-07, Pitfall 5) | — | None — blocking until created; document as a one-time manual step |
| `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` GitHub Actions secrets | Docker Hub auth | Not present yet (new, per D-07) | — | None — blocking until added; document as a one-time manual step |
| Repo Settings -> Actions -> Workflow permissions = "Read and write" | `git push` from `GITHUB_TOKEN` | Unknown from repo alone (org/account-level UI setting) | — | None — blocking until enabled; document as a one-time manual step (D-04 already calls this out) |
| Branch protection on `master` allowing `github-actions[bot]` pushes | `git push origin HEAD:master` | Unknown from repo alone (GitHub Settings -> Branches, not visible in the checked-out tree) | — | Fallback: fine-grained PAT secret in place of `GITHUB_TOKEN` if protection blocks the bot (Pitfall 2) |

**Missing dependencies with no fallback:**
- Docker Hub repository `peterscholer74/pellmon` must exist before first run.
- `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets must be added before first run.
- Repo's Actions workflow permissions must be set to "Read and write" before first run.

**Missing dependencies with fallback:**
- Branch protection blocking the bot push has a PAT-based fallback if it turns out to be an issue.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already declared in `ci.yml`: `pip install pytest pytest-mock pytest-socket`) |
| Config file | none detected (no `pytest.ini`/`pyproject.toml` `[tool.pytest]` section — pytest runs via `pytest tests/ -v` directly, matching `ci.yml`) |
| Quick run command | `pytest tests/test_version_bump.py -v` |
| Full suite command | `pytest tests/ -v` (existing `ci.yml` command, unchanged) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|--------------|
| D-03 | `decide_bump()` priority order (BREAKING CHANGE > feat > fix > none) | unit | `pytest tests/test_version_bump.py::test_breaking_change_wins_priority_over_feat_and_fix -x` | ❌ Wave 0 |
| D-03 | `feat`/`fix` must anchor at line start, not mid-sentence | unit | `pytest tests/test_version_bump.py::test_feat_must_be_at_line_start -x` | ❌ Wave 0 |
| D-06 | `decide_bump()` importable and callable with no git/Docker present (pure function) | unit | `pytest tests/test_version_bump.py -v` (no `needs_rrdtool`/`docker`-style skip markers should be required for these tests) | ❌ Wave 0 |
| D-04 | New workflow YAML contains `contents: write`, `[skip ci]` marker text, `fetch-depth: 0` | config-assertion | `pytest tests/test_ci_docker_config.py::test_publish_workflow_permissions_and_skip_ci -x` (new test, same pattern as `test_github_actions_workflow`) | ❌ Wave 0 |
| D-01/D-02 | Workflow YAML references `peterscholer74/pellmon`, `linux/amd64,linux/arm64`, both `:latest` and version tags | config-assertion | `pytest tests/test_ci_docker_config.py::test_publish_workflow_multiarch_and_tags -x` (new test) | ❌ Wave 0 |
| D-08 | `configure.ac` unchanged (no accidental sync attempt) | config-assertion (optional, low value) | manual review; not worth a dedicated test | n/a |

### Sampling Rate
- **Per task commit:** `pytest tests/test_version_bump.py -v` (fast, no external deps)
- **Per wave merge:** `pytest tests/ -v` (full suite, matches existing `ci.yml` gate)
- **Phase gate:** Full suite green before `/gsd:verify-work`; additionally, a real end-to-end
  workflow run (push a `feat:`/`fix:` test commit to a throwaway branch or, cautiously, to
  `master` once secrets/permissions are set up) should be verified manually at least once since
  the git-write-back and Docker Hub push steps cannot be meaningfully unit-tested — they are
  config-assertion-tested (YAML contains the right settings) but not behavior-tested in pytest.

### Wave 0 Gaps
- [ ] `tests/test_version_bump.py` — covers D-03, D-06 (new file)
- [ ] `tools/version_bump.py` itself does not exist yet — this phase creates it (not a gap, the
      deliverable)
- [ ] `VERSION` file does not exist yet at repo root — this phase creates it, initial value should
      probably be `0.1.0` or derived from `configure.ac`'s `0.7.0` as a one-time seed value (open
      question for discuss-phase/planning: reference doc doesn't specify a bootstrap value,
      D-08 says don't sync with `configure.ac` going forward, but an initial seed value is still
      needed — recommend planner treat "what should `VERSION` start at" as a task-level decision,
      defaulting to `0.1.0` unless the user prefers to seed from `configure.ac`'s `0.7.0`)
- [ ] New assertions in `tests/test_ci_docker_config.py` (or a new sibling file) for the publish
      workflow's permissions/skip-ci/multi-arch/tag content — covers D-01, D-02, D-04

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — no user-facing auth surface touched by this phase |
| V3 Session Management | no | N/A |
| V4 Access Control | yes (CI/CD supply-chain sense) | `permissions: contents: write` scoped to the minimum needed, at job level not workflow-default level if the workflow has other jobs; secrets (`DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`) restricted to the publish job's `env`/`with`, not exported workflow-wide |
| V5 Input Validation | yes (narrow) | `VERSION` file parsing must hard-fail (not silently coerce) on malformed content — see Pitfall 3; commit message content is read-only input, not executed, so injection risk is minimal but still route it only through `subprocess` list-argv calls (never `shell=True`), matching `pellmon_backup.py`'s existing `_run()` convention |
| V6 Cryptography | no | N/A — Docker Hub access token is an opaque bearer credential handled entirely by `docker/login-action`; no cryptographic code is written in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret leakage via workflow logs (`DOCKERHUB_TOKEN` echoed in a `run:` step) | Information Disclosure | Use `docker/login-action` (handles credentials without echoing) rather than a raw `docker login -p $TOKEN` shell line; GitHub Actions auto-masks registered secret values in logs but this is a defense-in-depth backstop, not a substitute for using the action |
| Overly broad `GITHUB_TOKEN` permissions (workflow-default `write-all`) enabling an unrelated job to push/modify the repo if compromised | Elevation of Privilege | Scope `permissions: contents: write` at the specific job level (the publish job only), leaving other jobs (e.g. `test`) at their existing default/read-only permissions |
| Supply-chain risk from unpinned third-party Actions (`uses: docker/build-push-action@main` or a floating tag) | Tampering | Pin to a specific major-version tag (e.g. `@v6`), and per general GitHub Actions hardening guidance consider pinning to a commit SHA for the highest assurance — not strictly required here since `docker/*` are first-party Docker Inc. actions, but worth noting as a discretionary hardening step |
| Malicious or accidental force-push tag collision (`v1.2.3` already exists, re-run overwrites release semantics) | Tampering | `git tag -a` without `--force` fails loudly if the tag already exists rather than silently overwriting — preserve this reference-doc behavior; do not add `--force` to the ported tag-creation step |

## Sources

### Primary (HIGH confidence)
- `D:\Antigravity\Kombikode tool\docs\versioning-and-publish-reference.md` — full algorithm,
  regex patterns, exit codes, and non-obvious rules for `increment-version.ps1`/`publish.ps1`,
  read in full for this research
- `D:\Antigravity\PellMon-master\.planning\phases\09-add-docker-hub-image-publishing-with-semver-versioning\09-CONTEXT.md` — locked decisions D-01..D-08
- `D:\Antigravity\PellMon-master\tools\pellmon_backup.py` — existing project convention for a `tools/` CLI script (argparse, `_run()` choke point, stdlib-only)
- `D:\Antigravity\PellMon-master\tests\test_backup_script.py` — existing test convention (`importlib.util` module loading for a `tools/` script)
- `D:\Antigravity\PellMon-master\tests\test_ci_docker_config.py` — existing convention for asserting on `.github/workflows/ci.yml` content via plain-text/regex checks (no yaml-parsing library used)
- `D:\Antigravity\PellMon-master\.github\workflows\ci.yml` — existing CI structure, trigger branches, runner
- `D:\Antigravity\PellMon-master\requirements.txt` — confirmed already `==`-pinned (OPS-04 precedent), no new pip deps needed for this phase
- `D:\Antigravity\PellMon-master\configure.ac` — confirmed `AC_INIT([PellMon], [0.7.0])`, per D-08 left untouched

### Secondary (MEDIUM confidence)
- GitHub changelog: skip-ci commit-message markers — https://github.blog/changelog/2021-02-08-github-actions-skip-pull-request-and-push-workflows-with-skip-ci/
- Docker Docs: multi-platform image build with GitHub Actions — https://docs.docker.com/build/ci/github-actions/multi-platform/
- `docker/build-push-action`, `docker/setup-qemu-action`, `docker/setup-buildx-action`, `docker/login-action` GitHub repos (official Docker org) — existence and general usage pattern confirmed via WebSearch, exact current major version NOT confirmed to a single authoritative number (see Assumptions Log A1)

### Tertiary (LOW confidence)
- Various blog/community posts surfaced by WebSearch on `GITHUB_TOKEN` push/branch-protection interplay (e.g. github.com/orgs/community/discussions threads) — used only to corroborate general `workflow_run`/`[skip ci]` mechanics, not treated as authoritative for this repo's specific (unknown) branch-protection configuration

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — stdlib-only Python part is HIGH confidence (verified against existing repo conventions); exact `docker/*` action version pins are LOW-MEDIUM (WebSearch-only, disagreeing sources, flagged in Assumptions Log)
- Architecture: HIGH — workflow structure, permissions model, and Python pure-function/I-O split are all standard, well-documented GitHub Actions and Python patterns cross-checked against this repo's own existing conventions
- Pitfalls: HIGH for algorithm-porting pitfalls (directly derived from the reference doc's own "non-obvious rules" section); MEDIUM for the two genuinely unknown-to-this-session risks (branch protection state, exact action version) which are explicitly flagged as open risks rather than asserted as fact

**Research date:** 2026-09-23
**Valid until:** 2026-10-23 (30 days — GitHub Actions ecosystem and Docker Marketplace action versions move quickly; re-verify action version pins if planning is delayed past this window)
</content>
