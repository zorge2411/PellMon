---
phase: 09-add-docker-hub-image-publishing-with-semver-versioning
plan: 02
subsystem: infra
tags: [github-actions, docker, buildx, semver, ci-cd]

# Dependency graph
requires:
  - phase: 09-01
    provides: "tools/version_bump.py decide CLI (bump=/version= GITHUB_OUTPUT contract)"
provides:
  - "publish job in .github/workflows/ci.yml: decide bump, commit+tag+push VERSION, multi-arch Docker Hub build+push"
  - "tests/test_ci_docker_config.py::test_publish_workflow_permissions_and_skip_ci"
  - "tests/test_ci_docker_config.py::test_publish_workflow_multiarch_and_tags"
affects: [09-03]

# Tech tracking
tech-stack:
  added:
    - "docker/setup-qemu-action@v4"
    - "docker/setup-buildx-action@v4"
    - "docker/login-action@v4"
    - "docker/build-push-action@v7"
  patterns:
    - "Second job in the same ci.yml workflow file (not a separate publish.yml) gated by needs: test + if: push-to-master, keeping [skip ci] semantics reliable (plain push: trigger, no workflow_run)"
    - "Job-scoped permissions: contents: write only on publish, test job keeps default read-only token"
    - "Flat plain-text assertion idiom for workflow config tests (no YAML parser), matching test_github_actions_workflow"

key-files:
  created: []
  modified:
    - .github/workflows/ci.yml
    - tests/test_ci_docker_config.py

key-decisions:
  - "Docker action versions pinned to current major release tags verified via GitHub releases API at execution time (setup-qemu-action v4, setup-buildx-action v4, login-action v4, build-push-action v7) rather than trusting 09-RESEARCH.md's disagreeing WebSearch-sourced numbers"
  - "All four docker/* build/push steps carry if: steps.bump.outputs.bump != 'none' so a no-release push is a clean no-op (D-03)"

patterns-established:
  - "Publish job lives in ci.yml as a second job, not a separate workflow file (09-RESEARCH.md Open Question 1 recommendation)"

requirements-completed: [D-01, D-02, D-03, D-04, D-07]

duration: ~20min
completed: 2026-09-23
---

# Phase 9 Plan 2: Publish job in ci.yml Summary

