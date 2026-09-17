# Architecture Research

**Domain:** Python 3 plugin-based hardware-monitoring daemon (import strategy, plugin isolation, hardware test boundary)
**Researched:** 2026-09-17
**Confidence:** HIGH (grounded in direct inspection of PellMon's own yapsy loader and package layout, cross-checked against PEP 328/420 and established pyserial mocking patterns)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  sys.path root: `src/`  (set once, at process startup —          │
│  PYTHONPATH / editable install / `python -m` from `src/`)        │
├─────────────────────────────────────────────────────────────────┤
│  Top-level importable packages (siblings under src/):            │
│  ┌───────────┐  ┌────────────┐  ┌──────────────────┐             │
│  │ Pellmonsrv│  │ Pellmonweb │  │ Scotteprotocol    │             │
│  └─────┬─────┘  └────────────┘  └───────┬───────────┘            │
│        │ Pellmonsrv.plugins.*            │ absolute import        │
│        ▼                                 │ (from scottecom/       │
│  ┌─────────────────────────┐             │  __init__.py)          │
│  │ Pellmonsrv.plugins.      │◄───────────┘                        │
│  │   scottecom (package)    │                                     │
│  │   nbecom (package)        │                                    │
│  │     └── nbeprotocol       │  (nested subpackage, own           │
│  │         (subpackage)      │   dotted namespace)                │
│  └─────────────────────────┘                                     │
├─────────────────────────────────────────────────────────────────┤
│  yapsy PluginManager — loads each plugin's __init__.py by         │
│  `exec(compile(source), synthetic_globals)`, NOT via normal       │
│  `import`. No __package__/__name__ context is established for     │
│  that one file — relative imports (`from .x import y`) fail       │
│  inside it. Everything that file then *imports* (via real         │
│  `import`/`from` statements) goes through the normal import       │
│  system and CAN use relative imports internally.                  │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `src/` sys.path root | Single, process-wide place that makes `Pellmonsrv`, `Pellmonweb`, `Scotteprotocol` importable as top-level packages | Set once via PYTHONPATH/entrypoint/editable install — **not** per-module `sys.path.append` |
| yapsy `PluginManager` | Discovers `.pellmon-plugin` descriptors, `exec()`s the matching plugin's `__init__.py` in a synthetic globals dict | `PluginManager.py:273-277` — confirmed by direct read, this is exec-based, not `importlib`-based |
| Plugin package `__init__.py` (e.g. `scottecom/__init__.py`, `nbecom/__init__.py`) | The one file yapsy exec's directly; wires the plugin class into the framework | Must use **absolute** imports (`from Pellmonsrv.plugins.scottecom.scottecom import scottecomplugin`) — relative imports don't work here because exec() gives it no package context |
| Plugin helper modules (`scottecom.py`, `menus.py`, `descriptions.py`, `datamenu.py`) and protocol subpackages (`Scotteprotocol/`, `nbecom/nbeprotocol/`) | Everything imported *by* the plugin's `__init__.py` via a real `import` statement | Once addressed by full dotted path and imported normally, these ARE real packages/modules in `sys.modules` and **can** use explicit relative imports (PEP 328) internally |
| Protocol package (`Scotteprotocol`, `nbeprotocol`) | Framing, checksums, byte-level encode/decode, transport I/O (serial/UDP) | Pure package with no dependency on `Pellmonsrv.plugin_categories`; should accept an injectable transport object rather than hard-constructing `serial.Serial`/`socket.socket` internally |

## Recommended Project Structure

No directory moves are required — the existing layout is already structurally sound (each protocol library is a proper package with `__init__.py`; plugins are proper subpackages of `Pellmonsrv.plugins`). The fix is entirely about **import statements**, not file locations:

```
src/
├── Pellmonsrv/
│   ├── plugins/
│   │   ├── scottecom/
│   │   │   ├── __init__.py       # yapsy entry — ABSOLUTE imports only
│   │   │   ├── scottecom.py      # → `from .menus import ...` (relative, PEP 328)
│   │   │   ├── menus.py          # → `from .datamenu import dataBaseTags`
│   │   │   ├── descriptions.py
│   │   │   └── datamenu.py
│   │   └── nbecom/
│   │       ├── __init__.py       # yapsy entry — ABSOLUTE imports only
│   │       └── nbeprotocol/
│   │           ├── __init__.py
│   │           ├── protocol.py   # → `from .frames import Request_frame, Response_frame`
│   │           ├── frames.py     # → `from .protocolexceptions import *`
│   │           ├── language.py
│   │           └── langmap.py
├── Scotteprotocol/
│   ├── __init__.py               # → `from .protocol import Protocol`
│   ├── protocol.py               # → `from .enumerations import dataEnumerations`
│   │                              #    `from .datamap import dataBaseMap` (was function-local bare import)
│   ├── frames.py                 # → `from .protocol import Frame`
│   ├── datamap.py                # → `from .frames import *`
│   └── enumerations.py
└── Pellmonweb/
```

### Structure Rationale

- **No new top-level packages, no namespace packages:** `Scotteprotocol` and `nbeprotocol` are single-owner, single-distribution packages that live inside this one repo — PEP 420 namespace packages exist to let *multiple independent distributions* contribute submodules to one shared namespace. That's not this problem; using them here would add import-resolution complexity (no `__init__.py`, multiple `__path__` entries to reason about) for zero benefit. **Regular packages with explicit relative imports are the correct, standard pattern.**
- **`nbeprotocol` stays nested under `nbecom/`, not promoted to a top-level package:** it's only ever consumed by the `nbecom` plugin, so keeping it as `Pellmonsrv.plugins.nbecom.nbeprotocol` is correct encapsulation — its dotted path already makes it collision-proof against `Scotteprotocol.protocol`/`Scotteprotocol.frames` once bare/sys.path imports are removed, since the two `frames` modules become `Scotteprotocol.frames` and `Pellmonsrv.plugins.nbecom.nbeprotocol.frames` in `sys.modules` — different keys, no shadowing possible regardless of load order.
- **`Scotteprotocol` stays a top-level sibling package** (not nested under `scottecom/`) since it's already an independent library imported via `from Scotteprotocol import Protocol` and `src/` is already its natural distribution root — no change needed there beyond fixing its internal imports.

## Architectural Patterns

### Pattern 1: Two-tier import strategy (absolute at the plugin boundary, relative inside packages)

**What:** Because yapsy loads each plugin's `__init__.py` via `exec(compile(source), globals_dict)` rather than the standard import machinery (confirmed at `src/Pellmonsrv/yapsy/PluginManager.py:273-277`), that one file has no `__package__`/parent-module context — `from . import x` raises `ImportError: attempted relative import with no known parent package` if used there. Every other module in the codebase, once imported via a real `import`/`from` statement (even indirectly, from inside that exec'd code), becomes a normal entry in `sys.modules` and gets full relative-import support.

**When to use:** Apply absolute imports (`from Pellmonsrv.plugins.scottecom.scottecom import scottecomplugin`, `from Pellmonsrv.plugins.nbecom.nbeprotocol.protocol import Proxy`) specifically in the files yapsy exec's directly (every `plugins/<name>/__init__.py`). Apply explicit relative imports (PEP 328: `from .frames import Frame`, `from . import language`) everywhere else — protocol subpackages, plugin helper modules, and the core `Pellmonsrv`/`Pellmonweb` packages (already partially done there per `CONCERNS.md`).

**Trade-offs:** Requires touching every plugin `__init__.py` once, but each fix is small and mechanical. In exchange, `sys.path.append(os.path.dirname(...))` shims are deleted entirely (they only existed to work around bare imports, not to solve a genuine path problem — `src/` is already the one true sys.path root). This is also what removes the module-name collision risk: `frames`/`protocol`/`datamap` never again become ambiguous top-level names shadowed by load order.

