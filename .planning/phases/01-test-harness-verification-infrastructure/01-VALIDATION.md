---
phase: 1
slug: test-harness-verification-infrastructure
status: aligned-to-plans
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-17
updated: 2026-09-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Updated 2026-09-17 during planning to match the actual 3-plan / 2-wave breakdown.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (`>=9.0,<10`), plus pytest-mock `>=3.15`, pytest-socket `>=0.8`, pytest-cov `>=7.1` — pinned in `requirements-dev.txt` |
| **Interpreter** | `venv-py3/Scripts/python.exe` — the ONLY interpreter in this checkout with both `cherrypy` and `pyserial`. The bare `C:\Python314\python.exe` has pytest but no cherrypy, so `Pellmonweb.auth` fails to import there. |
| **Config file** | `pytest.ini` (repo root — created by plan 01-01, does not exist yet) |
| **Green baseline command** | `venv-py3/Scripts/python.exe -m pytest tests/ -m "not known_broken" -q` |
| **Full-truth command** | `venv-py3/Scripts/python.exe -m pytest tests/ -v` (exits nonzero by design — see Expected Red Baseline) |
| **Quick per-commit loop** | `venv-py3/Scripts/python.exe -m pytest tests/ -x -q -m "not known_broken"` |
| **Estimated runtime** | ~10-20 seconds (no hardware I/O, all mocked) |

---

## Sampling Rate

- **After every task commit:** green baseline command with `-x` (fast fail on first error)
- **After every plan wave:** full-truth command, then confirm failures match the Expected Red Baseline exactly
- **Before `/gsd:verify-work`:** green baseline must be 100% green; full-truth run must show exactly 2 failures, both listed below
- **Max feedback latency:** 20 seconds

---

## Expected Red Baseline (by design, not a defect)

These two cases MUST fail at the end of Phase 1. Their failure is how ROADMAP Phase 1 success criterion 2 is satisfied — the import-check is working *because* it fails. They are filtered out of the green gate by the `known_broken` marker, never by `xfail`/`skip`/deletion.

| Failing case | Error | Owner |
|--------------|-------|-------|
| `tests/test_plugin_imports.py::test_plugin_module_imports[scottecom]` | `ModuleNotFoundError: No module named 'protocol'` | IMPORT-01, Phase 3 |
| `tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import` | `ModuleNotFoundError: No module named 'frames'` | IMPORT-02, Phase 3 |

Platform skips (expected on Windows, genuinely import-checked on the Phase 5 Linux CI runner): `calculate`, `consumption`, `customalarms`, `pelletcalc`, `silolevel`, and the `Pellmonsrv.pellmonsrv` core case all skip on missing Unix-only `grp`; `raspberrygpio` skips on missing `RPi`.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | TEST-01 | — | N/A | infra | `venv-py3/Scripts/python.exe -m pytest --version` + dep/spike import check | ⬜ created by task | ⬜ pending |
| 01-01-02 | 01 | 1 | TEST-01 | — | N/A | infra | `venv-py3/Scripts/python.exe -m pytest --collect-only -q` + `--fixtures` grep | ⬜ created by task | ⬜ pending |
| 01-01-03 | 01 | 1 | TEST-01 | — | N/A | unit | `pytest tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py -v` | ⬜ created by task | ⬜ pending |
| 01-02-01 | 02 | 2 | TEST-03 | — | N/A | unit | `pytest tests/Pellmonsrv/test_database.py -v` | ⬜ created by task | ⬜ pending |
| 01-02-02 | 02 | 2 | TEST-03 | — | ASVS V7: assert return values only, never `cherrypy.log` content (would codify SEC-01) | unit | `pytest tests/Pellmonweb/test_auth.py -v` | ⬜ created by task | ⬜ pending |
| 01-03-01 | 03 | 2 | TEST-02 | — | N/A | unit | `pytest tests/test_plugin_imports.py -m "not known_broken" -v` (green) + `-m "known_broken"` (must exit nonzero with 2 failures) | ⬜ created by task | ⬜ pending |
| 01-03-02 | 03 | 2 | TEST-01 | — | Blocks stray real network I/O toward a live burner on the LAN | enforcement | `pytest tests/test_socket_guardrail.py -v`; non-vacuity: same file with `--force-enable-socket` must exit nonzero | ⬜ created by task | ⬜ pending |
| 01-03-03 | 03 | 2 | TEST-02 | — | N/A | doc | `test -f tests/README.md && grep -q 'known_broken' tests/README.md && ... && echo README_OK` | ⬜ created by task | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Note: this phase has no threat model (test infrastructure only, no security-relevant runtime behavior), so Threat Ref is N/A throughout. Two tasks carry security-relevant *constraints* rather than threats, noted in the Secure Behavior column.*

---

## Wave Structure

**Wave 1 — plan 01-01 (the former "Wave 0"):** installs the entire baseline before any other test-writing task runs.
- [ ] `requirements-dev.txt` — pytest, pytest-mock, pytest-socket, pytest-cov pinned; installed into `venv-py3`
- [ ] Environment spike (RESEARCH.md Open Question 1) — confirm `Pellmonsrv.database`, `Pellmonsrv.plugins.testplugin`, `Pellmonweb.auth` all import with no generated `directories.py`. **Already verified by the planner; the task re-confirms it in the executor's environment.**
- [ ] `pytest.ini` — `pythonpath = src`, `testpaths = tests`, `addopts = --disable-socket`, `markers = known_broken: ...`
- [ ] `tests/` skeleton mirroring `src/` (`tests/Pellmonsrv/`, `tests/Pellmonsrv/plugins/`, `tests/Pellmonweb/`), no `__init__.py` files
- [ ] `tests/conftest.py` — `loop_serial`, `mocked_udp_socket`, `cherrypy_request_ctx`
- [ ] `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py`

**Wave 2 — plans 01-02 and 01-03 run in parallel** (zero `files_modified` overlap; both depend only on 01-01).

---

## Manual-Only Verifications

*None — all phase behaviors (mocked protocol round-trips, import-check, database/auth coverage, socket-block enforcement) have automated pytest verification. This phase deliberately avoids anything requiring physical hardware or manual steps.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 1 baseline dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 1 covers all MISSING references (the pytest framework itself, which did not exist in this repo)
- [x] No watch-mode flags
- [x] Feedback latency < 20s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** aligned to plans 01-01 / 01-02 / 01-03 on 2026-09-17
