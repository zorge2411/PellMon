# Phase 1: Test Harness & Verification Infrastructure - Pattern Map

**Mapped:** 2026-09-17
**Files analyzed:** 8 (all new — this phase is additive-only per CONTEXT.md "Integration Points: None yet")
**Analogs found:** 8 / 8 (all role-match or config-convention match; no pre-existing pytest suite exists in this repo, so no exact "test file" analogs exist — analogs are either the source-under-test or the closest existing config-split/script convention)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|-----------------|---------------|
| `pytest.ini` | config | request-response (CLI invocation config) | none (no existing pytest/tox/setup.cfg config in repo) | no-analog — use RESEARCH.md Pattern (pythonpath=src, addopts=--disable-socket) verbatim |
| `requirements-dev.txt` | config | batch (dependency manifest) | `requirements-wsl.txt` (repo root) | exact — same split-manifest convention as `requirements.txt`/`requirements-wsl.txt` |
| `tests/conftest.py` | test (fixtures) | event-driven (pytest fixture injection) | none (no existing conftest.py) | no-analog — use RESEARCH.md Patterns 3/4/6 verbatim |
| `tests/test_plugin_imports.py` | test | batch (parametrized discovery + import) | `test-imports.py` (repo root) + `src/Pellmonsrv/yapsy/PluginManager.py` (`.pellmon-plugin` INI parsing) | role-match — same "try-import and report" intent as `test-imports.py`, but discovery source is yapsy's own descriptor convention |
| `tests/Pellmonsrv/test_database.py` | test | CRUD | `src/Pellmonsrv/database.py` (`Keyval_storage`, lines 147-203) | exact — file under test is the analog; no mocking, real temp-file SQLite |
| `tests/Pellmonweb/test_auth.py` | test | request-response | `src/Pellmonweb/auth.py` (`AuthController`, lines 119-177) | exact — file under test is the analog; CherryPy thread-locals monkeypatched |
| `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py` | test | streaming / file-I/O (serial) + event-driven (mocked UDP) | none in `src/` (Scotteprotocol/nbeprotocol both import-broken, no injectable transport yet — Phase 4 scope) | no-analog — self-contained smoke test per RESEARCH.md Pitfall 2, does not import broken protocol packages |
| `tests/Pellmonsrv/plugins/__init__.py` (or no `__init__.py`, per pytest rootdir auto-discovery — verify convention) | test scaffold | n/a | `src/Pellmonsrv/plugins/*/__init__.py` (module marker convention) | role-match — only if package-style test dirs are chosen; pytest doesn't require `__init__.py` in test dirs by default |

## Pattern Assignments

### `pytest.ini` (config)

**Analog:** none exists in repo (confirmed: no `pyproject.toml`, `setup.cfg`, `tox.ini`, or `pytest.ini`).

**Use RESEARCH.md's verbatim recommendation** (Architecture Patterns, Recommended Project Structure + Pitfall 4):
```ini
[pytest]
pythonpath = src
addopts = --disable-socket
testpaths = tests
```
Rationale for `pythonpath = src` over `sys.path.insert` hacks: `test-imports.py` (repo root, lines 1-5) currently does `sys.path.insert(0, 'src')` manually — this is the exact hack `pytest.ini`'s `pythonpath` ini option (pytest ≥7, installed 9.0.2) is meant to replace, per RESEARCH.md Pitfall 4. Do not replicate the `sys.path.insert` pattern in new test files.

---

### `requirements-dev.txt` (config)

**Analog:** `requirements-wsl.txt` (repo root, full file read above) — this repo's existing precedent for a second, purpose-scoped requirements file alongside `requirements.txt`.

**Structure pattern to copy** (comment-header + version-pinned entries, same style as `requirements.txt`/`requirements-wsl.txt`):
```
# WSL/Linux-specific requirements with all dependencies
# Cross-platform dependencies
pyserial>=3.5
CherryPy>=18.8.0
...
```
Apply the same header-comment + `package>=X.Y` pinning style for `requirements-dev.txt`:
```
# Test/dev-only dependencies — NOT installed in production Docker image
pytest>=9.0,<10
pytest-mock>=3.15
pytest-socket>=0.8
pytest-cov>=7.1
```
(Versions per RESEARCH.md Standard Stack — already verified live against PyPI this session.)

---

### `tests/conftest.py` (fixtures)

