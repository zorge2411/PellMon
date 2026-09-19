---
phase: 03-import-strategy-plugin-loading
plan: 02
subsystem: plugins/nbecom
tags: [python3, relative-imports, nbecom, nbeprotocol, sys-path]
dependency-graph:
  requires: []
  provides:
    - PEP 328 explicit relative imports in Pellmonsrv.plugins.nbecom and nbeprotocol subpackage
    - Elimination of sys.path.append mutation in Pellmonsrv/plugins/nbecom/__init__.py
    - Python 3 compatible language property loading in nbeprotocol/language.py
    - Unit tests in tests/Pellmonsrv/plugins/test_nbecom_imports.py
  affects:
    - Pellmonsrv.plugins.nbecom plugin loading
    - nbeprotocol package consumers
tech-stack:
  added: []
  patterns:
    - Explicit relative imports (PEP 328)
    - Safe package directory resolution fallback
    - Non-destructive map iteration under Python 3
key-files:
  created:
    - tests/Pellmonsrv/plugins/test_nbecom_imports.py
  modified:
    - src/Pellmonsrv/plugins/nbecom/__init__.py
    - src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py
    - src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py
    - src/Pellmonsrv/plugins/nbecom/nbeprotocol/language.py
decisions: [D-01, D-02]
metrics:
  completed: 2026-09-18
---

# Phase 3 Plan 02: NBEcom & nbeprotocol Import Strategy Summary

Converted `src/Pellmonsrv/plugins/nbecom/` and its `nbeprotocol/` subpackage to PEP 328 explicit relative imports, removed the `sys.path.append` shim, ensured Python 3 compatible language property initialization, and added unit tests covering plugin and protocol imports and instantiation.

## What Was Built

### Task 1: Fix intra-package relative imports in NBEcom and nbeprotocol
- `src/Pellmonsrv/plugins/nbecom/__init__.py`: removed `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` and switched `from nbeprotocol.protocol import Proxy` and `from nbeprotocol.language import ...` to explicit relative imports (`from .nbeprotocol...`).
- `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`: converted intra-package imports to explicit relative imports (`from .frames import ...`, `from .protocolexceptions import *`, `from . import language`).
- `src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py`: converted `from protocolexceptions import *` to `from .protocolexceptions import *`.
- `src/Pellmonsrv/plugins/nbecom/nbeprotocol/language.py`: converted `from langmap import langmap` to `from .langmap import langmap`; updated DATADIR import to try `from Pellmonsrv.directories import DATADIR` with fallback to package-local `language/lang.uk.prop`; converted `map` results to lists to prevent Python 3 iterator exhaustion when constructing `lang_value_to_text` and iterating over enumerations.

### Task 2: Add unit tests for NBEcom and nbeprotocol imports
- Created `tests/Pellmonsrv/plugins/test_nbecom_imports.py` (74 lines) with 5 test cases:
  - `test_nbecom_plugin_import_and_instantiation`: tests clean import and instantiation of `nbecomplugin()`, verifying core methods.
  - `test_nbeprotocol_proxy_import_and_instantiation`: verifies clean import and instantiation of `Proxy("testpass")` with mocked UDP socket and patched background threads, asserting key protocol attributes.
  - `test_nbeprotocol_request_frame_instantiation`: tests instantiation and field defaults of `Request_frame()`.
  - `test_nbeprotocol_response_frame_instantiation`: tests instantiation of `Response_frame(req)` with a request frame reference.
  - `test_nbeprotocol_language_import_and_mappings`: tests loading and accessibility of language dictionaries and enumerations.

## Verification Results

1. Automated import verification:
```bash
$env:PYTHONPATH="src"; venv-py3/Scripts/python.exe -c "import Pellmonsrv.plugins.nbecom; import Pellmonsrv.plugins.nbecom.nbeprotocol.protocol; from Pellmonsrv.plugins.nbecom.nbeprotocol.protocol import Proxy"
# Exit code: 0
```

2. sys.path mutation check:
Verified that importing `Pellmonsrv.plugins.nbecom` does not modify `sys.path`.

3. Unit test execution:
```bash
venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_nbecom_imports.py -v
# 5 passed in 0.06s
```

4. Deferred protocol import test (TEST-02 Layer 2):
`tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import` PASSED cleanly.

5. Full suite execution:
53 passed, 8 skipped, 0 failed.

## Deviations from Plan

### Auto-fixed Python 3 map iteration in `nbeprotocol/language.py`
- **Deviation**: In `language.py`, converted `map(...)` to `list(map(...))` in `lang = [...]`.
- **Rationale**: In Python 3, `map()` returns a single-use iterator. Calling `dict(lang)` on line 30 consumed the inner tuples, causing line 39 (`get_settings_enumerations`) to raise `ValueError: not enough values to unpack (expected 2, got 0)` during module import. Converting the inner pairs to lists preserves Python 2 list behavior and allows repeatable iteration.

## Commits

- `e9597f2` fix(phase-3): fix intra-package relative imports in NBEcom and nbeprotocol
- `b936e83` test(phase-3): add unit tests for NBEcom and nbeprotocol imports
