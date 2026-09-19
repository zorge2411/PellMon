# Phase 1: Test Harness & Verification Infrastructure - Research

**Researched:** 2026-09-17
**Domain:** pytest test harness for a hardware-protocol Python daemon (serial/UDP), no CI hardware; SQLite keyval store; CherryPy form-auth module
**Confidence:** HIGH (tooling versions, file-level findings — all read directly from this repo) / MEDIUM (exact conftest fixture shape — design recommendation, not yet executed in this repo)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Test layout & tooling
- **D-01:** New top-level `tests/` directory mirroring `src/` package structure (e.g. `tests/Pellmonsrv/test_database.py`, `tests/Pellmonweb/test_auth.py`), not tests colocated inside `src/`. Standard pytest convention; keeps `src/` clean for the Autotools/Docker packaging that already treats it as the install tree.
- **D-02:** Test dependencies (`pytest`, `pytest-mock`, `pytest-socket`, `pytest-cov`) go in a new `requirements-dev.txt`, not the main `requirements.txt`. Keeps the production Docker image (`Dockerfile` installs from `requirements.txt`) lean — matches the existing `requirements.txt` / `requirements-wsl.txt` split pattern already used in this repo.
- **D-03:** Pytest config lives in a new `pytest.ini` at repo root (no `pyproject.toml` exists in this repo, so no reason to introduce one just for pytest config).

### Import-check strategy
- **D-04:** The broadened import-check (TEST-02) is a proper pytest test module (`tests/test_plugin_imports.py`), not a standalone script. It dynamically discovers plugins by reading every `src/Pellmonsrv/plugins/*.pellmon-plugin` descriptor file (INI format, `[Core] Module = <name>`) and asserts each corresponding plugin module imports without error — this way it runs as part of the same `pytest` invocation and the same CI gate as everything else, with no separate script to maintain. The existing root `test-imports.py` can stay as-is (it's out of this phase's scope to remove it) but is superseded as the source of truth by the new pytest-based check.

