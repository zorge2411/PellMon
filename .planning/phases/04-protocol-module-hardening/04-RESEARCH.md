# Phase 4: Protocol Module Hardening (Bytes/Str Semantics) - Research

**Researched:** 2026-09-18
**Domain:** Python 3 bytes/str semantics, I/O buffering, mockable transports, and protocol round-trip testing
**Confidence:** HIGH (verified via source code inspection and test harness capabilities)

## Summary

During the Python 2 to 3 migration, multiple byte/string mismatches and Python 2 standard library API changes were introduced or left unfixed:

1. **NBEcom `Proxy.get()` TypeError (PROTO-01):**
   In `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:144,146`:
   ```python
   if not group:
       return response.payload.encode('ascii').split('=', 1)[1]
   else:
       return response.payload.encode('ascii').split(';')
   ```
   `response.payload` is already decoded to `str` in `Response_frame.decode()`. Calling `.encode('ascii')` converts it to `bytes`, and then attempting `.split('=', 1)` with a `str` delimiter raises:
   `TypeError: a bytes-like object is required, not 'str'`.
   Fix: Remove `.encode('ascii')` so `response.payload.split('=', 1)[1]` and `.split(';')` operate cleanly on `str`.

2. **Calculate Plugin Python 2 Remnants (PROTO-02 & PROTO-05):**
   - Line 28 of `src/Pellmonsrv/plugins/calculate/__init__.py`: `from string import maketrans` raises `ImportError` in Python 3 because `string.maketrans` was removed. The module actually does translation using dictionary mapping with `str.translate` (line 252), so this import is obsolete.
   - Line 351 of `src/Pellmonsrv/plugins/calculate/__init__.py`: `stack = [unicode(value)]` raises `NameError: name 'unicode' is not defined`.
   Fix: Delete `from string import maketrans` and change `unicode(value)` to `str(value)`.

3. **Daemon Unbuffered Text I/O Crash (PROTO-03):**
   In `src/Pellmonsrv/daemon.py:72`:
   `se = open(self.stderr, 'a+', buffering=0)`
   In Python 3, `open()` in text mode (`'a+'`) with `buffering=0` raises:
   `ValueError: can't have unbuffered text I/O`.
   Fix: Change `buffering=0` to `buffering=1` (line-buffered text I/O).

4. **Hardware-Free Testing via Injectable Transports (PROTO-04):**
   Both `Scotteprotocol.Protocol` and `nbeprotocol.Proxy` previously hardcoded opening real hardware devices (`serial.Serial(device)` and `socket.socket()`).
   - `Scotteprotocol.Protocol`: Add `transport=None` parameter to `__init__`. When provided, use `self.ser = transport`. Tests use `serial.serial_for_url("loop://", timeout=1)` to send frames and read responses.
   - `nbeprotocol.Proxy`: Add `transport=None` parameter to `__init__`. When provided, use `self.s = transport`. Tests use mocked UDP sockets to verify request encoding and response handling.

5. **Database Keyval Storage Confval Binding Bug:**
   In `src/Pellmonsrv/database.py:199`:
   `cursor.execute("INSERT OR REPLACE INTO keyval (id, value, confvalue) VALUES (?,?,?)", (item, confval, confval))`
   Line 197 read `value, confvalue = next(cursor)`. Binding `confval` into the `value` column erroneously overwrites `value` when updating `confval`.
   Fix: Bind `(item, value, confval)`.
