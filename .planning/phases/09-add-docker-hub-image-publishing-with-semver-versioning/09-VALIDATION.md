---
phase: 9
slug: add-docker-hub-image-publishing-with-semver-versioning
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-09-22
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing `venv-wsl` + system-python3 setup; CI/YAML assertions use plain substring/regex on raw file text, no yaml parser dependency, per `tests/test_ci_docker_config.py`) |
| **Config file** | `pytest.ini` (existing — no new framework install needed) |
| **Quick run command** | `PYTHONPATH=src:venv-wsl/lib/python3.13/site-packages python3 -m pytest tests/test_version_source.py tests/test_version_bump.py tests/test_publish_workflow.py -q -p no:cacheprovider` |
| **Full suite command** | `wsl -d Debian -- bash -lc 'cd /mnt/d/Antigravity/PellMon-master && venv-wsl/bin/python -m pytest tests -q'` |
| **Estimated runtime** | ~9 seconds (quick), full suite matches Phase 8's baseline runtime (~389 tests) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command above (scoped to this phase's new test files)
- **After every plan wave:** Run the full suite command
- **Before `/gsd:verify-work`:** Full suite must be green (no new failures vs. Phase 8's closing baseline: 389 passed, 15 skipped)
- **Max feedback latency:** 9 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|--------------------|-------------|--------|
| 09-01-01 | 01 | 1 | D-02 | — | `configure.ac` reads version from `VERSION` via `m4_esyscmd_s`, no drift possible | unit | `pytest tests/test_version_source.py::test_configure_ac_reads_version_file -q` | ✅ | ⬜ pending |
| 09-01-02 | 01 | 1 | D-02, D-05 | — | Image build fails loudly if `@VERSION@` substitution yields empty; local `docker compose build` path unbroken | build+unit | `pytest tests/test_version_source.py::test_dockerfile_substitutes_version -q` | ✅ | ⬜ pending |
| 09-01-03 | 01 | 1 | D-02 | — | Reconciled version `1.1.0` never regresses below shipped tag `v1.0.0` | unit | `pytest tests/test_version_source.py::test_version_not_regressed_below_shipped_tag -q` | ✅ | ⬜ pending |
| 09-02-01 | 02 | 2 | D-03 | T-09-CredExposure (N/A here) | `bump-version.sh` follows Conventional Commits priority order (BREAKING CHANGE > feat > fix > no-op) and never runs `git add/commit/tag/push` itself | unit | `pytest tests/test_version_bump.py -q` | ✅ | ⬜ pending |
| 09-02-02 | 02 | 2 | D-03 | — | Multi-line commit body (`%B`) handled correctly; a `feat:` in a body line still bumps minor | unit | `pytest tests/test_version_bump.py::test_multiline_commit_body -q` | ✅ | ⬜ pending |
| 09-03-01 | 03 | 2 | D-01, D-04 | T-09-Trigger, T-09-SupplyChain | Workflow triggers only on `v*.*.*` tag push; all actions pinned to `@vN`, no `@main`/`@master`/`@latest` | unit (text assertions on raw YAML) | `pytest tests/test_publish_workflow.py::test_publish_triggers_on_tags_only tests/test_publish_workflow.py::test_actions_are_pinned -q` | ✅ | ⬜ pending |
| 09-03-02 | 03 | 2 | D-01, D-04 | T-09-CredExposure | Multi-arch build (`linux/amd64,linux/arm/v7`); PAT only in `docker/login-action`'s `password:` input, never on a `run:` line; tag-vs-VERSION guard runs before login | unit | `pytest tests/test_publish_workflow.py::test_credentials_come_only_from_secrets tests/test_publish_workflow.py::test_tag_matches_version_guard_precedes_login -q` | ✅ | ⬜ pending |
| 09-04-01 | 04 | 3 | D-01, D-05 | — | `DOCKER.md`/`DEPLOY-PI.md` document the Docker Hub image, the bump script, and that local build stays unchanged; existing compose/deploy assertions still pass | unit | `pytest tests/test_ci_docker_config.py -q` | ✅ | ⬜ pending |
| 09-04-02 | 04 | 3 | D-01 | T-09-CredExposure | **Manual** — Docker Hub repo created, PAT minted (Read & Write), `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` added as GitHub Actions secrets | manual | N/A — `checkpoint:human-action` | N/A | ⬜ pending |
| 09-04-03 | 04 | 3 | D-01, D-02, D-03 | — | **Manual** — first real `v1.1.0` tag cut and pushed; CI run inspected end-to-end; job log scanned for zero PAT hits; image confirmed live on Docker Hub | manual | N/A — `checkpoint:human-verify` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements — `pytest.ini`, `venv-wsl`, and the system-python3 fallback for dbus/gi-adjacent tests are already in place from prior phases. No new framework install needed. New test files (`tests/test_version_source.py`, `tests/test_version_bump.py`, `tests/test_publish_workflow.py`) are created by the plans themselves as part of each task, not as a separate Wave 0 step.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| Docker Hub repo + PAT + GitHub secrets setup | D-01 | Requires an external Docker Hub account action and a GitHub repo settings change; no executor credential access | Create `peterscholer74/pellmon` on Docker Hub, mint a Read & Write PAT, add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` as GitHub Actions repository secrets |
| First real `v1.1.0` release, end-to-end | D-01, D-02, D-03 | Pushing a real tag triggers billed CI minutes and a real Docker Hub push; must not be automated by an agent | Bump `VERSION` via `scripts/bump-version.sh`, commit, `git tag v1.1.0 -a -m "Release 1.1.0"`, `git push --tags`, watch the Actions run, grep the job log for the literal string `dckr_pat_` (expect zero matches), confirm `peterscholer74/pellmon:latest` and `:1.1.0` exist on Docker Hub |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the two `checkpoint:human-*` tasks are the documented exception, per gates.md)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (only the two manual checkpoint tasks lack one, and they are adjacent by necessity — both in wave 3, both requiring the same live Docker Hub/GitHub secrets setup)
- [x] Wave 0 covers all MISSING references (none missing — existing infra reused)
- [x] No watch-mode flags
- [x] Feedback latency < 9s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-09-22
