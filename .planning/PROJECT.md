# PellMon Python 3 Migration

## What This Is

PellMon is a two-process Linux monitoring system for pellet-burning stoves: `pellmonsrv`, a daemon that talks to burner hardware over serial/TCP protocols (Scotte, NBE) and polls sensors (OWFS, 1-Wire, GPIO), and `pellmonweb`, a CherryPy web app that reads/writes that data over D-Bus and serves a live dashboard. It's mid-migration from Python 2 to Python 3 on the `python3-migration` branch — this project finishes that migration and gets the result production-ready.

## Core Value

The daemon must actually talk to real burner hardware through its protocol plugins (Scotte, NBE) under Python 3 — a port where only the core modules import but the hardware plugins silently fail isn't done, no matter what the commit messages say.

## Requirements

### Validated

- ✓ Plugin-based daemon architecture (yapsy plugin discovery, D-Bus IPC, in-memory Item database, RRD persistence) — existing, core modules import cleanly under Python 3.14/3.13 per `test-imports.py`
- ✓ CherryPy + Mako web frontend (dashboard, websockets, graphs, log viewer, config UI) — existing, imports cleanly under Python 3
- ✓ Docker Compose deployment path (Debian bookworm-slim, two-service D-Bus setup) — existing, already built for the Python 3 port

### Active

- [ ] Fix broken implicit relative imports in `Scotteprotocol/` and `scottecom` plugin so ScotteCom actually loads under Python 3 (`src/Scotteprotocol/__init__.py:2`, `frames.py:19`, `datamap.py:21`, `protocol.py:25,216`, `scottecom/menus.py:19`)
- [ ] Fix broken implicit relative imports in `nbecom/nbeprotocol/` so NBEcom actually loads under Python 3 (`nbeprotocol/protocol.py:27,28,30`, `frames.py:21`)
- [ ] Fix bytes/str `TypeError` in NBEcom `Proxy.get()` (`nbeprotocol/protocol.py:144,146`)
- [ ] Fix `unbuffered text I/O` crash in daemonizer (`src/Pellmonsrv/daemon.py:69`)
- [ ] Fix leftover Python 2 `unicode()` call in Calculate plugin (`src/Pellmonsrv/plugins/calculate/__init__.py:351`)
- [ ] Remove `.py2bak` backup files once each module's port is confirmed stable
- [ ] Add automated test coverage for protocol/hardware modules (Scotteprotocol and nbeprotocol frame encode/decode round-trips, mocked serial/UDP I/O) so plugin activation isn't only verified by hand
- [ ] Fix plaintext password logging on failed web login (`src/Pellmonweb/auth.py:147,150`)
- [ ] Hash stored/compared web-auth credentials instead of plaintext comparison (`src/Pellmonweb/auth.py`)
- [ ] Fix shell-injection surface in Exec plugin readscript path — use `shell=False` like the writescript path already does (`src/Pellmonsrv/plugins/exec/__init__.py:86`)
- [ ] Standardize on explicit relative imports across `src/`, removing the inconsistent `sys.path.append` shims left from the partial port
- [ ] Replace bare `except:` clauses with `except Exception:` + logging in the most failure-critical paths (plugin loading, protocol parsing) so import/runtime failures are visible instead of silently swallowed
- [ ] Document/confirm Linux-only production runtime (D-Bus, GLib, rrdtool, serial, GPIO) since the server cannot start on Windows

### Out of Scope

- Windows production support — D-Bus/GLib/rrdtool/serial/GPIO are Linux-only dependencies by design; Windows stays a syntax-checking dev environment only
- New hardware protocol support (only hardening the existing Scotte and NBE protocols is in scope)
- Full rewrite of the Autotools/legacy init-script deployment path — Docker Compose is the supported deployment target; legacy path stays as-is
- Full auth system overhaul (SSO, multi-user roles) — only fixing the plaintext password logging/storage issues, not redesigning auth

## Context

- Codebase mapped via `/gsd:map-codebase` — see `.planning/codebase/` (STACK.md, ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, INTEGRATIONS.md, CONCERNS.md) for full detail.
- Recent commit `94c9b67` ("Porting to pyhton 3 complete") and docs (`PHASE3-COMPLETE.md`, `MIGRATION-SUMMARY.md`) claim the port is done, but verification was limited to `test-imports.py`, which only imports 4 top-level modules and never exercises the plugin system. The hardware/protocol plugins (ScotteCom, NBEcom) are demonstrably broken at import time — see Concerns audit.
- No automated test suite exists (`test-imports.py` is an ad hoc smoke script, not pytest/unittest, not wired into CI).
- Hardware plugins (Scotte serial burner, NBE UDP burner, OWFS/1-Wire, Raspberry Pi GPIO) require physical devices and can't be fully exercised in this dev environment — protocol-level unit tests with mocked I/O are the practical path to confidence.

## Constraints

- **Tech stack**: Python 3.13/3.14, CherryPy, Mako, D-Bus/GLib, rrdtool, pyserial — production runtime is Linux-only (Debian bookworm-slim container or Raspberry Pi/bare-metal Linux); Windows is dev-only for syntax porting
- **Hardware**: ScotteCom and NBEcom protocol fixes can't be fully runtime-verified without physical burner hardware — testing strategy must rely on mocked/unit-level verification for those paths
- **Compatibility**: `.py2bak` files exist as a rollback reference per already-migrated module; only remove once that module's Python 3 behavior is confirmed correct

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Treat "migration complete" commit as unverified for plugin code | `test-imports.py` never imports plugin packages; ScotteCom/NBEcom are confirmed broken by static analysis | — Pending |
| Production-readiness scope includes security fixes (password logging, plaintext auth, shell injection) | User asked to get the migration "production-ready," and these are pre-existing issues surfaced during codebase mapping that block that goal | — Pending |
| Add mocked/unit-level protocol tests rather than requiring physical hardware for verification | No CI or test suite exists today; hardware isn't available in this dev environment | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-17 after initialization*
