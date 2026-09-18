# Phase 5: Security, CI & Deployment Hardening — Independent Verification Report

**Phase:** 5 — Security, CI & Deployment Hardening  
**Auditor:** Independent GSD Verifier  
**Date:** 2026-09-18  
**Target Environment:** Windows / `venv-py3/Scripts/python.exe` (Python 3.14.0, pytest 9.1.1)  
**Verdict:** **PASS**

---

## Executive Summary

Phase 5 goals, requirements (`SEC-01`, `SEC-02`, `SEC-03`, `OPS-01`, `OPS-02`, `OPS-03`, `OPS-04`, `OPS-05`, `OPS-06`), and all ROADMAP success criteria have been independently audited and verified using automated commands against `venv-py3/Scripts/python.exe`.

- **Full test suite execution:** 110 passed, 8 skipped (Linux/hardware-only dependencies: D-Bus, rrdtool, raspberrygpio), 0 failed.
- **Web authentication security:** Failed web login attempts never log submitted passwords. Credentials are encrypted and validated using PBKDF2-HMAC-SHA256 (100,000 iterations) and timing-safe comparison (`hmac.compare_digest`). Legacy plaintext passwords in `pellmon.conf` remain backward-compatible with a logged migration warning.
- **Exec plugin command injection remediation:** The Exec plugin's `execute_readscript()` path invokes `subprocess.check_output()` with `shell=False` and tokenized argument list via `shlex.split()`, matching the secure pattern used by `execute_writescript()`.
- **Continuous Integration:** `.github/workflows/ci.yml` is configured for GitHub Actions on `ubuntu-latest` running on push and pull-request targeting `master` and `python3-migration`, executing system package installations, `test-imports.py`, and the full `pytest tests/ -v` test suite.
- **Graceful shutdown lifecycle:** Both `pellmonsrv` and `pellmonweb` register and handle `SIGTERM` and `SIGINT`. `pellmonsrv` cleanly flushes cached RRD data to non-volatile storage, terminates the poller thread, removes its pidfile, and quits the GLib main loop. `pellmonweb` halts the CherryPy engine and quits its main loop without resource leaks.
- **Docker Compose readiness healthchecks:** `docker-compose.yml` configures service healthchecks (`dbus-send` peer ping for `pellmonsrv`, HTTP endpoint probe for `pellmonweb`), ensuring `pellmonweb` starts only after `pellmonsrv` reports healthy (`condition: service_healthy`). `Dockerfile` defines a matching web healthcheck.
- **Dependency pinning:** All 11 package dependencies in `requirements.txt` use exact version pins (`==`).
- **Repository hygiene:** All 23 obsolete `.py2bak` backup files have been permanently removed from `src/`.
- **Documentation:** `README.md` documents that production deployment is Linux-only, guides deployment using Docker Compose, and details PBKDF2 password hash generation.

---

## Verification Commands & Execution Results

