# Phase 9: Add Docker Hub image publishing with semver versioning - Research

**Researched:** 2026-09-22
**Domain:** CI/CD release engineering — semver bump automation + multi-arch Docker image build/publish
**Confidence:** MEDIUM (mechanics are HIGH-confidence/verified against official docs; several project-specific decisions are unresolved and tagged ASSUMED — no CONTEXT.md/discuss-phase ran for this phase)

## Summary

No `CONTEXT.md` exists for this phase — `/gsd:discuss-phase` was skipped (`--auto`). The roadmap description and `docs/versioning-and-publish-reference.md` are the only requirement sources. The reference doc is explicit that it documents a **different, Windows/PowerShell-only project's** scripts (`increment-version.ps1`, `publish.ps1`), single-arch, hardcoded to Docker Hub with no registry-host prefix. PellMon's actual constraints diverge from that reference in three material ways this research confirms directly from the repo:

1. **No multi-arch build exists today.** `Dockerfile` and `docker-compose.yml` do a single native `docker build`/`docker compose build` with no `buildx`, no `--platform`, no QEMU setup anywhere in the repo (`.github/workflows/ci.yml`, `Dockerfile`, `docker-compose.yml`, `DOCKER.md`, `README.md` all checked — zero hits for `buildx`/`qemu`/`platform:`). Any arm/v7 (Raspberry Pi) image is new work for this phase, not a port of something existing. `[VERIFIED: repo grep]`
2. **Two version sources already exist and disagree.** `configure.ac`'s `AC_INIT([PellMon], [0.7.0])` (Autotools version, substituted into `version.py.in` as `@VERSION@`) says `0.7.0`; the most recent git tag is `v1.0.0`. Neither is a plain-text `VERSION` file — the reference doc's core assumption (`VERSION` file as single source of truth) does not exist yet in this repo. `[VERIFIED: repo read]`
3. **CI already runs on Linux (`ubuntu-latest`)** via `.github/workflows/ci.yml`, giving a natural place to add a publish job — but the reference scripts are PowerShell, which is not the runner's native shell (though `pwsh` is preinstalled on `ubuntu-latest` runners) and doesn't match `Dockerfile`'s Debian-only, Linux-only production posture. Bash or Python better matches this repo's existing shell-script conventions (`setup-wsl.sh`, `autogen.sh`, `install-2to3.sh` are all bash) and CI runner default shell.

**Primary recommendation:** Port the reference doc's *algorithm* (Conventional-Commits-driven semver bump; build→tag→push) rather than its *implementation* (PowerShell, single-arch, VERSION-file-as-source-of-truth if it conflicts with `configure.ac`). Reconcile the version source (either promote a root `VERSION` file to be authoritative and generate `configure.ac`'s `AC_INIT` / `version.py.in`'s `@VERSION@` from it, or accept two independently-bumped version strings — this is a decision the planner/user must make, not something research can resolve). Implement the actual build/push step as a GitHub Actions job using the official `docker/build-push-action` + `docker/setup-qemu-action` + `docker/setup-buildx-action` chain for `linux/amd64,linux/arm/v7`, triggered on version tags, with Docker Hub credentials as GitHub Actions secrets — not a local PowerShell script — because CI runners are Linux and multi-arch builds need QEMU regardless of host OS.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Semver version decision (parse Conventional Commits, bump) | CI / Build tooling | Developer local script (optional) | Must be deterministic and auditable; doing it in CI avoids "works on my machine" tag drift. A local script variant is fine as a convenience wrapper but should not be the only path. |
| Version string storage | Repo (source of truth file) | Autotools substitution (`configure.ac`/`version.py.in`) | A single file must be authoritative; today `configure.ac` and git tags already disagree, so this phase must pick and document one authority. |
| Docker image build (multi-arch) | CI / Backend build pipeline | Local dev machine (native-arch only, existing `docker compose build`) | QEMU emulation for `arm/v7` is slow and only worth doing once in CI, not on every developer's laptop; local dev keeps building native-arch images as today. |
| Docker Hub push + tagging | CI / Backend build pipeline | — | Requires a secret (Docker Hub access token) that must never live on a developer machine or in `.env`; GitHub Actions secrets are the correct tier. |
| Git tag creation (`vX.Y.Z`) | CI or developer via local script | — | Either a human runs the bump script and pushes the tag, or CI creates the tag on a trigger (e.g. merge to `master`) — a phase decision, not resolved by research. |
| Local dev docker-compose build path | Developer / Docker Compose | — | Must remain unchanged (`docker compose build` still works with no Docker Hub credentials needed) — publishing is an additional channel, not a replacement. |