**Analog:** none pre-existing. Use RESEARCH.md Patterns 3, 4, 6 verbatim — they were derived from direct inspection of `pyserial`'s `loop://` handler, `unittest.mock`, and this repo's own `src/Pellmonweb/auth.py` CherryPy thread-local usage (see below).

**Fixture 1 — loop:// serial** (RESEARCH.md Pattern 3):
```python
import pytest
import serial

@pytest.fixture
def loop_serial():
    ser = serial.serial_for_url("loop://", timeout=1)
    yield ser
    ser.close()
```

**Fixture 2 — mocked UDP socket** (RESEARCH.md Pattern 4):
```python
@pytest.fixture
def mocked_udp_socket(mocker):
    mock_socket_cls = mocker.patch("socket.socket")
    mock_sock = mock_socket_cls.return_value
    mock_sock.recvfrom.return_value = (b"", ("0.0.0.0", 0))
    return mock_sock
```

**Fixture 3 — cherrypy request/session context** (RESEARCH.md Pattern 6, keyed to `src/Pellmonweb/auth.py` lines 139-151 which read `cherrypy.request.headers["Remote-Addr"]`, `cherrypy.session`, `cherrypy.log`):
```python
@pytest.fixture
def cherrypy_request_ctx(mocker):
    import cherrypy
    fake_request = mocker.MagicMock()
    fake_request.headers = {"Remote-Addr": "127.0.0.1"}
    fake_request.script_name = ""
    mocker.patch.object(cherrypy, "request", fake_request)
    mocker.patch.object(cherrypy, "session", {})
    mocker.patch.object(cherrypy, "log")
    return fake_request
```
**Critical gotcha to encode in the fixture docstring** (from reading `auth.py:139-151` directly): `check_credentials()`'s bare `except:` block calls `cherrypy.log(...cherrypy.request.headers...)` — if `cherrypy.request` is unmocked, this raises a *second*, uncaught exception inside the except handler. The fixture MUST be applied to every test that calls `AuthController` methods, per RESEARCH.md Pitfall 3.

---

### `tests/test_plugin_imports.py` (test)

**Analog 1 — intent:** `test-imports.py` (repo root, full file read above) — same "try import, report pass/fail" idea, but converted from print-based ad hoc script to real pytest assertions/parametrization.

**Analog 2 — discovery mechanism:** `src/Pellmonsrv/plugins/scottecom.pellmon-plugin` (INI descriptor, confirmed format):
```ini
[Core]
Name = ScotteCom
Module = scottecom
```
15 descriptor files confirmed present in `src/Pellmonsrv/plugins/*.pellmon-plugin`: calculate, cleaning, consumption, customalarms, exec, heatingcircuit, nbecom, onewire, openweathermap, owfs, pelletcalc, raspberrygpio, scottecom, silolevel, testplugin.

**Discovery pattern** (RESEARCH.md Pattern 1, `configparser` — same library this codebase already uses for `pellmon.conf`):
```python
import configparser, glob, os

PLUGIN_DIR = os.path.join("src", "Pellmonsrv", "plugins")

def discover_plugin_modules():
    modules = []
    for descriptor in sorted(glob.glob(os.path.join(PLUGIN_DIR, "*.pellmon-plugin"))):
        cp = configparser.ConfigParser()
        cp.read(descriptor)
        modules.append(cp.get("Core", "Module"))
    return modules
```

