# Codebase Concerns

**Analysis Date:** 2026-09-17

## Migration State: What's Actually Verified vs. Still Risky

The `python3-migration` branch history (`PHASE3-COMPLETE.md`, `PHASE4-TESTING.md`, `MIGRATION-SUMMARY.md`, latest commit `94c9b67` "Porting to pyhton 3 complete") claims the Python 3 port is functionally complete. In reality, verification was limited to `test-imports.py`, which only imports four top-level modules:

- `Pellmonsrv.pellmonsrv`
- `Pellmonsrv.database`
- `Pellmonweb.pellmonweb`
- `Pellmonweb.pellmonconf`

**None of the hardware/protocol plugins are imported or exercised by that script**, and none of them are imported eagerly by `pellmonsrv.py` at module load time — they are discovered and loaded dynamically at runtime by the yapsy plugin manager (`src/Pellmonsrv/yapsy/PluginManager.py`) only when enabled in `config/pellmon.conf`. This means "all core modules import successfully" does **not** cover the plugin code paths at all, and several of them are demonstrably broken (see below). Anyone relying on the "migration complete" commit messages should treat plugin activation as **unverified and likely broken**, not production ready.

- Files: `test-imports.py`, `PHASE3-COMPLETE.md`, `PHASE4-TESTING.md`, `MIGRATION-SUMMARY.md`
- Impact: False confidence that the port is done; real breakage will only surface when a user enables ScotteCom or NBEcom plugins against physical hardware.
- Fix approach: Extend `test-imports.py` (or a real test suite) to import every plugin package with an enabled config, and to instantiate protocol classes with dummy/mock serial or socket I/O.

## Known Bugs (Python 3 Porting Defects)

**Broken implicit relative imports in Scotteprotocol package (ScotteCom plugin is non-functional):**
- Symptoms: `ModuleNotFoundError` at plugin activation time.
- Files:
  - `src/Scotteprotocol/__init__.py:2` — `from protocol import Protocol` (needs to be `from .protocol import Protocol`)
  - `src/Scotteprotocol/frames.py:19` — `from protocol import Frame`
  - `src/Scotteprotocol/datamap.py:21` — `from frames import *`
  - `src/Scotteprotocol/protocol.py:25` — `from enumerations import dataEnumerations`
  - `src/Scotteprotocol/protocol.py:216` — `from datamap import dataBaseMap` (inside `createDataBase`)
  - `src/Pellmonsrv/plugins/scottecom/scottecom.py:22` — `import menus`
  - `src/Pellmonsrv/plugins/scottecom/scottecom.py:23` — `from descriptions import dataDescriptions`
  - `src/Pellmonsrv/plugins/scottecom/menus.py:19` — `from datamenu import dataBaseTags`
- Trigger: Enable `ScotteCom = yes` in `config/pellmon.conf` and start the server, or simply `from Scotteprotocol import Protocol`.
- Why it wasn't caught: `scottecom/__init__.py` appends **its own** plugin directory to `sys.path` (`sys.path.append(os.path.dirname(os.path.abspath(__file__)))`), which fixes `import menus`/`from descriptions import ...` inside `scottecom.py` itself, but does nothing for the separate top-level `Scotteprotocol` package, whose own submodules use bare (Python 2-style) implicit relative imports among themselves.
- Fix approach: Convert all intra-package imports in `Scotteprotocol/` and `scottecom/menus.py` to explicit relative imports (`from .protocol import Frame`, `from .frames import *`, `from .datamenu import dataBaseTags`, etc.), consistent with the fix already applied to `Pellmonsrv/__init__.py`, `pellmonsrv.py`, and `plugin_categories.py`.

**Same defect class in nbecom/nbeprotocol (NBEcom plugin likely non-functional):**
- Files:
  - `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:27` — `from frames import Request_frame, Response_frame`
  - `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:28` — `from protocolexceptions import *`
  - `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:30` — `import language`
  - `src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py:21` — `from protocolexceptions import *`
- Trigger: Enable `NBEcom = yes` (this is enabled by default in `config/pellmon.conf`) and let `nbecomplugin.activate()` run `from nbeprotocol.protocol import Proxy` (`src/Pellmonsrv/plugins/nbecom/__init__.py:38`).
- Why it wasn't caught: `nbecom/__init__.py:28` appends the **nbecom plugin directory** to `sys.path`, which makes `nbeprotocol` importable as a package, but does not add the `nbeprotocol/` subdirectory itself, so `nbeprotocol/protocol.py`'s bare `from frames import ...` still fails to resolve.
- Fix approach: Same as above — convert to explicit relative imports inside `nbeprotocol/`.

