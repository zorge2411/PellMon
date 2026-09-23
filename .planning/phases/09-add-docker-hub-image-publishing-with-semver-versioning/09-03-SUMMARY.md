---
phase: 09-add-docker-hub-image-publishing-with-semver-versioning
plan: 03
subsystem: docs / release-process
tags: [docker-hub, releasing, ci-cd, documentation]
dependency-graph:
  requires: [09-01, 09-02]
  provides: ["RELEASING.md", "README.md release cross-reference", "DEPLOY-PI.md published-image note"]
  affects: ["tests/test_ci_docker_config.py"]
tech-stack:
  added: []
  patterns: ["flat assert \"<literal>\" in content doc-assertion idiom, mirroring test_deploy_guide_documents_persistent_data"]
key-files:
  created:
    - RELEASING.md
  modified:
    - tests/test_ci_docker_config.py
    - README.md
    - DEPLOY-PI.md
decisions:
  - "RELEASING.md documents all three blocking manual prerequisites (Docker Hub repo, two GitHub secrets, workflow write permissions) plus the branch-protection open risk, by exact literal name, per D-04/D-07"
  - "VERSION seeded at 1.0.0 per D-09; configure.ac's 0.7.0 explicitly stated as unsynced legacy (D-08)"
  - "Both disclosed deviations from the reference algorithm (CI commits/tags VERSION; atomic multi-tag buildx push vs. independent per-tag docker push) written into RELEASING.md verbatim per the plan's required wording"
metrics:
  duration: "~35 min (Tasks 1-2) + human checkpoint resolved same day"
  completed: "2026-09-23 (all 3 tasks complete)"
---

# Phase 9 Plan 3: Document the release pipeline and cross-reference it Summary

Wrote `RELEASING.md` (one-time setup, release mechanics, commit-message bump rules, local
dry-run instructions, both disclosed algorithm deviations, and a troubleshooting table), added
a pytest config-assertion (`test_releasing_doc_documents_manual_setup`) guarding its required
literals, and linked it from both `README.md` (new "Released images" subsection) and
`DEPLOY-PI.md` (published-image note in section 6). Task 3, the human-verify checkpoint for a
real end-to-end publish run, has **not** been executed — it requires live Docker Hub
credentials and GitHub repo-settings access that cannot be exercised from this sandboxed
worktree.

## What Was Done

### Task 1: RELEASING.md + config-assertion test

Created `RELEASING.md` at the repo root (122 lines) with the sections specified by the plan:

- **One-time setup (manual, cannot be automated)** — numbered checklist: create Docker Hub
  repository `peterscholer74/pellmon`; generate a Read & Write Docker Hub access token; add
  GitHub Actions secrets `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`; set repo Settings -> Actions
  -> General -> Workflow permissions to "Read and write permissions"; check Settings -> Branches
  for a protection rule blocking `github-actions[bot]`, with the PAT fallback noted.