## User Constraints

> No `CONTEXT.md` exists for this phase (discuss-phase was skipped under `--auto`). The items below are derived from the roadmap phase description and the reference doc, not a locked user decision — the planner and/or a follow-up discuss-phase pass should confirm them before treating as locked.

### From roadmap (`ROADMAP.md` Phase 9)
- Goal: "Add publish and versioning on Docker Hub, using `docs/versioning-and-publish-reference.md` as the base."
- Depends on: Phase 8 (must be complete/mergeable first).
- Requirements: **TBD** — no REQUIREMENTS.md entries exist for Phase 9 (traceability table stops at Phase 5/OPS-06). The planner will need to either add new requirement IDs or treat this as a phase with an inline `## Success Criteria` list only (matching Phase 6/7/8's pattern of `D-01..D-NN` decision IDs defined directly in a phase CONTEXT.md — which does not exist here).

### From reference doc (base to adapt, not copy verbatim — see divergences above)
- `VERSION` file, `MAJOR.MINOR.PATCH`, no `v` prefix, single source of truth.
- Bump decision reads git log since last tag for Conventional Commit prefixes: `BREAKING CHANGE` (substring, case-sensitive) → major; `^feat(\(.+\))?:` → minor; `^fix(\(.+\))?:` → patch; first match in that priority order wins; no match → no-op, exit 0.
- Bump script never commits/pushes/tags-and-pushes by itself (tag is local-only if created).
- Publish script builds, tags `:latest` and `:{version}`, pushes both; never touches git or the VERSION file.
- Docker Hub is implicit (no registry host prefix) in the reference; this repo has stated no Docker Hub username/org yet — **ASSUMED gap, needs a decision** (see Open Questions).

### Deferred / Out of scope
- Nothing explicitly deferred (no CONTEXT.md `## Deferred Ideas` section exists). Do not scope-creep into: GHCR/ECR multi-registry publishing, blue/green zero-downtime deploys (the reference's `restart-container.ps1` companion causes brief downtime and is explicitly "not the main subject" — out of scope here too unless the planner decides otherwise), or automatic `configure.ac`/Autotools version-string generation unless required to resolve the version-source conflict.

## Standard Stack

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|---------------|
| `docker/setup-qemu-action` | v4 | Registers QEMU binfmt handlers on the GitHub Actions runner so `arm/v7` code can run under emulation during build | `[CITED: docs.docker.com/build/ci/github-actions/multi-platform]` — official Docker documentation's own recommended action for this exact use case |
| `docker/setup-buildx-action` | v4 | Creates/boots a Buildx builder instance capable of multi-platform builds | `[CITED: docs.docker.com/build/ci/github-actions/multi-platform]` |
| `docker/login-action` | v4 | Authenticates to Docker Hub using a username + access token from GitHub Actions secrets, without exposing credentials in build logs | `[CITED: docs.docker.com/build/ci/github-actions/multi-platform]` |
| `docker/build-push-action` | v7 | Single step that builds for `linux/amd64,linux/arm/v7` and pushes both tags (`:latest`, `:{version}`) in one buildx invocation — replaces the reference doc's build→tag→push three-step sequence, which is single-arch-only | `[CITED: docs.docker.com/build/ci/github-actions/multi-platform]` |
| `actions/checkout` | v4 | Already used in `.github/workflows/ci.yml`; reuse the same version for consistency | `[VERIFIED: repo grep, .github/workflows/ci.yml:20]` |

### Supporting
| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| Conventional Commits parsing (bash/grep or a small Python script) | — | Reimplementation of `increment-version.ps1`'s bump-detection algorithm | Needed regardless of language choice; no external library required — the algorithm is ~20 lines of string matching against `git log` output |
| `git describe --tags --abbrev=0` / `git log <range> --pretty=%B` | (git, already present) | Same commit-range + message extraction as the reference script | Core to the bump algorithm; behavior is identical across bash/PowerShell/Python since it just shells out to `git` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled Conventional-Commits bump script (this phase's approach, matching the reference doc's own logic) | `semantic-release` / `python-semantic-release` / `standard-version` | Off-the-shelf tools handle changelog generation and edge cases (multiple bump types in one push, monorepo scoping) more robustly, but pull in a Node/Python dependency tree and impose their own commit-message/config conventions — likely overkill for a single-repo, single-image project that already has a working reference algorithm to port. Recommend staying with the ported reference logic unless the planner wants changelog generation as a stated goal. |
| GitHub Actions-only build/push | Reference doc's local PowerShell `publish.ps1` run by a developer | Local script keeps a human in the loop and matches the reference project's workflow, but requires every publishing developer to have Docker Hub write credentials on their own machine, and (per the reference doc's own porting notes) would need to be rewritten from single-`docker build` to `docker buildx build --platform ... --push` for multi-arch anyway. CI-triggered publish is safer (one set of credentials, in one place, as a secret) and is the recommended path; a local script can still exist as a manual/dry-run convenience wrapper around the same `docker buildx build` command. |
| Docker Hub only | GHCR (`ghcr.io`) alongside/instead of Docker Hub | Roadmap explicitly says "Docker Hub" — no signal to add GHCR. Note for the record only. |

**Installation:** No new pip/npm/system packages are required for this phase. `docker`, `git`, and `buildx` (bundled with modern Docker Engine/Docker Desktop and already implied by the existing `Dockerfile`/`docker-compose.yml` usage) are the only CLIs involved; GitHub Actions marketplace actions are referenced by tag in workflow YAML, not installed via a package manager.

**Version verification:** Versions above (`v4`/`v7`) were confirmed via WebFetch against `docs.docker.com/build/ci/github-actions/multi-platform` (official Docker documentation), current as of this research session. These are GitHub Actions marketplace action major-version tags (not npm/PyPI packages), so `npm view`/`pip index versions` do not apply; the standard verification for marketplace actions is checking the action's own repo tags/releases, which was not independently re-verified beyond the docs.docker.com citation — treat as `[CITED]`, not `[VERIFIED: registry]`.

## Package Legitimacy Audit

**Not applicable.** This phase installs no pip/npm/cargo packages. All tooling is either already present (git, docker, docker compose — verified present via existing `Dockerfile`/`docker-compose.yml`/CI usage) or is a GitHub Actions marketplace action referenced by version tag in workflow YAML (not a package-manager install, so `slopcheck`/npm-registry/PyPI-registry verification does not apply). The four Docker-maintained actions listed in Standard Stack (`docker/setup-qemu-action`, `docker/setup-buildx-action`, `docker/login-action`, `docker/build-push-action`) are published by the official `docker` GitHub organization and are the same actions documented on `docs.docker.com` — no separate legitimacy gate needed beyond pinning to a specific major version tag (already done above) rather than `@master`/`@main`.

**Packages removed due to slopcheck verdict:** none (no packages evaluated — none applicable)
**Packages flagged as suspicious:** none

## Architecture Patterns

### System Architecture Diagram

```
Developer commits with Conventional Commits prefix (feat:/fix:/BREAKING CHANGE)
        │
        ▼
   git push → branch (master / python3-migration)
        │
        ▼
┌───────────────────────────────┐
│ GitHub Actions: ci.yml         │   (existing — pytest + import-check, unchanged)
│  runs on every push/PR         │
└───────────────────────────────┘
        │
        │  (new, this phase — separate job or workflow, gated so it only
        │   runs on tag push / master merge, NOT every PR)
        ▼
┌────────────────────────────────────────┐
│ GitHub Actions: publish.yml (new)        │
│  1. Determine version                    │
│     - read VERSION file (source of truth)│
│     - OR: parse git log since last tag   │
│       for feat:/fix:/BREAKING CHANGE      │
│  2. docker/setup-qemu-action              │
│  3. docker/setup-buildx-action            │
│  4. docker/login-action (Docker Hub)      │
│     - creds from GitHub Actions secrets   │
│  5. docker/build-push-action               │
│     platforms: linux/amd64,linux/arm/v7    │
│     tags: {user}/{image}:latest,           │
│            {user}/{image}:{version}        │
│     push: true                             │
│  6. (optional) git tag v{version} + push    │
└────────────────────────────────────────┘
        │
        ▼
   Docker Hub registry: {user}/{image}:latest, :{version}
        │
        ▼
   Deployment host: docker compose pull && docker compose up -d
   (existing docker-compose.yml — UNCHANGED, still builds locally by default;
    Docker Hub is an additional distribution channel, not a replacement)
```

### Recommended Project Structure
```
.github/workflows/
├── ci.yml           # existing — pytest + import-check on push/PR (unchanged)
└── publish.yml       # new — version bump decision + multi-arch build/push, gated to tags or master
VERSION                # new, repo root — plain-text MAJOR.MINOR.PATCH, single source of truth (decision needed re: configure.ac/version.py.in reconciliation)
scripts/ (or tools/)
├── bump-version.sh    # or .py — ports increment-version.ps1's algorithm to bash/Python
└── publish-image.sh   # optional local/manual wrapper around docker buildx build --platform ... --push, for dry-run/local testing without waiting on CI
```

### Pattern 1: CI-gated multi-arch publish, separate from the PR test workflow
**What:** Keep `ci.yml`'s pytest/import-check job running on every push/PR unchanged. Add a second, separate workflow (or a second job in the same workflow gated by an `if:` condition) that only runs on tag pushes (`on: push: tags: ['v*']`) or on merge to `master`, and does the version-bump-decision + Docker build/push.
**When to use:** Always, for this phase — publishing on every PR would push unreviewed/unmerged code to `:latest`, which is the opposite of what semver tagging is for.
**Example:**
```yaml
# Source: docs.docker.com/build/ci/github-actions/multi-platform (adapted)
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
            ${{ secrets.DOCKERHUB_USERNAME }}/pellmon:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/pellmon:${{ github.ref_name }}
```

### Pattern 2: Ported bump algorithm (bash), matching reference doc semantics exactly
**What:** Same priority-order logic as `increment-version.ps1` — `BREAKING CHANGE` substring (any commit) → major; `^feat(\(.+\))?:` (any commit, line-start) → minor; `^fix(\(.+\))?:` (any commit, line-start) → patch; else no-op exit 0.
**When to use:** As a standalone script callable both locally (dry-run) and from CI.
**Example:**
```bash
# Source: docs/versioning-and-publish-reference.md algorithm, ported to bash
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
**Caution:** `grep -q "BREAKING CHANGE"` on the whole multi-line `commits` string checks substring presence anywhere, matching the reference's "any commit line" semantic — but `git log --pretty=%B` line-anchored `^feat:` checks need `grep -m1` per-line behavior verified against multi-line commit bodies (test with a commit that has `feat:` in the subject and unrelated text in the body before trusting this in CI).

### Anti-Patterns to Avoid
- **Copying the reference doc's single-arch `docker build -t {ImageName} .` step verbatim:** this repo needs `linux/amd64,linux/arm/v7`; a plain `docker build` only produces the runner's native arch (amd64 on GitHub-hosted runners), silently producing an image that won't run on a Raspberry Pi.
- **Hardcoding a Docker Hub username/token in a script or `.env`:** the reference doc's `-DockerUsername` parameter and implicit `docker login` session are fine for a local dev machine but must become GitHub Actions **secrets** (`DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`) for CI — never commit credentials, and note `.env`/`.env.example` in this repo are Compose-only knobs (TZ, ports, `PELLMON_DATA_DIR`), not a place for registry credentials.
- **Publishing on every push/PR:** would tag `:latest` with unreviewed code; gate to tag pushes or protected-branch merges only.
- **Leaving `configure.ac`'s `AC_INIT([PellMon], [0.7.0])` and the new `VERSION` file to drift independently:** pick one authority and either generate the other from it or explicitly document that Autotools versioning and Docker image versioning are now two separate, intentionally-decoupled numbers (defer this exact call to the planner/user — see Open Questions).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multi-arch image build/push | A bash script chaining `docker build` per-arch and manually creating a manifest list | `docker buildx build --platform linux/amd64,linux/arm/v7 --push` (single invocation) or the `docker/build-push-action` wrapper | Buildx handles the OCI manifest-list creation, QEMU delegation, and layer caching correctly; a hand-rolled per-arch-build-then-manifest-push script is exactly the kind of "deceptively complex" problem `docker buildx` already solves and is what the reference doc itself flags as the needed change (`publish.ps1`'s porting notes explicitly call out buildx as the fix for "no multi-arch build") |
| Conventional Commits parsing for arbitrary edge cases (squash-merge messages, multi-paragraph bodies, scoped `feat(api):`) | A regex library or custom parser trying to handle every Conventional Commits edge case | The reference doc's simple 3-pattern priority check (`BREAKING CHANGE` substring / `^feat` / `^fix`) — port it as-is | The reference doc's own algorithm is already deliberately minimal (documented explicitly as "no docs:/chore:/other-prefix handling") — matching it exactly (not extending it) keeps behavior predictable and matches what was asked ("using the reference doc as the base") |

**Key insight:** Both of this phase's core problems (multi-arch builds, semver-from-commits) already have a "right-sized" solution named directly in the reference doc's own porting notes — the research task here was confirming those notes are still accurate against current tooling (they are) and identifying what's project-specific to PellMon (nothing off-the-shelf handles the `VERSION`-vs-`configure.ac` conflict; that's a repo-specific decision).

## Common Pitfalls

### Pitfall 1: QEMU emulation silently produces a broken/slow arm/v7 image
**What goes wrong:** Building for `arm/v7` via QEMU emulation on an amd64 GitHub Actions runner works, but any native-code compilation step in the Dockerfile (this repo's `Dockerfile` does `apt-get install ... gcc pkg-config` and installs several packages with C extensions — `rrdtool`/`librrd-dev`, `python3-dev`) can take dramatically longer under emulation, sometimes hitting the GitHub Actions job timeout.
**Why it happens:** QEMU emulates the CPU instruction-by-instruction; anything that compiles C code (pip installing non-wheel packages, `apt-get` triggering builds) is 5-20x slower than native.
**How to avoid:** Time a full CI run for the `arm/v7` leg before assuming it's viable inside the default job timeout; if it's too slow, consider (a) a longer `timeout-minutes`, (b) Docker's cross-runner "Docker GitHub Builder" split-by-platform approach the official docs mention, or (c) pre-built arm/v7 base-layer caching via `docker/build-push-action`'s `cache-from`/`cache-to` with GitHub Actions cache.
**Warning signs:** CI job for the publish workflow runs far longer than the existing `ci.yml` pytest job; job gets cancelled at the default 6-hour Actions limit or a custom shorter timeout.

### Pitfall 2: `docker/login-action` credentials must be a Docker Hub **access token**, not the account password
**What goes wrong:** Using a Docker Hub account password directly in the `DOCKERHUB_TOKEN` secret works today but is deprecated/discouraged by Docker Hub itself, and 2FA-enabled accounts cannot use a password for API/CLI login at all.
**Why it happens:** Docker Hub's own UI still allows password login for humans, but CLI/API auth (which `docker/login-action` uses) is expected to use a scoped Personal Access Token (PAT) generated from Docker Hub account settings.
**How to avoid:** Generate a Docker Hub PAT scoped to "Read & Write" for the target repo, store it as the `DOCKERHUB_TOKEN` GitHub secret; store the Docker Hub username as `DOCKERHUB_USERNAME` (can be a plain repo variable, not necessarily a secret, since usernames aren't sensitive — though the reference doc's own porting notes flag "push access denied ... insufficient_scope" as the most common failure, which is almost always a token-scope issue).
**Warning signs:** Push step fails with `denied: requested access to the resource is denied` or `insufficient_scope` — per the reference doc's own experience, this is the overwhelmingly common failure mode, not a code bug.

### Pitfall 3: `configure.ac`'s `AC_INIT` version and the new `VERSION` file diverge silently
**What goes wrong:** `version.py.in`'s `@VERSION@` (substituted from `configure.ac`'s `AC_INIT([PellMon], [0.7.0])` at Autotools build time) will keep reporting `0.7.0` (or whatever `configure.ac` says) in the app's own `--version` flag and web UI footer, while the Docker image tag says something else entirely (currently the latest git tag is `v1.0.0` — already inconsistent with `configure.ac`'s `0.7.0` before this phase even starts).
**Why it happens:** Two independent version-authority mechanisms (Autotools `AC_INIT` vs. a new plain-text `VERSION` file) were never reconciled; the reference doc's project apparently has no Autotools layer at all, so this conflict is unique to porting it into PellMon.
**How to avoid:** This phase's plan must explicitly decide: (a) make `VERSION` the single source of truth and have `configure.ac`/`version.py.in` generation read from it (bigger change, touches the Autotools build), (b) keep them separate and accept the app-reported version and the Docker tag are different numbers (simpler, but confusing for support/debugging), or (c) retire `configure.ac`'s version entirely in favor of `VERSION` now that Docker Compose is the primary deployment path (per `REQUIREMENTS.md`'s Out-of-Scope note that "Full rewrite of Autotools ... legacy path is stable ... stays as-is" — suggesting option (b) may be the pragmatic choice, but this is a call for the planner/user, not research). **This is the single most important open question for planning this phase.**
**Warning signs:** A bug report references "version 1.3.0" (Docker tag) but `pellmonsrv --version` on that same container reports `0.7.0` or `_dev_`.

## Code Examples

### Reading and validating the VERSION file (bash port of the reference's precondition check)
```bash
# Source: docs/versioning-and-publish-reference.md preconditions, ported
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

### Multi-arch build/push via raw Docker CLI (for a local/manual dry-run wrapper, not CI)
```bash
# Source: docs.docker.com/build/ci/github-actions/multi-platform (CLI-equivalent of the Actions workflow)
docker buildx create --use --name pellmon-builder 2>/dev/null || docker buildx use pellmon-builder
docker buildx build \
  --platform linux/amd64,linux/arm/v7 \
  -t "$DOCKERHUB_USERNAME/pellmon:latest" \
  -t "$DOCKERHUB_USERNAME/pellmon:$(cat VERSION)" \
  --push \
  .
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `docker build` (single native arch) then `docker tag`/`docker push` per tag (the reference doc's `publish.ps1`) | `docker buildx build --platform <list> --push` (single invocation builds and pushes all platforms as one manifest list) | Buildx has been Docker's recommended multi-arch path since Docker 19.03+ (long-stable, not a recent change) | Eliminates the reference doc's own noted limitation ("No multi-arch build"); this is exactly the gap this phase must close relative to the reference |
| `docker/build-push-action@v2`/`v3` (older tags) | `docker/build-push-action@v7` | Ongoing action releases; v7 is current per official docs as of this research session | Use `@v7`, not older tutorials/blog posts that may reference `@v2` |

**Deprecated/outdated:**
- Docker Hub password-based CLI login for `docker/login-action`: superseded by Personal Access Tokens; password auth may be blocked entirely for 2FA-enabled accounts.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The project wants a `linux/amd64,linux/arm/v7` multi-arch image (carried over from the orchestrator's additional_context, not independently confirmed as a locked decision — no CONTEXT.md exists) | Summary, Architecture, Standard Stack | If the actual target is amd64-only (e.g. Docker Hub is just for easier amd64 deployment, not Raspberry Pi), the QEMU/buildx multi-arch work is unnecessary complexity; if arm64 (not arm/v7) is the real Pi target (newer Pi OS 64-bit images), the platform string needs updating |
| A2 | Docker Hub is the only target registry (no GHCR) | User Constraints, Standard Stack | Low risk — explicitly stated in the roadmap phase title itself ("Docker Hub"), so this is well-supported, not purely assumed |
| A3 | Publishing should be CI-triggered (tag push or master merge), not a manual local-only PowerShell/bash script | Architecture Pattern 1, Don't Hand-Roll | If the user actually wants a local-first workflow (matching the reference doc's own "human runs the script" model) rather than full CI automation, the plan would need a different trigger/ownership model |
| A4 | The `VERSION`-vs-`configure.ac` conflict should be resolved by keeping them independent (option b in Pitfall 3) rather than unifying | Pitfall 3 | If the user actually wants unification, the plan needs an Autotools-generation task that this research did not scope in detail |
| A5 | `docker/build-push-action@v7`, `setup-qemu-action@v4`, `setup-buildx-action@v4`, `login-action@v4` are current and stable choices | Standard Stack | Low risk if wrong — these are pinned major versions from an official Docker doc page fetched this session; a minor version drift wouldn't break the plan, only a major deprecation would |
| A6 | Docker Hub repository (`{username}/pellmon` or similar) does not yet exist and must be created before first push | Common Pitfalls, Open Questions | If a Docker Hub repo/org already exists under a name the user has in mind, the plan should reference it directly instead of treating repo creation as a task |

**If this table is empty:** N/A — see entries above; this research has open assumptions that need user confirmation before the planner locks task details, particularly A1, A3, A4, and A6.

## Open Questions

1. **What Docker Hub username/organization and image name should be used?**
   - What we know: The reference doc parameterizes `-DockerUsername`/`-ImageName`; this repo's `Dockerfile`/`docker-compose.yml` locally tag the image as bare `pellmon:latest` with no registry namespace.
   - What's unclear: No Docker Hub account/org name appears anywhere in the repo (checked `README.md`, `DOCKER.md`, `.env.example`, `docker-compose.yml` — no hits).
   - Recommendation: This needs a direct answer from the user before planning can assign a concrete `{username}/{imagename}` — flag as a required input to the planner, likely surfaced as a `checkpoint:human-verify` or an explicit question task.

2. **Should the Docker tag and the app's own `__version__` (from `version.py.in`) match?**
   - What we know: `pellmonsrv.py`/`pellmonweb.py` both report `__version__` from Autotools-substituted `version.py.in`, currently driven by `configure.ac`'s `0.7.0`, independent of git tags (`v1.0.0` latest) or any future `VERSION` file.
   - What's unclear: Whether unifying these is in scope for this phase or deliberately deferred (see Pitfall 3 / Assumption A4).
   - Recommendation: Planner should ask the user directly; recommend NOT unifying in this phase unless explicitly requested, since it touches the Autotools build path which `REQUIREMENTS.md`'s Out-of-Scope table says should stay "as-is."

3. **Should `arm/v7` be the correct Pi target, or should it be `arm64` (aarch64)?**
   - What we know: Raspberry Pi OS has shipped 64-bit (`arm64`) as the default since Raspberry Pi OS Bullseye (2021); `arm/v7` (32-bit ARMv7) is the older default. The reference doc's own porting note only says "For multi-arch, this needs buildx" without specifying which arm variant.
   - What's unclear: Which Pi models/OS versions PellMon's actual users run — the codebase mentions `RPi.GPIO` (Raspberry Pi hardware target) but no OS-bitness signal.
   - Recommendation: Confirm with the user which architecture(s) their target Pi hardware/OS actually needs; `linux/arm/v7,linux/arm64,linux/amd64` (three platforms) is also a valid choice if both older and newer Pi OS need support, at the cost of longer CI build time (see Pitfall 1).

4. **Should the version-bump script auto-create and push a git tag, or remain purely local (matching the reference doc's `-UpdateTag` being local-only, never pushed)?**
   - What we know: The reference script's tag creation is explicitly local-only; pushing tags is the caller's separate job.
   - What's unclear: Whether this phase should automate tag-push in CI (e.g., a workflow_dispatch job that bumps, commits, tags, and pushes in one go) or keep the human-in-the-loop model.
   - Recommendation: Default to keeping the human-in-the-loop model (matches the reference doc's explicit design choice) unless the user asks for full automation.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker Engine + Buildx | Multi-arch build/push | ✓ (implied — existing `Dockerfile`/`docker-compose.yml` already require Docker) | Not directly queried this session (no shell access to a Docker daemon in this research environment) | GitHub Actions `ubuntu-latest` runners ship Docker + Buildx preinstalled — CI does not depend on the local dev machine having Buildx |
| GitHub Actions (`ubuntu-latest` runner) | CI-based publish workflow | ✓ | Existing `.github/workflows/ci.yml` already targets `ubuntu-latest` | — |
| Docker Hub account/org + access token | Push destination + CI secret | ✗ (not found in repo — see Open Question 1) | — | None — this blocks the push step until a human provides credentials/naming; no code fallback exists |
| `configure.ac`/Autotools toolchain | Only relevant if the planner chooses to unify version sources (Assumption A4) | ✓ (already used for the existing build, per `configure.ac`/`Makefile.am` presence) | Not version-checked this session | Skip entirely if version sources are kept independent (recommended default) |

**Missing dependencies with no fallback:**
- Docker Hub account/org name + access token — must be supplied by the user before the publish workflow can run for real (dry-run/local-build-only testing can proceed without it).

**Missing dependencies with fallback:**
- None beyond the Docker Hub credentials item above.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing, per `.github/workflows/ci.yml` and `tests/` — no new framework needed for this phase) |
| Config file | `pytest.ini` (existing, from Phase 1) |
| Quick run command | `pytest tests/ -k "version or publish"` (once new tests exist — see gaps below) |
| Full suite command | `pytest tests/ -v` (existing CI command) |

### Phase Requirements → Test Map
> No formal requirement IDs exist for Phase 9 (TBD in ROADMAP.md/REQUIREMENTS.md). The rows below are inferred candidate behaviors the planner should turn into real requirement IDs.

| Candidate Req | Behavior | Test Type | Automated Command | File Exists? |
|--------------|----------|-----------|-------------------|-------------|
| (TBD-1) | Version-bump script correctly classifies a `feat:` commit as minor, `fix:` as patch, `BREAKING CHANGE` as major, and no-match as no-op | unit | `pytest tests/test_version_bump.py -x` | ❌ Wave 0 |
| (TBD-2) | Version-bump script rejects a malformed `VERSION` file (not exactly 3 integers) with a nonzero exit | unit | `pytest tests/test_version_bump.py -x` | ❌ Wave 0 |
| (TBD-3) | `publish.yml` workflow YAML is syntactically valid and references the pinned action versions (no `@main`/`@master` floating tags) | static / lint | `actionlint .github/workflows/publish.yml` (new tool — not yet in this repo, see gap below) or manual review | ❌ Wave 0 |
| (TBD-4) | Multi-arch build actually produces a runnable `arm/v7` image | manual-only (requires either real Pi hardware or QEMU-run smoke test) | N/A — flagged manual-only; justification: no arm/v7 hardware or emulated runtime is available in this research/CI environment beyond the build step itself | — |

### Wave 0 Gaps
- [ ] `tests/test_version_bump.py` — unit tests for the ported bump-decision script (mock `git log`/`git describe` output, assert classification)
- [ ] Decide and install `actionlint` (or skip — a lightweight, common but non-default tool) if workflow-YAML validation is wanted as an automated gate; otherwise rely on manual review + a real `workflow_dispatch` dry run
- [ ] No existing fixture mocks `git` subprocess calls — new tests will need a `tmp_path` git repo fixture or a `subprocess.run` mock, whichever matches this repo's existing test conventions (check `tests/conftest.py` from Phase 1 for a reusable pattern before adding a new one)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Not applicable — this phase has no end-user-facing auth surface |
| V6 Cryptography | No | Not applicable — no new crypto code |
| Secrets management (not a numbered ASVS category here, but directly relevant) | Yes | GitHub Actions **encrypted secrets** (`Settings → Secrets and variables → Actions`) for `DOCKERHUB_TOKEN`; never place credentials in `.env`, `.env.example`, or committed workflow YAML. This matches the project's existing pattern of keeping `.env` out of git (`.dockerignore`/`.gitignore` already exclude it) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Docker Hub credential leakage via workflow logs or a misconfigured action input | Information Disclosure | Use `docker/login-action` (which masks credentials in logs by design) rather than a raw `docker login -p $PASSWORD` shell command; use a scoped PAT, not the account password |
| Supply-chain risk from unpinned GitHub Actions (`uses: docker/build-push-action@main`) | Tampering | Pin every action to an explicit major-version tag (`@v7`, not `@main`/`@latest`) — already the recommendation throughout this document |
| Publishing an unreviewed/unmerged build to the `:latest` tag | Tampering (of the deployed artifact's provenance) | Gate the publish workflow to tag pushes or protected-branch merges only (Architecture Pattern 1), never on arbitrary PR branches |

## Sources

### Primary (HIGH confidence)
- `docs.docker.com/build/ci/github-actions/multi-platform` — fetched via WebFetch this session; workflow YAML, action names, and version pins (`docker/login-action@v4`, `docker/setup-qemu-action@v4`, `docker/setup-buildx-action@v4`, `docker/build-push-action@v7`) taken directly from this page.
- Repo files read directly this session: `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/ROADMAP.md`, `docs/versioning-and-publish-reference.md`, `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `configure.ac`, `src/Pellmonsrv/version.py.in`, `requirements.txt`, `.env.example`, `DOCKER.md` — plus `git tag -l` and `git log --oneline`.

### Secondary (MEDIUM confidence)
- WebSearch results confirming `docker/build-push-action` v7/`setup-qemu-action` v4/`setup-buildx-action` v4 as current — cross-verified against the primary WebFetch of the official docs page above, so elevated from the search alone.

### Tertiary (LOW confidence)
- None used directly as a basis for a claim in this document (all WebSearch findings were cross-checked against the official Docker docs page before being stated as fact).

## Metadata

**Confidence breakdown:**
- Standard stack (GitHub Actions multi-arch tooling): HIGH — directly sourced from official Docker documentation, current as of this session.
- Architecture (workflow gating, secrets handling): MEDIUM — sound general CI/CD practice, but the specific trigger model (tag push vs. master merge vs. manual dispatch) is an unconfirmed assumption (A3).
- Pitfalls: MEDIUM-HIGH — QEMU slowness and Docker Hub PAT requirements are well-documented, widely-known issues; the `configure.ac`/`VERSION` conflict pitfall is HIGH confidence because it was verified directly by reading this repo's own files.
- Project-specific decisions (Docker Hub naming, arm/v7 vs arm64, version-source unification): LOW — genuinely unresolved; flagged as Open Questions and Assumptions, not stated as fact.

**Research date:** 2026-09-22
**Valid until:** 30 days (GitHub Actions marketplace action versions and Docker Hub auth requirements move slowly, but re-check action version pins if planning is delayed significantly)