**Bytes/str split TypeError in NBEcom `Proxy.get()`:**
- Symptoms: `TypeError: a bytes-like object is required, not 'str'` at runtime whenever a value is read from the NBE controller.
- Files: `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py:144` and `:146`
  ```python
  return response.payload.encode('ascii').split('=', 1)[1]
  ...
  return response.payload.encode('ascii').split(';')
  ```
  `response.payload` is already a decoded `str` (see `frames.py:176`, `self.payload = (record[i:i+self.size]).decode('ascii')`). Encoding it to `bytes` and then calling `.split()` with a `str` separator (`'='`, `';'`) raises `TypeError` in Python 3 (bytes/str mixing is not allowed, unlike Python 2).
- Fix approach: Drop the `.encode('ascii')` call and split the `str` directly, or use byte separators (`b'='`, `b';'`) consistently if bytes are actually intended.

**Unbuffered text-mode file open in daemonizer:**
- Symptoms: `ValueError: can't have unbuffered text I/O` when the server daemonizes (double-forks and redirects stdio).
- Files: `src/Pellmonsrv/daemon.py:69` — `se = open(self.stderr, 'a+', buffering=0)`
- Cause: Python 2's `file()` allowed `buffering=0` for any mode; Python 3's `open()` only allows `buffering=0` in binary mode. This was a direct 1:1 `file()` → `open()` substitution (see `.py2bak`) that didn't account for the semantic change.
- Fix approach: Open in binary mode (`'ab', buffering=0`) or open in text mode and call `.flush()` explicitly after writes, or wrap with `io.TextIOWrapper(open(path, 'ab', buffering=0), write_through=True)`.

**Leftover Python 2 `unicode()` builtin call:**
- Symptoms: `NameError: name 'unicode' is not defined` — will crash the Calculate plugin's `setItem()` whenever it's invoked.
- Files: `src/Pellmonsrv/plugins/calculate/__init__.py:351` — `stack = [unicode(value)]`
- Impact: Any write to a calculated item (`CalcItem.setItem`) will always raise `NameError` (caught by a broad `except Exception as e:` immediately below, so it silently degrades to `logger.info(...)` + `return 'error'`, masking the root cause).
- Fix approach: Replace with `str(value)`.

**`.py2bak` backup files left throughout the tree (23 files):**
- Files (non-exhaustive, full package coverage): `src/Pellmonsrv/daemon.py.py2bak`, `database.py.py2bak`, `pellmonsrv.py.py2bak`, `plugin_categories.py.py2bak`, all `plugins/*/__init__.py.py2bak`, `yapsy/*.py.py2bak`, `Pellmonweb/*.py.py2bak`, `Scotteprotocol/protocol.py.py2bak`.
- Issue: These are pre-conversion Python 2 snapshots kept alongside the migrated `.py` files, tracked in git (`git status` shows them as modified, meaning they were committed). They add no value going forward, bloat the diff noise on every future commit that touches these files, and risk someone accidentally importing/executing the wrong one or treating them as current reference.
- Fix approach: Delete all `*.py2bak` files once the migration is confirmed stable (or move them to a single `migration-backup/` branch/tag instead of leaving them interspersed in `src/`).

**Commented-out `nbeprotocol/frames.py` and `protocol.py` debug prints kept as dead code:**
- Files: `src/Pellmonsrv/yapsy/PluginManager.py:187,260,315,401`, `VersionedPluginManager.py:97,108`, `plugins/consumption/__init__.py:236`, `plugins/nbecom/nbeprotocol/protocol.py:109,250`, `plugins/silolevel/__init__.py:156`
- Issue: Old Python 2 `print "..."` statements were left commented out rather than removed or converted, adding noise and stale syntax examples in the codebase.
- Fix approach: Delete dead commented-out debug prints, or convert to proper `logger.debug()` calls if the intent was diagnostic logging.

## Tech Debt

