---
phase: quick-260919-bbw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - .gitignore
  - src/Pellmonsrv/pellmonsrv.py
  - src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py
  - src/Pellmonweb/auth.py
  - src/Pellmonweb/pellmonweb.py
  - src/Pellmonweb/pellmonconf.py
  - src/conf.d/webinterface.conf.in
  - config/pellmon.conf.example
  - docker-compose.yml
  - README.md
  - tests/Pellmonsrv/test_db_copy.py
  - tests/Pellmonweb/test_auth_security.py
  - tests/Pellmonweb/test_auth.py
  - tests/Pellmonweb/test_pellmonconf_csrf.py
autonomous: true
requirements: [REVIEW-04, REVIEW-05, REVIEW-06, REVIEW-07, REVIEW-08]

must_haves:
  truths:
    - "pellmonsrv no longer shells out via os.system for db copy or rrd create; failures are logged, not silently swallowed"
    - "Concurrent copy_db calls are serialized by a module-level lock, not a globals() probe"
    - "A plaintext password in pellmon.conf can no longer authenticate to the web UI"
    - "New password hashes use 600000 PBKDF2 iterations; existing hashes still verify with their own stored iteration count"
    - "pellmonweb binds 127.0.0.1 by default and only 0.0.0.0 when explicitly configured; Docker still reachable"
    - "Session cookies carry HttpOnly and SameSite=Lax; Secure is configurable"
    - "A cross-origin POST to pellmonconf /save is rejected"
    - ".env is git-ignored while .env.example stays tracked"
    - "The NBE mock server enforces the pincode check and logs instead of printing"
  artifacts:
    - path: "src/Pellmonsrv/pellmonsrv.py"
      provides: "shutil/subprocess-based copy_db + rrd create, _copy_lock"
      contains: "shutil.copy"
    - path: "src/Pellmonweb/auth.py"
      provides: "PBKDF2-only verification, 600000 default iterations"
      contains: "600000"
    - path: "tests/Pellmonsrv/test_db_copy.py"
      provides: "copy_db / RrdCreateCommand regression tests"
    - path: "tests/Pellmonweb/test_pellmonconf_csrf.py"
      provides: "same-origin enforcement tests for save()"
  key_links:
    - from: "src/Pellmonsrv/pellmonsrv.py"
      to: "conf.RrdCreateCommand"
      via: "subprocess.run argv list"
      pattern: "subprocess\\.run\\(conf\\.RrdCreateCommand"
    - from: "docker-compose.yml"
      to: "src/Pellmonweb/pellmonweb.py"
      via: "PELLMON_WEB_HOST env var"
      pattern: "PELLMON_WEB_HOST"
---

<objective>
Close review items 4-8 from the PellMon security review: remove shell-string command execution and the unsafe `globals()` concurrency flag in the daemon, drop the plaintext-password authentication fallback and raise PBKDF2 iterations, harden the web/config servers (bind address, cookie flags, CSRF, no debug environment), git-ignore `.env`, and repair the disabled pincode check plus stray `print()` calls in the NBE mock server.

Purpose: These are the remaining exploitable/foot-gun findings after the earlier command-injection quick fix (260919-atb).
Output: Hardened source in `src/`, updated config/docs samples, new regression tests under `tests/`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@.planning/quick/260919-atb-fix-command-injection-in-graph-endpoint-/260919-atb-SUMMARY.md

@src/Pellmonsrv/pellmonsrv.py
@src/Pellmonweb/auth.py
@src/Pellmonweb/pellmonconf.py
@tests/conftest.py

**Project conventions that apply here** (from CLAUDE.md):
- `%`-formatting for log messages inside `src/Pellmonsrv/`; shared logger `getLogger('pellMon')`.
- No type hints; match surrounding untouched indentation exactly, do not reformat whole blocks.
- Do not edit `*.py2bak` files — they are pre-migration snapshots.

**Execution constraints (from the task brief):**
- Work happens on the main tree (no worktree). Many unrelated files carry uncommitted user edits.
- Commit ONLY files this plan touches, with explicit paths. Never `git add -A`, `git stash`, `git restore`, or `git checkout --`.
- Record a pre-change pytest baseline before editing anything.
- This is a Windows dev box: `cherrypy`, `dbus`, `gi`, `Crypto`, `rrdtool` are NOT installed. Tests importing them will error at collection — that is the known baseline condition, not a regression. Note in the SUMMARY which new tests could not run locally.

