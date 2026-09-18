---
phase: 03-import-strategy-plugin-loading
plan: 03
subsystem: yapsy & import-enforcement
tags: [python3, relative-imports, yapsy, ast, sys-path, pep-328]
dependency-graph:
  requires: []
  provides:
    - PEP 328 explicit relative imports in Pellmonsrv.yapsy managers
    - AST automated enforcement test tests/test_no_sys_path_shims.py for zero sys.path shims and zero implicit sibling imports
  affects:
    - Pellmonsrv.yapsy plugin managers
    - CI / pytest import integrity test suite
tech-stack:
  added: []
  patterns:
    - Explicit relative imports (PEP 328)
    - AST static analysis enforcement test pattern
key-files:
  created:
    - tests/test_no_sys_path_shims.py
  modified:
    - src/Pellmonsrv/yapsy/ConfigurablePluginManager.py
    - src/Pellmonsrv/yapsy/VersionedPluginManager.py
decisions: [D-01, D-02, D-06]
metrics:
  completed: 2026-09-18
---

# Phase 3 Plan 03: Yapsy Managers & AST Import Enforcement Summary

Standardized yapsy internal imports on PEP 328 explicit relative syntax and implemented an AST-based enforcement test (`tests/test_no_sys_path_shims.py`) ensuring zero `sys.path` mutations and zero implicit sibling imports remain in `src/` (IMPORT-03).

## What Was Built

### Task 1: Fix intra-package relative imports in yapsy managers
- `src/Pellmonsrv/yapsy/ConfigurablePluginManager.py`: Converted implicit relative imports (`from IPlugin import IPlugin`, `from PluginManager import PluginManager, PluginManagerDecorator`, `from PluginManager import PLUGIN_NAME_FORBIDEN_STRING`) to PEP 328 explicit relative imports (`from .IPlugin ...`, `from .PluginManager ...`).
- `src/Pellmonsrv/yapsy/VersionedPluginManager.py`: Converted implicit relative imports (`from PluginManager import ...`, `from IPlugin import IPlugin`) to PEP 328 explicit relative imports (`from .PluginManager ...`, `from .IPlugin ...`).

### Task 2: Implement AST-based sys.path shim and relative import enforcement test
- Created `tests/test_no_sys_path_shims.py` (230 lines) with 4 test cases:
  - `test_no_sys_path_mutation_in_src`: Parses AST of all `*.py` files in `src/` (excluding `.py2bak`) and verifies zero calls to `sys.path.append`, `insert`, `extend`, or assignments to `sys.path`.
  - `test_no_implicit_sibling_imports_in_target_packages`: Parses AST of `Scotteprotocol`, `scottecom`, `nbecom` (including `nbeprotocol`), and `yapsy` packages to ensure no `level == 0` imports resolve to sibling modules or subpackages.
  - `test_no_implicit_sibling_imports_in_all_src`: Sweeps all package directories across `src/` to ensure full codebase compliance with PEP 328 intra-package relative import standards.
  - `test_detector_identifies_synthetic_violations`: Non-vacuous test ensuring the AST visitor correctly detects synthetic `sys.path` manipulations and implicit sibling imports while permitting valid relative and external imports.

## Verification Results

1. Automated import verification:
```bash
$env:PYTHONPATH="src"; venv-py3/Scripts/python.exe -c "import Pellmonsrv.yapsy.ConfigurablePluginManager; import Pellmonsrv.yapsy.VersionedPluginManager; print('yapsy ok')"
# Output: yapsy ok
```

2. Enforcement test execution:
```bash
venv-py3/Scripts/python.exe -m pytest tests/test_no_sys_path_shims.py -v
# 4 passed in 0.25s
```

3. Regression check with existing enforcement gates:
```bash
venv-py3/Scripts/python.exe -m pytest tests/test_no_sys_path_shims.py tests/test_no_ad_hoc_print.py -v
# 6 passed in 0.44s
```

## Deviations from Plan

None.

## Commits

- `5234098` fix(phase-3): Fix intra-package relative imports in yapsy managers
- `7aaf4a1` test(phase-3): Implement AST-based sys.path shim and relative import enforcement test