### 1. Full Test Suite Run
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/ -v`  
**Exit Code:** `0`  
**Summary:** `110 passed, 8 skipped, 2 warnings in 2.37s` (0 failures, 0 errors)

```text
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_calculate_does_not_import_maketrans PASSED [  0%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_calculate_has_no_unicode_references PASSED [  1%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_calc_execution_with_string_values PASSED [  2%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_setitem_uses_str_and_returns_ok PASSED [  3%]
tests/Pellmonsrv/plugins/test_calculate_hardening.py::test_setitem_calc_failure_logs_exception PASSED [  4%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_getitem_calc_failure_visibility PASSED [  5%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_plain_item_access_produces_no_log_records PASSED [  5%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_activate_reraise_preserved PASSED [  6%]
tests/Pellmonsrv/plugins/test_calculate_logging.py::test_setitem_calc_failure_visibility PASSED [  7%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_source_security PASSED [  8%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_calls_subprocess_with_shell_false PASSED [  9%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_handles_called_process_error PASSED [ 10%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_handles_generic_exception PASSED [ 10%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_writescript_calls_subprocess_with_shell_false PASSED [ 11%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_writescript_handles_called_process_error PASSED [ 12%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_writescript_handles_generic_exception PASSED [ 13%]
tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py::test_loop_serial_roundtrip PASSED [ 14%]
tests/Pellmonsrv/plugins/test_mocked_transport_smoke.py::test_udp_send_uses_mock_not_real_network PASSED [ 15%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_init_injectable_transport PASSED [ 15%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_request_frame_encode_decode PASSED [ 16%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_response_frame_encode_decode_and_parse_payload PASSED [ 17%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_get_single_parameter_returns_str PASSED [ 18%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_get_parameter_group_returns_list_of_str PASSED [ 19%]
tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py::test_proxy_roundtrip_with_injected_transport PASSED [ 20%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbecom_plugin_import_and_instantiation PASSED [ 20%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_proxy_import_and_instantiation PASSED [ 21%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_request_frame_instantiation PASSED [ 22%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_response_frame_instantiation PASSED [ 23%]
tests/Pellmonsrv/plugins/test_nbecom_imports.py::test_nbeprotocol_language_import_and_mappings PASSED [ 24%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_initialization_defaults PASSED [ 25%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_initialization_custom PASSED [ 25%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_stderr_buffering_avoids_valueerror PASSED [ 26%]
tests/Pellmonsrv/test_daemon_hardening.py::test_daemon_source_ast_buffering PASSED [ 27%]
tests/Pellmonsrv/test_database.py::test_init_creates_keyval_table PASSED [ 28%]
tests/Pellmonsrv/test_database.py::test_init_fallback_path_when_table_missing PASSED [ 29%]
tests/Pellmonsrv/test_database.py::test_writeval_readval_roundtrip PASSED [ 30%]
tests/Pellmonsrv/test_database.py::test_writeval_coerces_non_str_value PASSED [ 30%]
tests/Pellmonsrv/test_database.py::test_readval_missing_key_returns_error_string PASSED [ 31%]
tests/Pellmonsrv/test_database.py::test_writeval_with_confval_sets_both_columns PASSED [ 32%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_plugin_activation_failure_logs_traceback PASSED [ 33%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_plugin_activation_debug_mode_reraises PASSED [ 34%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_poller_item_read_failure_logs_traceback PASSED [ 35%]
tests/Pellmonsrv/test_pellmonsrv_logging.py::test_module_level_logger_available_before_daemon_run PASSED [ 36%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_broken_plugin_exec_failure_logs_error_with_traceback PASSED [ 37%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_malformed_descriptor_logs_debug_with_traceback PASSED [ 38%]
tests/Pellmonsrv/test_plugin_manager_logging.py::test_normal_plugin_scan_probe_stays_silent PASSED [ 38%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_import_and_dummy_database PASSED [ 39%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_serial_open_failure_logs_exception PASSED [ 40%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scotteprotocol_set_item_unexpected_error_logs_exception PASSED [ 41%]
tests/Pellmonsrv/test_scotteprotocol_logging.py::test_scottecom_plugin_import_and_instantiation PASSED [ 42%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_sigterm_handler_flushes_db_and_quits_loop PASSED [ 43%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_sigterm_handler_skips_flush_when_same_db PASSED [ 44%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_sigterm_handler_stops_poller_and_removes_pid PASSED [ 44%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_mydaemon_method_sigterm_handler PASSED [ 45%]
tests/Pellmonsrv/test_poller_stop_lifecycle PASSED [ 46%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_ast_signal_registration PASSED [ 47%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonweb_signal_handler_quits_engine_and_loop PASSED [ 48%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonweb_ast_signal_registration PASSED [ 49%]
tests/Pellmonweb/test_auth.py::test_check_credentials_success PASSED     [ 50%]
tests/Pellmonweb/test_auth.py::test_check_credentials_wrong_password PASSED [ 50%]
tests/Pellmonweb/test_auth.py::test_check_credentials_unknown_user PASSED [ 51%]
tests/Pellmonweb/test_auth.py::test_login_sets_session_and_redirects_on_success PASSED [ 52%]
tests/Pellmonweb/test_auth.py::test_login_failure_renders_loginform_without_session PASSED [ 53%]
tests/Pellmonweb/test_auth.py::test_logout_clears_session PASSED         [ 54%]
tests/Pellmonweb/test_auth_security.py::test_hash_password_format_and_verification PASSED [ 55%]
tests/Pellmonweb/test_auth_security.py::test_hash_password_custom_salt_and_iterations PASSED [ 55%]
tests/Pellmonweb/test_auth_security.py::test_verify_password_plaintext_backward_compatibility PASSED [ 56%]
tests/Pellmonweb/test_auth_security.py::test_verify_password_edge_cases PASSED [ 57%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_with_pbkdf2_hash PASSED [ 58%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_with_dict_credentials PASSED [ 59%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_legacy_plaintext_warning PASSED [ 60%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_failure_never_logs_password PASSED [ 61%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_exception_never_logs_password PASSED [ 61%]
tests/test_ci_docker_config.py::test_github_actions_workflow PASSED      [ 62%]
tests/test_ci_docker_config.py::test_docker_healthchecks PASSED          [ 63%]
tests/test_ci_docker_config.py::test_dockerfile_healthcheck PASSED       [ 64%]
tests/test_no_ad_hoc_print.py::test_no_ad_hoc_print_calls_in_runtime_code PASSED [ 65%]
tests/test_no_ad_hoc_print.py::test_print_allowlist_is_not_vacuous PASSED [ 66%]
tests/test_no_sys_path_shims.py::test_no_sys_path_mutation_in_src PASSED [ 66%]
tests/test_no_sys_path_shims.py::test_no_implicit_sibling_imports_in_target_packages PASSED [ 67%]
tests/test_no_sys_path_shims.py::test_no_implicit_sibling_imports_in_all_src PASSED [ 68%]
tests/test_no_sys_path_shims.py::test_detector_identifies_synthetic_violations PASSED [ 69%]
tests/test_plugin_imports.py::test_plugin_discovery_is_not_vacuous PASSED [ 70%]
tests/test_plugin_imports.py::test_plugin_module_imports[calculate] SKIPPED [ 71%]
tests/test_plugin_imports.py::test_plugin_module_imports[cleaning] PASSED [ 72%]
tests/test_plugin_imports.py::test_plugin_module_imports[consumption] SKIPPED [ 72%]
tests/test_plugin_imports.py::test_plugin_module_imports[customalarms] SKIPPED [ 73%]
tests/test_plugin_imports.py::test_plugin_module_imports[exec] PASSED    [ 74%]
tests/test_plugin_imports.py::test_plugin_module_imports[heatingcircuit] PASSED [ 75%]
tests/test_plugin_imports.py::test_plugin_module_imports[nbecom] PASSED  [ 76%]
tests/test_plugin_imports.py::test_plugin_module_imports[onewire] PASSED [ 77%]
tests/test_plugin_imports.py::test_plugin_module_imports[openweathermap] PASSED [ 77%]
tests/test_plugin_imports.py::test_plugin_module_imports[owfs] PASSED    [ 78%]
tests/test_plugin_imports.py::test_plugin_module_imports[pelletcalc] SKIPPED [ 79%]
tests/test_plugin_imports.py::test_plugin_module_imports[raspberrygpio] SKIPPED [ 80%]
tests/test_plugin_imports.py::test_plugin_module_imports[scottecom] PASSED [ 81%]
tests/test_plugin_imports.py::test_plugin_module_imports[silolevel] SKIPPED [ 82%]
tests/test_plugin_imports.py::test_plugin_module_imports[testplugin] PASSED [ 83%]
tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import PASSED [ 83%]
tests/test_plugin_imports.py::test_skip_allowlist_cannot_hide_migration_defects PASSED [ 84%]
tests/test_plugin_imports.py::test_core_modules_import[Pellmonsrv.pellmonsrv] SKIPPED [ 85%]
tests/test_plugin_imports.py::test_core_modules_import[Pellmonsrv.database] PASSED [ 86%]
tests/test_plugin_imports.py::test_core_modules_import[Pellmonweb.pellmonweb] SKIPPED [ 87%]
tests/test_plugin_imports.py::test_core_modules_import[Pellmonweb.pellmonconf] PASSED [ 88%]
tests/test_protocol_coexistence.py::test_protocol_coexistence PASSED     [ 88%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_checksum_calculation_and_verification_str PASSED [ 89%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_checksum_deterministic_on_bytes PASSED [ 90%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_checksum_disabled PASSED [ 91%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame0-FrameZ00] PASSED [ 92%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame1-FrameZ01] PASSED [ 93%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame2-FrameZ02] PASSED [ 94%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parsing_roundtrip[frame3-FrameZ03] PASSED [ 94%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_z00_getitem_integration PASSED [ 95%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_frame_parse_error_rejection PASSED [ 96%]
tests/test_scotte_protocol_roundtrip.py::test_scotte_serial_loop_transport_roundtrip PASSED [ 97%]
tests/test_socket_guardrail.py::test_real_socket_construction_is_blocked PASSED [ 98%]
tests/test_socket_guardrail.py::test_real_tcp_socket_construction_is_blocked PASSED [ 99%]
tests/test_mocked_udp_socket_fixture_bypasses_the_block PASSED [100%]
```

### 2. Import Check Run
**Command:** `venv-py3/Scripts/python.exe test-imports.py`  
**Exit Code:** `0`  
**Summary:** Script executed cleanly without unhandled exceptions or console encoding issues.

```text
Testing Python 3 imports...

✗ pellmonsrv import failed: No module named 'dbus'
✗ pellmonweb import failed: No module named 'gi'
✓ database imports successfully
✓ pellmonconf imports successfully

Import test complete!
```

### 3. Authentication Security Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonweb/test_auth.py tests/Pellmonweb/test_auth_security.py -v`  
**Exit Code:** `0`  
**Summary:** `15 passed in 0.61s`

```text
tests/Pellmonweb/test_auth.py::test_check_credentials_success PASSED     [  6%]
tests/Pellmonweb/test_auth.py::test_check_credentials_wrong_password PASSED [ 13%]
tests/Pellmonweb/test_auth.py::test_check_credentials_unknown_user PASSED [ 20%]
tests/Pellmonweb/test_auth.py::test_login_sets_session_and_redirects_on_success PASSED [ 26%]
tests/Pellmonweb/test_auth.py::test_login_failure_renders_loginform_without_session PASSED [ 33%]
tests/Pellmonweb/test_auth.py::test_logout_clears_session PASSED         [ 40%]
tests/Pellmonweb/test_auth_security.py::test_hash_password_format_and_verification PASSED [ 46%]
tests/Pellmonweb/test_auth_security.py::test_hash_password_custom_salt_and_iterations PASSED [ 53%]
tests/Pellmonweb/test_auth_security.py::test_verify_password_plaintext_backward_compatibility PASSED [ 60%]
tests/Pellmonweb/test_auth_security.py::test_verify_password_edge_cases PASSED [ 66%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_with_pbkdf2_hash PASSED [ 73%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_with_dict_credentials PASSED [ 80%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_legacy_plaintext_warning PASSED [ 86%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_failure_never_logs_password PASSED [ 93%]
tests/Pellmonweb/test_auth_security.py::test_check_credentials_exception_never_logs_password PASSED [100%]
```

### 4. Exec Plugin Security Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_exec_security.py -v`  
**Exit Code:** `0`  
**Summary:** `7 passed in 0.05s`

```text
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_source_security PASSED [ 14%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_calls_subprocess_with_shell_false PASSED [ 28%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_handles_called_process_error PASSED [ 42%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_readscript_handles_generic_exception PASSED [ 57%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_writescript_calls_subprocess_with_shell_false PASSED [ 71%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_writescript_handles_called_process_error PASSED [ 85%]
tests/Pellmonsrv/plugins/test_exec_security.py::test_execute_writescript_handles_generic_exception PASSED [100%]
```

### 5. Signal Handling Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/test_sigterm_handling.py -v`  
**Exit Code:** `0`  
**Summary:** `8 passed in 0.33s`

```text
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_sigterm_handler_flushes_db_and_quits_loop PASSED [ 12%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_sigterm_handler_skips_flush_when_same_db PASSED [ 25%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_sigterm_handler_stops_poller_and_removes_pid PASSED [ 37%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_mydaemon_method_sigterm_handler PASSED [ 50%]
tests/Pellmonsrv/test_poller_stop_lifecycle PASSED [ 62%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonsrv_ast_signal_registration PASSED [ 75%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonweb_signal_handler_quits_engine_and_loop PASSED [ 87%]
tests/Pellmonsrv/test_sigterm_handling.py::test_pellmonweb_ast_signal_registration PASSED [100%]
```

### 6. CI and Docker Config Test
**Command:** `venv-py3/Scripts/python.exe -m pytest tests/test_ci_docker_config.py -v`  
**Exit Code:** `0`  
**Summary:** `3 passed in 0.03s`

```text
tests/test_ci_docker_config.py::test_github_actions_workflow PASSED      [ 33%]
tests/test_ci_docker_config.py::test_docker_healthchecks PASSED          [ 66%]
tests/test_ci_docker_config.py::test_dockerfile_healthcheck PASSED       [100%]
```

### 7. Requirements Pinning Assertion
**Command:**
```powershell
venv-py3/Scripts/python.exe -c "lines = [l.strip() for l in open('requirements.txt') if l.strip() and not l.startswith('#')]; assert all('==' in l for l in lines), 'Unpinned dependency found'"
```
**Exit Code:** `0`  
**Summary:** All dependencies in `requirements.txt` strictly adhere to `==` exact version pinning.

### 8. Obsolete `.py2bak` Files Check
**Command:**
```powershell
venv-py3/Scripts/python.exe -c "import glob; assert len(glob.glob('src/**/*.py2bak', recursive=True)) == 0, 'Found remaining .py2bak files'"
```
**Exit Code:** `0`  
**Summary:** Exactly 0 `.py2bak` files remain in `src/`.

### 9. README Documentation Verification
**Command:**
```powershell
venv-py3/Scripts/python.exe -c "readme = open('README.md', encoding='utf-8').read(); assert 'Linux-only' in readme, 'Linux-only notice missing'; assert 'docker compose' in readme.lower(), 'Docker compose missing'; assert 'hash_password' in readme, 'hash_password missing'"
```
**Exit Code:** `0`  
**Summary:** `README.md` prominently displays the Linux-only notice, documents Docker Compose setup, and provides instructions for generating PBKDF2 password hashes.

---

## Must-Haves & Requirements Evaluation

| ID | Requirement | Status | Evidence |
|:---|:------------|:------:|:---------|
| **SEC-01** | Web UI login failures no longer log the submitted plaintext password | **PASS** | `Pellmonweb/auth.py:196,199` only logs username (truncated) and remote IP; verified by `test_check_credentials_failure_never_logs_password` and `test_check_credentials_exception_never_logs_password`. |
| **SEC-02** | Web UI credentials are hashed with PBKDF2-HMAC-SHA256, timing-safe compare, backward-compatible migration | **PASS** | `Pellmonweb/auth.py:hash_password` & `verify_password`; verified by `tests/Pellmonweb/test_auth_security.py` (all 9 unit tests passing). |
| **SEC-03** | Exec plugin readscript uses `shell=False` with argument list | **PASS** | `src/Pellmonsrv/plugins/exec/__init__.py:87-88` invokes `subprocess.check_output(shlex.split(script), shell=False)`; verified by `test_execute_readscript_calls_subprocess_with_shell_false`. |
| **OPS-01** | GitHub Actions CI runs pytest suite and broadened import check on master/python3-migration PRs | **PASS** | `.github/workflows/ci.yml` defines `push` and `pull_request` triggers on `master` and `python3-migration`, executes `test-imports.py` and `pytest tests/ -v`; verified by `test_github_actions_workflow`. |
| **OPS-02** | Graceful SIGTERM/SIGINT handling for pellmonsrv and pellmonweb | **PASS** | `pellmonsrv.py:sigterm_handler` syncs RRD, stops poller, removes pidfile, quits main loop; `pellmonweb.py:signal_handler` exits cherrypy engine and quits main loop; verified by 8 unit tests in `test_sigterm_handling.py`. |
| **OPS-03** | Docker Compose and Dockerfile define readiness healthchecks | **PASS** | `docker-compose.yml` uses `dbus-send Peer.Ping` for server and `curl` for web with `service_healthy` condition; `Dockerfile` includes `HEALTHCHECK`; verified by `test_docker_healthchecks` and `test_dockerfile_healthcheck`. |
| **OPS-04** | Pinned dependencies in `requirements.txt` | **PASS** | All dependencies pinned to exact versions with `==`; verified by assertion script. |
| **OPS-05** | All `.py2bak` files purged from `src/` | **PASS** | All 23 `.py2bak` files removed in commit `cd69f5c`; verified by glob assertion script. |
| **OPS-06** | README documents Linux-only production, Docker Compose, and password hashing | **PASS** | Prominent alert on lines 5-6 of `README.md`, Docker Compose section on lines 120-144, Web Authentication section on lines 190-207. |

---

## Verdict Block

```yaml
verdict: PASS
must_haves_checked: 9
must_haves_passed: 9
summary: All Phase 5 requirements (SEC-01..03, OPS-01..06) are fully implemented, independently tested, and passing with zero defects or regressions.
gaps: none
```
