# Phase 3: Import Strategy & Plugin Loading Fixes — Independent Verification Report

**Phase:** 3 — Import Strategy & Plugin Loading Fixes  
**Auditor:** Independent GSD Verifier  
**Date:** 2026-09-18  
**Target Environment:** Windows / `venv-py3/Scripts/python.exe` (Python 3.14.0, pytest 9.1.1)  
**Verdict:** **PASS**

---

## Executive Summary

Phase 3 goals, requirements (`IMPORT-01`, `IMPORT-02`, `IMPORT-03`, `IMPORT-04`, and inherited `OBS-02`), and all four ROADMAP success criteria have been independently audited and verified using automated commands against `venv-py3/Scripts/python.exe`.

- **Full test suite execution:** 58 passed, 8 skipped (platform-unavailable Linux/Pi dependencies: D-Bus, GLib, rrdtool, wiringpi), 0 failed, 0 known_broken.
- **Green baseline:** Exit code 0 across the test suite (`pytest tests/ -q`), establishing a zero-failure baseline with `KNOWN_BROKEN_MODULES = set()`.
- **ScotteCom plugin & protocol imports:** `Scotteprotocol` imports cleanly as a top-level package with PEP 328 intra-package relative imports, and `Pellmonsrv.plugins.scottecom` imports and activates without `ModuleNotFoundError`.
- **NBEcom plugin & protocol imports:** `Pellmonsrv.plugins.nbecom` and its `nbeprotocol` subpackage use PEP 328 explicit relative imports; deferred activate-time protocol import passes cleanly.
- **sys.path shims & PEP 328 compliance:** Zero `sys.path` modifications exist anywhere in `src/` runtime code (verified by `git grep` and AST static analysis in `tests/test_no_sys_path_shims.py`). Intra-package imports use explicit relative imports across all target packages and codebase-wide.
- **Protocol coexistence:** `Scotteprotocol` and `Pellmonsrv.plugins.nbecom.nbeprotocol` co-exist simultaneously in the same interpreter session without duplicate-module collision or namespace interference (`tests/test_protocol_coexistence.py`).
- **Inherited exception sweep:** All 23 bare/broad exception sites in `src/Scotteprotocol/protocol.py` have been refactored (0 bare `except:` remain), critical error paths log tracebacks via `logger.exception(...)`, and fallback handlers catch targeted exception tuples.

---

## Verification Commands & Execution Results

