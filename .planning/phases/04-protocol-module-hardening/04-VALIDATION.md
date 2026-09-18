---
phase: 4
slug: protocol-module-hardening
status: draft
nyquist_compliant: true
created: 2026-09-18
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest `>=9.0,<10` |
| **Config file** | `pytest.ini` |
| **Interpreter** | `venv-py3/Scripts/python.exe` |
| **Full suite command** | `venv-py3/Scripts/python.exe -m pytest tests/ -v` |
| **NBE round-trip test** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py -v` |
| **Scotte round-trip test** | `venv-py3/Scripts/python.exe -m pytest tests/test_scotte_protocol_roundtrip.py -v` |
| **Calculate & Daemon test** | `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_calculate_hardening.py tests/Pellmonsrv/test_daemon_hardening.py -v` |

---

## Success Criteria Mapping

| Criterion | Requirement | Test / Verification Command |
|-----------|-------------|-----------------------------|
| 1. NBE `Proxy.get()` splits correctly without `TypeError` | PROTO-01 | `pytest tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py -k test_proxy_get` |
| 2. Calculate `setItem` has no `unicode()` `NameError` | PROTO-02 | `pytest tests/Pellmonsrv/plugins/test_calculate_hardening.py -k test_calculate_setitem` |
| 3. Daemon stderr buffering allows daemonization | PROTO-03 | `pytest tests/Pellmonsrv/test_daemon_hardening.py -k test_daemon_stderr_buffering` |
| 4. Injectable transports & round-trip tests | PROTO-04 | `pytest tests/test_scotte_protocol_roundtrip.py tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py -v` |
| 5. Calculate imports on Linux without `maketrans` error | PROTO-05 | `pytest tests/Pellmonsrv/plugins/test_calculate_hardening.py -k test_calculate_no_maketrans` |

---

## Validation Sign-Off

- [x] Automated commands defined for every success criterion
- [x] Hardware-free round-trip testing using `loop://` and mock UDP
- [x] No `TypeError`, `NameError`, or `ValueError` on hardened paths
