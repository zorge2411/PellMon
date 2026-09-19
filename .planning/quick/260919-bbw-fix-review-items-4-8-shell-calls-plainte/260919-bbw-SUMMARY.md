---
phase: quick-260919-bbw
plan: 01
status: complete
requirements: [REVIEW-04, REVIEW-05, REVIEW-06, REVIEW-07, REVIEW-08]
commits: [124159d, 510e158, 67778a7]
---

# Quick 260919-bbw: Review items 4-8 Summary

Removed shell-string execution and the globals() flag from the daemon, dropped plaintext web passwords (PBKDF2 only, 600000 iterations), hardened web/conf servers (localhost bind, cookie flags, same-origin CSRF check, no debug env), git-ignored `.env`, and fixed the NBE mock pincode check.

## ACTION REQUIRED: migrate your config/pellmon.conf password

**Plaintext passwords are no longer accepted.** Your live `config/pellmon.conf` (git-ignored, deliberately not edited) still has a plaintext password in `[authentication]`. After this change you cannot log in until you replace it with a hash. Generate one (from the repo `src` directory or with Pellmonweb on PYTHONPATH):

```
python3 -c "from Pellmonweb.auth import hash_password; print(hash_password('yourpassword'))"
```

Then set the line to `username = pbkdf2:sha256:600000$<salt>$<hash>` and restart pellmonweb. Existing hashes at 100000 iterations keep working. If no `[authentication]` section exists, all logins are rejected (the old `testuser/12345` default is gone).

Also note: pellmonweb now binds 127.0.0.1 by default. Bare-metal setups that need LAN access must set `[conf] host = 0.0.0.0` or `PELLMON_WEB_HOST=0.0.0.0`. Docker sets it via docker-compose.

## Commits
- 124159d: shutil/argv, `_copy_lock`, NBE pincode, `.gitignore`
- 510e158: PBKDF2-only auth, 600000 iterations, samples/docs
- 67778a7: bind host, cookie flags, conf CSRF, debug removal

## Changes
- `copy_db`: `shutil.copy` under a module-level non-blocking lock, `logger.exception` on failure; rrd create is `subprocess.run(conf.RrdCreateCommand, check=True)` (argv list; `RrdCreateString` kept as joined string for logs). No `os.system` remains in pellmonsrv.py.
- NBE mock `Controller.run()`: real pincode check (`hmac.compare_digest` on stripped values), `print` replaced by `logger.debug`; removed the Controller exemption from `tests/test_no_ad_hoc_print.py`.
- auth: `PBKDF2_ITERATIONS = 600000`, plaintext branch removed (error log naming `hash_password`, returns False), legacy-warning blocks removed.
- pellmonweb: `_resolve_socket_host` ([conf] host > PELLMON_WEB_HOST > 127.0.0.1), bind address logged, `httponly`, `samesite: Lax`, `secure` from `[conf] session_cookie_secure` (default False). CherryPy samesite support could not be checked locally (cherrypy not installed); it is set as planned.
- pellmonconf: `_check_same_origin()` (Origin, else Referer, vs Host; absent = reject) before save; default host 127.0.0.1; `server.environment: debug` removed.
- Samples/docs updated: `webinterface.conf.in`, `pellmon.conf.example`, `README.md`, `docker-compose.yml`, `.env.example`. `DOCKER.md` has no credential guidance (not edited).

## Deviations
- **[Rule 1] Pre-existing bug:** `config.__init__` referenced Python 2 `ConfigParser.NoSectionError` (NameError whenever `plugin_settings` section is absent). Fixed to `configparser`. Found because the new rrd test hit it.
- **[Rule 3] Existing test updated:** `test_save_allowed` in `test_pellmonconf_path_traversal.py` now sends Origin/Host headers, since save() requires them.
- `.env.example` was untracked (never committed), so `!.env.example` had nothing to keep tracked. I committed it with the PELLMON_WEB_HOST addition. `.env` is now ignored and untouched.
- None of the committed files had prior uncommitted user edits; unrelated modified files were not staged.
- Note: pre-existing latent bug seen, not fixed (out of scope): if `[rrd_ds_types]` section is absent, `rrd_ds_types` is unbound and polling silently turns off.

## Tests
Baseline (before): `3 failed, 127 passed, 7 skipped, 7 errors` (failures: test_plugin_imports nbecom deferred import, Pellmonweb.pellmonweb, Pellmonweb.pellmonconf; errors: cherrypy/Crypto missing on Windows).
After: `3 failed, 136 passed, 9 skipped, 11 errors`. Same 3 failures; no new failures. The 4 additional errors are the new CSRF tests in `test_pellmonconf_csrf.py` needing cherrypy at import.

Could not run on Windows (cherrypy/Crypto not installed):
- `test_pellmonconf_csrf.py` 4 save() tests (the 4 new errors); `test_auth.py`, `test_auth_security.py`, `test_pellmonconf_path_traversal.py` (already erroring at baseline, edited but unrun).
- 2 NBE Controller pincode tests in `test_db_copy.py` (skipped via importorskip("Crypto")).
- Substitute checks: with cherrypy/mako stubbed, hash/verify (600000 default, 100000 hash verifies, plaintext rejected) and `_check_same_origin` (cross-origin False, same-origin True, absent False) were verified ad hoc.
- Ran and passed locally: copy_db store/restore/failure/reentrancy, RrdCreateCommand argv, no-os.system, host resolver (3), no-debug-environment, no-ad-hoc-print sweep.
- Should be run on WSL/Linux with deps installed.

## Self-Check: PASSED
Commits 124159d, 510e158, 67778a7 exist; SUMMARY written; STATE.md not modified per instruction.
