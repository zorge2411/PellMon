# Phase 9: Add Docker Hub image publishing with semver versioning - Context

**Gathered:** 2026-09-23
**Status:** Ready for planning

<domain>
## Phase Boundary

PellMon publishes versioned Docker images to Docker Hub automatically. On every push to
`master`, CI inspects the commits since the last release tag using Conventional Commits
prefixes (`feat:`, `fix:`, `BREAKING CHANGE`), decides whether a version bump is warranted
and of what size (major/minor/patch), bumps a single `VERSION` file, commits and tags that
bump back to the repo, then builds a multi-arch (amd64 + arm64) image and pushes it to Docker
Hub as both `:latest` and `:{version}`. No commit since the last tag matching those prefixes
means no bump, no build, no push — a silent no-op, not a failure.

This phase does NOT cover: multi-registry publishing (GHCR etc.), blue/green or rolling
deploys, or a deploy-automation step that pulls the new image onto a running host (the
existing `docker compose pull && docker compose up -d` workflow from `DEPLOY-PI.md`, phase 7/8,
already covers that and stays manual/operator-triggered).

</domain>

<decisions>
## Implementation Decisions

### Registry target
- **D-01:** Docker Hub namespace/image is `peterscholer74/pellmon`. Published tags:
  `peterscholer74/pellmon:latest` and `peterscholer74/pellmon:{version}`. This matches the
  existing local dev convention where both `pellmonsrv` and `pellmonweb` services in
  `docker-compose.yml` already share one image tag (`pellmon:latest`) — one Docker Hub
  repository, not two.

### Architecture
- **D-02:** Build **multi-arch**: `linux/amd64` and `linux/arm64`, via
  `docker buildx build --platform linux/amd64,linux/arm64 --push` (with QEMU emulation set up
  in the CI job for the arm64 leg). Deviates from the reference script, which does a single
  native-arch build only — PellMon's own `CLAUDE.md` names Raspberry Pi (arm) as a production
  target, so an amd64-only Docker Hub image would be unusable there without a local rebuild.

### Trigger & automation model
- **D-03:** Fully CI-automated on push to `master`. GitHub Actions reads Conventional Commit
  messages since the last `v*` tag (or full history if no tag exists yet) and applies the
  reference algorithm's exact priority order: any commit containing `BREAKING CHANGE`
  (substring, case-sensitive) anywhere in the range → major; else any commit line starting
  `^feat(\(.+\))?:` → minor; else any commit line starting `^fix(\(.+\))?:` → patch; else
  no-op (exit success, nothing built/pushed/committed).
- **D-04:** Unlike the reference script (which deliberately never commits `VERSION` itself —
  "that's the caller's job"), this phase's CI **does** commit the bump and push the tag: CI
  writes the new `VERSION`, commits it as `chore: bump version to {version} [skip ci]` (the
  `[skip ci]` marker is mandatory — without it the bump commit re-triggers the same workflow),
  creates an annotated tag `v{version}`, pushes both commit and tag to `master`, THEN builds
  and pushes the image tagged with that version. This requires the workflow's token to have
  `contents: write` (GitHub Actions → repo Settings → Actions → General → Workflow permissions
  → "Read and write permissions" must be enabled once, by the developer, before this works —
  cannot be set from code; plan must document this as a manual one-time setup step, not silently
  assume it).

### Language / porting
- **D-05 (Claude's discretion, stated so the planner doesn't re-derive it):** The reference
  `.ps1` scripts are Windows-only tooling from an unrelated project and cannot run on the
  `ubuntu-latest` CI runner or in the Linux-only production environment. Port the bump-decision
  and publish logic as a **Python script** (e.g. `tools/version_bump.py`), consistent with this
  project's existing convention of Python-based tooling (`tools/pellmon_backup.py`,
  `tools/burner_sim.py`) rather than introducing Bash for this one job. The script must be
  runnable both standalone (for local dry-run / manual override, from the Windows dev venv or
  WSL) and as a CI step — no PowerShell involved anywhere in this project.
- **D-06:** The bump-decision function (parse commit messages → major/minor/patch/none) must be
  a pure, unit-testable function separable from its git/Docker I/O shell-outs, so it has real
  `pytest` coverage without needing a live git repo or Docker daemon in the test run — mirrors
  this project's existing test-harness philosophy (mocked I/O, no real hardware/network) from
  Phase 1.