**Pervasive bare `except:` clauses swallow all errors, including `SystemExit`/`KeyboardInterrupt`:**
- Files: `src/Pellmonsrv/pellmonsrv.py` (27 occurrences), `src/Scotteprotocol/protocol.py` (19), `src/Pellmonsrv/plugins/calculate/__init__.py` (7), `src/Pellmonsrv/plugins/pelletcalc/__init__.py` (6), `src/Pellmonsrv/plugins/customalarms/__init__.py` (4), plus at least one in `database.py`, `consumption`, `exec`, `nbecom`, `openweathermap`, `raspberrygpio`, `scottecom.py`, `transformations.py`.
- Impact: Failures inside protocol parsing, database writes, or plugin activation are silently discarded (often with no logging at all), making the migration's true failure surface invisible during runtime testing. This directly compounds the "unverified plugins" risk above — a broken import inside a `try/except:` block during plugin discovery may just silently disable the plugin instead of surfacing a clear error.
- Fix approach: Replace with `except Exception:` at minimum, and log the exception (`logger.exception(...)`) rather than swallowing it silently.

**Implicit-relative-import style was only partially modernized:**
- The commit `94c9b67` ("Porting to pyhton 3 complete") fixed relative imports in the plugin `__init__.py` files themselves (e.g. `nbecom/__init__.py`, `owfs/__init__.py`) by adding `sys.path.append(...)` shims, but did not fix the *internal* imports within nested subpackages (`Scotteprotocol/`, `nbeprotocol/`), and did not convert any of these plugins to use proper explicit relative imports (`from .x import y`) as was done for the core `Pellmonsrv` package. This inconsistency (sys.path hacking in some places, explicit relative imports in others, still-broken bare imports elsewhere) makes the import strategy hard to reason about and easy to regress.
- Files: `src/Pellmonsrv/plugins/scottecom/__init__.py:6`, `src/Pellmonsrv/plugins/nbecom/__init__.py:28` vs. `src/Pellmonsrv/__init__.py:2`, `src/Pellmonsrv/pellmonsrv.py:43-44`.
- Fix approach: Standardize on explicit relative imports (PEP 328) throughout `src/`, removing the `sys.path.append` shims.

