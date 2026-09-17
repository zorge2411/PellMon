# Project Research Summary

**Project:** PellMon — Python 2->3 migration completion + production-readiness hardening
**Domain:** Self-hosted hardware-monitoring daemon (serial/UDP burner-control protocols, plugin architecture, D-Bus IPC, Docker deployment)
**Researched:** 2026-09-17
**Confidence:** HIGH

## Executive Summary

PellMon is a two-process Linux daemon (`pellmonsrv` + `pellmonweb`) that polls pellet-burner hardware over serial and UDP protocols via a yapsy-based dynamic plugin system, exposes results over D-Bus to a CherryPy web UI, and stores history in RRD files. The Python 2->3 migration was previously declared "complete" based only on a shallow import-smoke-test, but the two hardware protocol plugins (ScotteCom, NBEcom) are confirmed broken at runtime: `ModuleNotFoundError` from Python-2-style bare/implicit relative imports, and a `TypeError` from mechanical bytes/str substitution in `nbeprotocol/protocol.py`. The codebase also carries ~148+ bare `except:` blocks that actively hide these and future regressions, plus real security bugs (plaintext password logging/comparison, one `shell=True` exec path) that predate the migration.

The recommended approach is not a rewrite: the existing package layout is architecturally sound (each protocol library is a proper package). The fix is a disciplined sequence: first build a hardware-free test harness (pytest + pyserial `loop://` + mocked sockets + `pytest-socket` to block accidental real I/O), then make failures loud (replace bare excepts with `logger.exception()`, without touching logic), then fix imports (absolute at the yapsy-exec'd plugin boundary, explicit relative — PEP 328 — everywhere else) and the bytes/str semantic bugs, verified by the harness at each step, then close the security gaps and add CI/Docker production-readiness items (healthchecks, graceful shutdown, pinned deps). The central risk across all research is verification theater: "it imports," "the diff looks like a standard migration pattern," and "the server started" have each already produced false confidence once in this project's history, so every phase must define "done" as an executed test passing, not a read-through.

Because hardware is unavailable for CI/dev, all protocol-level verification must be mocked (serial loopback, faked sockets) and explicitly labeled "unit-verified, not hardware-verified" rather than conflated with full verification. This shapes both the phase structure (test harness must exist before bug-fixing is meaningful) and the tooling choices (pytest-socket, `loop://`, constructor-injectable transports) recommended in STACK.md and ARCHITECTURE.md.

## Key Findings

### Recommended Stack

The stack is almost entirely testing/tooling additions on top of the existing dependency set — no new production dependencies are required to fix the confirmed bugs. pytest with pytest-mock/pytest-socket/pytest-cov forms the test harness; ruff replaces the old flake8/pyupgrade/isort combo and directly flags remaining Python-2 idioms; mypy (scoped narrowly to the protocol packages, not repo-wide) is the single most effective tool for catching the exact bytes/str boundary bug class already found in `nbeprotocol/protocol.py`.

**Core technologies:**
- pytest (>=8.3) + pytest-mock + pytest-cov — test framework and coverage, fixture-based mocking for serial/socket I/O
- pytest-socket (>=0.7) — blocks real network calls in CI so a broken/forgotten mock in the NBE UDP path fails loudly instead of hanging
- ruff (>=0.8, `UP`/`B`/`F`/`E`/`SIM` rules) — single fast linter catching leftover Python-2 idioms (`unicode()`, bare `except:`) and general bugs
- mypy (>=1.13, scoped to `Scotteprotocol/`, `nbeprotocol/`, `database.py`) — static bytes/str type-checking, directly targets the confirmed `TypeError` bug class
- pyserial's built-in `loop://` handler + `unittest.mock.MagicMock` for sockets — zero-new-dependency hardware mocking for serial and UDP respectively
- python-dbusmock (optional, later) — for testing the D-Bus IPC boundary between `pellmonsrv`/`pellmonweb` once protocol-level tests are in place

### Expected Features

This is a "production readiness checklist" rather than a product feature landscape — dashboards/graphs already exist and are out of scope. Findings are grounded directly in `.planning/codebase/CONCERNS.md`.

**Must have (table stakes):**
- Fix explicit relative imports across `src/` (root cause of ScotteCom/NBEcom breakage)
- Pytest suite covering protocol encode/decode (mocked I/O), database, and auth
- CI pipeline (Linux runner) running tests + broadened import checks on every PR
- Replace bare `except:` with `except Exception:` + `logger.exception()` in plugin loading/protocol parsing
- Leveled `logging` module usage everywhere (no bare `print`)
- Hash + compare web-auth credentials (no plaintext); stop logging plaintext passwords
- `shell=False` for the Exec plugin's readscript path (mirror the existing writescript pattern)
- Graceful SIGTERM handling (close serial/D-Bus/RRD cleanly) + Docker healthcheck for both services
- Pinned dependency versions; `.py2bak` file removal; documented Linux-only runtime

**Should have (differentiators):**
- Structured JSON log output option; `/healthz` endpoint reporting D-Bus + last-poll status
- systemd `Type=notify`/watchdog integration for the legacy (non-Docker) init-script path
- Non-root container user (blocked on reworking `privileged: true` serial/D-Bus access)
- Dependabot/Renovate once CI and pinning exist

**Defer (v2+/anti-features):**
- Full auth overhaul (SSO/OAuth/RBAC), Kubernetes manifests, a parallel Prometheus/Grafana metrics stack, rewriting the legacy Autotools deployment path, in-app rate limiting — all explicitly out of scope per PROJECT.md and disproportionate to a single-tenant hobby/prosumer tool.

### Architecture Approach

No directory restructuring is needed. The fix is entirely about import statements and a testing seam. Because yapsy loads each plugin's `__init__.py` via `exec()` rather than normal `import`, that one file per plugin has no package context and must use absolute imports (`from Pellmonsrv.plugins.scottecom.scottecom import scottecomplugin`); every module it subsequently imports normally is a real `sys.modules` entry and should use explicit relative imports (PEP 328) internally. Protocol classes (`Scotteprotocol.Protocol`, `nbeprotocol.Proxy`) should gain an optional `transport=None` constructor parameter — defaulting to the real hardware object, overridable with a fake/loopback in tests — which fully decouples protocol-level testing from the plugin-activation/D-Bus/yapsy pipeline with no changes to those systems.

**Major components:**
1. `yapsy PluginManager` — discovers and `exec()`s plugin `__init__.py` files; must use absolute imports and must log failures loudly (currently swallows them)
2. Plugin packages (`scottecom`, `nbecom`) — wire hardware protocol classes into the framework; helper modules within use relative imports
3. Protocol packages (`Scotteprotocol`, `nbeprotocol`) — pure byte/frame encode-decode + transport I/O, zero dependency on `Pellmonsrv.plugin_categories`, the natural unit-test boundary once transport injection is added
4. `pellmonsrv`/`pellmonweb` — daemon processes communicating over D-Bus, need graceful-shutdown and health-signal work

### Critical Pitfalls

1. **"It imports" treated as "it works"** — import success only exercises module-level code, never function bodies; the current `test-imports.py` never imports the two broken plugins. Fix: define "ported" as imports cleanly AND has an executed test calling `activate()`/encode-decode with mocked I/O.
2. **Mechanical bytes/str substitution instead of semantic reasoning** — adding `.encode()`/`.decode()` to "make an error go away" without tracing the actual data type produced the confirmed `TypeError` in `nbeprotocol/protocol.py:144`. Fix: line-by-line type audit per protocol module (raw read=bytes, post-decode=str, pre-write=bytes again), verified by round-trip tests.
3. **Bare `except:` turns every new regression into silence** — ~148+ occurrences concentrated exactly in the modules being fixed; a new bug introduced while fixing an old one will be hidden the same way. Fix: convert to `except Exception:` + `logger.exception()` as its own behavior-preserving phase, verified against an unchanged activation baseline, strictly before bug-fixing.
4. **Dynamic plugin loader swallows import failures as "plugin just not available"** — a broken plugin persists silently through multiple "complete" claims because there's no loud failure signal. Fix: ERROR-level logging plus a startup activation summary (N configured, M activated, failures listed).
5. **Retrofitting logging changes mid-bugfix masks which change did what** — interleaving observability changes and logic changes in the same commit makes regressions unbisectable. Fix: strictly sequence observability retrofit (phase N) before protocol bug fixes (phase N+1), each independently verified.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Test Harness & Verification Infrastructure
**Rationale:** Every subsequent phase needs a real pass/fail signal instead of import-checks or diff review; pitfalls research is unanimous that this must come first.
**Delivers:** pytest + pytest-mock + pytest-socket + pytest-cov configured; `loop://`-based serial fixtures and mocked-socket fixtures; extended import/activation smoke test covering ScotteCom and NBEcom (not just the 4 top-level modules); `pytest.ini` hardware marker to gate manual-only hardware tests.
**Addresses:** Pytest suite (table stakes, FEATURES.md); CI pipeline groundwork.
**Avoids:** Pitfall 1 ("it imports" false confidence), Pitfall 6 (trusting `.py2bak` diffs as proof).

### Phase 2: Exception-Visibility Retrofit (Observability, No Logic Changes)
**Rationale:** Must land before/separately from bug fixes so each fix afterward has a trustworthy feedback loop, and so regressions introduced later are bisectable.
**Delivers:** Bare `except:` -> `except Exception:` + `logger.exception()` across plugin loading (`yapsy/PluginManager.py`) and protocol parsing paths; startup plugin-activation summary log; leveled `logging` module usage replacing prints. Verified by re-running Phase 1's harness before/after — activation results must be identical, only log output changes.
**Uses:** stdlib `logging` (STACK.md — no new dependency needed for baseline).
**Implements:** Loud fault-isolation pattern from ARCHITECTURE.md's yapsy integration boundary.
**Avoids:** Pitfall 3 (bare except silencing regressions), Pitfall 4 (plugin loader swallowing failures), Pitfall 5 (interleaving observability and bug-fix changes) — must explicitly exclude/redact credential variables per the Security Mistakes table to avoid amplifying the plaintext-password-logging bug.

### Phase 3: Import Strategy & Plugin Loading Fixes
**Rationale:** Direct fix for the confirmed ScotteCom/NBEcom `ModuleNotFoundError` root cause; depends on Phase 1's harness existing to prove the fix and Phase 2's logging to surface any residual failures loudly.
**Delivers:** Absolute imports at every yapsy-exec'd `plugins/<name>/__init__.py`; explicit relative imports (PEP 328) throughout protocol helper modules and packages; removal of all `sys.path.append` shims.
**Addresses:** Explicit relative imports (table stakes, FEATURES.md).
**Avoids:** Anti-Pattern 1/2 from ARCHITECTURE.md (sys.path shims, implicit Python-2-style imports).

### Phase 4: Protocol Module Hardening (Bytes/Str Semantics)
**Rationale:** Gated behind the harness (Phase 1) and clean import path (Phase 3) so each fix is verified by an actual round-trip test, not re-reading code.
**Delivers:** Line-by-line bytes/str audit and fix for `Scotteprotocol/` and `nbeprotocol/` (including the confirmed `protocol.py:144/146` bug); constructor-injectable `transport=` parameter added to `Protocol`/`Proxy` classes; round-trip encode/decode unit tests per frame type.
**Uses:** mypy scoped to these packages (STACK.md) as a static safety net.
**Implements:** Constructor-injectable transport pattern (ARCHITECTURE.md Pattern 3).
**Avoids:** Pitfall 2 (mechanical str/bytes substitution).

### Phase 5: Security Fixes
**Rationale:** Independent, low-complexity, high-value fixes that should not wait on the protocol work but do benefit from Phase 2's logging being in place first (to avoid amplifying the plaintext-password-logging bug).
**Delivers:** Hashed credential storage/comparison (stdlib PBKDF2 or argon2-cffi); removal of plaintext password from failed-login logs; `shell=False` for the Exec plugin readscript path.
**Addresses:** Hash + compare credentials, stop logging plaintext passwords, shell=False fix (all P1 table stakes, FEATURES.md).

### Phase 6: CI, Deployment & Cleanup Hardening
**Rationale:** Comes last because it depends on the test suite (Phase 1) existing to have something to enforce, and benefits from the codebase being stable (imports/protocol/security fixed) before locking down CI gates.
**Delivers:** GitHub Actions CI (Linux runner, pytest + ruff + scoped mypy); pinned dependency versions; graceful SIGTERM handling in both daemons; Docker healthchecks; `.py2bak` removal; documented Linux-only runtime.
**Addresses:** CI pipeline, pinned deps, graceful shutdown, healthchecks, cleanup items (all P1, FEATURES.md).

### Phase Ordering Rationale

- Test harness must exist before anything else is "verified" rather than "looked correct" (Pitfall 1, 6).
- Observability (Phase 2) must be separable from bug fixes (Phases 3-4) per Pitfall 5 — interleaving these destroys the ability to bisect regressions.
- Import fixes (Phase 3) must precede protocol semantic fixes (Phase 4) because until imports work, the protocol code isn't even reachable to test meaningfully.
- Security fixes (Phase 5) are architecturally independent of the protocol work and could be parallelized, but are sequenced after Phase 2 so the logging retrofit doesn't accidentally re-expose the password-logging bug it's meant to help fix.
- CI/deployment hardening (Phase 6) is last because it's the enforcement mechanism for everything upstream — it only has value once there's a real test suite and a codebase that passes it.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Protocol Module Hardening):** NBE's XTEA-encrypted UDP payloads and Scotte's checksum/byte-packing logic are domain-specific enough that per-frame-type test fixtures may need additional protocol-spec research during planning, not just general bytes/str guidance.
- **Phase 6 (CI, Deployment & Cleanup Hardening):** D-Bus test infra (`python-dbusmock`) and systemd watchdog integration were only MEDIUM-confidence researched (viable options exist but no single official pick) — worth a short research pass when that phase is planned.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Test Harness):** pytest/pytest-mock/pytest-socket/`loop://` are well-documented, HIGH-confidence, standard patterns.
- **Phase 2 (Exception Visibility):** Mechanical, well-understood logging retrofit, no novel research needed.
- **Phase 3 (Import Strategy):** PEP 328 relative imports and the yapsy exec-boundary rule are fully diagnosed already in ARCHITECTURE.md via direct code inspection.
- **Phase 5 (Security Fixes):** Password hashing (PBKDF2/stdlib) and `shell=False` are standard, well-established fixes with a working in-repo precedent (writescript path).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (tooling) / MEDIUM (exact pins) | Test tooling choices (pytest, ruff, mypy, loop://, pytest-socket) are well-established; exact version pins should be re-verified against PyPI at install time since research noted the field moves fast |
| Features | MEDIUM-HIGH | Grounded directly in this repo's own CONCERNS.md/STACK.md/PROJECT.md rather than generic best-practice lists; password-hashing algorithm guidance is MEDIUM (cross-checked across sources, not an official OWASP page directly) |
| Architecture | HIGH | Grounded in direct inspection of PellMon's own yapsy loader and package layout (file:line citations), cross-checked against PEP 328/420 |
| Pitfalls | HIGH | Codebase findings are static-analysis-verified against this exact repo; general Py2/3 porting pitfalls are HIGH per official porting docs; phase-sequencing recommendations are MEDIUM (synthesized from general legacy-refactoring practice) |

**Overall confidence:** HIGH

### Gaps to Address

- **Exact version pins for pytest/pytest-cov/ruff/mypy:** STACK.md flags these as fast-moving; verify against PyPI at implementation time rather than trusting the pinned floors as final.
- **D-Bus test infrastructure (python-dbusmock) and GPIO mocking (fake-rpi):** Only needed if those boundaries enter test scope; LOW-MEDIUM confidence, worth a quick spike before committing if the roadmap pulls them in.
- **Real hardware quirks (serial timing, actual XTEA key exchange, real UDP broadcast responses):** All protocol fixes in this research are mocked-I/O verified only; explicitly flag as "unit-verified, not hardware-verified" in documentation, per PITFALLS.md's technical-debt table — do not let this be mistaken for full verification later.
- **Non-root container hardening:** Conflicts with current `privileged: true` serial/D-Bus access; deferred as a differentiator/P3 item since it requires an architecture change not yet scoped.

## Sources

### Primary (HIGH confidence)
- Direct inspection of this repo: `src/Pellmonsrv/yapsy/PluginManager.py`, `src/Pellmonsrv/plugins/scottecom/__init__.py`, `src/Pellmonsrv/plugins/nbecom/__init__.py`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/PROJECT.md`
- PEP 328 (explicit relative imports), PEP 420 (namespace packages) — stable stdlib import semantics
- Python 3 `struct` module documentation — bytes/binary data handling

### Secondary (MEDIUM confidence)
- pyserial `loop://` URL handler docs and pyserial test suite reference
- pytest-socket, python-dbusmock official repos/READMEs
- ruff rules documentation (UP/B/F categories)
- "Common migration problems" (python3porting.com), "Conservative Python 3 Porting Guide" — str/bytes separation guidance
- OWASP-aligned password hashing consensus (2026 sources, cross-checked but not against an official OWASP page directly)
- systemd `sd_notify`/watchdog pattern (official man page mechanism, MEDIUM on which Python library to pick)

### Tertiary (LOW confidence)
- fake-rpi / RPi.GPIO mocking library options — multiple competing small libraries, not independently verified; needs a spike before committing if GPIO plugin enters test scope

---
*Research completed: 2026-09-17*
*Ready for roadmap: yes*
