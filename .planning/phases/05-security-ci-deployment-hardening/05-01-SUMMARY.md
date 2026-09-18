---
phase: 05-security-ci-deployment-hardening
plan: 01
subsystem: security
tags: [security, pbkdf2, auth, exec, hardening, pytest]
dependency-graph:
  requires: []
  provides:
    - Raw password redaction on failed login attempts in Pellmonweb (SEC-01)
    - PBKDF2-HMAC-SHA256 password hashing with backward-compatible plaintext fallback (SEC-02)
    - Safe shell=False execution with shlex argument splitting in Exec plugin (SEC-03)
    - Unit test coverage for authentication security and exec hardening
  affects:
    - Pellmonweb.auth
    - Pellmonsrv.plugins.exec
    - config/pellmon.conf.example
tech-stack:
  added: []
  patterns:
    - PBKDF2-HMAC-SHA256 password hashing via hashlib and hmac.compare_digest
    - Constant-time password verification preventing timing attacks
    - Secure command invocation via subprocess.check_output(args, shell=False) with shlex.split
key-files:
  created:
    - tests/Pellmonweb/test_auth_security.py
    - tests/Pellmonsrv/plugins/test_exec_security.py
  modified:
    - src/Pellmonweb/auth.py
    - src/Pellmonsrv/plugins/exec/__init__.py
    - config/pellmon.conf.example
decisions: [D-01, D-02]
metrics:
  completed: 2026-09-18
---

# Phase 5 Plan 01: Web Authentication & Exec Plugin Hardening Summary

Hardened web authentication security and command execution against credential leakage and command injection:
1. Eliminated raw password logging on failed logins in `src/Pellmonweb/auth.py` (SEC-01).
2. Implemented PBKDF2-HMAC-SHA256 password hashing in `src/Pellmonweb/auth.py` with backward-compatible plaintext verification and configuration migration documentation in `config/pellmon.conf.example` (SEC-02).
3. Converted Exec plugin `execute_readscript` to `shell=False` using `shlex.split`, fixed potential `NameError` on `CalledProcessError`, and added exception logging (SEC-03).
4. Added comprehensive test coverage in `tests/Pellmonweb/test_auth_security.py` and `tests/Pellmonsrv/plugins/test_exec_security.py`.

## What Was Built

### Task 1: Eliminate password logging and add PBKDF2 hashing in Pellmonweb/auth.py (SEC-01, SEC-02)
- Added `hash_password(password, salt=None, iterations=100000)` and `verify_password(stored_credential, provided_password)` using standard library `hashlib.pbkdf2_hmac` and `hmac.compare_digest`.
- Format: `pbkdf2:sha256:100000$<salt_hex>$<hash_hex>`.
- Preserved backward compatibility for legacy plaintext credentials via `hmac.compare_digest(stored_credential, provided_password)` with a deprecation warning logged on successful login prompting migration to PBKDF2.
- In `AuthController.check_credentials`:
  - Handled both list-of-tuples and dictionary credential structures.
  - Eliminated raw password from failure and exception logs. Only remote IP address and username (truncated to 50 characters) are logged.
- Documented password generation and hash syntax in `config/pellmon.conf.example`.

### Task 2: Harden Exec plugin execute_readscript with shell=False (SEC-03)
- Converted `execute_readscript` to parse command lines using `shlex.split` and execute via `subprocess.check_output(args, shell=False).decode('utf-8', errors='replace').strip()`.
- Explicitly caught `subprocess.CalledProcessError` (fixing potential `NameError`), and added general exception handling with `logger.exception`.
- Hardened `execute_writescript` error and exception handling as well.

### Task 3: Add unit tests for auth security and exec hardening
- Created `tests/Pellmonweb/test_auth_security.py` (124 lines):
  - Verified `hash_password` format and salt/hash lengths.
  - Verified `verify_password` with valid and invalid passwords.
  - Verified backward compatibility with legacy plaintext credentials.
  - Verified edge cases: `None`, empty strings, malformed hashes.
  - Verified `AuthController.check_credentials` with hashed and plaintext credentials, list and dict formats.
  - Verified failed logins and credential check exceptions never log submitted passwords, while logging remote IP and username.
- Created `tests/Pellmonsrv/plugins/test_exec_security.py` (89 lines):
  - Verified source code contains `shell=False` and `shlex.split` and no `shell=True`.
  - Verified `execute_readscript` parses arguments with `shlex.split` and executes with `shell=False`.
  - Verified `execute_readscript` handles `subprocess.CalledProcessError` and generic exceptions cleanly.
  - Verified `execute_writescript` invokes `subprocess.check_call` with `shell=False` and handles errors.

## Verification Results

1. Task 1 Verification:
```powershell
$env:PYTHONPATH='src'; venv-py3/Scripts/python.exe -c "from Pellmonweb.auth import hash_password, verify_password; h = hash_password('secret'); assert verify_password(h, 'secret'); assert not verify_password(h, 'wrong'); assert verify_password('plaintext', 'plaintext'); assert 'password: %s' not in open('src/Pellmonweb/auth.py').read()"
# Exit 0
```

2. Task 2 Verification:
```powershell
$env:PYTHONPATH='src'; venv-py3/Scripts/python.exe -c "import inspect; from Pellmonsrv.plugins.exec import execplugin; src = inspect.getsource(execplugin.execute_readscript); assert 'shell=False' in src; assert 'shell=True' not in src; assert 'shlex.split' in src"
# Exit 0
```

3. Task 3 and Security Test Suite Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/Pellmonweb/test_auth.py tests/Pellmonweb/test_auth_security.py tests/Pellmonsrv/plugins/test_exec_security.py -v
# 22 passed in 0.66s
```

4. Full Test Suite Verification:
```powershell
venv-py3/Scripts/python.exe -m pytest tests/
# 99 passed, 8 skipped, 2 warnings in 2.36s
```

## Deviations from Plan

None. Implementation strictly followed D-01, D-02, and plan instructions.

## Commits

- `1de8bc5` fix(phase-05): eliminate password logging and add PBKDF2 hashing
- `5a81347` fix(phase-05): harden exec plugin with shell=False
- `c85c305` test(phase-05): add unit tests for auth and exec security hardening
