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

## Expected-red baseline (as of Phase 1 completion)

These two cases MUST fail. Their failure is how ROADMAP Phase 1 success
criterion 2 is satisfied — the import-check is *working* because it fails.
They are filtered out of the green gate by the `known_broken` marker, never
by `xfail`/`skip`/deletion.

| Failing test ID | Error | Owner |
|---|---|---|
| `tests/test_plugin_imports.py::test_plugin_module_imports[scottecom]` | `ModuleNotFoundError: No module named 'protocol'` | IMPORT-01, Phase 3 |
| `tests/test_plugin_imports.py::test_nbecom_deferred_protocol_import` | `ModuleNotFoundError: No module named 'frames'` | IMPORT-02, Phase 3 |

The correct response to these two failures is to fix the underlying imports
in Phase 3, never to `xfail`, `skip`, or delete the tests, and never to widen
`PLATFORM_UNAVAILABLE` in `tests/test_plugin_imports.py` to make them
disappear (a tripwire test guards against exactly that).

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

## Phase 4 hook

`tests/conftest.py`'s `loop_serial` and `mocked_udp_socket` fixtures are the
hardware-mock boundary Phase 4 will inject into `Scotteprotocol.Protocol`
and `nbeprotocol.Proxy` constructors, once those packages' import breakage
(IMPORT-01/IMPORT-02) is fixed in Phase 3.