**Duplicate/parallel `datamap`, `frames`, `protocol` module names across two independent packages:**
- `src/Scotteprotocol/` (`frames.py`, `datamap.py`, `enumerations.py`, `protocol.py`) and `src/Pellmonsrv/plugins/nbecom/nbeprotocol/` (`frames.py`, `protocol.py`, `langmap.py`, `language.py`) both define modules with generic names like `frames`, `protocol`. Combined with the `sys.path.append`-per-plugin-directory pattern, this risks import shadowing if two plugins with same-named submodules are both active (whichever plugin's directory was appended to `sys.path` first "wins" for a bare `import protocol`).
- Files: `src/Scotteprotocol/*.py`, `src/Pellmonsrv/plugins/nbecom/nbeprotocol/*.py`
- Fix approach: Converting to explicit relative imports (above) eliminates this collision risk entirely, since modules would be addressed via their fully-qualified package path rather than resolved off `sys.path`.

**Hardware plugin code has no automated coverage and cannot be tested without physical devices:**
- `src/Pellmonsrv/plugins/nbecom/` (UDP/XTEA-encrypted protocol to NBE pellet burner controllers) — requires a real NBE controller on the LAN; `find_controller()` does UDP broadcast discovery (`nbeprotocol/protocol.py:154+`).
- `src/Pellmonsrv/plugins/scottecom/` and `src/Scotteprotocol/` — requires a physical serial connection (`pyserial`) to a Scotte pellet burner (`self.ser.write(...)`, `self.ser.read(...)` in `Scotteprotocol/protocol.py:239-301`).
- `src/Pellmonsrv/plugins/owfs/` and `src/Pellmonsrv/plugins/onewire/` — requires an OWFS daemon (`pyownet`) or direct 1-Wire bus access.
- `src/Pellmonsrv/plugins/raspberrygpio/__init__.py` — hard-imports `RPi.GPIO` at module level (`import RPi.GPIO as GPIO`, line 24), which only installs/imports successfully on actual Raspberry Pi hardware (or with a stub package); this plugin **cannot even be imported** on the Windows/WSL dev machines used for this migration, so it was never exercised by `test-imports.py` or any Phase 3/4 testing.
- Impact: None of the actual Python-2-to-3 semantic changes in these protocol/byte-handling code paths (the most bug-prone category, per the bugs above) have been runtime-validated. Confidence in "migration complete" should be lowest for exactly this code.
- Fix approach: Introduce a hardware abstraction/mock layer (fake serial port, fake UDP socket, fake OWFS server) so protocol framing/parsing logic can be unit-tested without hardware; gate `import RPi.GPIO` behind a try/except with a mock fallback for non-Pi environments during development.

**No automated test suite exists:**
- The only test-like artifact is `test-imports.py` at the repo root, a manual smoke-test script with no assertions framework (just try/except + print), and it is not wired into CI (no CI config found in the repo).
- Files: `test-imports.py`; absence confirmed via repo-wide search for `test_*.py` / `*_test.py` / pytest/unittest config.
- Impact: Every migration "fix" commit is verified by ad hoc manual runs rather than a repeatable, regression-preventing suite, which is how the bugs listed above went unnoticed.
- Fix approach: Add `pytest` (already implied by the general Python 3 toolchain) with unit tests for `database.py`, `Scotteprotocol` frame encode/decode round-trips, and `nbeprotocol` frame encode/decode round-trips using recorded sample byte sequences instead of live hardware.

**Windows/Linux platform split is fragile and undocumented in code:**
- `requirements.txt` comments out `rrdtool`, `dbus-python`, and `PyGObject` as "Linux/Unix" system packages, yet `pellmonsrv.py` unconditionally does `from gi.repository import GLib, GObject` and `import dbus as Dbus` at module import time (per `PHASE3-COMPLETE.md` section "GObject/GLib") and multiple plugins (`cleaning`, `consumption`, `silolevel`, `pellmonweb.py`, `pellmonsrv.py`) reference `rrdtool`.
- Impact: The server cannot start on Windows at all (confirmed by the project's own reliance on WSL per `WSL-SETUP.md`), despite `venv-py3` (a native Windows virtualenv) existing in the repo root, implying dual, only-partially-compatible dev environments.
- Fix approach: Document the Linux-only runtime requirement prominently (partially done in `MIGRATION-SUMMARY.md`, but not in `README.md`), or wrap DBUS/GObject imports in a conditional/optional-feature pattern if Windows support is ever a goal.

## Security Considerations

**Passwords logged in plaintext on failed web login:**
- Risk: Failed login attempts write the raw submitted password to the CherryPy log.
- Files: `src/Pellmonweb/auth.py:147,150` —
  ```python
  cherrypy.log('Login failed from %s, username: %s, password: %s'%(cherrypy.request.headers["Remote-Addr"], username[:50], password[:50]))
  ```
- Current mitigation: None; this runs on every failed login.
- Recommendations: Remove `password` from the log line entirely; log only username and remote address.

**Plaintext credential storage/comparison for web auth:**
- Risk: `check_credentials()` compares `(username, password)` tuples directly against an in-memory `self.credentials` collection (`src/Pellmonweb/auth.py:139-151`), implying credentials are held and compared in plaintext rather than hashed (the one hashing reference, `md5.new(password).hexdigest()`, is commented out as an "example implementation," confirming no hashing is actually used).
- Files: `src/Pellmonweb/auth.py:36-44,139-151`; credential source is `config/pellmon.conf` under `[authentication]` (`username`, `password` in cleartext in the config file).
- Recommendations: Hash stored passwords (e.g. `bcrypt`/`argon2`) and compare hashes; avoid ever holding/logging the raw password beyond the initial comparison.

**Shell-injection surface in Exec plugin:**
- Risk: The Exec plugin runs administrator-configured shell scripts via `subprocess.check_output(script, shell=True)`.
- Files: `src/Pellmonsrv/plugins/exec/__init__.py:86` (readscript path); a safer `subprocess.check_call([command]+parameters, shell=False)` form exists for the writescript path at line 94, showing the codebase already knows the safer pattern but didn't apply it consistently.
- Current mitigation: `script`/`command`/`parameters` come only from the local config file (`config/pellmon.conf` / `config_dir`), not from remote/web input directly, which limits — but does not eliminate — risk if config values are ever templated from less-trusted sources.
- Recommendations: Use `shell=False` with an argument list for the readscript path as well, matching the writescript pattern.

**Local config file with cleartext admin password is present on disk (untracked, but unencrypted):**
- Risk: `config/pellmon.conf` (git-ignored via root `.gitignore` pattern `pellmon.conf`, confirmed untracked in `git status`) stores the web UI admin password in plaintext. Not a repo leak, but a general secrets-hygiene concern given the plaintext-comparison auth design above.
- Files: `config/pellmon.conf` (existence only — content not reproduced here), `.gitignore` (pattern `pellmon.conf`)
- Recommendations: If password hashing is added (see above), migrate config to store only the hash.

## Fragile Areas

**Plugin activation error handling in yapsy hides real failures:**
- Files: `src/Pellmonsrv/yapsy/PluginManager.py` (500 lines; largest single module besides `pellmonweb.py`/`pellmonsrv.py`), with mixed tabs/spaces history noted in `PHASE3-COMPLETE.md` ("Fixed mixed tabs/spaces in PluginManager.py").
- Why fragile: Combined with the broken relative imports above, a plugin whose module fails to import will likely be silently skipped or logged tersely by the plugin manager rather than crashing loudly, making it easy to believe "the server started fine" while a configured plugin (e.g. ScotteCom, NBEcom) never actually activated.
- Safe modification: When touching plugin loading/error paths, add explicit `logger.exception()` calls so import failures during plugin discovery are visible in server logs, not just silently absent from the running item list.
- Test coverage: None.

**Byte/string boundary code in protocol modules (`Scotteprotocol/protocol.py`, `nbeprotocol/frames.py`, `nbeprotocol/protocol.py`):**
- Files: `src/Scotteprotocol/protocol.py` (399 lines, 19 bare excepts), `src/Pellmonsrv/plugins/nbecom/nbeprotocol/frames.py`, `protocol.py`
- Why fragile: These modules do manual byte-packing/unpacking with `%`-formatting + `.encode()`/`.decode()` calls (frame headers, checksums, XTEA-encrypted payloads) that were mechanically translated from Python 2's unified str/bytes model. The confirmed bug at `protocol.py:144` shows this translation is not fully correct; other adjacent lines follow the same pattern and warrant careful re-review line-by-line rather than assuming correctness because "it imports."
- Safe modification: Add round-trip encode/decode unit tests using captured real frame byte sequences (if any exist from pre-migration usage) before making further changes.
- Test coverage: None.

**`database.py` uses raw string-interpolated SQL alongside parameterized queries:**
- Files: `src/Pellmonsrv/database.py:187` uses a triple-quoted `INSERT OR REPLACE` with `%` placeholders mixed with parameterized `?` queries elsewhere in the same file (lines 165, 193, 196, 199 use `?` placeholders correctly).
- Why fragile: Inconsistent query-building style in the same module increases the chance a future edit reintroduces string-formatted SQL with unsanitized input.
- Safe modification: Audit `database.py:180-200` to confirm the triple-quoted statement doesn't interpolate variables via `%` string formatting (it appears to use `?` on closer read, but the module should be standardized to always use parameterized `cursor.execute(sql, params)` calls for clarity).
- Test coverage: None (no dedicated tests for `database.py`).

## Test Coverage Gaps

**No coverage for any protocol/hardware plugin:**
- What's not tested: `nbecom`, `scottecom`/`Scotteprotocol`, `owfs`, `onewire`, `raspberrygpio`, `openweathermap`.
- Files: `src/Pellmonsrv/plugins/nbecom/`, `src/Pellmonsrv/plugins/scottecom/`, `src/Scotteprotocol/`, `src/Pellmonsrv/plugins/owfs/`, `src/Pellmonsrv/plugins/onewire/`, `src/Pellmonsrv/plugins/raspberrygpio/`, `src/Pellmonsrv/plugins/openweathermap/`
- Risk: Confirmed-broken imports (ScotteCom, NBEcom) and the unverified `unicode()`/bytes-split bugs above would all have been caught immediately by even minimal unit tests.
- Priority: High — these are also the modules explicitly called out for attention in this analysis and are core to the product's purpose (monitoring a pellet stove).

**No coverage for `database.py` SQLite operations:**
- What's not tested: keyval storage get/set/init logic, including the `sqlite3.OperationalError` fallback table-creation path (`database.py:154-156`).
- Files: `src/Pellmonsrv/database.py`
- Risk: Low-medium; SQLite usage is simple, but this is the persistence layer for all cached/stored item values.
- Priority: Medium.

**No coverage for `Pellmonweb` auth/session logic:**
- What's not tested: `check_auth`, `check_credentials`, session-based login flow.
- Files: `src/Pellmonweb/auth.py`
- Risk: Medium — combined with the plaintext password logging/comparison issues above, this is the access-control boundary for the web UI.
- Priority: Medium-High given the security findings above.

---

*Concerns audit: 2026-09-17*
