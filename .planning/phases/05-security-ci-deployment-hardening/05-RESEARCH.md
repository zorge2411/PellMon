# Phase 5: Security, CI & Deployment Hardening - Research

**Researched:** 2026-09-18
**Domain:** Web authentication security, command execution hardening, GitHub Actions CI, process lifecycle & signals, Docker Compose healthchecks, dependency pinning
**Confidence:** HIGH (verified against repository sources, installed packages, and runtime behavior)

## Summary

Phase 5 addresses the final security, continuous integration, and operational requirements needed to complete the v1.0 milestone.

### 1. Web Authentication Hardening (SEC-01 & SEC-02)
- **Plaintext Logging (SEC-01):**
  In `src/Pellmonweb/auth.py` lines 147 and 150:
  `cherrypy.log('Login failed from %s, username: %s, password: %s'%(cherrypy.request.headers["Remote-Addr"], username[:50], password[:50]))`
  This outputs the raw password submitted by the user directly to the log file.
  Solution: Remove password from the format string, and safely retrieve `Remote-Addr` with `.get()` to avoid `KeyError` if header is missing.
- **Password Hashing (SEC-02):**
  Currently, `check_credentials` in `auth.py` does `if (username, password) in self.credentials:`.
  Credentials in `config/pellmon.conf` under `[authentication]` are stored as plaintext `username = password`.
  Solution:
  Implement PBKDF2-HMAC-SHA256 with 100,000 iterations using Python standard library `hashlib` and `secrets`.
  Format: `pbkdf2:sha256:100000$<salt_hex>$<hash_hex>`.
  Provide `hash_password(password)` and `verify_password(stored, password)`.
  Support backward compatibility: if `stored` does not start with `pbkdf2:`, compare with `hmac.compare_digest(stored, password)` and log a configuration migration notice.
  Provide documented migration instructions in `README.md` and `config/pellmon.conf.example`.

### 2. Exec Plugin Command Hardening (SEC-03)
- In `src/Pellmonsrv/plugins/exec/__init__.py:86`:
  `return subprocess.check_output(script, shell=True)`
  Using `shell=True` allows shell metacharacters and command injection. Additionally, line 87 catches `CalledProcessError` without `subprocess.` namespace qualifier (potential `NameError`).
  In contrast, `execute_writescript` already safely uses `shell=False`.
  Solution:
  Use `shlex.split(script)` and pass the list with `shell=False` to `subprocess.check_output()`. Ensure `subprocess.CalledProcessError` is caught.

### 3. GitHub Actions CI (OPS-01)
- Create `.github/workflows/ci.yml` running on `ubuntu-latest`.
- Install Debian/Ubuntu system packages required for D-Bus, GLib, and rrdtool (`python3-dbus`, `python3-gi`, `python3-gi-cairo`, `gir1.2-glib-2.0`, `librrd-dev`, `rrdtool`, `python3-rrdtool`).
- Set up Python 3.11.
- Run `test-imports.py` and `pytest tests/ -v`.
- Trigger on `push` and `pull_request` to `master` and `python3-migration`.

### 4. Process Lifecycle & Graceful SIGTERM (OPS-02)
- **`pellmonsrv.py`:**
  Line 493 previously called `signal.signal(signal.SIGTERM, sigterm_handler)`, but `sigterm_handler` was never defined!
  Solution: Implement `sigterm_handler(signum, frame)`:
  - Log graceful shutdown message.
  - If `conf.polling` and `conf.nvdb != conf.db`, call `copy_db('store')` to flush RRD data to disk.
  - Call `DBUSMAINLOOP.quit()`.
  - Remove pidfile.
  - Register for both `SIGTERM` and `SIGINT`.
- **`pellmonweb.py`:**
  Lines 952-953 disable CherryPy's default SIGTERM handling, and lines 1021-1024 only trap `SIGINT`.
  Solution: Register `signal.signal(signal.SIGTERM, signal_handler)` to ensure `cherrypy.engine.exit()` and `main_loop.quit()` are invoked on SIGTERM during container stops or service restarts.

### 5. Docker Healthchecks (OPS-03)
- `docker-compose.yml`:
  `pellmonsrv` currently uses `pgrep -f pellmonsrv`, which only checks process existence, not readiness.
  Update to probe the session bus using `dbus-send` to ping `org.pellmon.int`:
  `dbus-send --session --address=unix:path=/var/run/pellmon/bus_socket --dest=org.pellmon.int --print-reply /org/pellmon/int org.freedesktop.DBus.Peer.Ping`
  Update `pellmonweb` dependency to wait for `service_healthy`.
  `pellmonweb` healthcheck already uses `curl -f http://localhost:8081/`.
  `Dockerfile` healthcheck also checks HTTP port 8081.

### 6. Dependency Pinning & Cleanup (OPS-04, OPS-05, OPS-06)
- **OPS-04:** Replace all `>=` floors in `requirements.txt` with verified exact pins (`pyserial==3.5`, `CherryPy==18.10.0`, `Mako==1.3.10`, `python-dateutil==2.9.0.post0`, `argcomplete==3.6.3`, `simplejson==4.1.2`, `ws4py==0.6.0`, `pyownet==0.10.0.post1`, `pycryptodome==3.23.0`, `xtea==0.7.1`, `pyowm==3.5.0`).
- **OPS-05:** Remove all 23 `.py2bak` files from `src/` using `git rm`.
- **OPS-06:** Update `README.md` to state clearly that production deployment is Linux-only, recommend Docker Compose, describe password hashing, and update legacy Python 2 packages to Python 3.