### Secrets & legacy version sources
- **D-07:** Docker Hub push auth uses two new GitHub Actions repo secrets:
  `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (a Docker Hub access token, not the account
  password). These must be added once by the developer in repo Settings → Secrets — the plan
  must document the exact secret names required but cannot create them itself.
- **D-08:** `configure.ac`'s `AC_INIT([PellMon], [0.7.0])` and any Autotools version references
  are legacy and explicitly called "largely superseded" in `CLAUDE.md` — this phase does NOT
  attempt to keep them in sync with the new `VERSION` file. `VERSION` becomes the sole source
  of truth for the Docker image tag only. No changes to `configure.ac`/`version.py.in` are in
  scope here.
- **D-09:** Seed `VERSION` at `1.0.0` for the very first commit of this file (no prior tag
  exists in the repo). Chosen over matching `configure.ac`'s `0.7.0` or starting fresh at
  `0.1.0` — the Python 3 migration milestone (v1.0) is essentially complete, so the first
  public Docker Hub image should signal production-readiness rather than pre-1.0 status. The
  planner's bootstrap task must write this literal value; it is not derived by the bump
  algorithm (there is no prior tag to diff against on the very first run).

### Claude's Discretion
- Exact GitHub Actions job/workflow structure (new workflow file vs. extending `ci.yml`) —
  planner should keep the existing PR-gating `ci.yml` test job intact and either add a
  dependent job/workflow that only runs after tests pass on `master`, or reuse call.
- Whether the version-bump script also supports a `--dry-run` / local CLI mode for developers
  who want to preview the next version before pushing — reasonable convenience, not required.
- Exact commit message wording, as long as it includes the mandatory `[skip ci]` marker on the
  bump commit (D-04).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Versioning & publish algorithm (source of truth for logic to port)
- `D:\Antigravity\Kombikode tool\docs\versioning-and-publish-reference.md` — exact algorithm
  for `increment-version.ps1` (semver bump decision from Conventional Commits, priority order,
  exit codes, non-obvious rules) and `publish.ps1` (Docker build/tag/push, registry
  assumptions, multi-arch limitation called out explicitly as needing `docker buildx` instead).
  This project's Python port must preserve the algorithm and exit-code/no-op semantics from
  this doc exactly, only replacing the PowerShell/Windows-Docker-CLI mechanics with
  Python + `docker buildx` shell-outs, and adding CI git write-back (D-04, a deviation from
  the doc's "never commits" rule, noted above).

### Existing project infrastructure this phase builds on
- `Dockerfile` — single image (`debian:bookworm-slim` base) shared by both services; build
  context is repo root.
- `docker-compose.yml` — both `pellmonsrv` and `pellmonweb` already reference one image tag
  `pellmon:latest`; confirms D-01's one-repository decision.
- `.github/workflows/ci.yml` — existing PR-gating test workflow (pytest + import-check on
  `ubuntu-latest`); the new publish automation should not duplicate or bypass this gate.
- `CLAUDE.md` §Platform Requirements — states Raspberry Pi/bare-metal Linux as a production
  deployment target, directly motivating D-02's multi-arch decision.
- `DEPLOY-PI.md` — existing deploy documentation (from Phase 8) already tells operators to run
  `docker compose pull && docker compose up -d`; this phase's docs task should cross-reference
  it rather than duplicate the pull/redeploy instructions.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/pellmon_backup.py` — precedent for a standalone Python CLI tool under `tools/` with
  its own `pytest` coverage; the new version-bump script should follow the same shape
  (argparse-based CLI, testable core function separated from I/O).
- `.github/workflows/ci.yml`'s venv-with-system-site-packages pattern is specific to running
  the app's own tests (needs `dbus`/`gi`/`rrdtool`); the publish job does NOT need that — it
  only needs `git`, `docker buildx`, and Python for the bump-decision script, so it should use
  a plain `actions/setup-python` step, not the system-site-packages venv trick.

### Established Patterns
- No `VERSION` file exists yet anywhere in the repo — this phase introduces it fresh at repo
  root, mirroring the reference doc's own layout.
- Existing version signal is `configure.ac`'s `AC_INIT([PellMon], [0.7.0])`, but per D-08 this
  is intentionally left alone (legacy Autotools, superseded).

### Integration Points
- New CI job/workflow triggers off `push: branches: [master]`, same branch `ci.yml` already
  gates PRs into.
- Multi-arch build needs `docker/setup-qemu-action` + `docker/setup-buildx-action` +
  `docker/login-action` (Docker Hub) + `docker/build-push-action` (or equivalent buildx CLI
  invocation) added to the workflow.

</code_context>

<specifics>
## Specific Ideas

- Exact push order from the reference doc must be preserved: `:latest` push failure stops
  before attempting `:{version}` (checked independently, not both-or-nothing) — port this
  fail-fast-per-tag behavior into the Python/buildx equivalent where feasible (buildx's
  multi-tag single invocation may push both atomically in one command; if so, document that as
  an intentional, disclosed deviation rather than silently dropping the reference's ordering
  guarantee).
- Reuse the reference doc's exact commit-message regexes: `^feat(\(.+\))?:`, `^fix(\(.+\))?:`,
  and bare substring `BREAKING CHANGE` — do not invent new patterns.

</specifics>

<deferred>
## Deferred Ideas

- A `restart-container.ps1`-equivalent auto-redeploy-on-publish step — explicitly out of scope.
  PellMon already standardizes on `docker compose pull && docker compose up -d` as an operator
  action (per `DEPLOY-PI.md`); auto-triggering a redeploy from CI would need a way to reach the
  Pi/host from GitHub Actions (webhook, SSH, watchtower, etc.) that hasn't been decided and
  wasn't asked for here. Candidate for a future phase if wanted.
- GHCR or other secondary registry mirroring — not requested; Docker Hub only for this phase.
- Pinning/locking `requirements.txt` versions to a specific Docker base image digest — unrelated
  to this phase's semver/publish scope (already covered by Phase 5's OPS-04).

</deferred>

---

*Phase: 09-add-docker-hub-image-publishing-with-semver-versioning*
*Context gathered: 2026-09-23*
