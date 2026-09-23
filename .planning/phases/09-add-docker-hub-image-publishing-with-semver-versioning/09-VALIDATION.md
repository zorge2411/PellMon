---
phase: 09
slug: add-docker-hub-image-publishing-with-semver-versioning
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-23
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (already declared in `ci.yml`: `pytest pytest-mock pytest-socket`) |
| **Config file** | none — pytest runs via `pytest tests/ -v` directly, matching `ci.yml` |
| **Quick run command** | `pytest tests/test_version_bump.py -v` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~2 seconds (quick) / matches existing full-suite runtime (no new I/O-bound tests) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_version_bump.py -v`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds
- **Phase gate (manual, not pytest-covered):** the git write-back and Docker Hub push steps
  cannot be meaningfully unit-tested — a real end-to-end workflow run (a `feat:`/`fix:` test
  commit, ideally on a throwaway branch first) should be manually verified at least once after
  the Docker Hub repo + secrets + workflow permissions are set up.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 0 | D-03/D-06 | — | `decide_bump()` BREAKING CHANGE > feat > fix > none priority | unit | `pytest tests/test_version_bump.py::test_breaking_change_wins_priority_over_feat_and_fix -x` | ❌ W0 | ⬜ pending |
| 09-01-02 | 01 | 0 | D-03 | — | `feat`/`fix` must anchor at line start, not mid-sentence | unit | `pytest tests/test_version_bump.py::test_feat_must_be_at_line_start -x` | ❌ W0 | ⬜ pending |
| 09-01-03 | 01 | 0 | D-06 | — | `decide_bump()` importable/callable with no git/Docker present | unit | `pytest tests/test_version_bump.py -v` | ❌ W0 | ⬜ pending |
| 09-02-01 | 02 | 1 | D-04 | T-09-01 | publish workflow sets `contents: write`, `[skip ci]` marker, `fetch-depth: 0` | config-assertion | `pytest tests/test_ci_docker_config.py::test_publish_workflow_permissions_and_skip_ci -x` | ❌ W0 | ⬜ pending |
| 09-02-02 | 02 | 1 | D-01/D-02 | T-09-02 | workflow references `peterscholer74/pellmon`, `linux/amd64,linux/arm64`, both `:latest` and version tags | config-assertion | `pytest tests/test_ci_docker_config.py::test_publish_workflow_multiarch_and_tags -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_version_bump.py` — stubs for D-03, D-06 (`decide_bump()` priority order, line-anchoring, pure-function isolation)
- [ ] New assertions in `tests/test_ci_docker_config.py` (or sibling file) for the publish workflow's permissions/skip-ci/multi-arch/tag content — covers D-01, D-02, D-04
- [ ] `VERSION` file (does not exist yet) — seeded at `1.0.0` per D-09
- [ ] `tools/version_bump.py` — the deliverable itself, not a gap

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| CI commits VERSION bump + tag back to `master` and pushes successfully | D-04 | Needs live GitHub Actions run with real `contents: write` permission and no branch-protection block — cannot be simulated in pytest | Push a `feat:`/`fix:` commit (ideally to a throwaway branch first, or to `master` once secrets/permissions are configured) and confirm the workflow run: bumps VERSION, commits `chore: bump version to X.Y.Z [skip ci]`, creates+pushes tag `vX.Y.Z`, does not re-trigger itself |
| Multi-arch image pushes to Docker Hub and both `:latest`/`:{version}` tags are pullable on amd64 and arm64 | D-01, D-02, D-04 | Needs real Docker Hub credentials and registry push — cannot be simulated in pytest | After a successful publish run, `docker pull peterscholer74/pellmon:latest` and `:{version}` on both an amd64 host and a Raspberry Pi (or `docker buildx imagetools inspect peterscholer74/pellmon:latest` to confirm both platform manifests exist) |
| No-op behavior: a commit with no `feat:`/`fix:`/`BREAKING CHANGE` produces no VERSION change, no tag, no Docker push | D-03 | End-to-end trigger behavior on the real workflow, not just the pure function | Push a `docs:`/`chore:`-only commit to `master` and confirm the publish job exits cleanly with no commit/tag/push |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