- **How a release happens** — describes the actual `publish` job as implemented in
  `.github/workflows/ci.yml` (Plan 02's real step names/action pins, not research placeholders):
  `decide` -> commit+tag -> QEMU/buildx/login/build-push-action -> both image tags. States
  `VERSION` is the sole source of truth and `configure.ac`'s `0.7.0` stays unsynced (D-08);
  states the `1.0.0` seed (D-09).
- **Commit message rules** — table: `BREAKING CHANGE` substring -> major, `feat:`/`feat(scope):`
  line-start -> minor, `fix:`/`fix(scope):` line-start -> patch, else no-op; priority is
  existence-based not chronological.
- **Previewing the next version locally** — `python tools/version_bump.py decide --dry-run` and
  `--dry-run --type minor`.
- **Known deviations from the reference algorithm** — (a) this CI commits/tags `VERSION` itself
  where the reference script left that to the caller (D-04); (b) buildx pushes all tags as one
  atomic manifest operation vs. the reference's two independent fail-fast `docker push` calls
  (D-02 consequence).
- **Troubleshooting** — four failure signatures: 403/protected-branch-hook-declined, Docker Hub
  `insufficient_scope`, duplicate workflow runs (`[skip ci]` not honoured), `VERSION` parse
  `ValueError`.
- **Deploying a published image** — one short paragraph pointing at `DEPLOY-PI.md` section 6,
  no duplicated instructions.

Appended `test_releasing_doc_documents_manual_setup` to `tests/test_ci_docker_config.py`,
following the existing `test_deploy_guide_documents_persistent_data` flat-assertion idiom:
asserts `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `peterscholer74/pellmon`,
`Read and write permissions`, `[skip ci]`, `BREAKING CHANGE`, `tools/version_bump.py`,
`DEPLOY-PI.md`, `branch protection` are all present.

Commit: `e097bab` — `docs(09-03): add RELEASING.md and its config-assertion test`

### Task 2: Cross-references from README.md and DEPLOY-PI.md

- `README.md`: added a "### Released images" subsection under "## Deployment & Installation" /
  "### Docker Compose (Recommended)" stating the published tags, platforms, that `VERSION` is
  the tag source of truth, and linking to `RELEASING.md`.
- `DEPLOY-PI.md`: added a paragraph in section "6. Updating, backups, troubleshooting" explaining
  that a Pi can run the prebuilt `peterscholer74/pellmon:latest` (or pinned `:{version}`) image
  by setting `docker-compose.yml`'s `image:` value, and that `docker compose pull && docker
  compose up -d` is what picks up a new release from that path (distinct from the existing
  build-locally `docker compose build && docker compose up -d` update command, which is
  unchanged). Links to `RELEASING.md`. Section 5's build-locally instructions were left
  untouched; both paths remain valid. `docker-compose.yml` itself was not modified.

Commit: `79f5a8e` — `docs(09-03): cross-reference RELEASING.md and the published image`

### Task 3: EXECUTED by the human operator — checkpoint resolved

The operator completed RELEASING.md's One-time setup checklist (Docker Hub repository
`peterscholer74/pellmon` created, `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` secrets added via
`gh secret set`, workflow permissions set to "Read and write" via `gh api
repos/.../actions/permissions/workflow`, branch protection confirmed absent via `gh api
repos/.../branches/master/protection` returning 404).

**Discovery during verification (process gap, not a pipeline bug):** the operator's first
verification push landed on local `master`, which at that point still lacked the `publish` job
entirely — all of Plan 09-01/09-02/09-03's work had been executed on git branch
`feat/phase-8-burner-svg` and never merged to `master`. Opened
[PR #16](https://github.com/zorge2411/PellMon/pull/16) (`feat/phase-8-burner-svg` -> `master`),
CI passed (`test` job green, `publish` job correctly shown as `skipping` — its
`if: github.event_name == 'push' && github.ref == 'refs/heads/master'` guard is exactly right
for a `pull_request` event), operator merged it.

The merge commit (`caea242`, a push to `master`) triggered the real `publish` job:
- `Decide version bump` -> `bump=major`, `version=2.0.0`. Investigated: triggered by commit
  `e4526fa` (`test(09-01): add failing pytest suite for version_bump bump algorithm`), whose
  message body contains the literal substring `"BREAKING CHANGE > feat > fix > none"` — the
  Wave 1 executor describing the algorithm's own priority order in prose. The unanchored
  substring match (ported verbatim from the reference algorithm, and explicitly documented in
  RELEASING.md and 09-CONTEXT.md as a known false-positive shape, e.g. `"see BREAKING CHANGE
  below"`) correctly matched it per spec. Not a bug; an unlucky first real trigger.
- `Commit and tag version bump` -> committed `VERSION=2.0.0`, pushed `chore: bump version to
  2.0.0 [skip ci]` and annotated tag `v2.0.0` to `master`. Verified via `gh run list` that this
  commit did NOT trigger a second workflow run (`[skip ci]` guard confirmed working).
- QEMU/buildx/login/build-push -> `peterscholer74/pellmon:latest` and `:2.0.0` pushed. Verified
  via `docker buildx imagetools inspect` on both tags: both list `Platform: linux/amd64` and
  `Platform: linux/arm64` manifests.

Also discovered: the repo already had a pre-existing lightweight tag `v1.0.0` (from an unrelated
September 21 merge, predating this phase's research, which had incorrectly assumed zero tags
existed). `git describe --tags --abbrev=0` correctly found it as the base for the commit-range
scan — the "first-run bootstrap" concern RESEARCH.md flagged did not actually apply; the
existing-tag code path was exercised instead, and worked correctly.

**Resume signal received:** operator confirmed the live run via Docker Hub/GitHub verification
(not a bare "approved" — verified directly with `gh` and `docker buildx imagetools inspect`
against the actual published artifacts).

## Verification

```
python -m pytest tests/test_ci_docker_config.py -v   # 17 passed
```

Full `tests/ -v` run in this Windows dev venv shows 8 pre-existing collection errors and 7
pre-existing failures, all caused by missing Linux-only packages in this environment
(`cherrypy`, `Crypto`/pycryptodome, D-Bus-dependent modules) — none touch
`test_ci_docker_config.py`, `RELEASING.md`, `README.md`, or `DEPLOY-PI.md`, and none are new
regressions introduced by this plan's changes. Per `CLAUDE.md`, Windows is a syntax-only dev
environment; the full-feature verification environment is the WSL venv, which was not available
in this sandboxed worktree run.

## Deviations from Plan

None in Tasks 1-2. Task 3 surfaced one out-of-plan process gap (the executed branch was never
merged to `master`, so the first verification attempt correctly showed no `publish` job) —
resolved by opening and merging PR #16 rather than force-pushing directly to `master`, keeping
a reviewable record. Not a deviation in the plan's own deliverables, but worth flagging per
`/gsd:plan-phase --gaps` guidance for future phases: a phase's branching strategy should confirm
before Wave 3 whether the working branch is expected to reach `master` before or as part of the
human-verify checkpoint.

## Self-Check

- FOUND: RELEASING.md (122 lines, >= 60 required)
- FOUND: tests/test_ci_docker_config.py::test_releasing_doc_documents_manual_setup (passing)
- FOUND: commit e097bab (docs(09-03): add RELEASING.md and its config-assertion test)
- FOUND: commit 79f5a8e (docs(09-03): cross-reference RELEASING.md and the published image)
- FOUND: README.md contains "RELEASING.md" (1 occurrence) and "peterscholer74/pellmon" (1 occurrence)
- FOUND: DEPLOY-PI.md contains "RELEASING.md" (1 occurrence) and "peterscholer74/pellmon" (2 occurrences)

## Self-Check: PASSED

## Known Stubs

None — this plan is documentation-only plus one test assertion; no code paths were stubbed.

## Threat Flags

None — this plan introduces no new network endpoints, auth paths, file access patterns, or
schema changes. It documents (but does not implement) the credential-handling steps that Plan
02 already built and threat-modeled (T-09-08, T-09-09, T-09-10 in 09-02/09-03's threat register).
