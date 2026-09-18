# Phase 3: Import Strategy & Plugin Loading Fixes - Context

**Gathered:** 2026-09-18
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase fixes the broken implicit relative imports across `src/Scotteprotocol/`, `src/Pellmonsrv/plugins/scottecom/`, and `src/Pellmonsrv/plugins/nbecom/` (including `nbeprotocol/`), eliminates all `sys.path.append` shims in `src/`, standardizes on explicit relative imports (PEP 328), executes the deferred exception-visibility retrofit for `src/Scotteprotocol/protocol.py` (inherited from Phase 2), and proves that ScotteCom and NBEcom both import and activate cleanly in the same daemon process without module collision.

Underlying protocol payload logic bugs (such as bytes/str mixing in `Proxy.get()`) belong to Phase 4; security issues belong to Phase 5.

</domain>

<decisions>
## Implementation Decisions

### D-01: PEP 328 Explicit Relative Imports
All intra-package imports in `src/` must use explicit relative syntax (e.g. `from .protocol import Protocol`, `from .frames import *`, `from .datamap import dataBaseTags`). No bare implicit relative imports (`from protocol import Protocol`) may remain anywhere in `src/`.

### D-02: Zero `sys.path` Mutations
Remove `sys.path.append(os.path.dirname(os.path.abspath(__file__)))` from `src/Pellmonsrv/plugins/scottecom/__init__.py` and `src/Pellmonsrv/plugins/nbecom/__init__.py`. Plugin packages are regular Python packages located under `Pellmonsrv.plugins`; plugin `__init__.py` files import their local submodules using explicit relative imports (`from .scottecom import scottecom`, `from .nbeprotocol.protocol import Proxy`).

### D-03: Top-level `Scotteprotocol` Package Architecture
`src/Scotteprotocol` is a standalone top-level package installed into `site-packages` (or resolved via `src/` in development). Intra-package imports inside `Scotteprotocol` use explicit relative imports (`from .protocol import Protocol`, `from .enumerations import dataEnumerations`, etc.). External consumers (`src/Pellmonsrv/plugins/scottecom/scottecom.py` and test suites) import it as `from Scotteprotocol import Protocol`.

### D-04: Inherited `Scotteprotocol/protocol.py` Exception Visibility Sweep
Phase 3 inherits the exception-visibility sweep of `src/Scotteprotocol/protocol.py`'s 19 bare/broad excepts (deferred from Phase 2 because the module was unimportable under Python 3). Following Phase 2's Category A/B disposition rules:
- Category A (failure paths: serial I/O errors, frame read/write failures, unexpected exceptions) become `logger.exception(...)` with full traceback attached.
- Category B (expected fallbacks: dictionary key lookups, numeric conversion fallbacks, optional config fallbacks) are narrowed to specific exception types (`KeyError`, `ValueError`, etc.) with debug logging or clean fallback return values.

### D-05: Elimination of `known_broken` Baseline
Phase 1 established `tests/test_plugin_imports.py` with two expected-red failures marked `@pytest.mark.known_broken` (`test_plugin_module_imports[scottecom]` and `test_nbecom_deferred_protocol_import`). With Phase 3 fixes in place:
- Both tests must pass cleanly.
- `KNOWN_BROKEN_MODULES` in `tests/test_plugin_imports.py` is cleared.
- `tests/README.md` is updated to reflect that the suite has 0 expected-red failures.

### D-06: Enforcement and Coexistence Gates
Add automated pytest gates:
- `tests/test_no_sys_path_shims.py`: statically asserts no `sys.path.append` or `sys.path.insert` shims exist in `src/`, and no implicit relative sibling imports exist in protocol/plugin modules.
- `tests/test_protocol_coexistence.py`: dynamically verifies that `Scotteprotocol` and `Pellmonsrv.plugins.nbecom.nbeprotocol` can be imported and used simultaneously in the same interpreter session without namespace shadowing or collision.

</decisions>

<canonical_refs>
## Canonical References

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — IMPORT-01, IMPORT-02, IMPORT-03, IMPORT-04
- `.planning/ROADMAP.md` — Phase 3 Goal, Requirements, and Success Criteria
- `.planning/phases/02-exception-visibility-retrofit/02-06-SUMMARY.md` — Phase 2 closeout and deferral handover to Phase 3

### Test Harness
- `tests/test_plugin_imports.py` — TEST-02 import test containing `KNOWN_BROKEN_MODULES`
- `tests/README.md` — Test suite baseline documentation

</canonical_refs>