**Two-layer import check** (RESEARCH.md Pattern 2). Confirmed directly from source this session:
- `src/Pellmonsrv/plugins/scottecom/scottecom.py:19` — `from Scotteprotocol import Protocol` (module-level, EAGER failure — a plain `importlib.import_module("Pellmonsrv.plugins.scottecom")` correctly fails today).
- `src/Pellmonsrv/plugins/nbecom/__init__.py:37-38` — `from nbeprotocol.protocol import Proxy` is INSIDE `nbecomplugin.activate()`, not at module level (confirmed by reading the file: `__init__.py`'s only module-level executable code is `sys.path.append(...)` at line 28 and `logger = getLogger('pellMon')` at line 30 — no protocol import). A plain per-module import check gives NBEcom a **false pass**.

```python
import importlib
import pytest

@pytest.mark.parametrize("module_name", discover_plugin_modules())
def test_plugin_module_imports(module_name):
    """scottecom is EXPECTED to fail today (IMPORT-01, Phase 3) — do not xfail/skip."""
    importlib.import_module(f"Pellmonsrv.plugins.{module_name}")

def test_nbecom_deferred_import_is_broken_today():
    """Probes the deferred import inside nbecomplugin.activate() directly.
    Expected to FAIL until Phase 3 (IMPORT-02)."""
    importlib.import_module("Pellmonsrv.plugins.nbecom.nbeprotocol.protocol")
```

---

### `tests/Pellmonsrv/test_database.py` (test, CRUD)

**Analog:** `src/Pellmonsrv/database.py` — `Keyval_storage` class, lines 147-203 (full class read above, exact quoted).

Key concrete facts extracted directly from source for test-writing accuracy:
- Constructor (`__init__`, lines 148-158): connects to `dbfile`, tries `SELECT value from keyval`, on `sqlite3.OperationalError` falls back to `CREATE TABLE keyval (id TEXT PRIMARY KEY, value TEXT, confvalue TEXT NOT NULL DEFAULT '-')` — this is the fallback path TEST-03 must exercise.
- `readval()` (lines 160-171): on any `Exception`, does `print(e); return 'error'` — **does not raise**. Tests for missing keys must assert `== 'error'`, not `pytest.raises(...)`.
- `writeval()` (lines 173-203): coerces non-str `value`/`confval` to `str()` (lines 176-180); has a nested bare `except:` (line 198) that falls through to an `INSERT OR REPLACE` — this is intentional existing behavior for the "confval differs" upsert path, not a bug to fix this phase.

```python
import sqlite3
from Pellmonsrv.database import Keyval_storage

def test_init_creates_keyval_table(tmp_path):
    dbfile = str(tmp_path / "test.db")
    Keyval_storage(dbfile)
    conn = sqlite3.connect(dbfile)
    conn.cursor().execute("SELECT value FROM keyval")  # must not raise
    conn.close()

def test_writeval_readval_roundtrip(tmp_path):
    store = Keyval_storage(str(tmp_path / "test.db"))
    store.writeval("mykey", value="42")
    assert store.readval("mykey") == "42"

def test_init_fallback_path_when_table_missing(tmp_path):
    dbfile = str(tmp_path / "other_schema.db")
    conn = sqlite3.connect(dbfile)
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit(); conn.close()
    Keyval_storage(dbfile)  # must hit OperationalError -> CREATE TABLE keyval
```

---

### `tests/Pellmonweb/test_auth.py` (test, request-response)

**Analog:** `src/Pellmonweb/auth.py` — `AuthController`, lines 119-177 (full class read above, exact quoted).

Key concrete facts extracted directly from source:
- `__init__(self, credentials, lookup)` (lines 121-123) — plain Python objects, no CherryPy machinery needed to instantiate.
- `check_credentials()` (lines 139-151) — success returns `None`; failure returns `"Incorrect username or password."`; failure path (both `else` at line 148 and bare `except:` at line 149) calls `cherrypy.log(...cherrypy.request.headers["Remote-Addr"]..., username[:50], password[:50])` — **logs raw password**, this is `SEC-01` (Phase 5), do not "fix" or assert-and-lock-in the log content in this phase's tests, only assert the return value.
- `login()` (lines 153-167) raises `cherrypy.HTTPRedirect(from_page)` on success (line 167) — assert with `pytest.raises(cherrypy.HTTPRedirect)`, this is existing control flow not an error.
- **Note:** `logout()`'s default arg `from_page=cherrypy.request.script_name` (line 170) is evaluated at class-definition/import time — this means simply `import Pellmonweb.auth` requires `cherrypy.request` to already be a valid thread-local-or-proxy object at import time (CherryPy's `cherrypy.request` is itself a proxy object so this generally works, but worth flagging if `import Pellmonweb.auth` ever fails at collection time in a fresh test run — not something identified as broken, just a fragile pattern worth a note in the plan).

```python
from Pellmonweb.auth import AuthController, SESSION_KEY
import cherrypy, pytest

def test_check_credentials_success(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    assert ctrl.check_credentials("alice", "s3cret") is None

def test_check_credentials_failure(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    assert ctrl.check_credentials("alice", "wrong") == "Incorrect username or password."

def test_login_sets_session_on_success(cherrypy_request_ctx):
    ctrl = AuthController(credentials=[("alice", "s3cret")], lookup=None)
    with pytest.raises(cherrypy.HTTPRedirect):
        ctrl.login(username="alice", password="s3cret", from_page="/")
    assert cherrypy.session[SESSION_KEY] == "alice"
```

---

### `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py` (test, streaming/event-driven)

