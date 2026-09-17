# Stack Research

**Domain:** Finishing a Python 2→3 migration + adding automated tests for a hardware-protocol daemon (serial/UDP burner control), no CI hardware available
**Researched:** 2026-09-17
**Confidence:** HIGH (test tooling, pyserial mocking, ruff/ pyupgrade) / MEDIUM (D-Bus mocking, exact pin versions — verify against PyPI at install time)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| pytest | `>=8.3,<10` (current stable line is 9.x as of mid-2026; pin to `>=8.3` for broad compatibility, upgrade to 9.x once verified against this codebase) | Test runner/framework | De facto standard Python test framework; fixtures + `tmp_path`/`monkeypatch` cover almost everything this project needs (mocked serial, mocked sockets, mocked D-Bus) without extra machinery. `unittest` would work but pytest's fixture model and plugin ecosystem (`pytest-mock`, `pytest-socket`) is the current standard for this exact "hardware I/O, no CI hardware" problem. |
| pytest-mock | `>=3.14` | Thin `mocker` fixture wrapper over `unittest.mock` | Avoids hand-rolling `unittest.mock.patch` context managers in every protocol test; integrates cleanly with pytest fixtures/parametrize, which you'll want heavily for frame encode/decode round-trip tests. |
| pytest-socket | `>=0.7` | Blocks real network/socket calls during test runs | Directly solves "hardware dependencies that can't run in CI" for the NBE plugin's UDP path: add `addopts = --disable-socket` to `pytest.ini`/`pyproject.toml` so any test that accidentally tries real UDP broadcast discovery (`find_controller()`) fails loudly instead of hanging on a CI runner with no burner on the LAN. Use `@pytest.mark.enable_socket` only on tests that explicitly want a local loopback socket pair. |
| pytest-cov | `>=6.0` (7.x current) | Coverage reporting | Needed to see which of the newly-fixed protocol/byte-boundary code paths are actually exercised — this project's core risk (bytes/str bugs) lives exactly in the untested code, so coverage numbers are the feedback loop that tells you when "it imports" has become "it's verified." |
| ruff | `>=0.8` (0.16+ current) | Linter + formatter, replaces flake8 + pyupgrade + isort | Single fast tool that both (a) flags remaining Python-2-only idioms via its `UP` (pyupgrade) rule set and (b) catches general bugs via `B` (flake8-bugbear) and `F` (pyflakes) rules, including the bare `except:` clauses and `unicode()`-style leftovers already found in `CONCERNS.md`. Ruff has absorbed pyupgrade's rule set (UP) plus flake8-bugbear (B), flake8-comprehensions, etc., so it replaces the old flake8+pyupgrade+isort combo used pre-2025 with one binary and one config block. |
| mypy | `>=1.13` | Static type checker, focused on bytes/str boundary bugs | This is the single most effective tool for exactly the confirmed bug class in this codebase (`nbeprotocol/protocol.py:144,146` — encoding an already-decoded `str` then calling `.split()` with a `str` separator on the resulting `bytes`). mypy treats `bytes` and `str` as distinct, non-interchangeable types by default and will flag `bytes.split(str)`/`str.split(bytes)` mismatches at the call site without running the code. No serial/network hardware needed — pure static analysis. Start with `--check-untyped-defs` on `Scotteprotocol/` and `nbeprotocol/` only (not the whole codebase) to keep noise low. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyserial's built-in `loop://` URL handler | (ships with `pyserial>=3.5`, already a dependency) | In-process software loopback serial port for unit tests | Use `serial.serial_for_url('loop://')` instead of a real `/dev/ttyUSB0` device wherever `Scotteprotocol`/`scottecom` code takes a `Serial` object. It's pyserial's own supported test mechanism (used in pyserial's own test suite), so it has zero extra dependency and zero drift risk versus a real `Serial` instance's API surface. |
| `unittest.mock.MagicMock` (stdlib, via `pytest-mock`'s `mocker`) | stdlib | Mock the `socket` object for NBE's UDP protocol | For `nbeprotocol/protocol.py`'s UDP broadcast (`find_controller()`) and request/response exchange, patch `socket.socket` with a `MagicMock` (or a small fake class exposing `sendto`/`recvfrom`) that returns pre-captured byte payloads. This is simpler and has fewer moving parts than a real loopback UDP socket for most tests; use a real `socket.socketpair()`-based fixture only for the handful of tests that need genuine two-way byte-level behavior. |
| `python-dbusmock` | `>=0.30` | Fake D-Bus service objects for testing IPC between `pellmonsrv`/`pellmonweb` | Not needed for the protocol-parsing tests, but directly applicable once you want to test the D-Bus IPC boundary (item read/write between daemon and web frontend) without a real D-Bus session and without needing the full daemon running. Provides a `DBusTestCase`/pytest fixture that spins up a private D-Bus session bus per test. Lower priority than serial/UDP mocking given the project's stated scope (protocol plugins first), but worth adding once the daemon/web D-Bus contract needs regression coverage. |
| `fake-rpi` or `Mock.GPIO` | latest | Stub `RPi.GPIO` so `raspberrygpio` plugin is importable off-Pi | Only needed if the roadmap decides to bring the GPIO plugin under test/CI import-checking (it's not in the Active requirements list currently, and hard-imports `RPi.GPIO` at module level today). If added, patch `sys.modules['RPi.GPIO']` with the fake before import in a conftest fixture rather than adding a runtime try/except fallback into production code (keeps the hardware-abstraction concern in test infrastructure, not application code, unless a fallback becomes a real feature requirement). |
| `pyupgrade` (standalone, or via `ruff --fix` with `UP` rules enabled) | `>=3.19` if run standalone | One-shot codemod for remaining Python-2 syntax | Already referenced in this repo's migration docs (`python-modernize`). Prefer running `ruff check --select UP --fix` now instead of standalone `pyupgrade`/`2to3`/`python-modernize` — `2to3` was removed from the stdlib and both `2to3`/`modernize` target Py2/3 *dual-compatible* code (six-based), which is the wrong goal now that this project is Python 3-only. `pyupgrade`'s rule set (also embedded in ruff's `UP` codes) is the correct current tool because it upgrades *to* modern Python 3 syntax rather than preserving Python 2 compatibility shims. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `ruff check --select UP,B,F,E,SIM` | Find remaining Python 2 idioms + general bug patterns | Run against `src/Scotteprotocol/`, `src/Pellmonsrv/plugins/nbecom/nbeprotocol/`, and `src/Pellmonsrv/plugins/*/` specifically — these are exactly the packages flagged in `CONCERNS.md` with bare imports, bare `except:`, and leftover `unicode()`. `UP` rules catch `unicode()`, old-style `%` formatting where relevant, `except X, e:` syntax, etc.; `B` catches bare `except:` (B001/E722 combination) and other bug-prone patterns. |
| `ruff format` | Formatting (replaces `black` if adopted) | Optional — not required to fix the migration, but if the roadmap wants consistent formatting while touching every plugin file anyway, this is the current standard tool (faster than Black, compatible output). |
| `mypy --strict-equality --check-untyped-defs` scoped to protocol packages | Catch bytes/str boundary bugs statically | Do NOT attempt `mypy --strict` codebase-wide on a project this size with zero prior typing — that produces hundreds of errors and stalls the effort. Scope it to `Scotteprotocol/`, `nbecom/nbeprotocol/`, and `database.py` first (the modules `CONCERNS.md` flags as most bug-prone), add minimal type annotations to function signatures only in those modules, and expand later. |
| `pytest.ini` / `pyproject.toml` `[tool.pytest.ini_options]` with `markers = ["hardware: requires physical burner hardware"]` | Separate hardware-dependent tests from CI-safe unit tests | Mark any test that genuinely needs a real serial device or LAN-connected NBE controller with `@pytest.mark.hardware` and exclude it by default (`addopts = "-m 'not hardware'"`); these become manual/on-device verification tests, run only when physical hardware is available, while the mocked frame encode/decode tests run in every CI invocation. |
| GitHub Actions (or equivalent CI) running on Linux runner, Python 3.13 | CI enforcement | Hardware plugins can still be **imported** and their pure encode/decode logic **unit-tested** on a stock Linux CI runner with no physical device — only the actual `ser.read()`/`socket.recvfrom()` calls need hardware, and those are exactly what `loop://`/mocked sockets replace. D-Bus/GLib can run in CI too (a private session bus can be started headlessly, e.g. via `dbus-run-session` or `python-dbusmock`'s bus-launching helpers), so CI is not blocked on Windows-vs-Linux — just make sure the CI job runs on Linux (matches the project's own Debian bookworm-slim production target), not Windows. |

## Installation

```bash
# Test framework + hardware-mocking support
pip install "pytest>=8.3" "pytest-mock>=3.14" "pytest-cov>=6.0" "pytest-socket>=0.7"

# Optional: D-Bus IPC test coverage (add when targeting the daemon<->web boundary)
pip install "python-dbusmock>=0.30"

# Optional: GPIO plugin off-Pi import/test support (only if GPIO plugin enters scope)
pip install "fake-rpi"

# Linting / static analysis
pip install "ruff>=0.8" "mypy>=1.13"
```

```toml
# pyproject.toml additions
[tool.pytest.ini_options]
addopts = "--disable-socket --cov=Pellmonsrv --cov=Pellmonweb -m 'not hardware'"
markers = ["hardware: requires physical burner/1-Wire/GPIO hardware, run manually"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.13"
# Start scoped — do not enable check_untyped_defs repo-wide yet
files = ["src/Scotteprotocol", "src/Pellmonsrv/plugins/nbecom/nbeprotocol", "src/Pellmonsrv/database.py"]
check_untyped_defs = true
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| pytest | stdlib `unittest` | If the team strongly prefers zero third-party test deps; loses fixture composability and the `pytest-socket`/`pytest-mock` plugin ecosystem, so not recommended here given the hardware-mocking needs. |
| pyserial `loop://` + `MagicMock` for sockets | `dummyserial` / `Mock.Serial`-style third-party mock packages | Use a dedicated mock package only if you need scripted, stateful request→response behavior keyed by exact bytes sent (e.g. simulating a specific Scotte burner's quirky responses across many test cases) — otherwise `loop://` plus writing the expected bytes directly in the test is simpler and has one fewer dependency. |
| ruff (`UP` rules) | standalone `pyupgrade` or `python-modernize`/`2to3` | Only reach for standalone `pyupgrade` if the team doesn't want to introduce ruff as a general linter yet and just wants a one-time codemod CLI; never reach for `2to3`/`python-modernize` again — both target Python 2/3 dual compatibility, which is not this project's goal now that Python 2 support is being dropped entirely. |
| mypy | pyright | Pyright is also a fine choice (arguably faster, better IDE integration) and would catch the same bytes/str mismatches; mypy is recommended here mainly because it's the more common CLI-first choice for a Linux/CI-focused server project without heavy editor tooling investment already in place. Either is fine — don't research this further, just pick one. |
| python-dbusmock | Real D-Bus session in CI (`dbus-run-session` + mocked service objects hand-rolled) | Use hand-rolled D-Bus test doubles only if `python-dbusmock`'s template system doesn't fit the project's custom `pellmonsrv`/`pellmonweb` D-Bus interface (it won't have a pre-built template for this app-specific interface, so you'd be writing custom mock objects either way — `python-dbusmock` still saves the bus-lifecycle boilerplate). |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| `2to3` | Removed from the Python standard library entirely (gone since Python 3.13); even as a standalone PyPI package it's unmaintained and only does the original 2008-era Py2→3 syntax rewrite, not the byte/str semantic fixes this project actually needs. | `ruff check --select UP --fix` for syntax modernization; manual review + mypy for the semantic bytes/str bugs, since no automated tool can safely infer whether a given call site should end up as `bytes` or `str`. |
| `python-modernize` / `six`-based compatibility shims | Both target maintaining simultaneous Python 2 *and* 3 compatibility (that's the whole point of `six`). This project has committed to Python 3 only (per `PROJECT.md` constraints) — adding `six` imports now would be moving backward, reintroducing the exact bytes/str ambiguity that caused the current bugs. | Direct Python 3 code; remove any remaining `six` usage if present rather than adding more. |
| Real hardware in CI (physical serial device or LAN-connected NBE controller as a CI dependency) | Not reproducible, not available in this dev environment or any standard CI runner, and explicitly called out as a project constraint. | `loop://` pyserial handler + mocked/patched `socket` objects, gated behind a `hardware` pytest marker so genuine hardware tests are opt-in/manual only. |
| `mypy --strict` applied repo-wide on day one | On a codebase with zero prior type annotations and a live migration in progress, full-strict mode produces hundreds of unrelated errors, burying the specific bytes/str bugs you actually care about and stalling adoption. | Scope mypy to the flagged protocol packages first (see Development Tools table), then expand module-by-module. |
| Bare `assert` statements as the only test mechanism, or continuing to rely on `test-imports.py`-style print/try-except scripts | Neither integrates with coverage, CI pass/fail signaling, parametrization, or fixtures — exactly the gap that let the confirmed plugin-import bugs ship as "migration complete." | pytest test functions with real `assert`/fixture-based tests; keep `test-imports.py` only as a quick manual smoke script if useful, but don't treat it as the test suite. |

## Stack Patterns by Variant

**If testing Scotte serial protocol frame encode/decode:**
- Use `serial.serial_for_url('loop://')` (or, for pure encode/decode logic with no I/O at all, just call the frame-building functions directly with byte strings and assert on output)
- Because the actual bug risk (per `CONCERNS.md`) is in manual byte-packing/frame parsing logic, most of which doesn't need a live serial object at all — prioritize pure unit tests on `Frame`/`Protocol` encode/decode methods over full loopback-serial integration tests, and reserve `loop://` for the smaller set of tests that exercise the read/write/timeout loop itself.

**If testing NBE UDP protocol (including XTEA-encrypted payloads):**
- Use `pytest-mock`'s `mocker.patch("socket.socket")` returning a `MagicMock` configured with `sendto`/`recvfrom` side effects built from captured real frame bytes (if any exist from pre-migration logs/docs) or hand-constructed per the protocol spec
- Because UDP is connectionless and broadcast-based (`find_controller()`), full loopback socket tests are more awkward than for serial; mocking `socket.socket` directly at the call site is simpler and also naturally blocked/caught by `pytest-socket` if a test accidentally tries the real thing.

**If testing the D-Bus IPC boundary between `pellmonsrv` and `pellmonweb`:**
- Use `python-dbusmock`'s pytest fixture / `DBusTestCase` to start a private session bus per test
- Because this avoids needing the real system D-Bus daemon or a full second process running, and keeps these tests hermetic and CI-safe on a standard Linux runner.

**If adding CI for the first time:**
- Run on a Linux runner (GitHub Actions `ubuntu-latest` or self-hosted Debian bookworm to match prod) with Python 3.13, `pytest -m "not hardware"` as the default job, `ruff check` and a scoped `mypy` run as separate lint jobs
- Because the project's production target is Linux-only already (D-Bus/GLib/rrdtool/serial/GPIO), testing on Windows CI would just reintroduce the same platform-split problems already documented in `CONCERNS.md` — don't try to make the test suite Windows-compatible beyond what's already true (syntax/import checks only).

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `pytest>=8.3` | Python 3.13/3.14 | No known incompatibilities; pytest 9.x (current stable as of mid-2026) also supports 3.13/3.14 — pin the floor at 8.3 and let CI pick up the latest 9.x unless a specific plugin requires an older pytest. |
| `pytest-socket` | `pytest>=7` | Actively maintained fork lineage (originally `atugushev/pytest-socket`, now maintained at `miketheman/pytest-socket`) — use the `miketheman/pytest-socket` PyPI package, not an abandoned fork. |
| `pyserial>=3.5` (already a project dependency) | `loop://` URL handler | No version bump needed — `loop://` has shipped with pyserial for years and is already covered by the existing `pyserial>=3.5` floor in `requirements.txt`. |
| `python-dbusmock` | Requires `dbus-python`/`PyGObject` and a D-Bus daemon binary available on the test runner (same system packages the project already needs in Docker/Debian) | On the Windows dev venv, `python-dbusmock` tests will not run at all (same constraint as the app itself) — scope these tests to the Linux/WSL dev environment and Linux CI only, matching the project's existing platform split. |
| `mypy` | `bytes`/`str` distinction works out of the box, no special config needed | No plugin required for this specific bug class — plain `mypy` already treats `bytes` and `str` as incompatible for `.split()`/`.encode()`/`.decode()` call chains, which is exactly the confirmed defect class in this codebase. |

## Sources

- pyserial `loop://` URL handler — https://pyserial.readthedocs.io/en/latest/url_handlers.html — MEDIUM confidence (WebSearch, cross-checked against pyserial's own test suite reference at github.com/pyserial/pyserial/blob/master/test/test.py)
- pytest-socket — https://github.com/miketheman/pytest-socket — MEDIUM confidence (WebSearch, official repo/README)
- python-dbusmock — https://github.com/martinpitt/python-dbusmock — MEDIUM confidence (WebSearch, official repo)
- ruff rules (UP/B/F categories, pyupgrade + flake8-bugbear coverage) — https://docs.astral.sh/ruff/rules/ — MEDIUM confidence (WebSearch summary of official Astral docs; recommend a final glance at the live rules page when configuring `pyproject.toml`, rule codes shift between ruff releases)
- pytest/pytest-cov current versions (pytest ~9.1, pytest-cov ~7.1 as of mid-2026) — https://github.com/pytest-dev/pytest/releases, https://pytest-cov.readthedocs.io/ — MEDIUM confidence (WebSearch; verify exact pin against PyPI at implementation time since this field moves fast)
- fake-rpi / RPi.GPIO mocking options — https://github.com/MomsFriendlyRobotCompany/fake_rpi, https://github.com/vapor-ware/fake-rpigpio — LOW confidence (WebSearch only, multiple competing small libraries, not independently verified against current RPi.GPIO API — worth a quick spike before committing if GPIO plugin testing enters scope)
- `2to3` removal from Python stdlib and general Py2→3 tooling landscape — https://github.com/PyCQA/modernize, https://blog.modelcode.ai/p/migrating-python-2-to-python-3-at — MEDIUM confidence (WebSearch, cross-referenced across multiple 2025/2026-dated articles agreeing on ruff/pyupgrade as the current recommended path)
- mypy bytes/str type-checking behavior — general mypy documentation knowledge (training data) cross-checked conceptually against the confirmed bug in `CONCERNS.md` (`response.payload.encode('ascii').split('=', 1)`) — HIGH confidence on the mechanism (bytes vs str are structurally distinct types in typeshed/mypy, this is core, stable mypy behavior, not a recent/volatile feature), not independently re-verified via Context7/live docs this session

---
*Stack research for: finishing Python 2→3 migration + test/lint tooling for a hardware-protocol daemon*
*Researched: 2026-09-17*
