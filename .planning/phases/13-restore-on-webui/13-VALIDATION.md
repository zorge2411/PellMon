---
phase: 13
slug: restore-on-webui
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-11-06
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. No REQUIREMENTS.md IDs exist for this
> phase; the RESEARCH.md decisions D-01..D-16 stand in for requirement IDs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-mock, pytest-socket) |
| **Config file** | `tests/conftest.py`, `tests/Pellmonsrv/conftest.py` (no pytest.ini) |
| **Quick run command** | `python -m pytest tests/Pellmonsrv/test_backup_restore.py tests/Pellmonsrv/test_backup_core.py tests/Pellmonsrv/test_backup_dbus.py tests/Pellmonsrv/test_db_copy.py tests/Pellmonsrv/plugins/test_backup_restore_plugin.py tests/Pellmonweb/test_backup_page.py tests/Pellmonweb/test_backup_js.py tests/test_backup_script.py tests/test_backup_compose.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` (CI also `pytest tests/browser -v -rs --allow-unix-socket`) |
| **Estimated runtime** | ~30 seconds quick, ~120 seconds full |

Fake `rrdtool` shell scripts (POSIX) stand in for the binary in the dev container; the real-rrdtool round trip runs in CI and on the Pi.

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run `python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green, plus the Pi UAT (plan 13-06 Task 2)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | D-03, D-04, D-07, D-12 | T-13-01..05 | Only listed regular archives accepted; malicious tar rejected identically to the host tool; preview whitelisted | unit | `python -m pytest tests/Pellmonsrv/test_backup_restore.py -x -q -k "name or extract or validate or preview"` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | D-05, D-06 | T-13-06 | Staging 0700 in data dir, leftovers removed, low space refused | unit | `python -m pytest tests/Pellmonsrv/test_backup_restore.py -x -q -k staging` | ❌ W0 | ⬜ pending |
| 13-02-01 | 02 | 2 | D-07 | T-13-07, T-13-08 | rrdtool restore staged with timeout; layout/future checks | unit (fake rrdtool) | `python -m pytest tests/Pellmonsrv/test_backup_restore.py -x -q -k "validate or carry"` | ❌ W0 | ⬜ pending |
| 13-02-02 | 02 | 2 | D-01, D-08, D-09, D-11, D-12 | T-13-09..11 | Swap under locks, .pre-restore 0600, rollback, live files untouched on any failure, safe result file | unit + integration (real rrdtool in CI) | `python -m pytest tests/Pellmonsrv/test_backup_restore.py -x -q -k "swap or rollback or result or validate or roundtrip"` | ❌ W0 | ⬜ pending |
| 13-03-01 | 03 | 1 | D-09, D-10 | T-13-13, T-13-14 | No store copy after restore_done; Poller update and copy_db hold restore_lock | unit | `python -m pytest tests/Pellmonsrv/test_db_copy.py -x -q -k restore` | ✅ extend | ⬜ pending |
| 13-03-02 | 03 | 1 | D-15 | T-13-16, T-13-17 | D-Bus restore methods delegate, never leak exception text | unit | `python -m pytest tests/Pellmonsrv/test_backup_dbus.py -x -q` | ✅ extend | ⬜ pending |
| 13-04-01 | 04 | 3 | D-01, D-03, D-09, D-10, D-11 | T-13-18..21, T-13-23 | Single-flight worker, backups blocked, swap locks, SIGTERM only after success in Docker | unit | `python -m pytest tests/Pellmonsrv/plugins/test_backup_restore_plugin.py -x -q` | ❌ W0 | ⬜ pending |
| 13-04-02 | 04 | 3 | D-05, D-12 | T-13-22 | Result survives restart until acked, leftovers cleaned at start, all archives listed | unit | `python -m pytest tests/Pellmonsrv/plugins/test_backup_restore_plugin.py tests/Pellmonsrv/plugins/test_backup_plugin.py -x -q` | ❌ W0 / ✅ extend | ⬜ pending |
| 13-05-01 | 05 | 3 | D-03, D-13, D-15 | T-13-24..27, T-13-29 | Login + same-origin POST + typed RESTORE; GET has no side effects; fixed reasons only | unit | `python -m pytest tests/Pellmonweb/test_backup_page.py -x -q -k "restore or run or auth"` | ✅ extend | ⬜ pending |
| 13-05-02 | 05 | 3 | D-02, D-14, D-16 | T-13-28 | Escaped template values, url-escaped links, textContent-only polling script | unit (source scan + template render) | `python -m pytest tests/Pellmonweb/test_backup_page.py tests/Pellmonweb/test_backup_js.py tests/Pellmonweb/test_source_js_no_html_sink.py -x -q` | ❌ W0 (test_backup_js.py) | ⬜ pending |
| 13-06-01 | 06 | 4 | D-11, D-12, D-16 | T-13-30, T-13-31 | Every failure reason documented; rollback steps stop the daemon first | unit (doc test) | `python -m pytest tests/test_backup_compose.py -x -q` | ✅ extend | ⬜ pending |
| 13-06-02 | 06 | 4 | D-10 (A1), A3 | T-13-23 | Real restore on the Pi, container restarts | manual | see Manual-Only Verifications | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/Pellmonsrv/test_backup_restore.py` — created by 13-01 Task 1 (tool parity loader, `_tar_with`), extended by 13-01 Task 2 and 13-02 (fake rrdtool implementing `restore`, `info`, `last`, `dump`, `--version`)
- [ ] `tests/Pellmonsrv/plugins/test_backup_restore_plugin.py` — created by 13-04 Task 1
- [ ] `tests/Pellmonweb/test_backup_js.py` — created by 13-05 Task 2
- [ ] Extend `tests/Pellmonsrv/test_db_copy.py`, `tests/Pellmonsrv/test_backup_dbus.py` (FakePlugin restore methods), `tests/Pellmonweb/test_backup_page.py` (FakeDbus/FakeLookup restore support), `tests/test_backup_compose.py`

Each test file is created by the first task that needs it (tdd="true" tasks write the tests before the code), so no separate scaffold plan is needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Container restarts after the daemon SIGTERMs itself | D-10 (assumption A1) | Docker restart policy cannot run in the dev container | 13-06 Task 2 steps 5-6 |
| rrdtool restore of a real multi-month dump finishes within RRD_RESTORE_TIMEOUT on the Pi | D-07 (assumption A3) | ARM rrdtool timing and memory | 13-06 Task 2 step 5 (note the rebuild time) |
| Real NAS archive restore, graphs show restored data, .pre-restore files 0600, no leftovers | D-08, D-05 | Needs NAS mount, uid 999, real data | 13-06 Task 2 steps 7-8 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
