---
phase: 5
slug: security-ci-deployment-hardening
status: draft
nyquist_compliant: true
created: 2026-09-18
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9.0,<10` |
| **Config file** | `pytest.ini` |
| **Interpreter** | `venv-py3/Scripts/python.exe` |
| **Full suite command** | `venv-py3/Scripts/python.exe -m pytest tests/ -v` |
| **Auth security test** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonweb/test_auth.py tests/Pellmonweb/test_auth_security.py -v` |
| **Exec security test** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_exec_security.py -v` |
| **Signal handling test** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_sigterm_handling.py -v` |
| **CI & Docker config test** | `venv-py3/Scripts/python.exe -m pytest tests/test_ci_docker_config.py -v` |
| **Requirements check** | `venv-py3/Scripts/python.exe -c "lines = [l.strip() for l in open('requirements.txt') if l.strip() and not l.startswith('#')]; assert all('==' in l for l in lines), 'Unpinned dependency found'"` |
| **py2bak check** | `venv-py3/Scripts/python.exe -c "import glob; assert len(glob.glob('src/**/*.py2bak', recursive=True)) == 0, 'Found remaining .py2bak files'"` |

---

## Success Criteria Mapping

| Criterion | Requirement | Test / Verification Command |
|-----------|-------------|-----------------------------|
| 1. Failed web login doesn't log passwords; credentials hashed with migration path | SEC-01, SEC-02 | `pytest tests/Pellmonweb/test_auth_security.py -v` |
| 2. Exec plugin readscript uses `shell=False` | SEC-03 | `pytest tests/Pellmonsrv/plugins/test_exec_security.py -v` |
| 3. GitHub Actions CI pipeline runs pytest & import check | OPS-01 | `pytest tests/test_ci_docker_config.py -k test_github_actions_workflow -v` |
| 4. SIGTERM handling closes resources & healthcheck defined in compose/docker | OPS-02, OPS-03 | `pytest tests/Pellmonsrv/test_sigterm_handling.py tests/test_ci_docker_config.py -k test_docker_healthchecks -v` |
| 5. Requirements pinned, .py2bak removed, Linux-only docs | OPS-04, OPS-05, OPS-06 | Verification commands above + documentation inspection |

---

## Validation Sign-Off

- [x] Automated commands defined for every success criterion
- [x] Password logging and hashing verified by unit tests
- [x] Command injection risk mitigated in Exec plugin
- [x] CI workflow validated against schema/triggers
- [x] Process shutdown resilience tested
- [x] All backup files purged and requirements pinned