**Example:**
```python
# src/Pellmonsrv/plugins/scottecom/__init__.py  (yapsy-exec'd file — absolute import)
from Pellmonsrv.plugins.scottecom.scottecom import scottecomplugin

# src/Pellmonsrv/plugins/scottecom/scottecom.py  (normal package member — relative import)
from .menus import get_menu
from .descriptions import dataDescriptions
from Scotteprotocol import Protocol   # absolute, cross-package reference to a sibling top-level package

# src/Scotteprotocol/protocol.py  (normal package member — relative import)
from .enumerations import dataEnumerations
from .datamap import dataBaseMap      # moved from function-local bare import to module-level relative import
```

### Pattern 2: Regular packages, not namespace packages, for protocol libraries

**What:** Keep `Scotteprotocol/` and `nbecom/nbeprotocol/` as ordinary packages (`__init__.py` present, single `__path__`).

**When to use:** Always, for this codebase — namespace packages (PEP 420) solve cross-distribution merging, which doesn't apply here (single repo, single install).

**Trade-offs:** None significant; this is simply not changing what already works, and avoids the debugging cost of namespace-package `__path__` surprises.

### Pattern 3: Constructor-injectable transport for hardware I/O (seam for testing)

**What:** `Scotteprotocol.Protocol` and `nbeprotocol.Proxy` currently construct their own `serial.Serial(...)` / UDP `socket.socket(...)` internally inside `__init__`/connect methods. Add an optional constructor parameter (e.g. `transport=None`) — if `None`, construct the real hardware object exactly as today (zero behavior change for `scottecom.py`/`nbecom/__init__.py`, which never pass it); if provided, use it as-is. The injected object only needs to satisfy the narrow subset of the pyserial/socket API the protocol code actually calls (`write`, `read`, `in_waiting` for serial; `sendto`, `recvfrom` for UDP) — a small hand-rolled fake or `pyserial`'s built-in `serial_for_url('loop://')` is enough; no mocking framework required.

**When to use:** Any protocol/transport-owning class that needs to be exercised without physical hardware.

**Trade-offs:** Small, additive, backward-compatible change (default parameter) — not a rewrite. The alternative (monkeypatching `serial.Serial` globally in tests) works too but is more fragile and couples tests to import order; constructor injection is the more standard, durable pattern.

**Example:**
```python
# Scotteprotocol/protocol.py
class Protocol:
    def __init__(self, port, chipversion, transport=None):
        self.transport = transport or serial.Serial(port, ...)  # unchanged default path
    def send(self, frame):
        self.transport.write(frame.encode())
    def receive(self):
        return self.transport.read(...)

# tests/test_scotteprotocol.py
class FakeSerial:
    def __init__(self, canned_response: bytes):
        self._response = canned_response
        self.written = b""
    def write(self, data): self.written += data
    def read(self, n): return self._response[:n]
    @property
    def in_waiting(self): return len(self._response)

def test_frame_roundtrip():
    fake = FakeSerial(canned_response=b"\x02...checksum bytes...")
    proto = Protocol(port=None, chipversion="v1", transport=fake)
    proto.send(some_frame)
    assert fake.written == expected_bytes
    assert proto.receive() == expected_decoded_value
```

## Data Flow

### Plugin load / import flow (fixed state)

```
Process start (PYTHONPATH=src, or editable install)
    ↓
yapsy locatePlugins() scans plugin dirs for *.pellmon-plugin
    ↓
yapsy loadPlugins(): exec(compile(<plugin>/__init__.py source), synthetic_globals)
    │   (no __package__ context here — MUST use absolute imports)
    ↓
plugin __init__.py:  `from Pellmonsrv.plugins.<name>.<name> import <name>plugin`
    │   (this IS a real `import` statement → goes through normal import system)
    ↓
<name>.py module imported normally → registered in sys.modules under its
full dotted path → free to use `from .helper import x` (relative) internally
    ↓
<name>.py imports its protocol package: `from Scotteprotocol import Protocol`
    or `from .nbeprotocol.protocol import Proxy` (relative, since nbeprotocol
    is a subpackage of the already-imported nbecom package)
    ↓
protocol package's own submodules use relative imports among themselves
    (`from .frames import Frame`) — no sys.path involvement anywhere
```