<interfaces>
Current shapes the executor must work against (already read — do not re-read to confirm):

`src/Pellmonsrv/pellmonsrv.py`
- L327-352 `copy_db(direction='store')` — `global copy_in_progress`; `if not 'copy_in_progress' in globals()`; two branches each doing `os.system('cp %s %s'%(...))` inside try/except/finally.
- L551-555 — `if conf.polling: if not os.path.exists(conf.nvdb): os.system(conf.RrdCreateString)` then `logger.info('Created rrd database: '+conf.RrdCreateString)`.
- L754-760 `config.__init__` — builds `self.RrdCreateString` as `"rrdtool create %s --step %u "%(self.nvdb, self.poll_interval)` then appends `item['ds_type'] % (item['ds_name'], self.poll_interval*4) + ' '` per polled item, then four `RRA:AVERAGE:...` tokens. Every appended token is space-free.
- `subprocess` is already imported (used at L566). `shutil` is NOT yet imported.

`src/Pellmonweb/auth.py`
- `hash_password(password, salt=None, iterations=100000)` -> `'pbkdf2:sha256:%d$%s$%s'`
- `verify_password(stored_credential, provided_password)` — L67-68 is the plaintext fallback (`hmac.compare_digest(stored_str, provided_str)`).
- `AuthController.check_credentials` L184-195 — dict and list branches, each with a `logger.warning(... legacy plaintext ...)` block when the stored value lacks the `pbkdf2:` prefix.

`src/Pellmonweb/pellmonweb.py`
- L849-853 — `credentials = parser.items('authentication')` with `except: credentials = [('testuser','12345')]`.
- L904-927 — `port` parsed from `[conf] port` (fallback 8081); `global_conf` dict with a commented-out `#w'server.environment': 'debug',`, `tools.sessions.on/timeout`, `'server.socket_host': '0.0.0.0'`.

`src/Pellmonweb/pellmonconf.py`
- `_resolve(filename)` allowlist already exists (from quick-260919-atb) — do not change it.
- `save(self, filename='', data=None)` L120-132 — guards on `cherrypy.request.method == "POST"`, no CSRF check.
- `run()` L151-164 — `'server.environment': 'debug'` is ACTIVE here; `--host` defaults to `'0.0.0.0'`.
- Client posts via `src/Pellmonweb/media/js/source.js:44` `$.post('/save', {filename, data})` and `html_conf/layout.html:36` `<form action="/save" method="post">`.

