# Testing Patterns

**Analysis Date:** 2026-09-17

## Test Framework

**Runner:** None. There is no `pytest`, `unittest`, `nose`, or `tox` configuration anywhere in the repository (no `pytest.ini`, `setup.cfg` test section, `tox.ini`, or `conftest.py` under `src/` — the only `conftest.py`/test files present live inside `venv-py3/Lib/site-packages/...` third-party package installs and are not part of this project).

**Assertion Library:** None used. No `assert`-based test modules exist in `src/`.

**Config:** None.

**Run Commands:**
```bash
# There is no test suite / test runner. The closest thing to "testing"
# in this repo is a manual import-smoke-test script:
python test-imports.py
```

## What Exists Instead of Automated Tests

PellMon currently has **no automated test suite** (no unit tests, no integration tests, no CI test job). Verification during the Python 2 → 3 migration has been done through:

1. **Import smoke test** — `test-imports.py` (repo root). A standalone script (not part of `src/`) that adds `src` to `sys.path` and attempts to import the four top-level entry modules, printing ✓/✗ per module:
   - `Pellmonsrv.pellmonsrv`
   - `Pellmonweb.pellmonweb`
   - `Pellmonsrv.database`
   - `Pellmonweb.pellmonconf`

   Run with `python test-imports.py` from the repo root. This only checks that modules import without raising — it does not exercise any behavior. When adding a new top-level module, add an equivalent `try/except` import block here if it should be part of the smoke check.

2. **Manual CLI smoke checks** — documented in `PHASE4-TESTING.md`:
   ```bash
   python src/Pellmonsrv/pellmonsrv.py --help
   python src/Pellmonweb/pellmonweb.py --help
   python src/Pellmonweb/pellmonconf.py --help
   ```
   These confirm `argparse` setup and import chains work, nothing more.

3. **Manual/hardware-dependent verification checklist** — `PHASE4-TESTING.md` tracks unchecked items requiring actual pellet-burner hardware, a DBUS daemon, and `rrdtool` (Linux-only), e.g. server startup, DBUS communication, web interface, plugin loading, serial communication, RRD database operations. As of this analysis these remain unverified (checkboxes unchecked).

4. **A `testplugin` plugin** exists at `src/Pellmonsrv/plugins/testplugin/` with `src/conf.d/plugins/testplugin.conf` and `src/Pellmonsrv/plugins/testplugin.pellmon-plugin` — this is a *sample/reference plugin* for the yapsy plugin framework (demonstrating the plugin contract), not an automated test of plugin-loading behavior. It is not invoked by any test runner.

**Implication for new work:** There is no existing test harness or convention to imitate for unit/integration tests. If a phase requires adding tests, you must introduce the framework choice (pytest is the natural fit given `requirements.txt`/`requirements-wsl.txt` already target Python 3.9+ tooling) as well as its directory convention — there is no established `tests/` directory anywhere in `src/`.

## Test File Organization

**Location:** Not applicable — no test files exist under `src/`.

**Naming:** Not applicable.

**Structure:** Not applicable.

## Test Structure

Not applicable — no test suites to derive a pattern from.

## Mocking

**Framework:** None used/configured.

**What would need mocking if tests were added:**
- Hardware/serial I/O: `pyserial` usage in protocol plugins (e.g. `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`, `src/Pellmonsrv/plugins/scottecom/scottecom.py`).
- DBus: `dbus`, `dbus.service`, `gi.repository.GLib/GObject` in `src/Pellmonsrv/pellmonsrv.py` — requires a running DBus daemon; would need to be faked/mocked for unit tests.
- `subprocess` calls to `rrdtool` (`src/Pellmonsrv/plugins/consumption/__init__.py:rrd_total`) — `rrdtool` is a Linux-only system package, not installable via pip; must be mocked for cross-platform/CI testing.
- SQLite access in `src/Pellmonsrv/database.py` (`Keyval_storage`) — straightforward to test against a real in-memory/temp sqlite3 file rather than mocking, since it's already file-based and lightweight.
- External HTTP APIs: `pyowm` (OpenWeatherMap) in `src/Pellmonsrv/plugins/openweathermap/__init__.py`, and `urllib.request` calls in `src/Pellmonsrv/pellmonsrv.py`.

## Fixtures and Factories

None exist. No `tests/fixtures/`, `conftest.py`, or factory helpers are present in this project's own source tree.

## Coverage

**Requirements:** None enforced. No coverage tool (`coverage.py`, `pytest-cov`) is configured in `requirements.txt` or `requirements-wsl.txt`.

**View Coverage:** Not applicable.

## Test Types

**Unit Tests:** None present.

**Integration Tests:** None present.

**E2E Tests:** None present. `Pellmonweb` (the web UI, `src/Pellmonweb/`) has no browser-level or HTTP-level test coverage.

## Common Patterns

**Async Testing:** Not applicable (no async code and no tests).

**Error Testing:** Not applicable — no tests assert on error/exception behavior. Note that much production code swallows exceptions broadly (see `CONVENTIONS.md` "Error Handling"), which would need tightening before meaningful error-path tests could be written.

## Recommendations for Future Work

If a future phase introduces testing:
- Adopt `pytest` (add to `requirements.txt`); it is the de facto standard and nothing in this codebase conflicts with it.
- Start with the modules that have the fewest hardware dependencies: `src/Pellmonsrv/database.py` (sqlite3-backed, no hardware) and `src/Pellmonsrv/plugin_categories.py` (pure Python base class) are the best first candidates for unit tests.
- Create a `tests/` directory at the repo root (or `src/tests/`) — no existing convention to conflict with.
- Expand `test-imports.py` into real `pytest` import-smoke tests rather than a standalone script, or keep it as a fast pre-test sanity check invoked by CI before the full suite runs.

---

*Testing analysis: 2026-09-17*