### Hardware test boundary (independent of the plugin activation flow)

```
pytest test module
    ↓
imports Scotteprotocol.Protocol / nbeprotocol.Proxy DIRECTLY
    (bypasses pellmonsrv.py, Database, yapsy, Pellmonsrv.plugins entirely)
    ↓
constructs Protocol(..., transport=FakeSerial(canned_bytes))
    ↓
exercises encode/decode/checksum/frame-parsing logic against canned
request/response byte sequences — no physical device, no daemon process,
no D-Bus, no plugin manager involved
```

**Key insight:** the mock boundary does **not** need to be layered into `protocols.activate()` or the yapsy plugin lifecycle at all. Unit tests target the protocol packages as ordinary, standalone-importable Python packages — which is also exactly what `STRUCTURE.md` already documents as their intended design ("no dependency on `Pellmonsrv.plugin_categories`"). This keeps the testing work isolated from the plugin-activation code path and requires no changes to `pellmonsrv.py`, `database.py`, or the yapsy loader.

### Key Data Flows

1. **Import resolution:** `src/` (sys.path root, set once) → top-level packages (`Pellmonsrv`, `Scotteprotocol`) → subpackages addressed by full dotted path → internal relative imports. No per-module `sys.path.append` anywhere in this chain once the fix lands.
2. **Plugin activation (unchanged by this work):** `Database.__init__()` → yapsy `PluginManager` → `plugin.activate(conf, globals(), db)` → plugin constructs its protocol object (now optionally with an injected transport, defaulting to real hardware) → inserts `Item`s into shared `Database`.
3. **Test flow (new, additive):** pytest → direct import of protocol package → construct with fake transport → assert on encode/decode/checksum behavior. Fully decoupled from flow 2.

## Scaling Considerations

Not applicable in the traditional user-scale sense (single-daemon, single-site hardware monitor). The relevant "scale" axis here is **plugin count / protocol library count**:

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (2 hardware protocols: Scotte, NBE) | Regular packages + explicit relative imports, as recommended above, fully sufficient |
| If a 3rd+ hardware protocol library is added later | Same pattern scales linearly — each new protocol package gets its own dotted namespace; no collision risk regardless of how many are added, since none of them share `sys.path` entries anymore |
| If protocol libraries were ever split into separately-published packages | That's the point at which PEP 420 namespace packages or proper PyPI sub-distributions would become relevant — not needed now |

### Scaling Priorities

1. **First (and only) real risk today:** the exec-based yapsy loader silently swallowing `ImportError`/`ModuleNotFoundError` during `loadPlugins()` (per `CONCERNS.md`, plugin activation failures are individually caught and logged tersely). Fixing imports must be paired with making that failure path loud (`logger.exception(...)`) so a future regression is caught immediately rather than silently disabling a plugin.
2. **Second:** as more protocol libraries/plugins are added, keep the "absolute imports at the yapsy-exec'd boundary, relative imports inside real packages" rule documented (e.g. in a CONTRIBUTING note) so it isn't rediscovered ad hoc per plugin, which is exactly how the current inconsistency (some `sys.path.append`, some relative, some still-bare) happened.

## Anti-Patterns

### Anti-Pattern 1: `sys.path.append(os.path.dirname(__file__))` per plugin

**What people do:** Each plugin directory appends itself to `sys.path` so its sibling modules can be bare-imported (`import menus`).
**Why it's wrong:** Creates load-order-dependent name collisions (two plugins with a module named `frames.py` or `protocol.py` will shadow each other depending on which plugin activated first), and is entirely unnecessary — `src/` is already the one legitimate sys.path root for this project.
**Do this instead:** Absolute imports at the yapsy-exec'd `__init__.py` boundary; explicit relative imports (PEP 328) everywhere else.

### Anti-Pattern 2: Bare/implicit relative imports (Python 2 style) inside real packages

