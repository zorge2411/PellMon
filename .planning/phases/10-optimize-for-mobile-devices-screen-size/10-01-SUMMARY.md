---
phase: 10-optimize-for-mobile-devices-screen-size
plan: 01
subsystem: testing
tags: [playwright, cherrypy, pytest, headless-browser, stub-server]
requires: []
provides:
  - env-gated Playwright fixtures (tests/browser/conftest.py)
  - stub CherryPy server running real PellMonWeb handlers over FakeDbus
  - Windows-safe drift guard for pellmonweb.run() globals
affects: [10-05, 10-06]
tech-stack:
  added: [playwright==1.63.0 (test-only)]
  patterns: [subprocess stub server with READY port=N handshake, AST drift guard]
key-files:
  created:
    - requirements-browser.txt
    - tests/browser/conftest.py
    - tests/browser/stub_server.py
    - tests/browser/fake_dbus.py
    - tests/browser/plugin_templates.py
    - tests/browser/test_browser_harness.py
    - tests/Pellmonweb/test_mobile_stub_guard.py
  modified: []
key-decisions:
  - "Playwright pinned to 1.63.0 in requirements-browser.txt, kept out of requirements.txt, requirements-dev.txt and the Dockerfile"
  - "Stub server picks a free port with a throwaway socket (CherryPy start() waits on the bound port, so port 0 is not usable) and reports it on stdout"
requirements-completed: [D-06]
duration: n/a
completed: 2026-09-24
---

# Phase 10 Plan 01: Browser test harness Summary

Env-gated Playwright harness plus a stub web server (real PellMonWeb handlers over a fake D-Bus) that serves all six key pages; the `--disable-socket` spike could NOT be run here (see below).

## Task 1 (human gate, already passed)
The user approved the playwright PyPI package before any install: "Approved, use 1.63.0" (PyPI shows 1.63.0, author Microsoft Corporation, Python >=3.10, homepage github.com/Microsoft/playwright-python). Nothing was pip-installed by this executor; the pin is only written to `requirements-browser.txt`.

## Spike result
`BROWSER_PYTEST_FLAGS = --allow-unix-socket` (DETERMINED by the orchestrator after the executor
was sandbox-blocked from wsl.exe; see the "Orchestrator spike result" paragraph below).

**Orchestrator spike result (2026-09-24, WSL Debian, Python 3.13.5, system gi+dbus,
`--system-site-packages` scratch venv at `$HOME/pellmon-browser-venv`, playwright 1.63.0):**
`PELLMON_BROWSER_TESTS=1 PYTHONPATH=src python -m pytest tests/browser/test_browser_harness.py -v -rs --allow-unix-socket`
gave 8 passed in 3.45s: `test_playwright_starts_under_socket_guard`, `test_chromium_launches_and_renders_about_blank`
and `test_stub_serves_key_pages` for all 6 paths. So `--allow-unix-socket` is sufficient under
`--disable-socket` (no `-o addopts=""` fallback needed), and Chromium's headless shell
(`python -m playwright install chromium`, Chrome Headless Shell 153) launches in WSL without sudo.
CI still needs `playwright install --with-deps --only-shell chromium` on ubuntu-latest.

The plan requires running the harness tests in a WSL scratch venv. In this worktree-isolated executor every `wsl.exe` invocation was refused by the sandbox ("runs wsl in a plain command ... cannot be shown not to run git"), including `wsl.exe --status`. I did not try to bypass this. Consequences:
- Not verified: whether `test_playwright_starts_under_socket_guard` passes with `--allow-unix-socket` under `--disable-socket`, and whether Chromium can launch in WSL (missing shared libraries is unknown).
- Follow-up needed (by the orchestrator or a human, outside the worktree): create the scratch venv and run
  `PELLMON_BROWSER_TESTS=1 PYTHONPATH=src <venv>/bin/python -m pytest tests/browser/test_browser_harness.py -v -rs --allow-unix-socket`.
  If it fails with SocketBlockedError, retry with `-o addopts=""`. Default assumption for Plan 06 until then: `--allow-unix-socket` (research assumption A1, unverified). Never `--force-enable-socket`, never an `enable_socket` marker.

