---
phase: 04-protocol-module-hardening
plan: 02
subsystem: nbecom-protocol
tags: [python3, nbecom, nbeprotocol, bytes-str, transport-injection, mock-udp, pytest]
dependency-graph:
  requires: []
  provides:
    - Fixed bytes/str split TypeError in Proxy.get() (PROTO-01)
    - Constructor-injectable transport and start_threads parameter in Proxy.__init__ (PROTO-04)
    - Unit tests in tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py
  affects:
    - Pellmonsrv.plugins.nbecom.nbeprotocol
tech-stack:
  added: []
  patterns:
    - Direct str splitting on decoded ASCII payload frames without re-encoding to bytes
    - Constructor transport injection allowing mocked UDP sockets in offline tests
key-files:
  created:
    - tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py
  modified:
    - src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py
decisions: [D-01, D-04]
metrics:
  completed: 2026-09-18
---

# Phase 4 Plan 02: NBE Protocol Hardening & Round-Trip Testing Summary

Hardened the NBE protocol implementation: fixed the `TypeError` in `Proxy.get()` caused by an unnecessary `.encode('ascii')` call prior to string splitting (PROTO-01), added constructor-injectable transport and thread control parameters to `Proxy.__init__` (PROTO-04), and implemented comprehensive unit tests covering frame encoding/decoding, payload parsing, and mock socket round-trips.

## What Was Built

### Task 1: Fix bytes/str split in Proxy.get() and add injectable transport to Proxy.__init__
- In `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`:
  - Updated `Proxy.__init__` signature to:
    `def __init__(self, password, port=1920, addr=None, serial=None, transport=None, start_threads=True):`
  - When `transport is not None`, assigned `self.s = transport` directly, bypassing real UDP socket creation.
  - Guarded background thread spawning with `if start_threads:` to prevent uncontrollable background network threads during unit testing.
  - In `Proxy.get()`, changed `response.payload.encode('ascii').split(...)` to `response.payload.split(...)` for both single parameter (`'='`) and parameter group (`';'`) queries (D-01). Because `response.payload` is already decoded to `str` in `Response_frame.decode()`, splitting on string delimiters now succeeds without `TypeError`.

### Task 2: Implement NBE protocol frame round-trip and Proxy.get() tests
- Created `tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py`:
  - `test_proxy_init_injectable_transport`: Verified `Proxy` accepts an injectable transport and `start_threads=False` without spawning background threads (PROTO-04).
  - `test_request_frame_encode_decode`: Verified `Request_frame` header lengths, sequence numbers, and payload encoding/decoding.
  - `test_response_frame_encode_decode_and_parse_payload`: Verified `Response_frame` encoding and `parse_payload()` parsing into string dictionary key-values.
  - `test_proxy_get_single_parameter_returns_str`: Verified `Proxy.get()` returns a `str` value for single items without `TypeError` (PROTO-01).
  - `test_proxy_get_parameter_group_returns_list_of_str`: Verified `Proxy.get(group=True)` returns a `list[str]` for parameter groups without `TypeError` (PROTO-01).
  - `test_proxy_roundtrip_with_injected_transport`: Verified end-to-end request/response round-trip through an injected mock transport without physical hardware or real network access.

## Verification Results

1. Task 1 Verification:
```bash
$env:PYTHONPATH="src"; venv-py3/Scripts/python.exe -c "from Pellmonsrv.plugins.nbecom.nbeprotocol.protocol import Proxy; p = Proxy('pass', transport='mock', start_threads=False); assert p.s == 'mock'"
# Exited 0
```

2. Task 2 Verification:
```bash
venv-py3/Scripts/python.exe -m pytest tests/Pellmonsrv/plugins/test_nbe_protocol_roundtrip.py -v
# 6 passed in 0.06s
```

3. Full Test Suite Verification:
```bash
venv-py3/Scripts/python.exe -m pytest
# 73 passed, 8 skipped, 2 warnings in 1.96s
```

## Deviations from Plan

None. Implementation strictly followed D-01 and D-04 decisions.

## Commits

- `2a3d875` fix(phase-4): fix bytes/str split in Proxy.get() and add injectable transport
- `c6d120e` test(phase-4): implement NBE protocol frame round-trip and Proxy.get() tests
