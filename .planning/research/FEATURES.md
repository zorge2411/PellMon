# Feature Research

**Domain:** Production-readiness checklist for a small self-hosted Python daemon + web app (hardware monitoring, single-tenant, hobby-to-prosumer)
**Researched:** 2026-09-17
**Confidence:** MEDIUM-HIGH (stdlib/framework behavior HIGH; specific library picks MEDIUM, verified against current guidance but not against PellMon's exact runtime)

## Scope Note

This is not a feature landscape in the product sense (dashboards, alerts, graphs already exist and are out of scope per PROJECT.md). "Features" here means the checklist items that collectively define "production-ready" for a project this size and shape: two cooperating Linux processes (`pellmonsrv`, `pellmonweb`) talking over D-Bus, deployed via Docker Compose or legacy init scripts, mid Python 2→3 port, currently with print/bare-except logging, plaintext credential handling, a `shell=True` exec path, and no CI or test suite.

## Feature Landscape

### Table Stakes (Must Fix Before Calling This "Production Ready")

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Hash + compare web-auth credentials (no plaintext storage/comparison) | Any credential-gated web app that fails this is broken by definition, not just "less secure" | LOW | Codebase already has stdlib alternative; use `hashlib.pbkdf2_hmac` (stdlib, no new dependency) or `argon2-cffi` if a dependency is acceptable. PROJECT.md scopes this to fixing storage/comparison, not a full auth redesign — stdlib PBKDF2 keeps the footprint minimal and matches "fix, don't rebuild." Requires a one-time migration: existing plaintext passwords in `config/pellmon.conf` must be rehashed, and the config format/docs updated. |
| Stop logging plaintext passwords on failed login | Logging secrets is a hard-fail security bug, not a style choice; log files often get shipped to support/bug reports | LOW | `src/Pellmonweb/auth.py:147,150` — delete `password` from the log line. No dependency, single-line fix. Do before or together with the hashing fix since both touch the same function. |
| `shell=False` for the Exec plugin's readscript path | The writescript path already proves the safer pattern is known and available; leaving one path as `shell=True` is an inconsistency bug, not a design choice | LOW | `src/Pellmonsrv/plugins/exec/__init__.py:86`. Mirror the `subprocess.check_call([command]+parameters, shell=False)` pattern already used at line 94. |
| Structured, leveled logging via Python's `logging` module everywhere (no bare `print`, no swallowed exceptions) | A daemon with no operator-visible failure signal is not diagnosable in production; this is the single biggest blocker to calling the migration "done" per CONCERNS.md ("plugin activation error handling hides real failures") | MEDIUM | Two sub-parts: (1) replace remaining `print`/ad hoc logging with `logging.getLogger(__name__)` calls at appropriate levels; (2) replace bare `except:` with `except Exception:` + `logger.exception(...)` in plugin loading and protocol parsing, per CONCERNS.md. JSON/structured-format output is a nice-to-have (see Differentiators) — plain leveled logging to stderr/file is the actual table-stakes bar. |
| CI pipeline running tests + import checks on every PR before merge to `main`/`master` | The existing "migration complete" commit shipped with broken plugins because there was no automated gate — this is the concrete mechanism that prevents that class of regression from recurring | MEDIUM | GitHub Actions workflow: `pytest` for unit tests (protocol encode/decode, database, auth), plus a broadened `test-imports.py`-style step that imports every plugin package (not just the 4 core modules). Linux runner required (D-Bus/GLib/rrdtool are Linux-only) — use `ubuntu-latest` with `apt-get install` for system deps, matching the Dockerfile's approach. This is a prerequisite for the "Add automated test coverage" item already in PROJECT.md Active — tests without CI enforcement don't prevent regressions, they just exist. |
| Pytest-based regression suite for protocol/hardware modules (mocked I/O) | Byte/str boundary bugs (the confirmed NBE `TypeError`) are exactly the class of error unit tests catch immediately and code review doesn't | MEDIUM-HIGH | Already an Active item in PROJECT.md. Table stakes because it's the direct fix for the root cause of the false "migration complete" claim. Use `unittest.mock` for serial/socket I/O; no physical hardware needed for frame encode/decode round-trip tests. |
| Graceful shutdown (SIGTERM handling that closes serial ports, D-Bus connections, and RRD files cleanly) | Docker Compose sends SIGTERM on `docker compose down`/restart; an ungraceful daemon leaves serial ports locked, D-Bus names unreleased, or RRD writes half-committed, which surfaces as "container works until first restart" | MEDIUM | `pellmonsrv.py` and `pellmonweb.py` need explicit `signal.signal(signal.SIGTERM, handler)` (or GLib's `MainLoop.quit()` wired to SIGTERM) that stops the main loop, closes the serial handle, and lets in-flight D-Bus/RRD calls finish. Check current daemonizer behavior in `daemon.py` — double-forking daemons commonly only handle SIGHUP/SIGINT by default. |
| Docker healthcheck for both services | Docker Compose `depends_on` without a healthcheck only waits for container *start*, not for the app being ready to serve/poll — this matters here because `pellmonweb` depends on `pellmonsrv` being up on D-Bus before it can serve real data | LOW-MEDIUM | Add `HEALTHCHECK` to `Dockerfile` or `healthcheck:` to `docker-compose.yml`. For `pellmonweb`: HTTP GET against a lightweight endpoint (CherryPy already listens on 8081). For `pellmonsrv`: a check script that confirms the D-Bus name is registered and/or a sentinel file/socket is present — CherryPy doesn't run in this process so it needs its own signal. |
| Pin dependency versions (replace `>=` floors with a lockfile or `==` pins) | Reproducible builds are non-negotiable at "production ready" — the CONCERNS.md/STACK.md finding of "no lockfile, `>=` only" means a `docker build` next month can silently pull a breaking dependency update | LOW-MEDIUM | Generate `requirements.txt` pins via `pip freeze` inside the actual Docker build, or adopt `pip-tools` (`requirements.in` → compiled `requirements.txt`). Given the project's small dependency surface (CherryPy, Mako, pyserial, etc.), a simple pinned `requirements.txt` is sufficient — no need for Poetry/PDM. |
| Remove `.py2bak` files and dead commented-out code from the shipped tree once each module is confirmed stable | Already an Active PROJECT.md item; grouped here because it's a prerequisite for calling the *codebase itself* production-ready, not just the running app — stale parallel source files are a maintenance/audit hazard (CONCERNS.md flags risk of "someone accidentally importing/executing the wrong one") | LOW | Mechanical cleanup once import fixes are verified. Move to a git tag/branch instead of deleting outright if a rollback reference is still wanted — but they must not stay interspersed in `src/`. |
| Document/enforce Linux-only runtime clearly in README and container image | Already an Active PROJECT.md item; table stakes because a "production ready" project must not let an operator discover Linux-only-ness by crash | LOW | README section stating supported platforms; Dockerfile already targets Debian bookworm-slim, which is correct — just needs the doc-level confirmation this item calls for. |
| Explicit relative imports throughout `src/` (remove `sys.path.append` shims) | Already an Active PROJECT.md item; table stakes because the current inconsistent import strategy is the direct cause of the ScotteCom/NBEcom breakage — shipping "production ready" while this pattern remains means the next added plugin is likely to hit the same bug class | MEDIUM | Mechanical but touches many files; do this before/alongside the CI test suite so the fix is caught by tests immediately. |

### Differentiators (Worth Doing, Not Blocking "Production Ready")

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Structured (JSON) log output as an option | Makes logs greppable/parseable if the operator later feeds them into `journalctl -o json`, Loki, or similar — valuable for a prosumer running multiple PellMon instances, not needed for a single home install | LOW | Python's `logging` supports a custom `Formatter` outputting JSON with no extra dependency; `python-json-logger` is a common optional add-on if desired. Layer this on top of the table-stakes leveled-logging fix, don't block on it. |
| systemd `Type=notify` + watchdog integration for the non-Docker/legacy init-script deployment path | Lets systemd auto-restart a hung daemon (e.g. a wedged serial read) without an operator noticing — meaningfully improves resilience for bare-metal/Raspberry Pi installs | MEDIUM | Verified current pattern (2026): service sends `READY=1` via `sd_notify` on startup and periodic `WATCHDOG=1` heartbeats; unit file sets `Type=notify`, `WatchdogSec=`, `Restart=on-watchdog`. Python libraries: `sdnotify` (pure Python, no libsystemd dependency) or the `systemd-python` bindings. PROJECT.md explicitly keeps the Autotools/init-script path "as-is" — so this is optional polish for that path, not required, and Docker Compose (the supported target) uses container healthchecks instead. |
| `/healthz`-style endpoint on `pellmonweb` reporting D-Bus connectivity + last successful hardware poll timestamp | Turns "is it working" into a single HTTP check instead of tailing logs — useful for anyone fronting this with a reverse proxy or uptime monitor | LOW-MEDIUM | CherryPy route returning JSON with D-Bus status and staleness of the last item update; the Docker healthcheck (table stakes) can literally curl this endpoint instead of a generic port-open check. |
| Non-root container user | Defense-in-depth; currently `pellmonsrv` runs `privileged: true` for serial/D-Bus access, which already grants broad host access, so a non-root *user* inside the container is a smaller marginal win here than in a typical web app | MEDIUM | Requires reworking how the container gets serial device (`/dev/ttyUSB0`) and D-Bus socket access without full `privileged: true` — e.g. explicit `--device` mapping and D-Bus socket group permissions instead of privileged mode. Worth doing but nontrivial given current architecture; don't let it block the table-stakes security fixes (plaintext creds, shell=True) which are more directly exploitable. |
| Rehash-on-login migration path for existing plaintext `pellmon.conf` passwords | Smooths the upgrade for existing installs so operators aren't forced to manually regenerate config | LOW | Small addition to the hashing fix: on startup, detect an unhashed password in config, hash it, log a one-time warning telling the operator to update their config. Optional convenience on top of the table-stakes hashing fix. |
| Dependabot/Renovate for automated dependency update PRs | Keeps the newly-pinned dependency set from going stale silently | LOW | Trivial to add once CI exists; GitHub-native, no extra infra. |

### Anti-Features (Skip for a Project This Size)

| Feature | Why It Seems Appealing | Why Problematic Here | Alternative |
|---------|------------------------|----------------------|-------------|
| Full auth system overhaul (SSO, OAuth, multi-user RBAC) | "Production ready" often gets conflated with "enterprise-grade auth" | Explicitly out of scope per PROJECT.md; single-operator home/hobby tool doesn't need multi-tenant identity — adds real complexity (session/token management, external IdP dependency) for zero benefit to this user base | Fix the two concrete bugs (plaintext logging, plaintext comparison) and stop there |
| Kubernetes manifests / Helm chart | "Production ready" sometimes gets read as "cloud-native ready" | This is a single-instance, stateful (serial port, D-Bus, RRD files), physically-hardware-attached daemon — it cannot horizontally scale or be rescheduled across nodes by design; k8s adds orchestration overhead with no matching benefit | Docker Compose (already the supported path) is the right ceiling for this deployment shape |
| Prometheus/Grafana metrics exporter as a new subsystem | Metrics pipelines are a common "production ready" checkbox | The project already has RRD-based time-series storage and a dashboard — duplicating that with a second metrics stack is scope creep the PROJECT.md explicitly says not to do ("not adding new product features") | If observability is wanted later, expose existing RRD data via a Prometheus textfile exporter as a thin translation layer, not a parallel metrics system |
| Rewriting the legacy Autotools/init-script deployment path | Consistency with the Docker path feels tidy | PROJECT.md explicitly keeps this out of scope; it's a stable, working path for existing installs and touching it risks breaking real deployments for no stated benefit | Leave as-is; document Docker Compose as the recommended path |
| Full observability stack (tracing, APM) | Seems like standard "production" tooling | Two cooperating local processes on one host with a handful of concurrent users don't have a distributed-tracing problem; this is solved by good logging + a health endpoint | Structured logging (differentiator above) covers the actual debugging need |
| Rate limiting / DDoS protection on the web UI | Common web-app hardening checklist item | Single-tenant, typically LAN-only or behind the user's own reverse proxy/VPN; building this in-app duplicates what a reverse proxy (nginx/Caddy/Traefik) does better and is explicitly the operator's responsibility for a self-hosted tool | Document that internet-facing deployment should sit behind a reverse proxy; don't build rate limiting into CherryPy |
| Automatic dependency vulnerability blocking in CI (e.g. `pip-audit` as a hard merge gate) day one | Sounds like good hygiene to bolt on immediately | With no CI at all today, adding a hard security-gate as the *first* CI check risks blocking all merges on pre-existing transitive CVEs in old pinned versions before the team has bandwidth to triage them | Add `pip-audit`/`safety` as a non-blocking CI report first; make it a hard gate once the baseline is clean |

## Feature Dependencies

```
Explicit relative imports (fix broken plugin loading)
    └──requires──> (blocks) Automated pytest suite for protocol modules
                       └──requires──> (blocks) CI pipeline enforcing tests on PRs
                                          └──enables──> Confident merge-to-main workflow

Leveled logging + except Exception replacement
    └──enhances──> Automated pytest suite (failures become visible instead of silently swallowed)
    └──enables──> Structured JSON logging (differentiator)
    └──enables──> /healthz endpoint (needs reliable status signal to report)

Hash + compare web-auth credentials
    └──requires──> Stop logging plaintext passwords (same code path, fix together)
    └──enables──> Rehash-on-login migration path (differentiator)

Docker healthcheck
    └──enhances──> /healthz endpoint (differentiator; healthcheck can call it once it exists)
    └──conflicts with──> nothing; independent of auth/logging work

Pin dependency versions
    └──enables──> Dependabot/Renovate (differentiator)
    └──enables──> pip-audit as CI gate (deferred anti-feature-turned-later-feature)

Non-root container user (differentiator)
    └──conflicts with──> current privileged:true serial/D-Bus access pattern; requires reworking device/socket permissions first
```

### Dependency Notes

- **Explicit relative imports must land before the pytest suite is meaningful:** tests written against currently-broken plugin imports will just confirm the plugins are broken; fix imports first (or in the same PR) so tests validate real behavior, not known failures.
- **The pytest suite must exist before CI can enforce anything:** CI without tests is just an import-smoke-check, which is still valuable (catches the ScotteCom/NBEcom class of bug) but is not equivalent to regression protection for protocol logic.
- **Logging fixes enhance, not block, the test suite:** tests can be written against current bare-except code, but failures will be harder to diagnose from CI output until `logger.exception()` calls are in place. Do them in the same phase for efficiency, not because one strictly blocks the other.
- **Password hashing and password-logging fixes share one function** (`check_credentials`/login failure path in `auth.py`) — fix both in the same change to avoid touching that security-sensitive code twice.
- **Non-root container hardening conflicts with the current `privileged: true` requirement** for serial and D-Bus access — this is why it's a differentiator, not table stakes: doing it right requires an architecture change (explicit `--device` + D-Bus socket group perms) that's riskier than the other fixes and shouldn't block shipping "production ready."

## MVP Definition

### Launch With (v1 — "Production Ready" Bar)

- [ ] Hash + compare web-auth credentials — closes the most direct security hole
- [ ] Stop logging plaintext passwords — closes the second half of the same hole
- [ ] `shell=False` for Exec plugin readscript path — closes the injection surface
- [ ] Explicit relative imports across `src/` — fixes the actual broken plugins (ScotteCom, NBEcom)
- [ ] `except Exception:` + `logger.exception()` in plugin loading and protocol parsing — makes failures visible
- [ ] Leveled `logging` module usage replacing prints/silent swallows — baseline observability
- [ ] Pytest suite covering protocol encode/decode (mocked I/O), database, and auth — regression protection for the bug class that caused the false "migration complete" claim
- [ ] CI pipeline (GitHub Actions, Linux runner) running the pytest suite + broadened import-check on every PR — the actual mechanism preventing recurrence
- [ ] Graceful SIGTERM handling in both daemon processes — correct behavior under `docker compose down`/restart
- [ ] Docker healthcheck for both services — Compose can actually tell when the stack is ready/healthy
- [ ] Pinned dependency versions — reproducible builds
- [ ] `.py2bak` files removed, Linux-only runtime documented — codebase-level cleanliness items already scoped in PROJECT.md

### Add After Validation (v1.x)

- [ ] Structured JSON logging option — once plain leveled logging is proven sufficient in practice, add machine-parseable format if an operator asks
- [ ] `/healthz` endpoint reporting D-Bus + last-poll status — natural follow-on once healthchecks and logging exist
- [ ] Dependabot/Renovate — trivial once CI and pinning exist
- [ ] `pip-audit`/`safety` as a non-blocking CI report, later promoted to a hard gate

### Future Consideration (v2+)

- [ ] systemd `Type=notify`/watchdog integration for the legacy init-script path — only if bare-metal/non-Docker installs are still common among users; Docker healthchecks already cover the primary deployment target
- [ ] Non-root container user — valuable but requires an architecture change to device/D-Bus access; defer until the higher-value security fixes are shipped
- [ ] Rehash-on-login migration convenience — nice UX polish once credential hashing itself is in place

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Hash + compare web-auth credentials | HIGH | LOW | P1 |
| Stop logging plaintext passwords | HIGH | LOW | P1 |
| `shell=False` Exec plugin fix | HIGH | LOW | P1 |
| Explicit relative imports (fix plugin loading) | HIGH | MEDIUM | P1 |
| Replace bare excepts with logged exceptions | HIGH | MEDIUM | P1 |
| Leveled logging module usage | HIGH | MEDIUM | P1 |
| Pytest suite (protocol/db/auth, mocked I/O) | HIGH | MEDIUM-HIGH | P1 |
| CI pipeline enforcing tests on PRs | HIGH | MEDIUM | P1 |
| Graceful SIGTERM shutdown | MEDIUM-HIGH | MEDIUM | P1 |
| Docker healthcheck | MEDIUM-HIGH | LOW-MEDIUM | P1 |
| Pin dependency versions | MEDIUM | LOW-MEDIUM | P1 |
| Remove `.py2bak`, document Linux-only | LOW-MEDIUM | LOW | P1 |
| Structured JSON logging | LOW-MEDIUM | LOW | P2 |
| `/healthz` endpoint | MEDIUM | LOW-MEDIUM | P2 |
| Dependabot/Renovate | LOW | LOW | P2 |
| `pip-audit` CI report | MEDIUM | LOW | P2 |
| systemd watchdog integration (legacy path) | LOW | MEDIUM | P3 |
| Non-root container user | MEDIUM | MEDIUM-HIGH | P3 |
| Rehash-on-login migration | LOW | LOW | P3 |

**Priority key:**
- P1: Must have to call this "production ready" (table stakes)
- P2: Should have, add once P1 is stable
- P3: Nice to have, defer until requested or until architecture allows it cheaply

## Sources

- Codebase analysis: `.planning/codebase/CONCERNS.md`, `.planning/codebase/STACK.md`, `.planning/PROJECT.md` (primary source for this research — findings are grounded in the actual repo state, not generic best-practice lists)
- Password hashing guidance (2026): OWASP-aligned consensus via multiple 2026 comparison articles — Argon2id recommended for new work, PBKDF2/bcrypt acceptable with adequate cost factors (bcrypt cost ≥12). MEDIUM confidence — cross-checked across several independent 2026 sources but not against an official OWASP page directly.
- systemd `sd_notify`/watchdog pattern: `freedesktop.org` `sd_notify` man page and `python-systemd` documentation, cross-checked against `bb4242/sdnotify` (pure-Python implementation) and a 2026 systemd watchdog configuration guide. HIGH confidence for the mechanism itself (official docs); MEDIUM for "which Python library to use" (multiple viable options, no single official pick).
- General container healthcheck and graceful-shutdown patterns for Docker Compose: based on documented Docker/Compose `HEALTHCHECK`/SIGTERM semantics (stable, well-established behavior, not independently re-verified via WebSearch this session — HIGH confidence based on training knowledge of unchanged Docker mechanics).

---
*Feature research for: Python 2→3 migration completion + production-readiness hardening for a self-hosted hardware-monitoring daemon*
*Researched: 2026-09-17*
