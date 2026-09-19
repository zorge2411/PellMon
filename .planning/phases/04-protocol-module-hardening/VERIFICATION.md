# Phase 4: Protocol Module Hardening (Bytes/Str Semantics) — Independent Verification Report

**Phase:** 4 — Protocol Module Hardening (Bytes/Str Semantics)  
**Auditor:** Independent GSD Verifier  
**Date:** 2026-09-18  
**Target Environment:** Windows / `venv-py3/Scripts/python.exe` (Python 3.14.0, pytest 9.1.1)  
**Verdict:** **PASS**

---

## Executive Summary

Phase 4 goals, requirements (`PROTO-01`, `PROTO-02`, `PROTO-03`, `PROTO-04`, `PROTO-05`, and architectural decision `D-05`), and all ROADMAP success criteria have been independently audited and verified using automated commands against `venv-py3/Scripts/python.exe`.

- **Full test suite execution:** 83 passed, 8 skipped (platform-dependent Linux/Pi dependencies: D-Bus, GLib, rrdtool, wiringpi), 0 failed, 0 known_broken.
- **Green baseline:** Exit code 0 across the test suite (`pytest tests/ -q`), establishing a 100% green test baseline.
- **NBE protocol bytes/str handling & transport injection:** `nbeprotocol.Proxy.get()` parses and splits payload responses on `'='` and `';'` cleanly without raising `TypeError`, and `Proxy` accepts constructor-injected transports with background threads suppressed.
- **Scotte protocol transport injection & frame round-trips:** `Scotteprotocol.Protocol` accepts constructor-injected transports (such as `loop://`), checksum verification handles both `str` and `bytes` deterministically without `TypeError`, and per-frame round-trips (`FrameZ00`–`FrameZ03`) pass with synthetic frames.
- **Calculate plugin hardening:** Obsolete Python 2 `from string import maketrans` import removed (PROTO-05); `setItem` replaced `unicode(value)` with `str(value)` (PROTO-02); AST inspections verify 0 occurrences of `maketrans` or `unicode`.
- **Daemon stderr buffering:** `src/Pellmonsrv/daemon.py:72` stderr redirection updated to line-buffered mode (`buffering=1`), eliminating `ValueError: can't have unbuffered text I/O` under Python 3 (PROTO-03).
- **Database keyval confval upsert:** `Keyval_storage.writeval()` parameter binding corrected in `src/Pellmonsrv/database.py:199` to `(item, value, confval)` (D-05), preserving existing item values when updating configuration entries.

---

## Verification Commands & Execution Results

