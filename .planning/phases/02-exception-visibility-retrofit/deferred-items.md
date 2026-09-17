# Deferred Items — Phase 2

Out-of-scope discoveries found while executing Phase 2 plans, logged here
rather than fixed (per the executor's scope-boundary rule: only auto-fix
issues directly caused by the current task's own changes).

## `Database` class is unhashable, crashes `threading.Thread.__init__`

- **Found during:** 02-03, Task 1 (writing caplog tests for the plugin-activation loop)
- **File:** `src/Pellmonsrv/pellmonsrv.py` — `class Database(threading.Thread, _Database)`
- **Root cause:** `_Database` (aliased from `Pellmonsrv.database.Database`) subclasses
  `weakref.WeakValueDictionary`, which defines `__eq__` without `__hash__`, so Python
  automatically sets `__hash__ = None` on it (and on `Database`, which inherits it).
  `threading.Thread.__init__` registers every new thread in a `WeakSet` (`_dangling`),
  which requires the thread object to be hashable — so `Database()` raises
  `TypeError: cannot use 'weakref.ReferenceType' as a set element (unhashable type:
  'Database')` the instant it is constructed, on every CPython 3.4+ runtime (the
  `_dangling` WeakSet registration in `threading.Thread.__init__` has been present since
  Python 3.4).
- **Blast radius:** This is the exact `Database` class instantiated in `MyDaemon.run()`
  (`conf.database = Database()`) — i.e. this crash path is reachable in production, not
  just under test. Not confirmed whether this is masked in the current production
  environment (e.g. an older Python 3 minor version, or a different construction path);
  flagged here for verification, not confirmed broken end-to-end.
- **Why not fixed here:** Out of Phase 2's exception-visibility scope (`files_modified`
  for 02-03 is `tests/Pellmonsrv/test_pellmonsrv_logging.py` and
  `src/Pellmonsrv/pellmonsrv.py`'s Category-A failure-path conversions only) and not
  caused by this plan's own changes.
- **Workaround used:** `tests/Pellmonsrv/test_pellmonsrv_logging.py` monkeypatches
  `daemon_module.Database.__hash__ = object.__hash__` for the duration of the two tests
  that construct a real `Database()`, restoring it on teardown (via `monkeypatch`). This
  is a test-only patch; `src/Pellmonsrv/pellmonsrv.py`'s `Database` class itself is
  unchanged.
- **Suggested fix (future phase):** Add `__hash__ = object.__hash__` (or
  `threading.Thread.__hash__`) explicitly on `Database` in `src/Pellmonsrv/pellmonsrv.py`
  so instances use identity-based hashing instead of inheriting `None` from the
  `WeakValueDictionary` mixin. Candidate for Phase 3 (core daemon hardening) or wherever
  `MyDaemon.run()`'s daemon-startup path gets verified against a real Linux runtime.