## Stub verification (substitute for the WSL run, Windows)
Chromium was not run at all (Playwright not installed, per the human gate scope). Instead I ran the stub in a scratch driver outside the repo, with `gi`, `dbus`, `pwd` and `grp` replaced by MagicMocks (Windows has none of them), and fetched pages over HTTP with urllib (not under pytest). HTTP status codes:

| Path | Status |
|------|--------|
| / | 200 (contains navbar) |
| /parameters/Overview | 200 |
| /settings/ | 200 |
| /consumptionview/consumption | 200 |
| /logview/logView | 200 |
| /auth/login | 200 |
| /export (stub override) | 200 (10508 bytes JSON) |
| /consumptionview/flotconsumption7d, /flotsilolevel, /systemimage, /about, /media/jquery/jquery.min.js | 200 |

The browser-level `test_stub_serves_key_pages` (six params) has therefore never run; it is skipped on Windows and awaits the WSL/CI run.

## Windows results
- `pytest tests/Pellmonweb/test_mobile_stub_guard.py tests/browser`: 2 passed, 8 skipped (every browser test skipped with "set PELLMON_BROWSER_TESTS=1 ...").
- Full suite `PYTHONPATH=src venv-py3 pytest tests/`: 3 failed, 383 passed, 58 skipped. The 3 failures are exactly the known baseline (test_backup_script::test_conf_d_overrides_pellmon_conf, test_plugin_loader::test_every_available_plugin_loads[consumption], [silolevel]).

## Commits
- 4c0d108: pin playwright, env-gated browser fixtures, harness smoke tests (Task 2)
- 03f8827: stub server, FakeDbus, plugin template lookup, drift guard (Task 3)

## Deviations from Plan

**1. [Blocked - environment] WSL spike and WSL stub run not executed.** See "Spike result". Substituted the Windows mock-`gi` HTTP run above for the stub check.

**2. [Rule 3 - Blocking] Port 0 not used for the stub.** The plan preferred `server.socket_port: 0`; CherryPy's server start waits on the configured port, so the stub uses the plan's stated fallback (throwaway socket to find a free port, then configure).

**3. [Rule 1 - Bug in own code] Stub `export` returns bytes.** A str body with `Content-Type: application/json` raised "Page handlers MUST return bytes"; fixed with `.encode("utf-8")`.

**4. `test_stub_serves_key_pages` is parametrized over the six paths** (one test id per path) rather than a single loop test.

## Deferred / observations (out of scope, not fixed)
- Under CherryPy 18.10.0 the same "Page handlers MUST return bytes" 500 occurs for the real `getparamlist` (str body with an explicit application/json header) in the stub; the real `export` and `getparam` handlers follow the same pattern. Not confirmed on the production image; worth checking separately. In the stub `/getparamlist` returns 500, which does not affect page layout.
- `run()` assigns `consumption_graph` as a local (no `global` statement), so `flotconsumption` would hit a NameError in production. The stub sets `web.consumption_graph` explicitly.
- `/graph` (rrdtool PNG) 500s in the stub (no rrdtool); the dashboard uses flot via `/export`, not `/graph`.

## Known Stubs
None in shipped code; `fake_dbus.py` is intentionally canned test data.

## Threat Flags
None beyond the plan's threat model (stub binds 127.0.0.1, auth off, lives under tests/).

## Self-Check: PASSED
Files exist (requirements-browser.txt, tests/browser/{conftest,stub_server,fake_dbus,plugin_templates,test_browser_harness}.py, tests/Pellmonweb/test_mobile_stub_guard.py) and commits 4c0d108 and 03f8827 are on the worktree branch. No `enable_socket`, `force-enable-socket` or module-level playwright import in tests/browser.
