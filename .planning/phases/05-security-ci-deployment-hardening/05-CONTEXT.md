# Phase 5: Security, CI & Deployment Hardening - Context

**Gathered:** 2026-09-18
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase addresses security hardening, continuous integration, and operational resilience:
1. **SEC-01**: Eliminate logging of raw passwords on failed login attempts in `Pellmonweb/auth.py:147,150`.
2. **SEC-02**: Implement secure password hashing (PBKDF2-HMAC-SHA256) in `Pellmonweb/auth.py` with backward-compatible verification and documented migration path for legacy plaintext passwords in `config/pellmon.conf`.
3. **SEC-03**: Secure Exec plugin `execute_readscript` by using `shell=False` with `shlex.split` arguments in `plugins/exec/__init__.py:86`, aligning with the existing safe writescript pattern.
4. **OPS-01**: GitHub Actions CI workflow (`.github/workflows/ci.yml`) on Ubuntu runner running pytest and broadened import check on PRs and pushes to `master` and `python3-migration`.
5. **OPS-02**: Graceful SIGTERM handling for both `pellmonsrv` and `pellmonweb` (close serial ports, release D-Bus names, flush RRD writes to persistent storage).
6. **OPS-03**: Healthchecks in `docker-compose.yml` and `Dockerfile` reflecting actual service readiness (D-Bus ping for server, HTTP check for web).
7. **OPS-04**: Pin dependencies in `requirements.txt` (`==` pins instead of `>=` floors) matching verified runtime environment.
8. **OPS-05**: Remove all 23 leftover `.py2bak` backup files from `src/`.
9. **OPS-06**: Update `README.md` to document that production deployment is Linux-only, recommend Docker Compose, and document password hash generation.

</domain>

<decisions>
## Implementation Decisions

### D-01: Password Hashing Standard & Migration (SEC-01, SEC-02)
- Use standard library `hashlib.pbkdf2_hmac` with SHA256 and 100,000 iterations.
- Format: `pbkdf2:sha256:100000$<salt_hex>$<hash_hex>`.
- `auth.py` provides `hash_password(password)` and `verify_password(stored_credential, provided_password)`.
- If `stored_credential` is in `pbkdf2:` format, verify via `hmac.compare_digest`.
- If `stored_credential` is legacy plaintext, verify via `hmac.compare_digest(stored_credential, provided_password)`. If valid, log a warning prompting configuration migration.
- In `check_credentials`: Remove `password` from failed login logs; use `cherrypy.request.headers.get("Remote-Addr", "unknown")`.

### D-02: Exec Plugin Command Execution (SEC-03)
- In `src/Pellmonsrv/plugins/exec/__init__.py:86`:
  Use `args = shlex.split(script)` and `subprocess.check_output(args, shell=False)`.
  Catch `subprocess.CalledProcessError` properly (fixing potential `NameError`).

### D-03: CI Workflow Specifications (OPS-01)
- Target: `.github/workflows/ci.yml`.
- Runner: `ubuntu-latest`.
- System packages: `python3-dbus`, `python3-gi`, `python3-gi-cairo`, `gir1.2-glib-2.0`, `librrd-dev`, `rrdtool`, `python3-rrdtool`.
- Python version: `3.11`.
- Triggers: `push` and `pull_request` against `master` and `python3-migration`.
- Checks: `test-imports.py` and `pytest tests/ -v`.

### D-04: Graceful Shutdown (OPS-02)
- `pellmonsrv.py`: Define `sigterm_handler(signum, frame)`:
  - If `conf.polling` and `conf.nvdb != conf.db`: call `copy_db('store')` to flush RRD data to persistent disk.
  - Quit GLib `DBUSMAINLOOP`.
  - Delete pidfile if it exists.
  - Connect handler to both `signal.SIGTERM` and `signal.SIGINT`.
- `pellmonweb.py`: Register `signal.signal(signal.SIGTERM, signal_handler)` in addition to `signal.SIGINT`.

### D-05: Docker Healthchecks & Dependency Pinning (OPS-03, OPS-04)
- `docker-compose.yml`:
  - `pellmonsrv` healthcheck uses `dbus-send` on shared session socket to ping `org.pellmon.int`.
  - `pellmonweb` sets `depends_on.pellmonsrv.condition: service_healthy`.
- `requirements.txt`:
  - Pin verified versions: `pyserial==3.5`, `CherryPy==18.10.0`, `Mako==1.3.10`, `python-dateutil==2.9.0.post0`, `argcomplete==3.6.3`, `simplejson==4.1.2`, `ws4py==0.6.0`, `pyownet==0.10.0.post1`, `pycryptodome==3.23.0`, `xtea==0.7.1`, `pyowm==3.5.0`.

### D-06: Cleanup and Documentation (OPS-05, OPS-06)
- Remove all 23 tracked `.py2bak` files via `git rm`.
- In `README.md`, add a prominent note: production deployment is Linux-only (D-Bus, GLib, rrdtool, serial, GPIO), document Docker Compose usage, document password hashing migration, and modernize dependency listings to Python 3.

</decisions>

<canonical_refs>
## Canonical References

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — SEC-01..03, OPS-01..06
- `.planning/ROADMAP.md` — Phase 5 Goal, Requirements, Success Criteria
- `.planning/PROJECT.md` — Key Decisions & Project Context

### Source Files Under Change
- `src/Pellmonweb/auth.py`
- `src/Pellmonsrv/plugins/exec/__init__.py`
- `src/Pellmonsrv/pellmonsrv.py`
- `src/Pellmonweb/pellmonweb.py`
- `.github/workflows/ci.yml`
- `docker-compose.yml`
- `Dockerfile`
- `requirements.txt`
- `README.md`
- `config/pellmon.conf.example`

</canonical_refs>