Added a `publish` job to `.github/workflows/ci.yml` that, only on push to `master` after the
`test` job passes, calls `tools/version_bump.py decide`, commits+tags a `[skip ci]` version bump,
and builds+pushes a `linux/amd64,linux/arm64` multi-arch image to Docker Hub
(`peterscholer74/pellmon:latest` and `:{version}`) via the official `docker/*` actions.

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-23T07:28:00Z
- **Completed:** 2026-09-23T07:34:48Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `publish` job added to `ci.yml`: `needs: test`, `if: github.event_name == 'push' && github.ref == 'refs/heads/master'`, job-scoped `permissions: contents: write`, full-depth checkout.
- `Decide version bump` step (`id: bump`) runs `python3 tools/version_bump.py decide` (runner's system python3, no `actions/setup-python` — the script is stdlib-only and the existing `test_github_actions_workflow` test forbids that action).
- `Commit and tag version bump` step (gated `if: steps.bump.outputs.bump != 'none'`) commits `VERSION` as `chore: bump version to {version} [skip ci]`, creates annotated tag `v{version}` (no `--force`), pushes both to `master`.
- QEMU/buildx/login/build-push chain (all four steps also gated on `bump != 'none'`) builds and pushes `peterscholer74/pellmon:latest` + `:{version}` for both target platforms.
- Docker Hub credentials flow only through `docker/login-action`'s `with:` inputs (`secrets.DOCKERHUB_USERNAME`/`secrets.DOCKERHUB_TOKEN`) — no raw shell `docker login -p`.
- Inline YAML comments document two deliberate deviations: (1) full-depth checkout is required because `git describe`/`git log {tag}..HEAD` are unreliable on the default shallow clone, (2) buildx pushes all `tags:` as one atomic manifest operation, unlike the reference `publish.ps1`'s two independent fail-fast `docker push` calls.
- Two new config-assertion tests added to `tests/test_ci_docker_config.py` (RED before Task 2, GREEN after) covering the permissions/skip-ci/master-gating literals and the multi-arch/tags/secrets literals, plus negative guards (`--force`, `git tag -f`, `workflow_run`, `docker login -p`, `--password `, `ghcr.io` all absent).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing config assertions for the publish job** - `abdeebd` (test)
2. **Task 2: Add the publish job to .github/workflows/ci.yml** - `93bdec5` (feat)

**Plan metadata:** (this commit)

_TDD RED/GREEN: Task 1 is the RED commit (both new tests fail against the unmodified ci.yml),
Task 2 is the GREEN commit (both tests pass once the publish job exists)._

## Files Created/Modified
- `.github/workflows/ci.yml` - added the `publish` job (decide bump, git write-back, multi-arch Docker Hub build+push); `on:` block and `test` job left byte-identical
- `tests/test_ci_docker_config.py` - added `test_publish_workflow_permissions_and_skip_ci` and `test_publish_workflow_multiarch_and_tags`

## Decisions Made
- Verified the four `docker/*` action current major-version tags live via the GitHub releases API (`curl https://api.github.com/repos/docker/<action>/releases/latest`) at execution time rather than trusting 09-RESEARCH.md's Assumptions Log A1 (which flagged disagreeing WebSearch sources): `docker/setup-qemu-action@v4`, `docker/setup-buildx-action@v4`, `docker/login-action@v4`, `docker/build-push-action@v7`.
- Kept the publish job in `ci.yml` as a second job rather than a separate `publish.yml`, per 09-RESEARCH.md Open Question 1's recommendation — simpler `[skip ci]` semantics with a plain `push:` trigger.

## Deviations from Plan

None - plan executed exactly as written. The action version pins (v4/v4/v4/v7) were determined per the plan's own instruction to verify at execution time rather than trust the research doc's disagreeing numbers; this was explicit plan guidance, not a deviation.

## Issues Encountered

None. Full suite run (`pytest tests/ -v`) surfaces 7 pre-existing failures and 32 pre-existing collection errors unrelated to this plan's two modified files (`ModuleNotFoundError: cherrypy`/`Crypto`, plugin-loader/fixture issues) — these are the same Windows-dev-venv environment gaps documented in `09-01-SUMMARY.md` ("Pre-existing collection errors ... are Windows-dev-venv environment gaps unrelated to this plan"). `tests/test_ci_docker_config.py` itself is 16/16 green, and none of the pre-existing failures touch `ci.yml` or the docker-config test file. Out of scope per the executor's scope-boundary rule — not fixed here.

## User Setup Required

None from this plan's code changes, but the workflow cannot successfully run end-to-end until these one-time manual GitHub/Docker Hub setup steps (documented in 09-RESEARCH.md, not actionable from code) are completed by the repo owner:
- Create the `peterscholer74/pellmon` repository on Docker Hub before the first publish run (Pitfall 5).
- Add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (a Docker Hub access token, not the account password) as GitHub Actions repo secrets (D-07).
- Enable Repo Settings -> Actions -> General -> Workflow permissions -> "Read and write permissions" so the default `GITHUB_TOKEN` can push the bump commit/tag (D-04).
- Confirm `master` branch protection (if any) allows `github-actions[bot]` pushes, or add a bypass — unverifiable from the repo alone (09-RESEARCH.md Pitfall 2, open risk).

## Next Phase Readiness
- The publish job is fully implemented and config-tested; end-to-end behavior (actual git push, actual Docker Hub push) cannot be verified in this dev environment and requires the manual setup above plus a real push to `master` to observe.
- Ready for 09-03 (or phase closeout) to document/verify the manual setup steps and, ideally, observe one real `feat:`/`fix:` push trigger a successful release.

---
*Phase: 09-add-docker-hub-image-publishing-with-semver-versioning*
*Completed: 2026-09-23*

## Self-Check: PASSED

- `.github/workflows/ci.yml` - FOUND
- `tests/test_ci_docker_config.py` - FOUND
- `.planning/phases/09-add-docker-hub-image-publishing-with-semver-versioning/09-02-SUMMARY.md` - FOUND
- Commit `abdeebd` - FOUND
- Commit `93bdec5` - FOUND
