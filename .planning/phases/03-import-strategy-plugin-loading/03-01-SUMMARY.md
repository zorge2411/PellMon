---
phase: 03-import-strategy-plugin-loading
plan: 01
subsystem: plugins/scottecom
tags: [python3, relative-imports, scotteprotocol, scottecom, sys-path, exception-visibility]
dependency-graph:
  requires: []
  provides:
    - PEP 328 explicit relative imports in Scotteprotocol and Pellmonsrv.plugins.scottecom
    - Zero sys.path mutations in Pellmonsrv/plugins/scottecom/__init__.py
    - Exception-visibility retrofit for Scotteprotocol/protocol.py (no bare except:)
    - Unit tests in tests/Pellmonsrv/test_scotteprotocol_logging.py
  affects:
    - Scotteprotocol package consumers
    - Pellmonsrv.plugins.scottecom plugin loading
tech-stack:
  added: []
  patterns:
    - Explicit relative imports (PEP 328)
    - Exception logging via logger.exception('...', ...) with exc_info
    - Specific exception handling for fallbacks (OSError, KeyError, IndexError, ValueError, TypeError)
key-files:
  created:
    - tests/Pellmonsrv/test_scotteprotocol_logging.py
  modified:
    - src/Scotteprotocol/__init__.py
    - src/Scotteprotocol/frames.py
    - src/Scotteprotocol/datamap.py
    - src/Scotteprotocol/protocol.py
    - src/Pellmonsrv/plugins/scottecom/__init__.py
    - src/Pellmonsrv/plugins/scottecom/scottecom.py
    - src/Pellmonsrv/plugins/scottecom/menus.py
decisions: [D-01, D-02, D-03, D-04]
metrics:
  completed: 2026-09-18
---

# Phase 3 Plan 01: Scotteprotocol & ScotteCom Import Strategy and Exception Visibility Summary

Converted `src/Scotteprotocol/` and `src/Pellmonsrv/plugins/scottecom/` to PEP 328 explicit relative imports, removed the `sys.path.append` shim, retrofitted all 23 bare/broad exception blocks in `src/Scotteprotocol/protocol.py`, and added unit tests covering imports and exception logging.

## What Was Built

### Task 1: Fix intra-package relative imports in Scotteprotocol and ScotteCom
- `src/Scotteprotocol/__init__.py`: changed `from protocol import Protocol` to `from .protocol import Protocol`.
- `src/Scotteprotocol/frames.py`: changed `from protocol import Frame` to `from .protocol import Frame`.
- `src/Scotteprotocol/datamap.py`: changed `from frames import *` to `from .frames import *`.
- `src/Scotteprotocol/protocol.py`: changed `from enumerations import ...` and `from transformations import ...` to relative imports; in `createDataBase`, changed `from datamap import dataBaseMap` to `from .datamap import dataBaseMap`.
- `src/Pellmonsrv/plugins/scottecom/__init__.py`: removed `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` and changed `from scottecom import scottecom` to `from .scottecom import scottecom`.
- `src/Pellmonsrv/plugins/scottecom/scottecom.py`: changed `import menus` and `from descriptions import ...` to explicit relative imports.
- `src/Pellmonsrv/plugins/scottecom/menus.py`: changed `from datamenu import ...` to `from .datamenu import dataBaseTags`.

### Task 2: Retrofit exception visibility in Scotteprotocol/protocol.py
- Replaced serial port open error path with `logger.exception("Could not open serial port %s: %s\n", device, e)`.
- Replaced version and connection auto-detect fallback bare except clauses (lines 73, 79, 84, 90, 97, 102, 107) with `except (OSError, KeyError, IndexError, ValueError, TypeError):`.
- Narrowed queue wait timeout and queue full in `getItem` to `except queue.Empty:` and `except queue.Full:`, and logged queue creation errors via `logger.exception`.
- Narrowed enumeration lookup and formatting fallbacks in `getItem` to specific exception tuples (`KeyError, ValueError, IndexError, TypeError`, `ValueError, TypeError`).
- Narrowed transformations encoding/decoding to specific tuples (`KeyError, ValueError, TypeError, AttributeError`).
- Converted `setItem` value parse fallback to `except (ValueError, TypeError):` and added `logger.exception` on unexpected exceptions.
- Converted low-level serial communication and retry loops in `run()` (lines 253, 285, 311) to catch `(serial.SerialException, OSError)` and `Exception`, logging tracebacks via `logger.exception`.
- Converted queue response delivery error paths in `run()` (lines 296, 320, 326) to log via `logger.exception`.

### Task 3: Unit tests for Scotteprotocol imports and exception logging
- Created `tests/Pellmonsrv/test_scotteprotocol_logging.py` (68 lines) with 4 test cases:
  - `test_scotteprotocol_import_and_dummy_database`: tests `Protocol(None, '6.99')` initialization, dummy device flag, and item get/set operations.
  - `test_scotteprotocol_serial_open_failure_logs_exception`: verifies `logger.exception` with full traceback when serial port fails to open.
  - `test_scotteprotocol_set_item_unexpected_error_logs_exception`: verifies `logger.exception` with full traceback on unexpected `setItem` failure.
  - `test_scottecom_plugin_import_and_instantiation`: tests clean import and instantiation of `Pellmonsrv.plugins.scottecom.scottecom()`.

## Verification Results

1. Automated import test:
```bash
$env:PYTHONPATH="src"; venv-py3/Scripts/python.exe -c "import Scotteprotocol; from Scotteprotocol import Protocol; import Pellmonsrv.plugins.scottecom"
# Exit code: 0
```

2. Bare `except:` verification:
```powershell
Select-String -Path src/Scotteprotocol/protocol.py -Pattern "except:"
# Output: 0 matches (zero bare excepts remain)
```

3. Test suite execution:
```bash
venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_scotteprotocol_logging.py -v
# 4 passed in 0.05s
```

4. Plugin import integration:
`tests/test_plugin_imports.py::test_plugin_module_imports[scottecom]` PASSED (previously broken before Phase 3).

## Deviations from Plan

None. The tasks were executed strictly according to plan specifications.

## Commits

- `94ba0c8` fix(phase-3): fix intra-package relative imports in Scotteprotocol and ScotteCom
- `33eb581` fix(phase-3): retrofit exception visibility in Scotteprotocol/protocol.py
- `7625106` test(phase-3): add unit tests for Scotteprotocol imports and exception logging
