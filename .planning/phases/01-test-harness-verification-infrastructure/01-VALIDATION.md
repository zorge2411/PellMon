---
phase: 1
slug: test-harness-verification-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.1.1 (already installed at 9.0.2; pin bumps as part of this phase), plus pytest-mock 3.15.1, pytest-socket 0.8.1, pytest-cov 7.1.0 |
| **Config file** | `pytest.ini` (repo root — created by this phase, does not exist yet) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~10-20 seconds (no hardware I/O, all mocked) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q` (fast fail on first error)
- **After every plan wave:** Run `pytest tests/ -v` (full suite)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | TEST-01 | — | N/A | infra | `test -f pytest.ini && test -f requirements-dev.txt` | ✅ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | TEST-02 | — | N/A | unit | `pytest tests/test_plugin_imports.py -v` | ✅ | ⬜ pending |
| 01-01-03 | 01 | 1 | TEST-01 | — | N/A | unit | `pytest tests/test_scotteprotocol_mock.py -v` | ✅ | ⬜ pending |
| 01-01-04 | 01 | 1 | TEST-01 | — | N/A | unit | `pytest tests/test_nbeprotocol_mock.py -v` | ✅ | ⬜ pending |
| 01-01-05 | 01 | 1 | TEST-03 | — | N/A | unit | `pytest tests/Pellmonsrv/test_database.py -v` | ✅ | ⬜ pending |
| 01-01-06 | 01 | 1 | TEST-03 | — | N/A | unit | `pytest tests/Pellmonweb/test_auth.py -v` | ✅ | ⬜ pending |
| 01-01-07 | 01 | 2 | TEST-01 | — | N/A | unit | `pytest --disable-socket tests/ -k "socket" -v` (expect failure on any real-socket test = pass condition for the enforcement check itself) | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: this phase has no threat model (no security-relevant runtime behavior — it's test infrastructure only), so Threat Ref / Secure Behavior columns are N/A throughout.*

---

## Wave 0 Requirements

- [ ] `requirements-dev.txt` — pytest, pytest-mock, pytest-socket, pytest-cov pinned
- [ ] `pytest.ini` — `addopts = --disable-socket`, test paths, markers
- [ ] `tests/` directory skeleton mirroring `src/` (`tests/Pellmonsrv/`, `tests/Pellmonweb/`, `tests/Pellmonsrv/plugins/`)
- [ ] `tests/conftest.py` — shared fixtures (mocked serial via `loop://`, mocked UDP socket)

No pre-existing test framework in this repo — Wave 0 installs the entire baseline before any test-writing tasks run.

---

## Manual-Only Verifications

*None — all phase behaviors (mocked protocol round-trips, import-check, database/auth coverage, socket-block enforcement) have automated pytest verification. This phase deliberately avoids anything requiring physical hardware or manual steps.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (pytest framework itself)
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