### Hardware I/O isolation
- **D-05:** `pytest-socket` is enabled globally via `addopts = --disable-socket` in `pytest.ini`, so any test that makes a real (unmocked) network call fails loudly by default (satisfies the phase's 4th success criterion). Tests that need mocked serial I/O use pyserial's own `loop://` URL handler (no extra dependency); tests that need mocked UDP use `unittest.mock`/`pytest-mock` — no real socket is opened even for tests, so `--disable-socket` stays on with no per-test opt-outs expected in this phase.

### Claude's Discretion
- Exact test file naming/organization within `tests/Pellmonsrv/plugins/` for the Scotte and NBE protocol round-trip tests (deferred to planning/execution — Phase 4 is where the actual protocol round-trip test *content* gets written against real bug fixes; this phase only needs the harness and mock fixtures to exist and be demonstrated working, e.g. via a smoke-level round-trip test).
- Whether `conftest.py` fixtures for mocked serial/UDP live at `tests/conftest.py` (shared) or a more scoped location — planner/executor can decide based on how many test modules end up needing them.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope. (mypy/ruff adoption, CI wiring, and actual protocol bug fixes are already scoped to their own later phases per ROADMAP.md and were not re-litigated here.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| TEST-01 | Developer can run a pytest suite locally that exercises protocol encode/decode logic without physical hardware attached (mocked serial via pyserial `loop://`, mocked UDP sockets) | Patterns 3-4 (loop:// serial fixture, mocked UDP socket fixture); Pitfall 2 explains why real `Scotteprotocol`/`nbeprotocol` round-trips can't be wired in yet (Phase 4 scope) and scopes this phase's demonstration to self-contained fixtures |
| TEST-02 | Developer can run a broadened import-check that imports every plugin package (not just the 4 core modules), so a plugin with broken imports fails the check instead of being silently skipped | Pattern 1 (`.pellmon-plugin` INI discovery via configparser), Pattern 2 (two-layer import check), Pitfall 1 (NBEcom's deferred-import false-pass trap and how to catch it) |
| TEST-03 | Developer can run a pytest suite covering `database.py` (SQLite keyval get/set/init incl. fallback table-creation path) and `Pellmonweb/auth.py` (credential check, session login flow) | Pattern 5 (`Keyval_storage` tests incl. `OperationalError` fallback path), Pattern 6 (`AuthController` tests via monkeypatched `cherrypy.request`/`session`, no live server), Pitfall 3 (bare-except re-raise gotcha in `check_credentials()`) |
</phase_requirements>

## Summary

This phase adds `pytest` + supporting plugins and a `tests/` tree to a repo that currently has zero automated tests (only `test-imports.py`, a print/try-except smoke script). All four target packages/files were read directly from the repo for this research: `src/Pellmonsrv/database.py`, `src/Pellmonweb/auth.py`, a sample `.pellmon-plugin` descriptor (`scottecom.pellmon-plugin`), and the two hardware-protocol constructors (`Scotteprotocol/protocol.py`, `nbecom/nbeprotocol/protocol.py`).

Two codebase-specific traps were found that materially change what the planner should ask for, both important enough to be called out up front:

1. **The NBEcom plugin's broken import is *not* triggered by a plain `import Pellmonsrv.plugins.nbecom`.** Unlike ScotteCom (whose broken import fires at module level via `scottecom.py:19 from Scotteprotocol import Protocol`), NBEcom's `from nbeprotocol.protocol import Proxy` is deferred inside `nbecomplugin.activate()` (`plugins/nbecom/__init__.py:38`). A naive "import every plugin module" check will **silently pass** for NBEcom today, contradicting the phase's own success criterion. The import-check test must additionally import `Pellmonsrv.plugins.nbecom.nbeprotocol.protocol` directly (see Pitfall 1 and Code Examples) to catch this.
2. **Neither `Scotteprotocol.Protocol` nor `nbeprotocol.Proxy` has a constructor-injectable transport today** — both hard-construct `serial.Serial()` / `socket.socket()` inside `__init__` with no seam for mocking (confirmed by reading the source). Per `REQUIREMENTS.md` (`PROTO-04`) and `.planning/ROADMAP.md`, adding that seam is explicitly Phase 4 scope, not this phase. This phase's TEST-01 round-trip demonstration therefore cannot exercise the *real* `Protocol`/`Proxy` classes yet — it must demonstrate the `loop://` / mocked-UDP-socket mechanism stands alone and is ready for Phase 4 to wire in, using self-contained frame bytes rather than importing the (currently import-broken) `Scotteprotocol`/`nbeprotocol` packages.

**Primary recommendation:** Add `pytest`, `pytest-mock`, `pytest-socket`, `pytest-cov` (all version-verified live against PyPI this session, see Standard Stack) via `requirements-dev.txt`; add `pytest.ini` at repo root with `pythonpath = src` and `addopts = --disable-socket`; build `tests/` mirroring `src/`; write the plugin import-check as two layers (top-level module import + explicit deferred-import probe for nbecom) so it actually satisfies the phase's stated success criteria against the current, partially-broken codebase.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Test execution/config (`pytest.ini`) | Dev tooling (repo root) | — | Not part of `src/` install tree; must not affect Autotools/Docker packaging |
| Plugin import discovery (dynamic `.pellmon-plugin` scan) | Test harness (`tests/`) | Database/Storage (reads `src/Pellmonsrv/plugins/*.pellmon-plugin` INI files) | Discovery source is the on-disk descriptor files already used by yapsy at runtime; the test reads the same files, it doesn't reimplement yapsy |
| Mocked serial I/O (`loop://`) | Test harness (`tests/conftest.py`) | — | pyserial's own supported loopback mechanism, zero new dependency |
| Mocked UDP socket | Test harness (`tests/conftest.py`) | — | `unittest.mock`/`pytest-mock`, no real socket opened |
| `database.py` keyval store verification | Backend/Daemon (`src/Pellmonsrv/database.py`) | Database/Storage (SQLite file) | Test exercises the real `Keyval_storage` class against a real (temp-file) SQLite DB — no mocking needed, SQLite itself is the test double |
| `Pellmonweb/auth.py` credential/session verification | Web/API layer (`src/Pellmonweb/auth.py`) | — | Tested via direct instantiation + monkeypatched `cherrypy.request`/`cherrypy.session`, not a live CherryPy server (see Code Examples) |
| Real-socket-call guardrail | Test harness (`pytest-socket` global `--disable-socket`) | — | Enforced at the pytest-plugin layer, applies uniformly to every test unless explicitly opted out |

## Standard Stack

### Core

| Library | Version (verified via `pip index versions`, 2026-09-17) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | `9.1.1` latest on PyPI; **`9.0.2` already installed** in this repo's active Python 3.14 environment | Test runner | De facto standard; fixture model + `pythonpath` ini option fits this project's `src/`-layout-without-packaging-metadata setup exactly |
| pytest-mock | `3.15.1` (latest, and **already installed** at 3.15.1) | `mocker` fixture over `unittest.mock` | Used for the mocked UDP socket and for monkeypatching `cherrypy.request`/`cherrypy.session` in auth tests |
| pytest-socket | `0.8.1` (latest; installed this session via `slopcheck install`, confirmed working) | Blocks real network calls | Directly implements the phase's 4th success criterion (`--disable-socket` in `addopts`) |
| pytest-cov | `7.1.0` (latest; installed this session) | Coverage reporting | Not required by any of TEST-01/02/03 literally, but `pytest-cov>=6.0` was already recommended in `.planning/research/STACK.md`; cheap to add now, `--cov` can be left out of default `addopts` if the planner wants a lean first cut |

All four packages were checked with `python -m slopcheck install pytest pytest-mock pytest-socket pytest-cov` this session — see Package Legitimacy Audit below. `pytest` and `pytest-mock` were already present in this repo's Python 3.14 venv (`pip list`); `pytest-socket` and `pytest-cov` were newly installed and confirmed importable.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyserial `loop://` URL handler | ships with `pyserial==3.5` — **already installed and already a pinned dependency** in `requirements.txt` (`pyserial>=3.5`) | In-process software loopback serial port | `serial.serial_for_url('loop://')` — use for any test that needs an actual open/readable/writable `Serial`-compatible object without a real device |
| `unittest.mock.MagicMock` (stdlib, via `pytest-mock`'s `mocker`) | stdlib | Mock `socket.socket` for UDP tests | Patch `socket.socket` (or the already-constructed `Proxy.s` attribute, once Phase 4 adds injection) with a `MagicMock` exposing `sendto`/`recvfrom` |
| `configparser` (stdlib) | stdlib | Parse `.pellmon-plugin` INI descriptors | Same library already used elsewhere in this codebase for `pellmon.conf` — no new dependency, matches established pattern (see `.pellmon-plugin` format below) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyserial `loop://` | third-party `dummyserial`/`Mock.Serial` packages | Only worth it for scripted stateful byte-for-byte response simulation across many burner quirks — not needed for Phase 1's harness-only scope; adds a dependency with no immediate payoff |
| Direct `AuthController` instantiation + monkeypatched `cherrypy.request` | `cherrypy.test.helper.CPWebCase` (spins a real embedded CherryPy server per test) | `CPWebCase` is heavier (starts an actual HTTP server thread per test class) and is CherryPy's own recommended integration-test tool, but the phase's own CONTEXT.md explicitly favors testing `auth.py`'s logic "without needing physical burner hardware" — the lighter monkeypatch approach is faster and sufficient for TEST-03's stated scope (credential check + session flow), and avoids port-binding flakiness in CI |

**Installation:**
```bash
# requirements-dev.txt (new file, per CONTEXT.md D-02)
pytest>=9.0,<10
pytest-mock>=3.15
pytest-socket>=0.8
pytest-cov>=7.1

pip install -r requirements-dev.txt
```

**Version verification:** Ran live against PyPI this session:
```
python -m pip index versions pytest         # 9.1.1 latest, 9.0.2 installed
python -m pip index versions pytest-mock    # 3.15.1 latest and installed
python -m pip index versions pytest-socket  # 0.8.1 latest
python -m pip index versions pytest-cov     # 7.1.0 latest
```
No training-data guessing was needed — all four are `[VERIFIED: PyPI registry]` for both existence and current version as of 2026-09-17.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pytest | PyPI | 15+ yrs, foundational project | very high | github.com/pytest-dev/pytest | [OK] | Approved |
| pytest-mock | PyPI | 10+ yrs | very high | github.com/pytest-dev/pytest-mock | [OK] | Approved |
| pytest-socket | PyPI | maintained since ~2019 | moderate/high | github.com/miketheman/pytest-socket | [OK] | Approved |
| pytest-cov | PyPI | 10+ yrs | very high | slopcheck reported "No source repository linked" for the PyPI metadata it fetched, but this is the well-known `pytest-dev/pytest-cov` package (cross-verified: already listed in `.planning/research/STACK.md` project research, and `pip index versions` shows the expected long, dense release history 0.6→7.1.0 matching the real project) | [OK] | Approved — metadata gap is a PyPI packaging quirk, not a legitimacy signal; treat as `[CITED: pytest-cov.readthedocs.io]` for the source-repo claim specifically |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

`slopcheck` ran successfully this session (`python -m slopcheck install pytest pytest-mock pytest-socket pytest-cov`), so none of the above need the `[ASSUMED]`-fallback / mandatory `checkpoint:human-verify` gate — all four are `[VERIFIED: PyPI registry]` per the package-name-provenance rule (discovered via official PyPI + this project's prior research, and passing slopcheck).

## Architecture Patterns

### System Architecture Diagram

```
pytest invocation (repo root, pytest.ini: pythonpath = src)
        │
        ├─► tests/test_plugin_imports.py
        │      │
        │      ├─► scan src/Pellmonsrv/plugins/*.pellmon-plugin (configparser)
        │      │        → list of Module names: calculate, cleaning, ..., scottecom, nbecom, ...
        │      │
        │      ├─► for each Module: importlib.import_module(f"Pellmonsrv.plugins.{Module}")
        │      │        → scottecom FAILS HERE (module-level `from Scotteprotocol import Protocol`)
        │      │        → nbecom SUCCEEDS HERE (import deferred to activate())
        │      │
        │      └─► explicit deferred-import probe:
        │               importlib.import_module("Pellmonsrv.plugins.nbecom.nbeprotocol.protocol")
        │               → nbecom's real brokenness surfaces HERE (`from frames import ...` bare import)
        │
        ├─► tests/Pellmonsrv/test_database.py
        │      └─► real sqlite3 file in tmp_path → Keyval_storage(dbfile) → readval/writeval,
        │              plus a pre-corrupted/missing-table temp DB to hit the OperationalError
        │              fallback CREATE TABLE path (database.py:153-156)
        │
        ├─► tests/Pellmonweb/test_auth.py
        │      └─► AuthController(credentials, lookup) instantiated directly
        │              cherrypy.request / cherrypy.session monkeypatched (no real HTTP server)
        │              → check_credentials() success/failure, login()/logout() session mutation
        │
        └─► tests/Pellmonsrv/test_mocked_transport_smoke.py  (demonstrates the harness, no
               dependency on the currently-broken Scotteprotocol/nbeprotocol packages)
               ├─► serial.serial_for_url('loop://') fixture: write bytes, read them back
               └─► mocker.patch('socket.socket') fixture: sendto/recvfrom via MagicMock

pytest-socket --disable-socket (pytest.ini addopts) wraps the ENTIRE run:
  any test that makes a real socket() call (not routed through the mocker.patch above)
  fails immediately with SocketBlockedError, regardless of which test file it's in.
```

### Recommended Project Structure
```
pytest.ini                          # NEW — root config, pythonpath=src, --disable-socket
requirements-dev.txt                # NEW — pytest + plugins (D-02)
tests/
├── conftest.py                     # shared fixtures: loop:// serial, mocked UDP socket,
│                                    #   cherrypy.request/session monkeypatch helper
├── test_plugin_imports.py          # TEST-02: dynamic .pellmon-plugin scan + import check
├── Pellmonsrv/
│   ├── test_database.py            # TEST-03 (database.py half)
│   └── plugins/                    # placeholder dir; Phase 4 fills in Scotte/NBE round-trip
│       └── test_mocked_transport_smoke.py   # TEST-01 smoke demo (self-contained, no
│                                             #   dependency on currently-broken protocol pkgs)
└── Pellmonweb/
    └── test_auth.py                # TEST-03 (auth.py half)
```
(Per CONTEXT.md D-01/D-05, exact file naming inside `tests/Pellmonsrv/plugins/` and whether `conftest.py` is single/shared is left to planner/executor discretion — the above is a concrete starting proposal, not a lock.)

### Pattern 1: Reading `.pellmon-plugin` descriptors for dynamic plugin discovery

**What:** Every plugin ships a sibling INI file, e.g. `src/Pellmonsrv/plugins/scottecom.pellmon-plugin`:
```ini
[Core]
Name = ScotteCom
Module = scottecom

[Documentation]
Author = Anders Nylund
Version = 0.1
Website = http://github.com/motoz/PellMon
Description = A plugin for communication with a NBE scotte/woody/bio comfort pellet burner
```
**When to use:** This is the enumeration source for TEST-02 — 15 files exist today at `src/Pellmonsrv/plugins/*.pellmon-plugin` (confirmed via glob this session): `calculate`, `cleaning`, `consumption`, `customalarms`, `exec`, `heatingcircuit`, `nbecom`, `onewire`, `openweathermap`, `owfs`, `pelletcalc`, `raspberrygpio`, `scottecom`, `silolevel`, `testplugin`.

**Example:**
```python
# Source: read directly from src/Pellmonsrv/yapsy/PluginManager.py locatePlugins()
# (this codebase's own runtime loader uses the same [Core] Module = ... convention)
import configparser
import glob
import os

PLUGIN_DIR = os.path.join("src", "Pellmonsrv", "plugins")

def discover_plugin_modules():
    modules = []
    for descriptor in sorted(glob.glob(os.path.join(PLUGIN_DIR, "*.pellmon-plugin"))):
        cp = configparser.ConfigParser()
        cp.read(descriptor)
        modules.append(cp.get("Core", "Module"))
    return modules
```

### Pattern 2: Two-layer plugin import check (catches both ScotteCom's eager failure and NBEcom's deferred failure)

**What:** A plain `importlib.import_module("Pellmonsrv.plugins.<name>")` per discovered module, PLUS one hardcoded deferred-import probe for `nbecom` specifically (see Pitfall 1 for why this is required).

**Example:**
```python
# tests/test_plugin_imports.py
import importlib
import pytest
from .conftest import discover_plugin_modules  # or inline the helper above

@pytest.mark.parametrize("module_name", discover_plugin_modules())
def test_plugin_module_imports(module_name):
    """Every plugin listed in a .pellmon-plugin descriptor must import cleanly.

    NOTE: scottecom is EXPECTED to fail here today (broken relative imports in
    Scotteprotocol/, tracked as IMPORT-01, fixed in Phase 3). This assertion is
    intentional and documents current state — do not xfail/skip it silently;
    let it report FAIL so the gap stays visible (per CONTEXT.md phase note).
    """
    importlib.import_module(f"Pellmonsrv.plugins.{module_name}")


def test_nbecom_deferred_import_is_broken_today():
    """nbecom/__init__.py imports nbeprotocol.protocol only inside activate(),
    so test_plugin_module_imports("nbecom") above passes even though the plugin
    is non-functional (confirmed: nbeprotocol/protocol.py:27 `from frames import
    Request_frame, Response_frame` — bare import, ModuleNotFoundError). This
    probe imports the nested module directly to surface that failure.
    Expected to FAIL until Phase 3 (IMPORT-02) fixes it.
    """
    importlib.import_module("Pellmonsrv.plugins.nbecom.nbeprotocol.protocol")
```

### Pattern 3: `loop://` mocked serial fixture

```python
# tests/conftest.py
import pytest
import serial

@pytest.fixture
def loop_serial():
    """In-process loopback serial port — anything written is immediately
    available to read back. Use for tests that need a live Serial-compatible
    object without a physical /dev/ttyUSB0 device.
    Source: pyserial docs, https://pyserial.readthedocs.io/en/latest/url_handlers.html#loop
    """
    ser = serial.serial_for_url("loop://", timeout=1)
    yield ser
    ser.close()
```
```python
# tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py
def test_loop_serial_roundtrip(loop_serial):
    loop_serial.write(b"\x02TEST\x03")
    loop_serial.flush()
    assert loop_serial.read(7) == b"\x02TEST\x03"
```
**Why self-contained today:** `Scotteprotocol/__init__.py` currently fails to import at all (`from protocol import Protocol` — needs `.protocol`, tracked as IMPORT-01). This test deliberately does NOT `import Scotteprotocol` — it proves the `loop://` mechanism itself works, ready for Phase 4 to wire into `Protocol.__init__` once that class gets a constructor-injectable transport (PROTO-04).

### Pattern 4: Mocked UDP socket fixture

```python
# tests/conftest.py
@pytest.fixture
def mocked_udp_socket(mocker):
    """Patches socket.socket so no real UDP packet is ever sent.
    Configure .recvfrom.return_value / .recvfrom.side_effect per test.
    """
    mock_socket_cls = mocker.patch("socket.socket")
    mock_sock = mock_socket_cls.return_value
    mock_sock.recvfrom.return_value = (b"", ("0.0.0.0", 0))
    return mock_sock
```
```python
def test_udp_send_uses_mock_not_real_network(mocked_udp_socket):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"ping", ("127.0.0.1", 1920))
    mocked_udp_socket.sendto.assert_called_once_with(b"ping", ("127.0.0.1", 1920))
```
This is also naturally backstopped by `pytest-socket --disable-socket`: if a test forgets to apply `mocked_udp_socket` and code path falls through to a real `socket.socket()` call, `pytest-socket` raises `SocketBlockedError` immediately instead of the test hanging on a real UDP broadcast with no burner on the LAN.

### Pattern 5: `database.py` keyval store — what to actually test

`src/Pellmonsrv/database.py:147-203` (`Keyval_storage`) is a plain sqlite3-backed class with no mocking needed — test it against a real temp-file SQLite DB:

```python
# tests/Pellmonsrv/test_database.py
import sqlite3
from Pellmonsrv.database import Keyval_storage

def test_init_creates_keyval_table(tmp_path):
    dbfile = str(tmp_path / "test.db")
    Keyval_storage(dbfile)  # constructor itself creates the table (database.py:153-156)
    conn = sqlite3.connect(dbfile)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM keyval")  # must not raise
    conn.close()

def test_writeval_readval_roundtrip(tmp_path):
    store = Keyval_storage(str(tmp_path / "test.db"))
    store.writeval("mykey", value="42")
    assert store.readval("mykey") == "42"

def test_init_fallback_path_when_table_missing(tmp_path):
    """Exercises database.py:153-156's `except sqlite3.OperationalError` ->
    CREATE TABLE fallback by pointing Keyval_storage at a DB file that has
    some OTHER schema (so SELECT ... FROM keyval genuinely raises
    OperationalError, not just 'file doesn't exist yet' which also works but
    doesn't prove the except branch specifically)."""
    dbfile = str(tmp_path / "other_schema.db")
    conn = sqlite3.connect(dbfile)
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()
    Keyval_storage(dbfile)  # must hit OperationalError -> CREATE TABLE keyval, not raise
    conn = sqlite3.connect(dbfile)
    conn.execute("SELECT value FROM keyval")  # now exists
    conn.close()
```
Note `readval()` returns the string `'error'` (not an exception) on failure — `database.py:169-171` catches `Exception` and does `print(e); return 'error'`. A test for "reading a nonexistent key" should assert `== 'error'`, not `pytest.raises(...)` — this is existing, intentional-if-crude behavior, not a bug to "fix" in this phase (fixing print()→logger is OBS-03, Phase 2 scope).

### Pattern 6: `Pellmonweb/auth.py` — testing without a real CherryPy server

`AuthController.__init__(self, credentials, lookup)` (`auth.py:121-123`) takes plain Python objects — no CherryPy machinery required to instantiate it. But `check_credentials()` (`auth.py:139-151`) and `login()`/`logout()` (`auth.py:153-177`) touch `cherrypy.log`, `cherrypy.request.headers`, `cherrypy.session`, `cherrypy.request.script_name` — all CherryPy thread-locals that raise `AttributeError` if accessed with no active request. **Important, codebase-specific gotcha:** `check_credentials()`'s failure branch calls `cherrypy.log(...cherrypy.request.headers["Remote-Addr"]...)` inside a bare `except:` — if that `cherrypy.log` call itself raises (e.g. because `cherrypy.request` isn't set up), the bare `except:` catches it, then the `except` block calls the **same** `cherrypy.log(...)` line again, which raises a **second**, uncaught time. So testing the failure path requires mocking `cherrypy.request`/`cherrypy.log` — you cannot call `check_credentials()` with wrong credentials outside a request context without doing so.

```python
# tests/conftest.py
@pytest.fixture
def cherrypy_request_ctx(mocker):
    """Monkeypatches enough of cherrypy's thread-local request/session state
    for auth.py's AuthController methods to run outside a real HTTP server."""
    import cherrypy
    fake_request = mocker.MagicMock()
    fake_request.headers = {"Remote-Addr": "127.0.0.1"}
    fake_request.script_name = ""
    mocker.patch.object(cherrypy, "request", fake_request)
    mocker.patch.object(cherrypy, "session", {})
    mocker.patch.object(cherrypy, "log")
    return fake_request
```
```python
# tests/Pellmonweb/test_auth.py
from Pellmonweb.auth import AuthController, SESSION_KEY

def test_check_credentials_success(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    assert ctrl.check_credentials("alice", "s3cret") is None

def test_check_credentials_failure(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    result = ctrl.check_credentials("alice", "wrong")
    assert result == "Incorrect username or password."

def test_login_sets_session_on_success(cherrypy_request_ctx):
    import cherrypy
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    with pytest.raises(cherrypy.HTTPRedirect):
        ctrl.login(username="alice", password="s3cret", from_page="/")
    assert cherrypy.session[SESSION_KEY] == "alice"
```
`login()` raises `cherrypy.HTTPRedirect` on success (`auth.py:167`) — that's existing control flow, not an error; assert it with `pytest.raises`.

**Security note for the planner (do not fix in this phase, but the test SHOULD document it):** `check_credentials()`'s failure branch logs the raw password (`auth.py:147,150` — `password[:50]`) via `cherrypy.log`. `SEC-01` (Phase 5) fixes this. A TEST-03 test can assert `check_credentials()`'s *return value* without needing to assert anything about the (currently insecure) log content — don't accidentally lock in "logs the password" as expected behavior via an overly literal assertion on `cherrypy.log.call_args`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Blocking real network calls in tests | A custom `socket.socket` monkeypatch applied globally in every test file | `pytest-socket` with `addopts = --disable-socket` | One-line global enforcement, per-test opt-out via `@pytest.mark.enable_socket` if ever needed, well-maintained (`miketheman/pytest-socket`, not the older abandoned fork) |
| Fake serial port for loopback testing | A custom `FakeSerial` class implementing pyserial's API surface | `serial.serial_for_url('loop://')` | Already ships with the `pyserial>=3.5` dependency this project has; zero drift risk vs. real `Serial` API since it's pyserial's own code, not a reimplementation |
| Plugin enumeration for the import-check | Hardcoded list of plugin module names in the test file | `configparser` scan of `*.pellmon-plugin` files (Pattern 1 above) | New plugins added later are automatically covered; matches the same discovery convention yapsy itself uses at runtime |
| CherryPy request context for auth tests | Spinning up a real `cherrypy.engine.start()` + HTTP client per test | Direct `AuthController` instantiation + `mocker.patch.object(cherrypy, "request", ...)` | Faster, no port binding/flakiness, and CONTEXT.md scope is "credential check, session login flow" logic — not HTTP routing, which is out of TEST-03's stated scope |

**Key insight:** Every piece of "hardware/hard-to-test" surface in this phase already has a first-party, zero-new-dependency answer (pyserial's own `loop://`, stdlib `unittest.mock`, stdlib `configparser`) — the only genuinely new dependencies needed are the two pytest plugins (`pytest-socket`, `pytest-cov`) that add cross-cutting enforcement/reporting pytest itself doesn't provide.

## Common Pitfalls

### Pitfall 1: A naive "import every plugin" check gives NBEcom a false pass
**What goes wrong:** `importlib.import_module("Pellmonsrv.plugins.nbecom")` succeeds today even though NBEcom is confirmed broken (`ModuleNotFoundError` per `CONCERNS.md`), because the broken `from nbeprotocol.protocol import Proxy` line lives inside `nbecomplugin.activate()` (`plugins/nbecom/__init__.py:38`), not at module import time.
**Why it happens:** `nbecom/__init__.py` only defines the `nbecomplugin` class and appends its own directory to `sys.path` at import time (line 28) — no protocol-package import happens until `.activate()` runs.
**How to avoid:** Add the explicit second-layer probe from Pattern 2 (`import Pellmonsrv.plugins.nbecom.nbeprotocol.protocol` directly) as its own test, not folded into the parametrized loop, so it's visibly named and documented.
**Warning signs:** If TEST-02's suite reports "14/15 plugins import cleanly, only scottecom fails" — that's the false-pass signature; NBEcom must also show as failing, per this phase's explicit acceptance criterion #2.

### Pitfall 2: `Scotteprotocol` and `nbeprotocol` cannot be round-trip-tested yet — don't try to force it this phase
**What goes wrong:** Attempting to write "real" Scotte/NBE frame encode/decode tests this phase either (a) can't run at all because `Scotteprotocol/__init__.py` itself fails to import (broken relative imports, confirmed by reading the source), or (b) requires constructing `Protocol(device, version_string)` / `Proxy(password, ...)`, both of which hard-open a real `serial.Serial()`/`socket.socket()` in `__init__` with no injection seam — confirmed by reading `Scotteprotocol/protocol.py:43` and `nbeprotocol/protocol.py:48`.
**Why it happens:** The constructor-injectable transport seam is explicitly out of scope for this phase — it's `PROTO-04`, scheduled for Phase 4 alongside the actual bug fixes, per `REQUIREMENTS.md` and `ROADMAP.md`.
**How to avoid:** Scope this phase's TEST-01 "smoke-level round-trip test" (per CONTEXT.md Claude's Discretion) to a self-contained demonstration of the `loop://`/mocked-socket fixtures (Patterns 3-4) that does NOT import `Scotteprotocol` or `nbeprotocol`. Leave the fixtures ready for Phase 4 to plug in once the transport seam exists.
**Warning signs:** A plan task that says "test `Scotteprotocol.Protocol.parseFrame()` round-trip using `loop://`" this phase is scope creep into Phase 4 and will likely also fail outright today due to the import-broken package.

### Pitfall 3: `check_credentials()`'s failure path re-raises if `cherrypy.request` isn't mocked
**What goes wrong:** Calling `AuthController.check_credentials()` with wrong credentials, outside a real CherryPy request/mock, raises an uncaught exception instead of returning the expected `"Incorrect username or password."` string — because the bare `except:` block's own recovery code (`cherrypy.log(...cherrypy.request.headers...)`) throws again when `cherrypy.request` has no active thread-local state.
**Why it happens:** See Pattern 6 above — this is existing, unfixed behavior in `auth.py:139-151`, not something to patch in this phase (only `logging.getLogger` conversion and password-logging removal are in scope, Phases 2/5).
**How to avoid:** Always use the `cherrypy_request_ctx` fixture (Pattern 6) when calling any `AuthController` method in tests.
**Warning signs:** `AttributeError: 'NoneType' object has no attribute ...` or similar bubbling up from inside a `check_credentials()` test that didn't mock `cherrypy.request`.

### Pitfall 4: `pytest.ini` `pythonpath` needs pytest ≥7 (already satisfied, but note for reproducibility)
**What goes wrong:** Using `sys.path.insert(0, 'src')` hacks scattered across test files (mirroring `test-imports.py`'s own pattern) instead of pytest's built-in `pythonpath` ini option.
**Why it happens:** No `setup.py`/`pyproject.toml`/`src`-layout packaging metadata exists in this repo (confirmed — none of `setup.py`, `pyproject.toml`, `setup.cfg` exist), so there's no `pip install -e .` path to make `Pellmonsrv`/`Pellmonweb` importable without a path hack of some kind.
**How to avoid:** Use `pytest.ini`'s `[pytest] pythonpath = src` (supported since pytest 7.0, confirmed available — installed pytest is 9.0.2) rather than per-file `sys.path` manipulation; this is centralized, and doesn't leak into non-test code.
**Warning signs:** `ModuleNotFoundError: No module named 'Pellmonsrv'` when running `pytest` from repo root without `pythonpath` configured.

## Code Examples

See Architecture Patterns section above (Patterns 1-6) — all code examples are inline there with the pitfalls they address, since each one is tightly coupled to a specific codebase finding rather than being generic pytest usage.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `test-imports.py` (print/try-except smoke script) | pytest-based `tests/` suite with real assertions, fixtures, parametrization | This phase | Enables CI gating (`OPS-01`, Phase 5), coverage reporting, and per-test isolation that a script can't provide |
| Implicit `sys.path.insert` hacks for import resolution | `pytest.ini` `[pytest] pythonpath = src` | pytest 7.0+ (already the installed version, 9.0.2) | Centralizes path setup in one config file instead of scattering it across test/script files |

**Deprecated/outdated:** None specific to this phase's tooling — `pytest-socket`'s current maintained fork is `miketheman/pytest-socket` (confirmed in `.planning/research/STACK.md`'s prior project-level research); do not use an older abandoned fork if one is suggested by training data.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pytest.ini`'s `[pytest] pythonpath = src` is the right mechanism (vs. a `conftest.py`-based `sys.path.insert`) given no packaging metadata exists | Pitfall 4 / Recommended Project Structure | Low — both approaches work; if the planner/executor finds `pythonpath` behaves unexpectedly with the Autotools `.in`-templated modules (`directories.py.in`), falling back to a `conftest.py` `sys.path.insert(0, "src")` at collection time is a safe, well-known alternative |
| A2 | `directories.py` (generated from `directories.py.in` by Autotools, not present in a fresh checkout) is not required for the specific modules under test in this phase (`database.py`, `auth.py`, plugin `.pellmon-plugin` scan) | Standard Stack / Recommended Project Structure | Medium — if `Pellmonsrv/pellmonsrv.py` or another eagerly-imported module transitively imports `directories` at package-`__init__` time and it's missing, `import Pellmonsrv.plugins.<x>` could fail for an unrelated reason (missing generated file, not a real code bug), producing false negatives in the TEST-02 import-check. **The planner should have the first execution task verify a fresh venv can `import Pellmonsrv.database` and `import Pellmonsrv.plugins.testplugin` cleanly before building the full suite on top of that assumption** — `directories.py` generation may need a one-time manual step or a test-local stub. |

## Open Questions (RESOLVED)

1. **Does `Pellmonsrv/__init__.py` or any module imported before plugin discovery require `directories.py` (Autotools-generated, not present in this checkout) at import time?**
   - What we know: `directories.py.in` is a template substituted by `configure`; `STRUCTURE.md` confirms it supplies `DATADIR`/`CONFDIR`/`LOCALSTATEDIR`. `pellmonsrv.py`'s import section (per `CONVENTIONS.md`) uses a `try/except ImportError` guard around similar optional generated modules (`version`).
   - What's unclear: Whether `directories.py` itself has the same optional-import guard, or is a hard import that would break `import Pellmonsrv.plugins.*` in a fresh dev checkout with no Autotools run.
   - Recommendation: First plan task should be a spike: `python -c "import sys; sys.path.insert(0,'src'); import Pellmonsrv.database"` in a clean shell, before committing to the full test suite design. If it fails, either generate a minimal `directories.py` stub for `tests/` or add the same `try/except ImportError` guard pattern.
   - **RESOLVED:** Confirmed during planning — `src/Pellmonsrv/directories.py` does not exist in this checkout, yet `Pellmonsrv.database`, `Pellmonsrv.plugins.testplugin`, and `Pellmonweb.auth` all import cleanly without it. No stub needed. 01-01-PLAN.md's `<environment_facts>` block records this, and Task 1 re-verifies it live in the executor's environment as a cheap re-confirmation.

2. **Should the `pytest-cov` `--cov` flags go into default `addopts` in `pytest.ini` this phase, or be left as an opt-in `pytest --cov=...` invocation?**
   - What we know: `pytest-cov` is in the approved Standard Stack and CONTEXT.md's D-02 lists it as a required dev dependency.
   - What's unclear: CONTEXT.md doesn't lock in whether coverage is enforced/reported by default or left manual for now — this is Claude's Discretion territory not explicitly discussed.
   - Recommendation: Leave `--cov` out of default `addopts` for this phase (keep `pytest` output clean/fast while the suite is being built); coverage reporting/thresholds are more naturally tied to `OPS-01`'s CI pipeline (Phase 5).
   - **RESOLVED:** 01-01-PLAN.md follows this recommendation verbatim — `--cov` is left out of `pytest.ini`'s default `addopts`; coverage enforcement is deferred to Phase 5's CI work.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pytest | All of TEST-01/02/03 | ✓ | 9.0.2 installed (9.1.1 latest on PyPI) | — |
| pytest-mock | UDP mock, cherrypy monkeypatch fixtures | ✓ | 3.15.1 installed | — |
| pytest-socket | 4th success criterion (real-socket guardrail) | ✓ | 0.8.1 installed this session | — |
| pytest-cov | Coverage reporting (not a hard TEST-01/02/03 requirement) | ✓ | 7.1.0 installed this session | Omit `--cov` from `addopts`; suite still functions without it |
| pyserial (`loop://`) | TEST-01 mocked serial | ✓ | 3.5 installed, matches `requirements.txt` floor | — |
| CherryPy | TEST-03 auth tests (import `cherrypy` only, no server needed) | ✓ | 18.8+ per `requirements.txt`; not independently re-verified this session but already a pinned project dependency | — |
| Windows dev environment (this research session ran on Windows, Python 3.14) | General test execution | ✓ | Python 3.14.0 | The project's production target is Linux-only; D-Bus/rrdtool/GPIO-dependent modules are NOT exercised by this phase's tests (database.py, auth.py, and plugin *imports* don't require D-Bus/rrdtool at import time for the modules in scope — confirmed no `import dbus`/`import rrdtool` inside `database.py` or `auth.py`) |

**Missing dependencies with no fallback:** none identified.
**Missing dependencies with fallback:** pytest-cov (optional this phase, per Open Question 2).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 (installed) / `>=9.0,<10` pinned in `requirements-dev.txt` |
| Config file | `pytest.ini` (new, repo root) — does not exist yet |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TEST-01 | Mocked serial (`loop://`) + mocked UDP round-trip harness demonstrable | unit/smoke | `pytest tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py -x` | ❌ Wave 0 |
| TEST-02 | Every `.pellmon-plugin`-listed module import-checked (incl. deferred-import probe for nbecom) | unit | `pytest tests/test_plugin_imports.py -x` | ❌ Wave 0 |
| TEST-03 | `database.py` keyval get/set/init + fallback table-creation path | unit | `pytest tests/Pellmonsrv/test_database.py -x` | ❌ Wave 0 |
| TEST-03 | `Pellmonweb/auth.py` credential check + session login flow | unit | `pytest tests/Pellmonweb/test_auth.py -x` | ❌ Wave 0 |
| (guardrail) | Real socket call fails loudly, not silently/hangs | enforcement | `pytest tests/ --disable-socket -x` (also the default via `addopts`) | Covered by `pytest.ini`, not a separate test file |

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work` — expected state: `scottecom` import test and `nbecom` deferred-import probe **intentionally FAIL** (document this in VERIFICATION.md as expected-red, tracked by IMPORT-01/IMPORT-02 in Phase 3) while every other test passes.

### Wave 0 Gaps
- [ ] `pytest.ini` — root config, `pythonpath = src`, `addopts = --disable-socket`
- [ ] `requirements-dev.txt` — pytest + 3 plugins (D-02)
- [ ] `tests/conftest.py` — `loop_serial`, `mocked_udp_socket`, `cherrypy_request_ctx` fixtures
- [ ] `tests/test_plugin_imports.py` — two-layer import check (Pattern 2)
- [ ] `tests/Pellmonsrv/test_database.py`
- [ ] `tests/Pellmonweb/test_auth.py`
- [ ] `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py`
- [ ] Spike task (Open Question 1): confirm a clean checkout can `import Pellmonsrv.database` without a manually-generated `directories.py`

## Security Domain

`security_enforcement` is not explicitly disabled in `.planning/config.json`, so this section is included per protocol. This phase does not introduce new user-facing input surface (it's test infrastructure only), but it directly touches the codebase's one confirmed auth-related weakness while writing tests for it:

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | Indirectly (test coverage only, not a fix) | Existing plaintext credential comparison in `auth.py` is out of scope to fix here (`SEC-02`, Phase 5) — tests must exercise current behavior without normalizing/hiding it |
| V7 Error Handling / Logging | Yes | `check_credentials()`'s failure path logs the raw password (`SEC-01`, Phase 5 fix) — Phase 1 tests should assert on `check_credentials()`'s **return value**, not assert-and-thereby-codify the current insecure log content, so the eventual `SEC-01` fix doesn't require rewriting this phase's tests |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Real hardware/network I/O accidentally triggered during automated test runs (e.g. a stray UDP broadcast hitting a real burner controller on someone's LAN) | Tampering / DoS (unintended side effect, not a security exploit per se, but a real operational risk this phase exists to close) | `pytest-socket --disable-socket` globally, per this phase's 4th success criterion |

## Sources

### Primary (HIGH confidence — read directly from this repository this session)
- `src/Pellmonsrv/database.py` — full file read, `Keyval_storage` class (lines 147-203), `.py` behavior confirmed
- `src/Pellmonweb/auth.py` — full file read, `AuthController`/`check_credentials`/`login`/`logout` (lines 119-177)
- `src/Pellmonsrv/plugins/scottecom.pellmon-plugin` — sample descriptor format confirmed
- `src/Pellmonsrv/plugins/scottecom/scottecom.py` — confirmed module-level `from Scotteprotocol import Protocol` (line 19)
- `src/Pellmonsrv/plugins/nbecom/__init__.py` — confirmed deferred `from nbeprotocol.protocol import Proxy` inside `activate()` (line 38)
- `src/Scotteprotocol/protocol.py` — confirmed `serial.Serial()` hard-constructed in `__init__`, no injection seam (lines 33-58)
- `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py` — confirmed `socket.socket()` hard-constructed in `__init__`, no injection seam (lines 40-53)
- `src/Pellmonsrv/yapsy/PluginManager.py` — confirmed `.pellmon-plugin` INI parsing/`locatePlugins` mechanism (lines 181-247)
- `python -m pip index versions pytest / pytest-mock / pytest-socket / pytest-cov` — live PyPI version check, 2026-09-17
- `python -m slopcheck install pytest pytest-mock pytest-socket pytest-cov` — legitimacy check, all 4 `[OK]`, run this session
- `python -m pip list` — confirmed `pytest 9.0.2`, `pytest-mock 3.15.1`, `pyserial 3.5`, `Mako 1.3.12` already installed in the active venv

### Secondary (MEDIUM confidence)
- pyserial `loop://` URL handler mechanism — https://pyserial.readthedocs.io/en/latest/url_handlers.html — carried over from `.planning/research/STACK.md` (project-level research, same session context), not independently re-fetched this session
- pytest `pythonpath` ini option (pytest ≥7) — training-knowledge, consistent with installed pytest 9.0.2's documented ini options; not independently re-verified via live docs fetch this session

### Tertiary (LOW confidence)
- None used without cross-verification in this document.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every package/version claim verified live via `pip index versions` and `slopcheck` this session, not training-data guesses
- Architecture (import-check two-layer design, auth mocking pattern): HIGH — derived directly from reading the actual source files that determine behavior (scottecom.py, nbecom/__init__.py, auth.py), not generic pytest advice
- Pitfalls: HIGH — all four pitfalls trace to specific line numbers read this session, cross-referenced against `.planning/codebase/CONCERNS.md`'s independent prior analysis (which agrees)

**Research date:** 2026-09-17
**Valid until:** 30 days (stable tooling domain; re-verify package versions if planning is delayed past ~2026-10-17)

---
*Phase: 1-Test Harness & Verification Infrastructure*
*Research completed: 2026-09-17*
