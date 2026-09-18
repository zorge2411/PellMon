---
phase: 04-protocol-module-hardening
plan: 03
subsystem: scotte-protocol
tags: [python3, scotteprotocol, checksum, transport-injection, loop-serial, pytest]
dependency-graph:
  requires: []
  provides:
    - Constructor-injectable transport and start_thread parameter in Scotteprotocol.Protocol (PROTO-04)
    - Deterministic bytes and string handling in addCheckSum and checkCheckSum
    - Unit tests in tests/test_scotte_protocol_roundtrip.py
  affects:
    - Scotteprotocol
tech-stack:
  added: []
  patterns:
    - Constructor transport injection allowing loop:// pyserial URL in offline tests
    - XOR checksum calculation and verification handling both str and bytes
key-files:
  created:
    - tests/test_scotte_protocol_roundtrip.py
  modified:
    - src/Scotteprotocol/protocol.py
decisions: [D-04]
metrics:
  completed: 2026-09-18
---

# Phase 4 Plan 03: Scotte Protocol Hardening & Round-Trip Testing Summary

Hardened the Scotteprotocol implementation: added constructor-injectable transport and thread control parameters to `Protocol.__init__` (PROTO-04), made `addCheckSum` and `checkCheckSum` handle both `str` and `bytes` deterministically without `TypeError`, and implemented comprehensive round-trip and frame parsing unit tests using pyserial's `loop://` transport fixture.

## What Was Built

### Task 1: Add constructor-injectable transport to Scotteprotocol.Protocol
- In `src/Scotteprotocol/protocol.py`:
  - Updated `Protocol.__init__` signature to:
    `def __init__(self, device, version_string, transport=None, start_thread=True):`
  - When `transport is not None`, assigned `self.ser = transport`, initialized `self.dataBase`, `self.q`, `self.checksum = True`, `self.frame_term_crlf = False`, and set `self.daemon = True`.
  - Conditioned thread startup on `if start_thread: self.start()` to prevent unmanaged background threads during offline unit tests.
  - When `device is None` (and `transport is None`), retained existing dummy device behavior.

### Task 2: Implement Scotte protocol per-frame round-trip tests and checksum handling
- In `src/Scotteprotocol/protocol.py`:
  - Updated `addCheckSum` and `checkCheckSum` to decode `latin-1` if given `bytes` input, ensuring checksum computation and verification behave deterministically regardless of whether input is `str` or `bytes`.
  - Replaced deprecated `self.setDaemon(True)` with `self.daemon = True`.
- Created `tests/test_scotte_protocol_roundtrip.py`:
  - `test_scotte_checksum_calculation_and_verification_str`: Verified `addCheckSum` and `checkCheckSum` on sample strings (`'Z000000'` -> `'Z000000Z'`), verified `checkCheckSum(addCheckSum(msg)) == 0`, and confirmed corrupted characters produce nonzero checksums.
  - `test_scotte_checksum_deterministic_on_bytes`: Verified identical checksum behavior on `bytes` and `str` inputs without raising `TypeError`.
  - `test_scotte_checksum_disabled`: Verified checksum pass-through when `protocol.checksum = False`.
  - `test_scotte_frame_parsing_roundtrip`: Parameterized tests across `FrameZ00`, `FrameZ01`, `FrameZ02`, and `FrameZ03` asserting successful parsing of synthetic frames matching each frame's `dataDef` widths.
  - `test_scotte_frame_z00_getitem_integration`: Verified parsed sensor readings from `FrameZ00` flow cleanly into `Protocol.getItem` with appropriate decimal scaling.
  - `test_scotte_frame_parse_error_rejection`: Verified rejection of invalid checksums, payload corruptions, error frames (`E0`, `E1`), and length mismatches.
  - `test_scotte_serial_loop_transport_roundtrip`: Verified write and read-back communication over pyserial `loop://` serial transport without physical hardware.

## Verification Results

1. Task 1 Verification:
```bash
$env:PYTHONPATH="src"; venv-py3/Scripts/python.exe -c "import Scotteprotocol, serial; ser = serial.serial_for_url('loop://', timeout=1); p = Scotteprotocol.Protocol(None, '6.99', transport=ser, start_thread=False); assert p.ser == ser; ser.close()"
# Exited 0
```

2. Task 2 Verification:
```bash
venv-py3/Scripts/python.exe -m pytest tests/test_scotte_protocol_roundtrip.py -v
# 10 passed in 0.05s
```

3. Full Test Suite Verification:
```bash
venv-py3/Scripts/python.exe -m pytest
# 83 passed, 8 skipped, 2 warnings in 2.03s
```

## Deviations from Plan

None. Implementation strictly followed D-04 and requirements.

## Commits

- `c4e6b74` feat(phase-4): add constructor-injectable transport to Scotteprotocol.Protocol
- `020226c` test(phase-4): implement scotte protocol per-frame round-trip tests
