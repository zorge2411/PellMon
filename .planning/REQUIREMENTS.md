# Requirements: PellMon Python 3 Migration

**Defined:** 2026-09-17
**Core Value:** The daemon must actually talk to real burner hardware through its protocol plugins (Scotte, NBE) under Python 3 — a port where only the core modules import but the hardware plugins silently fail isn't done.

## v1 Requirements

Requirements for the "finish the migration and get it production-ready" milestone. Each maps to roadmap phases.

### Test Infrastructure (TEST)

- [x] **TEST-01**: Developer can run a pytest suite locally that exercises protocol encode/decode logic without physical hardware attached (mocked serial via pyserial `loop://`, mocked UDP sockets)
- [x] **TEST-02**: Developer can run a broadened import-check that imports every plugin package (not just the 4 core modules `test-imports.py` currently covers), so a plugin with broken imports fails the check instead of being silently skipped
- [x] **TEST-03**: Developer can run a pytest suite covering `database.py` (SQLite keyval storage get/set/init, including the fallback table-creation path) and `Pellmonweb/auth.py` (credential check, session login flow)

### Failure Visibility (OBS)

- [x] **OBS-01**: Plugin import/activation failures are logged with a full traceback (`logger.exception(...)`) instead of being silently swallowed by bare `except:` clauses in the yapsy plugin manager
- [x] **OBS-02**: Protocol parsing and database write failures are logged with `logger.exception(...)` instead of bare `except:` swallowing, in `pellmonsrv.py` and `plugins/calculate/__init__.py`. (`Scotteprotocol/protocol.py` is excluded from Phase 2 — confirmed unreachable via import today since `Scotteprotocol/__init__.py:2`'s broken import fails first; its exception-visibility work is deferred to Phase 3, bundled with `IMPORT-01`'s relative-import fix.)
- [x] **OBS-03**: Remaining ad hoc `print`/inconsistent logging calls are replaced with `logging.getLogger('pellMon')` calls at appropriate levels across `src/` (matches the codebase's existing shared-logger convention per `CONVENTIONS.md`, rather than introducing `__name__`-based per-module loggers)

### Import Strategy & Plugin Loading (IMPORT)

- [ ] **IMPORT-01**: ScotteCom plugin loads and activates successfully under Python 3 (fixes broken implicit relative imports in `Scotteprotocol/__init__.py`, `frames.py`, `datamap.py`, `protocol.py`, and `scottecom/menus.py`)
- [ ] **IMPORT-02**: NBEcom plugin loads and activates successfully under Python 3 (fixes broken implicit relative imports in `nbecom/nbeprotocol/protocol.py` and `frames.py`)
- [ ] **IMPORT-03**: All intra-package imports in `src/` use explicit relative imports (PEP 328) instead of `sys.path.append` shims, with absolute imports only at the yapsy `exec()`-loaded plugin `__init__.py` boundary (which cannot resolve relative imports)
- [ ] **IMPORT-04**: No duplicate-module-name collision risk remains between `Scotteprotocol` and `nbecom/nbeprotocol` packages (resolved as a consequence of explicit relative/absolute import fixes)

### Protocol Correctness (PROTO)

- [ ] **PROTO-01**: NBEcom `Proxy.get()` correctly splits response payloads without raising `TypeError` (fixes the bytes/str mixing bug at `nbeprotocol/protocol.py:144,146`)
- [ ] **PROTO-02**: Calculate plugin's `setItem()` no longer raises `NameError` from the leftover Python 2 `unicode()` call (`plugins/calculate/__init__.py:351`)
- [ ] **PROTO-03**: Daemon can redirect stderr to a log file in daemonized mode without raising `ValueError: can't have unbuffered text I/O` (`daemon.py:69`)
- [ ] **PROTO-04**: Scotte and NBE protocol modules have a hardware-mock boundary (constructor-injectable transport) so encode/decode round-trip tests can run without physical hardware, verified via the TEST-01 suite
- [ ] **PROTO-05**: Calculate plugin imports successfully on Linux (fixes the Python-2-only `from string import maketrans` at `plugins/calculate/__init__.py:28`, which raises `ImportError` on Linux/WSL — found by Phase 2 research; distinct from PROTO-02's `unicode()` bug in the same file)

### Security (SEC)

- [ ] **SEC-01**: Web UI login failures no longer log the submitted plaintext password (`Pellmonweb/auth.py:147,150`)
- [ ] **SEC-02**: Web UI credentials are hashed (not compared in plaintext), with a one-time migration path for existing plaintext passwords in `config/pellmon.conf`
- [ ] **SEC-03**: Exec plugin's readscript path uses `shell=False` with an argument list, matching the safer pattern already used by the writescript path (`plugins/exec/__init__.py:86`)

### Deployment & Cleanup Hardening (OPS)

- [ ] **OPS-01**: A CI pipeline (GitHub Actions, Linux runner) runs the pytest suite and the broadened import-check on every pull request before merge to `master`/`python3-migration`
- [ ] **OPS-02**: Both `pellmonsrv` and `pellmonweb` handle SIGTERM gracefully (close serial ports, release D-Bus names, flush RRD writes) so `docker compose down`/restart doesn't leave locked resources
- [ ] **OPS-03**: `docker-compose.yml`/`Dockerfile` define a healthcheck for both services so Compose can tell when the stack is actually ready, not just started
- [ ] **OPS-04**: Dependency versions are pinned (lockfile or `==` pins) instead of `>=` floors, so builds are reproducible
- [ ] **OPS-05**: All `.py2bak` backup files are removed from `src/` once each corresponding module's Python 3 behavior is confirmed by the test suite
- [ ] **OPS-06**: README documents that production deployment is Linux-only (D-Bus, GLib, rrdtool, serial, GPIO dependencies), so this isn't discovered by a Windows crash

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Observability Polish

- **OBS-V2-01**: Structured JSON log output option (on top of the v1 leveled-logging fix)
- **OBS-V2-02**: `/healthz` endpoint on `pellmonweb` reporting D-Bus connectivity and last successful hardware poll timestamp

### Dependency Hygiene

- **OPS-V2-01**: Dependabot/Renovate for automated dependency update PRs
- **OPS-V2-02**: `pip-audit`/`safety` as a non-blocking CI report, later promoted to a hard gate once the baseline is clean

### Deployment Resilience (Legacy Path)

- **OPS-V2-03**: systemd `Type=notify` + watchdog integration for the non-Docker/legacy init-script deployment path

### Credential UX

- **SEC-V2-01**: Rehash-on-login migration convenience (auto-detect and hash unmigrated plaintext passwords in config with a one-time warning)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Windows production support | D-Bus/GLib/rrdtool/serial/GPIO are Linux-only dependencies by design; Windows stays dev-only for syntax porting |
| New hardware protocol support | Only hardening the existing Scotte and NBE protocols is in scope for this milestone |
| Full rewrite of Autotools/legacy init-script deployment path | Docker Compose is the supported deployment target; the legacy path is stable for existing installs and stays as-is |
| Full auth system overhaul (SSO, OAuth, multi-user RBAC) | Single-operator home/hobby tool; fixing the two concrete plaintext-credential bugs is sufficient, not a full redesign |
| Kubernetes manifests / Helm chart | Single-instance, hardware-attached daemon that cannot horizontally scale by design; Docker Compose is the right ceiling |
| Prometheus/Grafana metrics exporter | RRD-based time-series storage and a dashboard already exist; a second metrics stack is scope creep |
| Non-root container user | Conflicts with the current `privileged: true` requirement for serial/D-Bus access; requires a riskier architecture change than the other security fixes — deferred |
| Rate limiting / DDoS protection in-app | Single-tenant, typically LAN-only or behind a reverse proxy; that's the operator's responsibility, not CherryPy's |
| Full observability stack (tracing, APM) | Two cooperating local processes on one host don't have a distributed-tracing problem; good logging + healthchecks cover it |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TEST-01 | Phase 1 | Complete |
| TEST-02 | Phase 1 | Complete |
| TEST-03 | Phase 1 | Complete |
| OBS-01 | Phase 2 | Complete |
| OBS-02 | Phase 2 | Complete |
| OBS-03 | Phase 2 | Complete |
| IMPORT-01 | Phase 3 | Pending |
| IMPORT-02 | Phase 3 | Pending |
| IMPORT-03 | Phase 3 | Pending |
| IMPORT-04 | Phase 3 | Pending |
| PROTO-01 | Phase 4 | Pending |
| PROTO-02 | Phase 4 | Pending |
| PROTO-03 | Phase 4 | Pending |
| PROTO-04 | Phase 4 | Pending |
| PROTO-05 | Phase 4 | Pending |
| SEC-01 | Phase 5 | Pending |
| SEC-02 | Phase 5 | Pending |
| SEC-03 | Phase 5 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 5 | Pending |
| OPS-04 | Phase 5 | Pending |
| OPS-05 | Phase 5 | Pending |
| OPS-06 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-17*
*Last updated: 2026-09-17 after roadmap creation*