`src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`
- `Controller.run()` L354-395 — `print('< ' + ...)` / `print('  > ' + ...)` calls and `if True: #self.requset.pincode == self.password:` at L371 (note the typo `requset` in the dead comment). `logger` already exists in this module (used at L335).
- `frames.py:39` sets `self.pincode = '0123456789'`; `frames.py:65` encodes it as `('%10s'%self.pincode[:10])` (space-padded); `frames.py:110` decodes `record[i:i+10].decode('ascii')` — so a decoded pincode carries leading spaces and must be compared stripped.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 0: Record pytest baseline</name>
  <files>(none — read-only)</files>
  <action>
    Before any edit, run the suite and capture the exact pass/fail/error counts so the post-change run can be compared against it. Run from the repo root with the project's Python. Use `--continue-on-collection-errors` because several test modules import `cherrypy`/`dbus`/`Crypto`, which are absent on this Windows box and error at collection time by design. Save the summary line verbatim for the SUMMARY document. Per the previous quick task the expected baseline shape is roughly "3 failed, N passed, 7 skipped, 7 errors" — record the actual numbers, do not assume.
  </action>
  <verify>
    <automated>python -m pytest tests/ --continue-on-collection-errors -q</automated>
  </verify>
  <done>Baseline summary line recorded verbatim (failed/passed/skipped/errors counts) for later comparison.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 1: Daemon shell-call removal, copy lock, NBE mock server, .gitignore</name>
  <files>src/Pellmonsrv/pellmonsrv.py, src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py, .gitignore, tests/Pellmonsrv/test_db_copy.py</files>
  <behavior>
    - `copy_db('store')` calls `shutil.copy(conf.db, conf.nvdb)`; `copy_db('restore')` calls `shutil.copy(conf.nvdb, conf.db)`.
    - No `os.system` call remains anywhere in `src/Pellmonsrv/pellmonsrv.py`.
    - When `shutil.copy` raises, `copy_db` logs the failure (via `logger.exception`) and does not propagate.
    - While one `copy_db` call is in flight, a reentrant/concurrent call returns immediately without performing a second copy (lock held non-blocking).
    - After a failed copy the lock is released, so a subsequent `copy_db` call does perform a copy.
    - `config.RrdCreateCommand` is a `list` whose first three elements are `['rrdtool', 'create', <nvdb path>]` and which contains one `DS:` element per polled item plus four `RRA:AVERAGE:` elements, each as its own list element (no element contains a space).
    - `config.RrdCreateString` still exists as a human-readable `' '.join(RrdCreateCommand)` for log output.
    - The NBE `Controller.run()` rejects a request whose `pincode` does not match the controller password (responds `'wrong password'`, status 1) and accepts a matching, space-padded pincode.
  </behavior>
  <action>
    Item 4 — `src/Pellmonsrv/pellmonsrv.py`:
    1. Add `shutil` to the stdlib import block at the top of the module, matching the existing comma-separated import style. `subprocess` is already imported.
    2. Add a module-level `_copy_lock = threading.Lock()` immediately above `copy_db` (module level, not inside a function).
    3. Rewrite `copy_db` to drop the `global copy_in_progress` / `if not 'copy_in_progress' in globals()` probe entirely. Acquire the lock non-blocking: if `_copy_lock.acquire(False)` is falsy, log at debug level that a copy is already in progress and return. Otherwise `try:` pick src/dst from `direction` (`'store'` -> `conf.db` to `conf.nvdb`, anything else -> `conf.nvdb` to `conf.db`), call `shutil.copy(src, dst)` (it raises on failure, so the existing try/except now actually works), log success at the same level the current code uses for that direction (`debug` for store, `info` for restore), `except Exception:` -> `logger.exception('copy %s to %s failed'%(src, dst))`, and `finally: _copy_lock.release()`. Collapse the two near-duplicate branches into one body — keep the behaviour, not the duplication.
    4. In `config.__init__` (~L754-760) build `self.RrdCreateCommand` as a list: start `['rrdtool', 'create', self.nvdb, '--step', '%u'%self.poll_interval]`, append each `item['ds_type'] % (item['ds_name'], self.poll_interval*4)` as one element, then append the four `RRA:AVERAGE:0.1:1:20000`, `...:10:20000`, `...:100:20000`, `...:1000:20000` elements individually. Then set `self.RrdCreateString = ' '.join(self.RrdCreateCommand)` so existing log lines and any external reader keep working. Do not strip trailing spaces from the DS format strings by hand — the `%` result is already space-free.
    5. At ~L553, replace `os.system(conf.RrdCreateString)` with `subprocess.run(conf.RrdCreateCommand, check=True)` wrapped in try/except: on success keep the existing `logger.info('Created rrd database: '+conf.RrdCreateString)`; on `Exception` log `logger.exception('failed to create rrd database: %s'%conf.RrdCreateString)` so the daemon does not die on a missing rrdtool but the failure is visible.

    Item 8 — `src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py`, `Controller.run()`:
    6. Replace `if True: #self.requset.pincode == self.password:` with a real check comparing the decoded, space-padded request pincode against the controller password: compare `str(self.request.pincode).strip()` to `str(self.password).strip()` using `hmac.compare_digest` (add `import hmac` to the module's import block). The `else:` branch already sends the `'wrong password'` response — leave it as is.
    7. Replace every `print(...)` in `Controller.run()` with `logger.debug(...)` using `%`-style lazy args (e.g. `logger.debug('< %s', self.request.payload.decode('ascii'))`, `logger.debug('  > %s', frame.decode('ascii'))`). Then check `tests/test_no_ad_hoc_print.py` — if that module allowlists/exempts `nbeprotocol/protocol.py` for prints, remove the exemption so the sweep now covers it. Do not touch the `except Exception as e: pass` at ~L336 (out of scope).

    Item 7 — `.gitignore`:
    8. Append to the "Python 3 migration additions" area (or a new `# Local environment` section) the two lines `.env` and `!.env.example`, in that order. Confirm `.env.example` stays tracked and `.env` becomes ignored. Do not remove `.env` from the index if it is untracked (it is) — simply ignoring it is enough.

    Tests — `tests/Pellmonsrv/test_db_copy.py` (new):
    9. Write the behaviours above. Importing `Pellmonsrv.pellmonsrv` pulls in `dbus`/`gi`, which are absent on Windows: follow the exact import/stub pattern already used by `tests/Pellmonsrv/test_sigterm_handling.py` and `tests/Pellmonsrv/conftest.py` rather than inventing a new one. Patch `shutil.copy` via `mocker` and use a dummy `conf` object with `db`/`nvdb` attributes. For the lock behaviour, make the patched `shutil.copy` side effect call `copy_db` re-entrantly (or assert `_copy_lock` is held during the call) and assert only one copy happened. For `RrdCreateCommand`, assert it is a `list`, that `' ' not in element` for every element, and that `RrdCreateString == ' '.join(RrdCreateCommand)`. Add an NBE pincode test that constructs a `Controller`-like request with a mismatched pincode and asserts the `'wrong password'` path is taken — use the `mocked_udp_socket` fixture from `tests/conftest.py` (the suite-wide real-socket guardrail is active; that fixture is the only sanctioned way to touch `socket.socket`).
  </action>
  <verify>
    <automated>python -m pytest tests/Pellmonsrv/test_db_copy.py tests/test_no_ad_hoc_print.py -q --continue-on-collection-errors</automated>
  </verify>
  <done>
    `grep -n "os.system" src/Pellmonsrv/pellmonsrv.py` returns nothing; `_copy_lock` exists at module level; `RrdCreateCommand` is a list consumed by `subprocess.run(..., check=True)`; `if True:` is gone from `nbeprotocol/protocol.py` and no bare `print(` remains in `Controller.run()`; `git check-ignore .env` succeeds while `git ls-files .env.example` still lists it; new tests pass (or their inability to run locally is recorded).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: PBKDF2-only authentication, 600000 iterations, sample/doc migration</name>
  <files>src/Pellmonweb/auth.py, src/Pellmonweb/pellmonweb.py, src/conf.d/webinterface.conf.in, config/pellmon.conf.example, README.md, tests/Pellmonweb/test_auth_security.py, tests/Pellmonweb/test_auth.py</files>
  <behavior>
    - `verify_password('somePlaintext', 'somePlaintext')` returns `False`.
    - A non-`pbkdf2:`-prefixed stored credential causes an error-level log naming `hash_password` as the remedy.
    - `hash_password('pw')` produces a credential whose iteration field is `600000`.
    - A hash previously generated with 100000 iterations still verifies correctly (the stored count is honoured, not the new default).
    - `AuthController.check_credentials` returns the failure string for a plaintext stored credential, for both the dict and the list credential shapes.
    - No "legacy plaintext ... backward-compatible" warning path remains.
  </behavior>
  <action>
    Item 5 — `src/Pellmonweb/auth.py`:
    1. Add a module-level `PBKDF2_ITERATIONS = 600000` constant and use it as the `hash_password` default (`def hash_password(password, salt=None, iterations=PBKDF2_ITERATIONS)`). Do NOT change the verification path's iteration handling — it already parses the count out of the stored credential, which is exactly what keeps old 100000-iteration hashes working.
    2. In `verify_password`, delete the `# Legacy plaintext fallback` branch (the trailing `return hmac.compare_digest(stored_str, provided_str)`). In its place, log once at error level — e.g. `logger.error('stored web credential is not a PBKDF2 hash; plaintext passwords are no longer accepted. Generate a hash with: python3 -c "from Pellmonweb.auth import hash_password; print(hash_password(\'yourpassword\'))"')` — and `return False`. Keep `hmac` imported (still used by the pbkdf2 path).
    3. In `AuthController.check_credentials`, remove both `if not str(...).startswith('pbkdf2:'): logger.warning(... legacy plaintext ...)` blocks; a successful `verify_password` now always implies a hashed credential, so just `return None`.
    4. In `src/Pellmonweb/pellmonweb.py` L849-853, change the `except:` fallback from `credentials = [('testuser','12345')]` to `credentials = []` plus a `logger`/`cherrypy.log` error stating that no `[authentication]` section was found and that the web UI will reject all logins until hashed credentials are configured. That hardcoded plaintext default can no longer authenticate anyway; leaving it would be a silent-lockout trap.

    Samples and docs (the review item explicitly asks for these):
    5. `src/conf.d/webinterface.conf.in` — replace the live `testuser = 12345` line with a commented example showing the hashed form and the generation command. Leave the surrounding `# IMPORTANT! Change this ...` banner, updated to say passwords must be PBKDF2 hashes.
    6. `config/pellmon.conf.example` L25-29 — drop "or legacy plaintext" wording; state hashes are required, and update the shown example prefix from `pbkdf2:sha256:100000$...` to `pbkdf2:sha256:600000$...`.
    7. `README.md` L207 — replace the "legacy plaintext passwords remain backward-compatible" note with a breaking-change note: plaintext passwords are rejected; migrate with the `hash_password` one-liner.
    8. Check `DOCKER.md` and `.env.example` for any shipped plaintext credential guidance and update it the same way; if neither mentions credentials, note that in the SUMMARY rather than editing them.
    9. IMPORTANT — do NOT edit `config/pellmon.conf`. It is git-ignored and is the user's live config containing a plaintext password. Instead, call out prominently in the SUMMARY that the user must hash that password before restarting `pellmonweb`, and give them the exact one-liner.

    Tests:
    10. Update `tests/Pellmonweb/test_auth_security.py`: rename/invert `test_verify_password_plaintext_backward_compatibility` to assert rejection; fix `test_check_credentials_with_dict_credentials` (its `"user": "plaintext_user"` entry must now fail); convert `test_check_credentials_legacy_plaintext_warning` into a rejection test asserting the error-level log via `caplog`. Add a test that a 100000-iteration hash built with `hash_password(pw, iterations=100000)` still verifies, and that `hash_password(pw)` embeds `600000`. Adjust the module docstring line 6 which currently documents the plaintext behaviour.
    11. Update `tests/Pellmonweb/test_auth.py` fixtures to use hashed credentials wherever they currently pass plaintext. To keep these tests fast, build fixture hashes with an explicit low iteration count (e.g. `hash_password(pw, iterations=1000)`) rather than the 600000 default — the verification path honours the stored count.
  </action>
  <verify>
    <automated>python -m pytest tests/Pellmonweb/test_auth.py tests/Pellmonweb/test_auth_security.py -q --continue-on-collection-errors</automated>
  </verify>
  <done>
    No plaintext comparison path remains in `verify_password`; `grep -n "600000" src/Pellmonweb/auth.py` matches; old-iteration hashes still verify; auth tests pass (or the cherrypy-missing collection error is recorded as the known Windows limitation); samples/docs no longer advertise plaintext passwords.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Web bind address, session cookie flags, pellmonconf CSRF and debug removal</name>
  <files>src/Pellmonweb/pellmonweb.py, src/Pellmonweb/pellmonconf.py, docker-compose.yml, src/conf.d/webinterface.conf.in, tests/Pellmonweb/test_pellmonconf_csrf.py</files>
  <behavior>
    - With no config and no env var, the resolved web bind host is `127.0.0.1`.
    - `PELLMON_WEB_HOST=0.0.0.0` in the environment yields `0.0.0.0`.
    - An explicit `[conf] host` config value wins over the env var.
    - `save()` returns a failure JSON and performs no write when the `Origin` header names a different host than the request `Host`.
    - `save()` returns a failure JSON when both `Origin` and `Referer` are absent.
    - `save()` proceeds normally when `Origin` matches the request host.
    - `server.environment` is absent from both web apps' config dicts.
  </behavior>
  <action>
    Item 6 — `src/Pellmonweb/pellmonweb.py` (~L904-927):
    1. Next to the existing `port` parsing, resolve the bind host with this precedence: `parser.get('conf', 'host')` if present, else `os.environ.get('PELLMON_WEB_HOST')`, else `'127.0.0.1'`. Use the same defensive `try/except` idiom the surrounding `port` code uses (this file uses bare `except:` here — match it rather than reformatting). Set `'server.socket_host': socket_host` in `global_conf` instead of the hardcoded `'0.0.0.0'`, and log the resolved bind address at info level so a "can't reach the UI" report is diagnosable.
    2. In `global_conf['global']`, delete the commented-out `#w'server.environment': 'debug',` line entirely, and add the session cookie flags: `'tools.sessions.httponly': True`, `'tools.sessions.samesite': 'Lax'`, and `'tools.sessions.secure': <configurable>` where the value comes from a `[conf] session_cookie_secure` boolean (via `parser.getboolean`) defaulting to `False` — defaulting to `True` would break every plain-HTTP LAN deployment, which is the normal PellMon setup. If `cherrypy` rejects `tools.sessions.samesite` on the installed version, fall back to omitting it and record that in the SUMMARY rather than failing the task.
    3. `docker-compose.yml` — add `- PELLMON_WEB_HOST=${PELLMON_WEB_HOST:-0.0.0.0}` to the `pellmonweb` service `environment:` block so the container keeps binding all interfaces (port publishing depends on it). Add the same key with a `0.0.0.0` value and an explanatory comment to `.env.example`. Do not touch `.env`.
    4. Document both new options (`host`, `session_cookie_secure`) as commented entries in `src/conf.d/webinterface.conf.in`.

    Item 6 — `src/Pellmonweb/pellmonconf.py`:
    5. In `run()`'s `global_conf`, delete the active `'server.environment': 'debug',` entry and change the `-H/--host` argparse default from `'0.0.0.0'` to `'127.0.0.1'` (update its help text to match). This tool is explicitly "run as root to save changes" — it must not default to a public bind.
    6. Add CSRF protection for the `save()` POST as a same-origin check (no session token, so neither `html_conf/layout.html` nor `media/js/source.js` needs changing — browsers send `Origin` on same-origin POSTs and `Referer` covers the rest). Implement a module-level helper, e.g. `_check_same_origin()`, that: reads `cherrypy.request.headers`; takes `Origin`, falling back to `Referer`; if neither is present, returns `False`; otherwise parses it with `urllib.parse.urlparse` and compares `netloc` against the request's `Host` header; returns `True` only on an exact match. Call it at the top of the `POST` branch in `save()` before `_resolve()`; on failure `logger.warning('rejected cross-origin config save: origin=%r host=%r', ...)` and return `json.dumps({'success': False, 'error': 'cross-origin request rejected'})` without writing anything. Add `import urllib.parse` to the module imports. Leave `_resolve()` and the existing allowlist untouched.

    Tests — `tests/Pellmonweb/test_pellmonconf_csrf.py` (new):
    7. Cover the `save()` behaviours above by patching `cherrypy.request` headers/method — follow the stubbing approach already used in `tests/Pellmonweb/test_pellmonconf_path_traversal.py` (same module, same cherrypy-import problem) and reuse the `cherrypy_request_ctx` fixture from `tests/conftest.py` where it fits. Add the host-resolution cases as plain unit tests of the resolver if it can be reached without importing all of `pellmonweb.py`; if it cannot be isolated, extract the precedence logic into a small module-level function in `pellmonweb.py` (e.g. `_resolve_socket_host(parser)`) and test that.
  </action>
  <verify>
    <automated>python -m pytest tests/Pellmonweb/ -q --continue-on-collection-errors</automated>
  </verify>
  <done>
    `grep -rn "server.environment" src/Pellmonweb/` returns nothing; `grep -n "0.0.0.0" src/Pellmonweb/pellmonweb.py src/Pellmonweb/pellmonconf.py` returns no hardcoded bind; `PELLMON_WEB_HOST` present in `docker-compose.yml` and `.env.example`; `tools.sessions.httponly` set; cross-origin `save()` rejected by test (or the cherrypy-missing collection error is recorded).
  </done>
</task>

<task type="auto">
  <name>Task 4: Post-change verification and scoped commits</name>
  <files>(none — verification and git only)</files>
  <action>
    1. Re-run the full suite with `--continue-on-collection-errors` and diff against the Task 0 baseline. Any *new* failure or error beyond the baseline (other than newly added cherrypy-dependent test modules erroring at collection for the known missing-dependency reason) must be fixed before committing, not explained away.
    2. Compile-gate every touched Python file: `python -m py_compile` on each path in `files_modified`.
    3. Commit in three scoped commits using explicit paths only — never `git add -A`, `git stash`, `git restore`, or `git checkout --`. Several unrelated files in the tree carry the user's uncommitted edits and must stay untouched:
       - `fix(quick-260919-bbw): replace shell calls with argv/shutil, lock db copy, fix nbe mock auth` — the Task 1 paths.
       - `fix(quick-260919-bbw): require PBKDF2 hashed web passwords, raise iterations to 600000` — the Task 2 paths.
       - `fix(quick-260919-bbw): bind localhost by default, harden session cookies, add conf CSRF check` — the Task 3 paths.
       If a touched file also carries pre-existing user edits, that file's commit will include them — note this explicitly in the commit body and the SUMMARY, as the previous quick task did.
    4. Write the SUMMARY including: baseline vs. final test counts, which new tests could not run on Windows and why, the `config/pellmon.conf` plaintext-password migration call-out for the user, and any deviation (e.g. `samesite` unsupported).
  </action>
  <verify>
    <automated>python -m pytest tests/ -q --continue-on-collection-errors</automated>
  </verify>
  <done>Final counts recorded and compared to baseline; three scoped commits exist; no unrelated modified file was staged; SUMMARY written.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| config file -> `os.system` argv | `conf.db`/`conf.nvdb`/RRD DS names reach a shell string; a path with spaces or `;` becomes command execution |
| browser -> `pellmonweb` login | Untrusted credentials; stored secret material lives in a config file |
| network -> `pellmonweb` / `pellmonconf` bind address | Binding `0.0.0.0` exposes an auth-optional config editor to the LAN |
| cross-site browser -> `pellmonconf /save` | Any page can POST a form to a root-run config writer |
| NBE UDP peer -> mock `Controller` | Unauthenticated peer reaches the request handler |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-bbw-01 | Elevation of Privilege | `pellmonsrv.copy_db`, rrd create | mitigate | Replace `os.system` string with `shutil.copy` and `subprocess.run(argv, check=True)`; no shell (Task 1) |
| T-bbw-02 | Tampering | `copy_db` concurrency | mitigate | Module-level `threading.Lock` acquired non-blocking, released in `finally` (Task 1) |
| T-bbw-03 | Spoofing | `Pellmonweb.auth.verify_password` | mitigate | Remove plaintext comparison; PBKDF2-only with error log pointing at `hash_password` (Task 2) |
| T-bbw-04 | Information Disclosure | PBKDF2 work factor | mitigate | Default iterations 100000 -> 600000, stored counts still honoured (Task 2) |
| T-bbw-05 | Information Disclosure | `server.socket_host = 0.0.0.0` | mitigate | Default `127.0.0.1`; opt in via `[conf] host` / `PELLMON_WEB_HOST`; Docker sets it explicitly (Task 3) |
| T-bbw-06 | Information Disclosure | session cookie theft / XSS | mitigate | `httponly=True`, `samesite='Lax'`, configurable `secure` (Task 3) |
| T-bbw-07 | Tampering | `pellmonconf.save` CSRF | mitigate | Same-origin `Origin`/`Referer` check before write; reject when absent (Task 3) |
| T-bbw-08 | Information Disclosure | `server.environment: 'debug'` | mitigate | Remove from `pellmonconf.py`; delete the commented line in `pellmonweb.py` (Task 3) |
| T-bbw-09 | Spoofing | NBE mock `Controller` pincode | mitigate | Restore the real check with `hmac.compare_digest` on stripped pincode (Task 1) |
| T-bbw-10 | Information Disclosure | `.env` secrets committed | mitigate | `.gitignore` `.env`, keep `!.env.example` (Task 1) |
| T-bbw-SC | Tampering | dependency installs | accept | This plan adds no new package-manager installs; stdlib only (`shutil`, `hmac`, `urllib.parse`) |
</threat_model>

<verification>
- `grep -rn "os.system" src/Pellmonsrv/pellmonsrv.py` -> no matches
- `grep -rn "server.environment" src/Pellmonweb/` -> no matches
- `grep -n "if True:" src/Pellmonsrv/plugins/nbecom/nbeprotocol/protocol.py` -> no matches
- `git check-ignore -v .env` succeeds; `git ls-files .env.example` still lists the file
- `python -m pytest tests/ -q --continue-on-collection-errors` -> no new failures/errors beyond the Task 0 baseline
- `python -m py_compile` clean on every touched `.py`
</verification>

<success_criteria>
- Review items 4, 5, 6, 7 and 8 each have a concrete code change and a corresponding test (or an explicit, justified note that the test cannot run on this Windows host).
- No plaintext password can authenticate to the web UI, and the user has been told in the SUMMARY exactly how to migrate their live `config/pellmon.conf`.
- Docker deployment still binds `0.0.0.0` via `PELLMON_WEB_HOST`; a bare local run binds `127.0.0.1`.
- Exactly three scoped commits, each listing explicit paths; no unrelated user-modified file was staged.
</success_criteria>

<output>
Create `.planning/quick/260919-bbw-fix-review-items-4-8-shell-calls-plainte/260919-bbw-SUMMARY.md` when done.
</output>
