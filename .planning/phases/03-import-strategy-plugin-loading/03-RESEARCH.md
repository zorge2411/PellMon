# Phase 3: Import Strategy & Plugin Loading Fixes - Research

**Researched:** 2026-09-18
**Domain:** Python 3 relative imports (PEP 328), package structure, sys.path hygiene, exception visibility
**Confidence:** HIGH (verified via AST analysis and direct code inspection)

## Summary

In Python 2, an import statement like `from protocol import Protocol` inside `src/Scotteprotocol/__init__.py` or `from frames import *` inside `src/Scotteprotocol/datamap.py` would resolve to sibling files in the same directory (implicit relative imports). Python 3 abolished implicit relative imports; all intra-package imports must use explicit relative syntax (e.g. `from .protocol import Protocol`).

Furthermore, in an attempt to work around import issues, `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` was added to:
- `src/Pellmonsrv/plugins/scottecom/__init__.py:6`
- `src/Pellmonsrv/plugins/nbecom/__init__.py:28`

This created a severe module shadowing / collision risk (IMPORT-04): both `scottecom` (via `Scotteprotocol`) and `nbecom` (via `nbeprotocol`) have internal modules named `protocol.py` and `frames.py`. If both directories are on `sys.path`, whichever was appended first or imported first can shadow the other.

By converting all intra-package imports to explicit relative imports (`from . import ...`, `from .frames import ...`) and removing the `sys.path.append` shims, each package is completely self-contained and isolated within its own namespace.

Finally, `src/Scotteprotocol/protocol.py` was unreachable under Python 3 during Phase 2 due to `Scotteprotocol/__init__.py` failing on import. Its 19 bare/broad `except:` clauses were deferred to Phase 3 and must now undergo the exception-visibility retrofit.

---

## Detailed File & Import Inventory

### 1. Scotteprotocol Package (`src/Scotteprotocol/`)

| File | Line | Current Code (Python 2) | Target Code (Python 3 PEP 328) |
|------|------|-------------------------|--------------------------------|
| `src/Scotteprotocol/__init__.py` | 2 | `from protocol import Protocol` | `from .protocol import Protocol` |
| `src/Scotteprotocol/frames.py` | 19 | `from protocol import Frame` | `from .protocol import Frame` |
| `src/Scotteprotocol/datamap.py` | 21 | `from frames import *` | `from .frames import *` |
| `src/Scotteprotocol/protocol.py` | 25 | `from enumerations import dataEnumerations` | `from .enumerations import dataEnumerations` |
| `src/Scotteprotocol/protocol.py` | 26 | `from transformations import dataTransformations` | `from .transformations import dataTransformations` |
| `src/Scotteprotocol/protocol.py` | 216 | `from datamap import dataBaseMap` | `from .datamap import dataBaseMap` |

### 2. ScotteCom Plugin (`src/Pellmonsrv/plugins/scottecom/`)

| File | Line | Current Code | Target Code |
|------|------|--------------|-------------|
| `__init__.py` | 6 | `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` | *Remove entirely* |
| `__init__.py` | 8 | `from scottecom import scottecom` | `from .scottecom import scottecom` |
| `scottecom.py` | 24 | `import menus` | `from . import menus` |
| `scottecom.py` | 25 | `from descriptions import dataDescriptions` | `from .descriptions import dataDescriptions` |
| `menus.py` | 19 | `from datamenu import dataBaseTags` | `from .datamenu import dataBaseTags` |

### 3. NBEcom Plugin & NBEprotocol (`src/Pellmonsrv/plugins/nbecom/`)

| File | Line | Current Code | Target Code |
|------|------|--------------|-------------|
| `__init__.py` | 28 | `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` | *Remove entirely* |
| `__init__.py` | 38 | `from nbeprotocol.protocol import Proxy` | `from .nbeprotocol.protocol import Proxy` |
| `__init__.py` | 40 | `from nbeprotocol.language import event_text, ...` | `from .nbeprotocol.language import event_text, ...` |
| `nbeprotocol/protocol.py` | 27 | `from frames import Request_frame, Response_frame` | `from .frames import Request_frame, Response_frame` |
| `nbeprotocol/protocol.py` | 28 | `from protocolexceptions import *` | `from .protocolexceptions import *` |
| `nbeprotocol/protocol.py` | 30 | `import language` | `from . import language` |
| `nbeprotocol/frames.py` | 21 | `from protocolexceptions import *` | `from .protocolexceptions import *` |
| `nbeprotocol/language.py` | 21 | `from langmap import langmap` | `from .langmap import langmap` |
| `nbeprotocol/language.py` | 23 | `from directories import DATADIR` | `from Pellmonsrv.directories import DATADIR` (with fallback) |

### 4. Yapsy Plugin Managers (`src/Pellmonsrv/yapsy/`)

| File | Line | Current Code | Target Code |
|------|------|--------------|-------------|
| `ConfigurablePluginManager.py` | 13, 16, 17 | `from IPlugin import ...`, `from PluginManager import ...` | `from .IPlugin import ...`, `from .PluginManager import ...` |
| `VersionedPluginManager.py` | 13, 14 | `from PluginManager import ...`, `from IPlugin import ...` | `from .PluginManager import ...`, `from .IPlugin import ...` |

---

## Inherited `src/Scotteprotocol/protocol.py` Exception Visibility Audit

There are 19 bare/broad `except` blocks in `src/Scotteprotocol/protocol.py`. Per Phase 2 conventions (D-01, D-04):

1. **Category A: Unhandled error paths that hide bugs**
   - Lines 52, 177: Serial initialization and open port error paths (`logger.exception(...)`)
   - Lines 228-268 (`run` thread loop): Command execution and frame read/write failures (`logger.exception(...)`)
   - Lines 270-320: Low-level serial communication loop (`logger.exception(...)` on unexpected transmission aborts)

2. **Category B: Expected protocol conversion / checksum fallbacks**
   - Lines 70-110: `readval` / `writeval` type conversion fallback logic (e.g. `int()`, `float()`, or missing parameter keys). Narrow to `(ValueError, KeyError, TypeError)` and log at debug level or preserve clean return value.
   - Lines 140-166: CRC / checksum validation retries. Narrow to specific exceptions or debug logging.

---

## Coexistence & Isolation Verification (IMPORT-04)

To verify that `Scotteprotocol` and `nbeprotocol` coexist cleanly:
1. `import Scotteprotocol.protocol` and `import Pellmonsrv.plugins.nbecom.nbeprotocol.protocol` in the same Python process.
2. Verify `sys.modules['Scotteprotocol.frames']` and `sys.modules['Pellmonsrv.plugins.nbecom.nbeprotocol.frames']` are distinct objects and neither shadows the other.
3. Verify both `Scotteprotocol.Protocol` and `nbeprotocol.Proxy` can be instantiated without import or naming collision.

---

## Test Suite Baseline Impact

In `tests/test_plugin_imports.py`:
- `KNOWN_BROKEN_MODULES = {"scottecom"}` becomes empty: `KNOWN_BROKEN_MODULES = set()`.
- `@pytest.mark.known_broken` is removed from `test_nbecom_deferred_protocol_import`.
- `tests/README.md` is updated to show 0 expected-red baseline failures.