**Analog:** None in `src/` — confirmed `src/Scotteprotocol/protocol.py` hard-constructs `serial.Serial()` in `__init__` (no injection seam) and `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py` hard-constructs `socket.socket()` in `__init__` (no injection seam); both packages have broken imports today (`Scotteprotocol/__init__.py` fails at `from protocol import Protocol` — needs `.protocol`; `nbeprotocol/protocol.py:27` has a bare `from frames import ...`). Per RESEARCH.md Pitfall 2, do NOT attempt to import or exercise these real classes this phase — that is Phase 4 (`PROTO-04`) scope.

Self-contained demonstration using the `loop_serial`/`mocked_udp_socket` fixtures from `tests/conftest.py`:
```python
def test_loop_serial_roundtrip(loop_serial):
    loop_serial.write(b"\x02TEST\x03")
    loop_serial.flush()
    assert loop_serial.read(7) == b"\x02TEST\x03"

def test_udp_send_uses_mock_not_real_network(mocked_udp_socket):
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(b"ping", ("127.0.0.1", 1920))
    mocked_udp_socket.sendto.assert_called_once_with(b"ping", ("127.0.0.1", 1920))
```

---

## Shared Patterns

### Path setup (`pythonpath = src` ini option)
**Source:** `pytest.ini` (new) replacing `test-imports.py:4-5`'s `sys.path.insert(0, 'src')` hack.
**Apply to:** All test files — none should need their own `sys.path` manipulation.

### `.pellmon-plugin` INI descriptor discovery via `configparser`
**Source:** `src/Pellmonsrv/plugins/*.pellmon-plugin` (15 files), same convention `src/Pellmonsrv/yapsy/PluginManager.py` uses at runtime (`configparser`, `[Core] Module = <name>`), and the same library already used for `config/pellmon.conf`.
**Apply to:** `tests/test_plugin_imports.py` only (single consumer this phase).

### CherryPy thread-local monkeypatching (no live server)
**Source:** `src/Pellmonweb/auth.py:139-151` (what needs mocking: `cherrypy.request.headers`, `cherrypy.session`, `cherrypy.log`).
**Apply to:** `tests/Pellmonweb/test_auth.py` via the shared `cherrypy_request_ctx` fixture in `tests/conftest.py`.

### Requirements-file split convention
**Source:** `requirements.txt` / `requirements-wsl.txt` (repo root) — comment-header + `package>=X.Y` pinned lines, purpose-scoped file per install target.
**Apply to:** `requirements-dev.txt` (new, per CONTEXT.md D-02).

### `--disable-socket` global guardrail
**Source:** RESEARCH.md Standard Stack (`pytest-socket`), no existing codebase precedent (net-new safety net).
**Apply to:** `pytest.ini` `addopts` — applies to the entire suite; `tests/conftest.py`'s `mocked_udp_socket` fixture is the only sanctioned way to touch `socket.socket` in a test.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `pytest.ini` | config | request-response (CLI) | No existing pytest/test-runner config file in repo; use RESEARCH.md's verbatim recommendation (`pythonpath = src`, `addopts = --disable-socket`) |
| `tests/conftest.py` | fixtures | event-driven | No existing conftest.py or fixture module in repo; use RESEARCH.md Patterns 3/4/6 verbatim, cross-checked against `src/Pellmonweb/auth.py` for the exact CherryPy attributes to mock |
| `tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py` | test | streaming/event-driven | Deliberately self-contained per RESEARCH.md Pitfall 2 — no real `Scotteprotocol`/`nbeprotocol` analog can be used because both packages are import-broken today and lack an injectable transport seam (Phase 4 scope) |

## Metadata

**Analog search scope:** repo root (`requirements.txt`, `requirements-wsl.txt`, `test-imports.py`), `src/Pellmonsrv/database.py`, `src/Pellmonweb/auth.py`, `src/Pellmonsrv/plugins/*.pellmon-plugin` (15 descriptor files), `src/Pellmonsrv/plugins/scottecom/scottecom.py`, `src/Pellmonsrv/plugins/nbecom/__init__.py`, `src/Pellmonsrv/yapsy/PluginManager.py` (referenced via RESEARCH.md, not re-read this session — already confirmed there)
**Files scanned:** 8 source/config files read directly this session, cross-referenced against RESEARCH.md's prior direct reads of `Scotteprotocol/protocol.py` and `nbeprotocol/protocol.py`
**Pattern extraction date:** 2026-09-17

---
*Phase: 1-Test Harness & Verification Infrastructure*
*Patterns mapped: 2026-09-17*
