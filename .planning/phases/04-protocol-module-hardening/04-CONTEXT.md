# Phase 4: Protocol Module Hardening (Bytes/Str Semantics) - Context

**Gathered:** 2026-09-18
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase addresses protocol correctness and runtime reliability bugs:
1. Fix bytes/str `TypeError` in NBEcom's `Proxy.get()` (`nbeprotocol/protocol.py:144,146`).
2. Fix Python 2 remnants in the Calculate plugin: `unicode()` call in `setItem` (`calculate/__init__.py:351`) and leftover `from string import maketrans` (`calculate/__init__.py:28`).
3. Fix daemon stderr unbuffered text I/O `ValueError` in `daemon.py:72`.
4. Introduce constructor-injectable transports in both `Scotteprotocol.Protocol` and `nbeprotocol.Proxy` to enable hardware-free automated encode/decode round-trip testing via the Phase 1 test harness (`loop://` serial and mocked UDP).
5. Fix `Keyval_storage.writeval` confval-upsert column binding bug in `database.py:199`.

Security hardening (password hashing, shell injection in Exec) and deployment CI belong to Phase 5.

</domain>

<decisions>
## Implementation Decisions

### D-01: String Handling in NBE Protocol Payloads
`Response_frame.decode()` in `nbeprotocol/frames.py:179` already decodes payload bytes into `str` (`(record[i:i+self.size]).decode('ascii')`). In `Proxy.get()`, `response.payload` must NOT be encoded back to `bytes` before splitting with string delimiters (`'='` and `';'`). `response.payload.split('=', 1)[1]` and `response.payload.split(';')` directly return strings, resolving `TypeError` completely.

### D-02: String Compatibility in Calculate Plugin
In `calculate/__init__.py`, remove `from string import maketrans` (removed in Python 3; unneeded as string translation uses `str.translate` with a dictionary). In `setItem`, replace `unicode(value)` with `str(value)`.

### D-03: Line-Buffering for Daemon Text I/O
In `daemon.py:72`, Python 3 prohibits `buffering=0` for text streams (`open(..., 'a+', buffering=0)`). Change to line-buffered `buffering=1` so stderr output is flushed promptly without raising `ValueError`.

### D-04: Constructor-Injectable Transports
- In `Scotteprotocol.Protocol.__init__(self, device, version_string, transport=None)`: if `transport` is provided, assign `self.ser = transport` directly without opening `serial.Serial(device)`. This allows tests to inject `serial.serial_for_url("loop://", timeout=1)`.
- In `nbeprotocol.Proxy.__init__(self, password, port=1920, addr=None, serial=None, transport=None)`: if `transport` is provided, assign `self.s = transport` directly, enabling test fixtures to inject mocked UDP sockets without network interaction.

### D-05: Database Keyval Upsert Integrity
In `Keyval_storage.writeval()` (`database.py:199`), bind `(item, value, confval)` instead of `(item, confval, confval)` so existing `value` column data is preserved when updating `confval`.

</decisions>

<canonical_refs>
## Canonical References

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — PROTO-01, PROTO-02, PROTO-03, PROTO-04, PROTO-05
- `.planning/ROADMAP.md` — Phase 4 Goal, Requirements, and Success Criteria
- `.planning/PROJECT.md` — Database confval bug callout

### Test Harness
- `tests/conftest.py` — `loop_serial` and `mocked_udp_socket` fixtures
- `tests/Pellmonsrv/test_database.py` — `Keyval_storage` test suite

</canonical_refs>
