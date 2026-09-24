# PellMon test suite

## How to run

`venv-py3/Scripts/python.exe` is the correct interpreter on this Windows dev
box — it has both `cherrypy` and `pyserial` installed. The bare
`C:\Python314\python.exe` does not have `cherrypy`, so `Pellmonweb.auth` (and
anything importing `Pellmonweb.pellmonweb`) fails to import there.

Dev/test dependencies come from `requirements-dev.txt`, never from
`requirements.txt` (production runtime deps only). Install both into
`venv-py3` before running tests:

```
venv-py3/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

Three commands, in order of how often you'll use them:

- **Green baseline gate** (must be 100% green before `/gsd:verify-work`):
  ```
  venv-py3/Scripts/python.exe -m pytest tests/ -m "not known_broken" -q
  ```
- **Full-truth run** (shows the real state of the migration, including the
  expected-red baseline below):
  ```
  venv-py3/Scripts/python.exe -m pytest tests/ -v
  ```
- **Fast per-commit loop** (fail on first error, skip known_broken):
  ```
  venv-py3/Scripts/python.exe -m pytest tests/ -x -q -m "not known_broken"
  ```

## Expected-red baseline (resolved in Phase 3)

As of Phase 3 completion, there are **0 expected-red failures** in the suite.
Both previously-failing test cases now pass cleanly under Python 3:

| Previously failing test ID | Error (pre-Phase 3) | Status | Resolution |
|---|---|---|---|
| `tests/test_plugin_imports.py::test_plugin_module_imports[scottecom]` | `ModuleNotFoundError: No module named 'protocol'` | PASSED | Fixed intra-package relative imports and established top-level Scotteprotocol package (IMPORT-01) |
| `tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import` | `ModuleNotFoundError: No module named 'frames'` | PASSED | Fixed intra-package relative imports in nbeprotocol and removed sys.path shims (IMPORT-02) |

`KNOWN_BROKEN_MODULES` in `tests/test_plugin_imports.py` is empty, and running `pytest tests/ -v` produces a completely green baseline.

## Platform skips

These modules skip on Windows dev machines and are expected to be genuinely
import-checked (not skipped) once the Phase 5 Linux CI runner (OPS-01)
exists. A skip is never an acceptable resolution for a real defect — only
for a confirmed platform-unavailable dependency:

- `calculate`, `consumption`, `customalarms`, `pelletcalc`, `silolevel`, and
  the `Pellmonsrv.pellmonsrv` core case — all need Unix-only `grp`/`pwd`
  (privilege-drop imports), absent on Windows.
- `raspberrygpio` — needs `RPi.GPIO`, Raspberry Pi hardware only.
- `Pellmonweb.pellmonweb` — needs `gi` (PyGObject/GLib), a Linux system
  package not pip-installable on Windows.

## Anything a later phase must not do

- Do not remove `--disable-socket` from `pytest.ini` `addopts`.
- Do not add `@pytest.mark.enable_socket` anywhere in `tests/`.
- Do not assert on `cherrypy.log` content in `tests/Pellmonweb/test_auth.py`
  — that would codify the SEC-01 plaintext-password-logging defect as
  expected behavior instead of flagging it for a fix.
- Do not import `Scotteprotocol` or `nbeprotocol` from
  `test_mocked_transport_smoke.py` until Phase 4 adds the injectable
  transport seam (PROTO-04).

## Headless-browser layout tests (Phase 10)

- Tests live in `tests/browser/` and skip unless `PELLMON_BROWSER_TESTS=1`.
  With it set, a missing Playwright or browser is a failure, not a skip.
- They run in CI as a mandatory step of the `test` job (so `publish`, which
  `needs: test`, is blocked by a layout failure).
- The run passes `--allow-unix-socket` on that one `pytest` invocation.
  Playwright's asyncio self-pipe needs a Unix socket, while TCP stays blocked
  in the test process. The stub web server runs as a subprocess and reports
  its port on stdout. This is a CLI flag, not an `enable_socket` marker, and
  `--disable-socket` stays in `pytest.ini`.
- Local run (WSL): create a scratch venv with `--system-site-packages`, then
  ```
  pip install -r requirements-browser.txt
  python -m playwright install chromium
  PYTHONPATH=src PELLMON_BROWSER_TESTS=1 python -m pytest tests/browser -v -rs --allow-unix-socket
  ```
- Screenshots go to `PELLMON_SHOTS_DIR` (default `tests/browser/_shots/`,
  git-ignored); CI uploads them as the `mobile-layout-screenshots` artifact.

## Phase 4 hook

`tests/conftest.py`'s `loop_serial` and `mocked_udp_socket` fixtures are the
hardware-mock boundary Phase 4 will inject into `Scotteprotocol.Protocol`
and `nbeprotocol.Proxy` constructors, once those packages' import breakage
(IMPORT-01/IMPORT-02) is fixed in Phase 3.