### 1. Full Test Suite Run
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/ -v`  
**Exit Code:** `0`  
**Summary:** `58 passed, 8 skipped, 2 warnings in 1.97s` (0 failures, 0 known_broken)

```
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_setitem_namerror_visibility PASSED [  1%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_getitem_calc_failure_visibility PASSED [  3%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_plain_item_access_produces_no_log_records PASSED [  4%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_activate_reraise_preserved PASSED [  6%]
tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py::test_loop_serial_roundtrip PASSED [  7%]
tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py::test_udp_send_uses_mock_not_real_network PASSED [  9%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbecom_plugin_import_and_instantiation PASSED [ 10%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_proxy_import_and_instantiation PASSED [ 12%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_request_frame_instantiation PASSED [ 13%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_response_frame_instantiation PASSED [ 15%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_language_import_and_mappings PASSED [ 16%]
tests/Pellmonsrv/test_database.py::test_init_creates_keyval_table PASSED [ 18%]
tests/Pellmonsrv/test_database.py::test_init_fallback_path_when_table_missing PASSED [ 19%]
tests/Pellmonsrv/test_database.py::test_writeval_readval_roundtrip PASSED [ 21%]
tests/Pellmonsrv/test_database.py::test_writeval_coerces_non_str_value PASSED [ 22%]
tests/Pellmonsrv/test_database.py::test_readval_missing_key_returns_error_string PASSED [ 24%]
tests/Pellmonsrv/test_database.py::test_writeval_with_confval_sets_both_columns PASSED [ 25%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_plugin_activation_failure_logs_traceback PASSED [ 27%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_plugin_activation_debug_mode_reraises PASSED [ 28%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_poller_item_read_failure_logs_traceback PASSED [ 30%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_module_level_logger_available_before_daemon_run PASSED [ 31%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_broken_plugin_exec_failure_logs_error_with_traceback PASSED [ 33%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_malformed_descriptor_logs_debug_with_traceback PASSED [ 34%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_normal_plugin_scan_probe_stays_silent PASSED [ 36%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_import_and_dummy_database PASSED [ 37%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_serial_open_failure_logs_exception PASSED [ 39%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_set_item_unexpected_error_logs_exception PASSED [ 40%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scottecom_plugin_import_and_instantiation PASSED [ 42%]
tests/Pellmonweb/test_auth.py::test_check_credentials_success PASSED     [ 43%]
tests/Pellmonweb/test_auth.py::test_check_credentials_wrong_password PASSED [ 45%]
tests/Pellmonweb/test_auth.py::test_check_credentials_unknown_user PASSED [ 46%]
tests/Pellmonweb/test_auth.py::test_login_sets_session_and_redirects_on_success PASSED [ 48%]
tests/Pellmonweb/test_auth.py::test_login_failure_renders_loginform_without_session PASSED [ 50%]
tests/Pellmonweb/test_auth.py::test_logout_clears_session PASSED         [ 51%]
tests/test_no_ad_hoc_print.py::test_no_ad_hoc_print_calls_in_runtime_code PASSED [ 53%]
tests/test_no_ad_hoc_print.py::test_print_allowlist_is_not_vacuous PASSED [ 54%]
tests/test_no_sys_path_shims.py::test_no_sys_path_mutation_in_src PASSED [ 56%]
tests/test_no_sys_path_shims.py::test_no_implicit_sibling_imports_in_target_packages PASSED [ 57%]
tests/test_no_sys_path_shims.py::test_no_implicit_sibling_imports_in_all_src PASSED [ 59%]
tests/test_no_sys_path_shims.py::test_detector_identifies_synthetic_violations PASSED [ 60%]
tests/test_plugin_imports.py::test_plugin_discovery_is_not_vacuous PASSED [ 62%]
tests/test_plugin_imports.py::test_plugin_module_imports[calculate] SKIPPED [ 63%]
tests/test_plugin_imports.py::test_plugin_module_imports[cleaning] PASSED [ 65%]
tests/test_plugin_imports.py::test_plugin_module_imports[consumption] SKIPPED [ 66%]
tests/test_plugin_imports.py::test_plugin_module_imports[customalarms] SKIPPED [ 68%]
tests/test_plugin_imports.py::test_plugin_module_imports[exec] PASSED    [ 69%]
tests/test_plugin_imports.py::test_plugin_module_imports[heatingcircuit] PASSED [ 71%]
tests/test_plugin_imports.py::test_plugin_module_imports[nbecom] PASSED  [ 72%]
tests/test_plugin_imports.py::test_plugin_module_imports[onewire] PASSED [ 74%]
tests/test_plugin_imports.py::test_plugin_module_imports[openweathermap] PASSED [ 75%]
tests/test_plugin_imports.py::test_plugin_module_imports[owfs] PASSED    [ 77%]
tests/test_plugin_imports.py::test_plugin_module_imports[pelletcalc] SKIPPED [ 78%]
tests/test_plugin_imports.py::test_plugin_module_imports[raspberrygpio] SKIPPED [ 80%]
tests/test_plugin_imports.py::test_plugin_module_imports[scottecom] PASSED [ 81%]
tests/test_plugin_imports.py::test_plugin_module_imports[silolevel] SKIPPED [ 83%]
tests/test_plugin_imports.py::test_plugin_module_imports[testplugin] PASSED [ 84%]
tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import PASSED [ 86%]
tests/test_plugin_imports.py::test_skip_allowlist_cannot_hide_migration_defects PASSED [ 87%]
tests/test_core_modules_import[Pellmonsrv.pellmonsrv] SKIPPED [ 89%]
tests/test_core_modules_import[Pellmonsrv.database] PASSED [ 90%]
tests/test_core_modules_import[Pellmonweb.pellmonweb] SKIPPED [ 92%]
tests/test_core_modules_import[Pellmonweb.pellmonconf] PASSED [ 93%]
tests/test_protocol_coexistence.py::test_protocol_coexistence PASSED     [ 95%]
tests/test_socket_guardrail.py::test_real_socket_construction_is_blocked PASSED [ 96%]
tests/test_socket_guardrail.py::test_real_tcp_socket_construction_is_blocked PASSED [ 98%]
tests/test_socket_guardrail.py::test_mocked_udp_socket_fixture_bypasses_the_block PASSED [100%]
```

### 2. Green Baseline Check
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/ -q`  
**Exit Code:** `0`  
**Output:** `58 passed, 8 skipped, 2 warnings in 1.93s`

### 3. Plugin Import Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/test_plugin_imports.py -v`  
**Exit Code:** `0`  
**Summary:** `14 passed, 8 skipped in 0.36s`  
- `test_plugin_module_imports[scottecom]` PASSED
- `test_plugin_module_imports[nbecom]` PASSED
- `test_nbecom_deferred_protocol_import` PASSED

### 4. Protocol Coexistence Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/test_protocol_coexistence.py -v`  
**Exit Code:** `0`  
**Summary:** `1 passed in 0.06s`  
- `test_protocol_coexistence` PASSED: verifies `Scotteprotocol.protocol` and `Pellmonsrv.plugins.nbecom.nbeprotocol.protocol` are distinct objects in `sys.modules`, `frames` modules have disjoint attribute namespaces (`FrameZ00` vs `Request_frame`), and both `Protocol` and `Proxy` instantiate simultaneously without conflict.

### 5. sys.path Shim & PEP 328 AST Enforcement Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/test_no_sys_path_shims.py -v`  
**Exit Code:** `0`  
**Summary:** `4 passed in 0.23s`  
- `test_no_sys_path_mutation_in_src` PASSED
- `test_no_implicit_sibling_imports_in_target_packages` PASSED
- `test_no_implicit_sibling_imports_in_all_src` PASSED
- `test_detector_identifies_synthetic_violations` PASSED

### 6. Ad Hoc Print Enforcement Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/test_no_ad_hoc_print.py -v`  
**Exit Code:** `0`  
**Summary:** `2 passed in 0.19s`

### 7. Scotteprotocol Logging & Import Unit Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_scotteprotocol_logging.py -v`  
**Exit Code:** `0`  
**Summary:** `4 passed in 0.05s`  
- `test_scotteprotocol_import_and_dummy_database` PASSED
- `test_scotteprotocol_serial_open_failure_logs_exception` PASSED
- `test_scotteprotocol_set_item_unexpected_error_logs_exception` PASSED
- `test_scottecom_plugin_import_and_instantiation` PASSED

### 8. NBEcom Import & Proxy Unit Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_nbecom_imports.py -v`  
**Exit Code:** `0`  
**Summary:** `5 passed in 0.06s`  
- `test_nbecom_plugin_import_and_instantiation` PASSED
- `test_nbeprotocol_proxy_import_and_instantiation` PASSED
- `test_nbeprotocol_request_frame_instantiation` PASSED
- `test_nbeprotocol_response_frame_instantiation` PASSED
- `test_nbeprotocol_language_import_and_mappings` PASSED

### 9. Repo-Wide sys.path Inspection
**Command:** `git grep -n "sys.path" src/`  
**Exit Code:** `1` (0 matches found)  
Confirms complete elimination of all `sys.path.append`, `sys.path.insert`, and `sys.path` assignments across `src/`.

---

## Must-Haves & Success Criteria Audit

| Item | Requirement | ROADMAP Success Criterion | Verification Evidence | Status |
|------|-------------|---------------------------|-----------------------|--------|
| **SC-1** | `IMPORT-01` | The ScotteCom plugin imports and activates successfully under Python 3 — Phase 1's broadened import-check passes for it with no `ModuleNotFoundError`. | `test_plugin_imports.py::test_plugin_module_imports[scottecom]` PASSED; `tests/Pellmonsrv/test_scotteprotocol_logging.py` (4 tests) PASSED; `KNOWN_BROKEN_MODULES` empty. | **PASS** |
| **SC-2** | `IMPORT-02` | The NBEcom plugin imports and activates successfully under Python 3 — Phase 1's broadened import-check passes for it with no `ModuleNotFoundError`. | `test_plugin_imports.py::test_plugin_module_imports[nbecom]` PASSED; `test_nbecom_deferred_protocol_import` PASSED; `tests/Pellmonsrv/plugins/test_nbecom_imports.py` (5 tests) PASSED. | **PASS** |
| **SC-3** | `IMPORT-03` | A repo-wide search finds no remaining `sys.path.append` shims in `src/`; intra-package imports use explicit relative imports (PEP 328), with absolute imports used only at the yapsy `exec()`-loaded plugin `__init__.py` boundary. | `git grep -n "sys.path" src/` yields 0 matches; `tests/test_no_sys_path_shims.py` (4 AST tests) PASSED. | **PASS** |
| **SC-4** | `IMPORT-04` | `Scotteprotocol` and `nbecom/nbeprotocol` load together (both plugins active in the same daemon process) with no duplicate-module-name collision. | `tests/test_protocol_coexistence.py::test_protocol_coexistence` PASSED; separate `sys.modules` keys, distinct frames/classes, simultaneous instantiation confirmed. | **PASS** |
| **OBS-02** | `OBS-02` / `D-04` | Inherited: Exception-visibility sweep of `src/Scotteprotocol/protocol.py` (no bare `except:` swallowing exceptions). | `Select-String -Path src/Scotteprotocol/protocol.py -Pattern "except:"` yields 0 matches; 12 `logger.exception` calls present; unit tests assert exc_info capture. | **PASS** |
| **Baseline** | Test Contract | Full test suite has zero failures, zero known_broken entries. | `pytest tests/ -v` produces 58 passed, 8 skipped (platform deps), 0 failed; `tests/README.md` updated. | **PASS** |

---

## Verdict

```
verdict: PASS
must_haves_checked: 6
must_haves_passed: 6
summary: Phase 3 successfully resolved all Python 3 relative import breakages in Scotteprotocol, scottecom, and nbecom/nbeprotocol, eliminated all sys.path mutations from src/, refactored yapsy manager imports, retrofitted exception logging in Scotteprotocol/protocol.py, verified simultaneous protocol coexistence, and established a 100% green 0-failure pytest baseline.
gaps: none
```
