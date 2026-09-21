---
phase: 7
slug: persist-rrd-database-and-other-relevant-settings-outside-the
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-09-21
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from the "Validation Architecture" section of `07-RESEARCH.md`. The planner maps each task to a row below.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing `tests/`, `conftest.py`, `pytest.ini`) |
| **Config file** | `pytest.ini` (existing; `pythonpath = src`) |
| **Quick run command** | `python -m pytest tests/test_ci_docker_config.py tests/test_data_persistence.py -q` |
| **Full suite command** | `python -m pytest tests -q` (WSL Debian: `venv-wsl/bin/python -m pytest tests -q`) |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd:verify-work`:** Full suite must be green, plus the manual smoke test on Linux below
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Decision | Plan/Task | Behavior | Test Type | Automated Command | File Exists | Status |
|----------|-----------|----------|-----------|-------------------|-------------|--------|
| D-01/02/03/04 | 07-01 T1/T2 | Bind mounts use `${PELLMON_DATA_DIR:-./pellmon-data}`; `pellmonsrv` writable, `pellmonweb` data `:ro`; `pellmon-run` stays a named volume; no `pellmon-data`/`pellmon-logs` named volumes | text check on service blocks | `pytest tests/test_ci_docker_config.py -q` | extend | ⬜ pending |
| D-05 | 07-01 T1/T2 | `.gitignore` and `.dockerignore` contain `pellmon-data`; `.env.example` documents `PELLMON_DATA_DIR` | text | `pytest tests/test_ci_docker_config.py -q` | extend | ⬜ pending |
| D-06 | 07-01 T1/T2 | Init service: `user: root`, `restart: "no"`, chown 999:999, `pellmonsrv` depends on `service_completed_successfully`; `docker compose config -q` parses | text + `docker compose config -q` (skipped if `docker` absent) | `pytest tests/test_ci_docker_config.py -q` | Wave 0 | ⬜ pending |
| D-07 | 07-02 T1/T2 | Startup data-folder check fails loudly (exit 1 with message) on unwritable/missing/unreadable RRD when required; warning only otherwise; settings DB path derives from the RRD path when polling is off | unit, `tmp_path` | `pytest tests/Pellmonsrv/test_data_dir_check.py -q` | Wave 0 | ⬜ pending |
| D-08 | 07-03 T1/T2 | Config editor `save()` on a read-only file returns a friendly message (EROFS/EACCES/EPERM); allowlist and same-origin tests still pass | unit (monkeypatch `codecs.open` to raise `OSError(errno.EROFS)`) | `pytest tests/Pellmonweb -q` | Wave 0 | ⬜ pending |
| D-09 | 07-02 T1/T3 | Settings database file mode is 0600 | unit, `tmp_path` (skip on Windows) | `pytest tests/test_data_persistence.py -q` | Wave 0 | ⬜ pending |
| D-10 | 07-04 T1/T2/T3 | Backup/restore round trip (`--local`): RRD dump and restore, SQLite value survives, archive mode 0600; docker-mode command construction | integration (needs `rrdtool`; skipped if absent) + unit with fake runner | `pytest tests/test_backup_script.py -q` | Wave 0 | ⬜ pending |
| D-11 | 07-05 T1/T2 | `DEPLOY-PI.md` documents `pellmon-data`, backup/restore and the one-time old-volume copy | text | `pytest tests/test_ci_docker_config.py -q` | extend | ⬜ pending |
| D-12 | 07-05 T2 | No backup button/endpoint in the web GUI (deferred); documented as such | text (docs) + absence of changes to `src/Pellmonweb/pellmonweb.py` | `pytest tests/test_ci_docker_config.py -q` | extend | ⬜ pending |
| D-01/06/07/10 | 07-05 T3 | Real `docker compose up` on Linux: init exits 0, 999:999 ownership, 0600 settings DB, survives `down -v`, loud failure, backup/restore cycle | manual (checkpoint) | see "Manual-Only Verifications" below | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_data_persistence.py` — settings DB mode, volume/init-service text checks not covered elsewhere
- [ ] `tests/Pellmonsrv/test_data_dir_check.py` — startup check and settings-path derivation
- [ ] `tests/Pellmonweb/test_pellmonconf_readonly.py` — friendly read-only save message
- [ ] `tests/test_backup_script.py` — backup/restore round trip and docker-mode argv
- [ ] Permission-dependent cases skip when running as root or on Windows (`os.geteuid() == 0`, `sys.platform == "win32"`); prefer portable monkeypatching where possible

*Framework already installed; no new test dependency.*

---

## Manual-Only Verifications

| Behavior | Decision | Why Manual | Test Instructions |
|----------|-----------|----------|-----------|-------------------|-------------|--------|
| Real `docker compose up` with a host data folder: init exits 0, folder owned 999:999, data files present, data survives `down -v && up -d` | D-01, D-02, D-06 | Needs a Docker daemon and a Linux filesystem (WSL ext4 or the Pi); on Windows mounts `chown` is a no-op | On WSL2 Debian ext4 or the Pi: `PELLMON_DATA_DIR=./pd docker compose up -d --build`; expect `pellmon-init` Exited (0), `pd/data` owned 999:999, `rrd.db` and `pellmon_settings.db` present; `docker compose down -v && docker compose up -d` keeps the data |
| Loud failure when the data folder is unusable | D-07 | Needs permission changes on a real bind mount | Make the folder read-only (skipping the init step), start; expect a clear error naming the folder and the container unhealthy or exited |
| Backup, wipe, restore | D-10 | Needs a running daemon and real `rrdtool` in the container | Run the backup script, wipe the data folder, restore, confirm graphs and settings return |
| Do not place `pellmon-data` under `/mnt/c` when testing | all | Windows mounts ignore chown and permissions | Use WSL ext4 or the Pi only |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
