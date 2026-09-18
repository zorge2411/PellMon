---
phase: 05-security-ci-deployment-hardening
plan: 04
subsystem: hardening-documentation
tags: [dependencies, requirements, cleanup, hygiene, documentation, docker-compose, readme, verification]
dependency-graph:
  requires: [05-01, 05-02, 05-03]
  provides:
    - Pinned dependencies (==) matching verified runtime environment in requirements.txt (OPS-04)
    - Purged all 23 obsolete .py2bak backup files from src/ (OPS-05)
    - Modernized README.md with Linux-only production notice, Docker Compose setup, password hash instructions, and Python 3 dependencies (OPS-06)
    - Verified full test suite passing with zero regressions (110 passed, 8 skipped)
  affects:
    - requirements.txt
    - README.md
    - src/ (removed .py2bak files)
tech-stack:
  added: []
  patterns:
    - Exact dependency version pinning (`==`) for build reproducibility
    - Repository hygiene and legacy file purge
    - Production platform requirement documentation and Docker Compose orchestration guide
key-files:
  created: []
  modified:
    - requirements.txt
    - README.md
  deleted:
    - src/Pellmonsrv/daemon.py.py2bak
    - src/Pellmonsrv/database.py.py2bak
    - src/Pellmonsrv/pellmonsrv.py.py2bak
    - src/Pellmonsrv/plugin_categories.py.py2bak
    - src/Pellmonsrv/plugins/calculate/__init__.py.py2bak
    - src/Pellmonsrv/plugins/cleaning/__init__.py.py2bak
    - src/Pellmonsrv/plugins/consumption/__init__.py.py2bak
    - src/Pellmonsrv/plugins/customalarms/__init__.py.py2bak
    - src/Pellmonsrv/plugins/exec/__init__.py.py2bak
    - src/Pellmonsrv/plugins/heatingcircuit/__init__.py.py2bak
    - src/Pellmonsrv/plugins/onewire/__init__.py.py2bak
    - src/Pellmonsrv/plugins/owfs/__init__.py.py2bak
    - src/Pellmonsrv/plugins/pelletcalc/__init__.py.py2bak
    - src/Pellmonsrv/plugins/raspberrygpio/__init__.py.py2bak
    - src/Pellmonsrv/plugins/silolevel/__init__.py.py2bak
    - src/Pellmonsrv/plugins/testplugin/__init__.py.py2bak
    - src/Pellmonsrv/yapsy/ConfigurablePluginManager.py.py2bak
    - src/Pellmonsrv/yapsy/PluginManager.py.py2bak
    - src/Pellmonsrv/yapsy/VersionedPluginManager.py.py2bak
    - src/Pellmonweb/logview.py.py2bak
    - src/Pellmonweb/pellmonconf.py.py2bak
    - src/Pellmonweb/pellmonweb.py.py2bak
    - src/Scotteprotocol/protocol.py.py2bak
decisions: [D-05, D-06]
metrics:
  completed: 2026-09-18
---

# Phase 5 Plan 04: Hardening, Repository Hygiene & Documentation Summary

Completed project hardening, repository hygiene, and documentation modernization across the repository: pinned exact dependency versions in `requirements.txt` (OPS-04), purged all 23 obsolete `.py2bak` backup files from `src/` (OPS-05), updated `README.md` with explicit Linux-only production deployment notices, Docker Compose guides, authentication hash generation instructions, and Python 3 dependency packages (OPS-06), and verified the full test suite with zero failures across the entire project.

## What Was Built

### Task 1: Pin dependency versions in requirements.txt (OPS-04)
Replaced `>=` version floors with exact `==` pins matching the verified runtime environment:
- Core cross-platform packages: `pyserial==3.5`, `CherryPy==18.10.0`, `Mako==1.3.10`, `python-dateutil==2.9.0.post0`, `argcomplete==3.6.3`, `simplejson==4.1.2`
- Optional & plugin packages: `ws4py==0.6.0`, `pyownet==0.10.0.post1`, `pycryptodome==3.23.0`, `xtea==0.7.1`, `pyowm==3.5.0`
- Documented system package equivalents for platform-specific dependencies (`python3-rrdtool`, `python3-dbus`, `python3-gi`).

### Task 2: Delete all .py2bak files from src/ (OPS-05)
Removed all 23 tracked `.py2bak` backup files across `src/Pellmonsrv`, `src/Pellmonsrv/plugins`, `src/Pellmonsrv/yapsy`, `src/Pellmonweb`, and `src/Scotteprotocol` via `git rm -f`, eliminating leftover migration artifacts and reducing repo clutter by 6,590 lines.

### Task 3: Update README.md with Linux-only notice and modern deployment guide (OPS-06)
- Added prominent alert at the top of the documentation clarifying that production deployment is **Linux-only** due to hardware/OS subsystem requirements (D-Bus, PyGObject/GLib, RRDtool C-bindings, Linux serial devices `/dev/ttyUSB*`, and GPIO), with Windows supported for development, mock testing, and syntax verification.
- Documented **Docker Compose** as the recommended deployment approach, highlighting service separation (`pellmonsrv` / `pellmonweb`), shared session D-Bus socket over volume `/var/run/pellmon/bus_socket`, healthcheck gating (`service_healthy` condition on peer D-Bus ping), and persistent volume mounts.
- Added comprehensive documentation for web authentication and PBKDF2 credential generation (`hash_password` snippet) for `config/pellmon.conf`, noting backward compatibility with plaintext credentials.
- Modernized dependency documentation from Python 2 package names to Python 3 system and pip packages.

### Task 4: Full verification gate
- Ran `test-imports.py` and full pytest test suite across `tests/`.
- Verified 110 passed, 8 skipped (expected Linux-platform specific tests: D-Bus, rrdtool, raspberrygpio), 0 failed.

## Verification Results

1. Task 1 Verification:
```powershell
venv-py3/Scripts/python.exe -c "lines = [l.strip() for l in open('requirements.txt') if l.strip() and not l.startswith('#')]; assert all('==' in l for l in lines), 'Unpinned dependency found in requirements.txt'"
# Exit 0
```

2. Task 2 Verification:
```powershell
venv-py3/Scripts/python.exe -c "import glob; matches = glob.glob('src/**/*.py2bak', recursive=True); assert len(matches) == 0, f'Found remaining .py2bak files: {matches}'"
# Exit 0
```

3. Task 3 Verification:
```powershell
venv-py3/Scripts/python.exe -c "readme = open('README.md').read(); assert 'Linux-only' in readme; assert 'docker compose' in readme.lower(); assert 'hash_password' in readme"
# Exit 0
```

4. Task 4 Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/ -q
# 110 passed, 8 skipped, 2 warnings in 2.32s
```

## Deviations from Plan

None. Work followed the plan specifications and decisions D-05 and D-06 cleanly.

## Commits

- `3b6d3fe` chore(phase-5): pin dependency versions in requirements.txt
- `cd69f5c` chore(phase-5): remove obsolete py2bak files from src
- `f539201` docs(phase-5): update README with Linux-only notice, Docker Compose, and auth hashing