### 1. Full Test Suite Run
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/ -v`  
**Exit Code:** `0`  
**Summary:** `83 passed, 8 skipped, 2 warnings in 2.00s` (0 failures, 0 known_broken)

```
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_calculate_does_not_import_maketrans PASSED [  1%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_calculate_has_no_unicode_references PASSED [  2%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_calc_execution_with_string_values PASSED [  3%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_setitem_uses_str_and_returns_ok PASSED [  4%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_setitem_calc_failure_logs_exception PASSED [  6%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_getitem_calc_failure_visibility PASSED [  7%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_plain_item_access_produces_no_log_records PASSED [  8%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_activate_reraise_preserved PASSED [  9%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_setitem_calc_failure_visibility PASSED [ 10%]
tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py::test_loop_serial_roundtrip PASSED [ 12%]
tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py::test_udp_send_uses_mock_not_real_network PASSED [ 13%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_init_injectable_transport PASSED [ 14%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_request_frame_encode_decode PASSED [ 15%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_response_frame_encode_decode_and_parse_payload PASSED [ 16%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_get_single_parameter_returns_str PASSED [ 18%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_get_parameter_group_returns_list_of_str PASSED [ 19%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_roundtrip_with_injected_transport PASSED [ 20%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbecom_plugin_import_and_instantiation PASSED [ 21%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_proxy_import_and_instantiation PASSED [ 22%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_request_frame_instantiation PASSED [ 24%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_response_frame_instantiation PASSED [ 25%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_language_import_and_mappings PASSED [ 26%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_initialization_defaults PASSED [ 27%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_initialization_custom PASSED [ 28%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_stderr_buffering_avoids_valueerror PASSED [ 30%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_source_ast_buffering PASSED [ 31%]
tests/Pellmonsrv/test_database.py::test_init_creates_keyval_table PASSED [ 32%]
tests/Pellmonsrv/test_database.py::test_init_fallback_path_when_table_missing PASSED [ 33%]
tests/Pellmonsrv/test_database.py::test_writeval_readval_roundtrip PASSED [ 34%]
tests/Pellmonsrv/test_database.py::test_writeval_coerces_non_str_value PASSED [ 36%]
tests/Pellmonsrv/test_database.py::test_readval_missing_key_returns_error_string PASSED [ 37%]
tests/Pellmonsrv/test_database.py::test_writeval_with_confval_sets_both_columns PASSED [ 38%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_plugin_activation_failure_logs_traceback PASSED [ 39%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_plugin_activation_debug_mode_reraises PASSED [ 40%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_poller_item_read_failure_logs_traceback PASSED [ 42%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_module_level_logger_available_before_daemon_run PASSED [ 43%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_broken_plugin_exec_failure_logs_error_with_traceback PASSED [ 44%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_malformed_descriptor_logs_debug_with_traceback PASSED [ 45%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_normal_plugin_scan_probe_stays_silent PASSED [ 46%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_import_and_dummy_database PASSED [ 48%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_serial_open_failure_logs_exception PASSED [ 49%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_set_item_unexpected_error_logs_exception PASSED [ 50%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scottecom_plugin_import_and_instantiation PASSED [ 51%]
tests/Pellmonweb/test_auth.py::test_check_credentials_success PASSED     [ 53%]
tests/Pellmonweb/test_auth.py::test_check_credentials_wrong_password PASSED [ 54%]
tests/Pellmonweb/test_auth.py::test_check_credentials_unknown_user PASSED [ 55%]
tests/Pellmonweb/test_auth.py::test_login_sets_session_and_redirects_on_success PASSED [ 56%]
tests/Pellmonweb/test_auth.py::test_login_failure_renders_loginform_without_session PASSED [ 57%]
tests/Pellmonweb/test_auth.py::test_logout_clears_session PASSED         [ 59%]
tests/test_no_ad_hoc_print.py::test_no_ad_hoc_print_calls_in_runtime_code PASSED [ 60%]
tests/test_no_ad_hoc_print.py::test_print_allowlist_is_not_vacuous PASSED [ 61%]
tests/test_no_sys_path_shims.py::test_no_sys_path_mutation_in_src PASSED [ 62%]
tests/test_no_sys_path_shims.py::test_no_implicit_sibling_imports_in_target_packages PASSED [ 63%]
tests/test_no_sys_path_shims.py::test_no_implicit_sibling_imports_in_all_src PASSED [ 65%]
tests/test_no_sys_path_shims.py::test_detector_identifies_synthetic_violations PASSED [ 66%]
tests/test_plugin_imports.py::test_plugin_discovery_is_not_vacuous PASSED [ 67%]
tests/test_plugin_imports.py::test_plugin_module_imports[calculate] SKIPPED [ 68%]
tests/test_plugin_imports.py::test_plugin_module_imports[cleaning] PASSED [ 70%]
tests/test_plugin_imports.py::test_plugin_module_imports[consumption] SKIPPED [ 71%]
tests/test_plugin_imports.py::test_plugin_module_imports[customalarms] SKIPPED [ 72%]
tests/test_plugin_imports.py::test_plugin_module_imports[exec] PASSED    [ 73%]
tests/test_plugin_imports.py::test_plugin_module_imports[heatingcircuit] PASSED [ 74%]
tests/test_plugin_imports.py::test_plugin_module_imports[nbecom] PASSED  [ 75%]
tests/test_plugin_imports.py::test_plugin_module_imports[onewire] PASSED [ 77%]
tests/test_plugin_imports.py::test_plugin_module_imports[openweathermap] PASSED [ 78%]
tests/test_plugin_imports.py::test_plugin_module_imports[owfs] PASSED    [ 79%]
tests/test_plugin_imports.py::test_plugin_module_imports[pelletcalc] SKIPPED [ 80%]
tests/test_plugin_imports.py::test_plugin_module_imports[raspberrygpio] SKIPPED [ 81%]
tests/test_plugin_imports.py::test_plugin_module_imports[scottecom] PASSED [ 83%]
tests/test_plugin_imports.py::test_plugin_module_imports[silolevel] SKIPPED [ 84%]
tests/test_plugin_imports.py::test_plugin_module_imports[testplugin] PASSED [ 85%]
tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import PASSED [ 86%]
tests/test_plugin_imports.py::test_skip_allowlist_cannot_hide_migration_defects PASSED [ 87%]
tests/test_core_modules_import[Pellmonsrv.pellmonsrv] SKIPPED [ 89%]
tests/test_core_modules_import[Pellmonsrv.database] PASSED [ 90%]
tests/test_core_modules_import[Pellmonweb.pellmonweb] SKIPPED [ 91%]
tests/test_core_modules_import[Pellmonweb.pellmonconf] PASSED [ 92%]
tests/test_protocol_coexistence.py::test_protocol_coexistence PASSED     [ 93%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_checksum_calculation_and_verification_str PASSED [ 95%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_checksum_deterministic_on_bytes PASSED [ 96%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_checksum_disabled PASSED [ 97%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame0-FrameZ00] PASSED [ 98%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame1-FrameZ01] PASSED [100%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame2-FrameZ02] PASSED [ 1%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame3-FrameZ03] PASSED [ 2%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_z00_getitem_integration PASSED [ 3%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parse_error_rejection PASSED [ 4%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_serial_loop_transport_roundtrip PASSED [ 6%]
tests/test_socket_guardrail.py::test_real_socket_construction_is_blocked PASSED [ 7%]
tests/test_socket_guardrail.py::test_real_tcp_socket_construction_is_blocked PASSED [ 8%]
tests/test_socket_guardrail.py::test_mocked_udp_socket_fixture_bypasses_the_block PASSED [10%]
```

### 2. Green Baseline Check
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/ -q`  
**Exit Code:** `0`  
**Output:** `83 passed, 8 skipped, 2 warnings in 1.99s`

### 3. NBE Roundtrip & Proxy.get() Unit Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py -v`  
**Exit Code:** `0`  
**Summary:** `6 passed in 0.06s`  
- `test_proxy_init_injectable_transport` PASSED
- `test_request_frame_encode_decode` PASSED
- `test_response_frame_encode_decode_and_parse_payload` PASSED
- `test_proxy_get_single_parameter_returns_str` PASSED
- `test_proxy_get_parameter_group_returns_list_of_str` PASSED
- `test_proxy_roundtrip_with_injected_transport` PASSED

### 4. Scotte Roundtrip & Transport Unit Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/test_scotte_protocol_roundtrip.py -v`  
**Exit Code:** `0`  
**Summary:** `10 passed in 0.04s`  
- `test_scotte_checksum_calculation_and_verification_str` PASSED
- `test_scotte_checksum_deterministic_on_bytes` PASSED
- `test_scotte_checksum_disabled` PASSED
- `test_scotte_frame_parsing_roundtrip[frame0-FrameZ00]` PASSED
- `test_scotte_frame_parsing_roundtrip[frame1-FrameZ01]` PASSED
- `test_scotte_frame_parsing_roundtrip[frame2-FrameZ02]` PASSED
- `test_scotte_frame_parsing_roundtrip[frame3-FrameZ03]` PASSED
- `test_scotte_frame_z00_getitem_integration` PASSED
- `test_scotte_frame_parse_error_rejection` PASSED
- `test_scotte_serial_loop_transport_roundtrip` PASSED

### 5. Calculate Plugin Hardening Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_calculate_hardening.py -v`  
**Exit Code:** `0`  
**Summary:** `5 passed in 0.06s`  
- `test_calculate_does_not_import_maketrans` PASSED
- `test_calculate_has_no_unicode_references` PASSED
- `test_calc_execution_with_string_values` PASSED
- `test_setitem_uses_str_and_returns_ok` PASSED
- `test_setitem_calc_failure_logs_exception` PASSED

### 6. Daemon Hardening Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_daemon_hardening.py -v`  
**Exit Code:** `0`  
**Summary:** `4 passed in 0.04s`  
- `test_daemon_initialization_defaults` PASSED
- `test_daemon_initialization_custom` PASSED
- `test_daemon_stderr_buffering_avoids_valueerror` PASSED
- `test_daemon_source_ast_buffering` PASSED

### 7. Database writeval Confval-Upsert Tests
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_database.py -k test_writeval -v`  
**Exit Code:** `0`  
**Summary:** `3 passed, 3 deselected in 0.09s`  
- `test_writeval_readval_roundtrip` PASSED
- `test_writeval_coerces_non_str_value` PASSED
- `test_writeval_with_confval_sets_both_columns` PASSED (verifies existing `value` column preserved upon confval update)

### 8. Static & Source Inspections
- **Calculate `maketrans` / `unicode` audit:**
  - `calculate/__init__.py`: 0 matches for `maketrans` or `unicode`.
  - `calculate/__init__.py:350`: `stack = [str(value)]`.
- **Daemon stderr buffering audit:**
  - `src/Pellmonsrv/daemon.py:72`: `se = open(self.stderr, 'a+', buffering=1)`
- **NBEcom `Proxy.get()` audit:**
  - `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:148,150`: uses `.split('=', 1)` and `.split(';')` directly on decoded payload `str`.
- **Constructor-injectable transport audit:**
  - `src/Scotteprotocol/protocol.py:33`: `def __init__(self, device, version_string, transport=None, start_thread=True):`
  - `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:40`: `def __init__(self, password, port=1920, addr=None, serial=None, transport=None, start_threads=True):`
- **Database upsert binding audit:**
  - `src/Pellmonsrv/database.py:199`: `(item, value, confval)` correctly bound to `INSERT OR REPLACE INTO keyval(item, value, confvalue) VALUES(?, ?, ?)`.

---

## Must-Haves & Success Criteria Audit

| Item | Requirement | ROADMAP Success Criterion | Verification Evidence | Status |
|------|-------------|---------------------------|-----------------------|--------|
| **SC-1** | `PROTO-01` | NBEcom `Proxy.get()` splits response payloads correctly without raising `TypeError`, verified by a mocked-UDP round-trip test. | `test_proxy_get_single_parameter_returns_str` and `test_proxy_get_parameter_group_returns_list_of_str` PASSED in `tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py`. | **PASS** |
| **SC-2** | `PROTO-02` / `PROTO-05` | Calculate plugin's `setItem()` no longer raises `NameError` from leftover Python 2 `unicode()` call, and imports cleanly without `maketrans` error. | `test_calculate_hardening.py` (5 tests) PASSED; AST verifies no `unicode` or `maketrans` in `src/Pellmonsrv/plugins/calculate/__init__.py`. | **PASS** |
| **SC-3** | `PROTO-03` | The daemon can redirect stderr to a log file in daemonized mode without raising `ValueError: can't have unbuffered text I/O`. | `test_daemon_hardening.py` (4 tests) PASSED; `daemon.py:72` confirmed to use `buffering=1`. | **PASS** |
| **SC-4** | `PROTO-04` | `Scotteprotocol.Protocol` and `nbeprotocol.Proxy` accept a constructor-injectable `transport` parameter, and per-frame-type encode/decode round-trip tests pass against it via the Phase 1 harness. | `test_scotte_protocol_roundtrip.py` (10 tests) and `test_nbe_protocol_roundtrip.py` (6 tests) PASSED using `loop://` and mock UDP transports. | **PASS** |
| **Tech Debt** | `D-05` | `Keyval_storage.writeval()` confval-upsert parameter binding preserves existing value when updating `confval`. | `tests/Pellmonsrv/test_database.py::test_writeval_with_confval_sets_both_columns` queries SQLite directly and confirms value preservation; all 6 database tests PASSED. | **PASS** |
| **Baseline** | Test Contract | Full test suite has zero failures, zero known_broken entries. | `pytest tests/ -v` produces 83 passed, 8 skipped (platform deps), 0 failed; `pytest tests/ -q` exits with code 0. | **PASS** |

---

## Verdict

```
verdict: PASS
must_haves_checked: 6
must_haves_passed: 6
summary: Phase 4 successfully resolved bytes/str semantics and protocol bugs in NBEcom and Scotteprotocol, added constructor-injectable transports enabling hardware-free round-trip testing, hardened the Calculate plugin and Daemonizer against runtime crashes, fixed the Keyval_storage confval-upsert parameter binding, and established a 100% green 83-test verification baseline with 0 failures.
gaps: none
```