**What people do:** `from frames import Frame` inside `protocol.py`, relying on Python 2's implicit same-directory module resolution.
**Why it's wrong:** Doesn't work at all under Python 3 (`ModuleNotFoundError`) — this is the root cause of ScotteCom and NBEcom being non-functional today, per `CONCERNS.md`.
**Do this instead:** `from .frames import Frame` — the explicit form is unambiguous, doesn't depend on `sys.path` contents, and is what the core `Pellmonsrv` package already correctly does.

### Anti-Pattern 3: Constructing hardware I/O objects directly inside protocol class `__init__`/connect methods with no seam

**What people do:** `self.ser = serial.Serial(port, baudrate)` hard-coded inside `Protocol.__init__`, with no way to substitute a fake.
**Why it's wrong:** Forces every test of frame encode/decode logic to either mock at the `serial` module level (fragile, import-order-sensitive) or require physical hardware (impossible in CI/dev).
**Do this instead:** Accept an optional `transport` parameter defaulting to the real hardware constructor — a two-line change that unlocks direct, hardware-free unit testing without altering any call site.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Scotte burner (serial) | `pyserial` `Serial` object owned by `Scotteprotocol.Protocol`, used to write/read framed byte sequences | Inject via `transport=` param for tests; production default unchanged |
| NBE burner (UDP + XTEA) | Raw `socket` UDP send/recv + broadcast discovery (`find_controller()`) owned by `nbeprotocol.Proxy` | Same injection pattern; discovery (`find_controller`) is a separate concern from frame encode/decode and can be tested independently with a fake socket that returns canned discovery responses |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| yapsy `PluginManager` ↔ plugin `__init__.py` | `exec()` of file contents, not `import` | Governs the absolute-vs-relative import rule above; do not assume normal package semantics apply to this one file per plugin |
| Plugin `__init__.py` ↔ plugin helper modules / protocol package | Normal Python `import`/`from` statements | Full relative-import support once addressed correctly; this is where PEP 328 applies |
| `scottecom`/`nbecom` plugin class ↔ protocol package (`Scotteprotocol`/`nbeprotocol`) | Absolute import of a sibling/nested package + direct method calls (no IPC) | Protocol packages have (and should keep) zero dependency on `Pellmonsrv.plugin_categories`, keeping them independently testable |
| Test suite ↔ protocol package | Direct import + constructor-injected fake transport | Fully bypasses yapsy/Database/D-Bus — no changes needed to the plugin activation flow to enable this |

## Sources

- Direct inspection: `src/Pellmonsrv/yapsy/PluginManager.py:273-277` (confirms exec-based plugin loading, not `importlib`-based) — HIGH confidence, primary source
- Direct inspection: `src/Pellmonsrv/plugins/scottecom/__init__.py`, `src/Pellmonsrv/plugins/nbecom/__init__.py` (confirms current sys.path.append shim pattern and that absolute imports of `Pellmonsrv.*` already work without any path hack)
- `.planning/codebase/CONCERNS.md`, `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md` — existing codebase mapping
- PEP 328 (explicit relative imports) and PEP 420 (namespace packages) — standard library import semantics, HIGH confidence (well-established, stable since Python 3.3)
- [pyserial testing docs (DeepWiki)](https://deepwiki.com/pyserial/pyserial/8.2-testing) — confirms `loop://` URL handler and general community pattern of hand-rolled/lightweight fake serial objects for unit tests — MEDIUM confidence (community-verified pattern, not project-specific)
- [mock_serial](https://github.com/benthorner/mock_serial), [dummyserial](https://github.com/ampledata/dummyserial) — example fake-serial libraries demonstrating the canned request/response pattern — MEDIUM confidence, illustrative only (recommend hand-rolled fake given PellMon's narrow pyserial API surface, to avoid adding a new dependency for a ~15-line fake)

---
*Architecture research for: Python 2→3 migration completion — plugin import strategy and hardware test boundary*
*Researched: 2026-09-17*
