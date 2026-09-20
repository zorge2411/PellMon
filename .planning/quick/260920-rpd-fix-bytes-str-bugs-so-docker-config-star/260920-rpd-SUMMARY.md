---
phase: quick-260920-rpd
plan: 01
status: complete
branch: fix/pi-startup-crashes
requirements: [PY3-RRD-01, PY3-RRD-02, DEPLOY-PI-01]
---

# Quick 260920-rpd: rrdtool bytes/str fixes for Docker/Pi startup

## Commits (branch fix/pi-startup-crashes, nothing pushed)

| Hash | Message |
|------|---------|
| e69ca7b | test: add failing bytes/str regression tests for rrdtool parsing |
| c058b31 | fix(pellmonsrv): decode rrdtool lastupdate and update output (call sites 1 and 2, one commit) |
| f8cff5f | fix(cleaning): decode rrdtool graph PRINT output before parsing total |
| 17cad41 | fix(consumption): decode rrdtool graph PRINT output before caching total |
| 2eaee23 | fix(silolevel): decode rrdtool last/xport output before parsing |
| 2c5e256 | fix(pellmonweb): decode rrdtool xport output in export endpoint |
| 8088b0d | test: realistic one-key-per-line rrdtool xport fixture |
| 069e4b9 | fix(pellmonsrv): missing optional plugin_dirs is debug, not an error traceback |

Deviation: the two pellmonsrv.py call sites (lastupdate, Poller) landed in one commit
(c058b31) because my revert-to-split step failed; the message was amended to describe both.

## Bugs fixed
- src/Pellmonsrv/pellmonsrv.py (MyDaemon.run, was ~567): `s.split('\n')` on bytes killed startup. Extracted `read_lastupdate()`, decodes, guards short output.
- src/Pellmonsrv/pellmonsrv.py Poller failed-update log (~299): bytes.rstrip(str) TypeError.
- plugins/cleaning/__init__.py:87 (masked, always returned '0'), plugins/consumption/__init__.py:223 (masked, returned None), plugins/silolevel/__init__.py:189,207 (re.sub on bytes), src/Pellmonweb/pellmonweb.py export() (re.sub on bytes).
- pellmonweb graph() left returning raw PNG bytes; comment added.
- pellmonsrv.py plugin_dirs: missing optional option logged a full ERROR traceback; now debug (NoOptionError).
- Plan inaccuracy: silolevel `int(b"1758300060\n")` works in py3 (int accepts bytes); only the xport re.sub path failed.
- Test fixture correction: rrdtool xport emits one key per line; the plan's fixture put keys mid-line, which the code's regex does not handle. Fixture made realistic.

## RED evidence (before fixes)
- read_lastupdate: `AttributeError: module 'Pellmonsrv.pellmonsrv' has no attribute 'read_lastupdate'` (4 tests)
- Poller: only 'error in polling' logged (TypeError swallowed), decoded stderr absent
- cleaning: `assert '0' == '123'`; consumption: TypeError swallowed, returned None
- silolevel / web export: `TypeError: cannot use a string pattern on a bytes-like object`

## Test numbers
- Baseline (WSL venv-wsl): 252 passed, 6 skipped
- After: 260 passed, 7 skipped (new web test skips: no dbus in venv-wsl)
- System python3 with PYTHONPATH=src:venv-wsl site-packages: 264 passed, 3 skipped (includes test_export_bytes.py and the dbus-gated tests)

## WSL dry run (script: session scratchpad dryrun2.sh, config under /tmp/dry2, outside repo)
Executed via Git Bash `wsl -d Debian -- bash ...` with MSYS_NO_PATHCONV=1 (PowerShell tool was unavailable in this session). rrdtool was present; nothing was apt-installed.
- Daemon liveness >= 30 s: VERIFIED (pellmonsrv ~43 s, pellmonweb ~36 s at the kill -0 check; pollinterval 5).
- `Activated plugins: ScotteCom, SiloLevel, Consumption, Cleaning`: VERIFIED.
- GetItem via dbus-send: VERIFIED. boiler_temp "57.9", power "68"; simulator baseline before daemon start was 58.3 / 64 (sim drifts; RRD row at the same time held 57.9 / 68, exactly matching). Exact equality with baseline not asserted.
- RRD created and updated: VERIFIED (rrd.db created at step 5; `rrdtool lastupdate` and info last_update advanced across 3 samples).
- Web root: VERIFIED 200 (public page; contains no password form, login form lives at /auth/login).
- Login: VERIFIED (POST /auth/login -> 303, session cookie, logout link present afterwards).
- Graph PNG: VERIFIED (200 image/png, magic bytes 211 P N G). /export also 200 with JSON.
- No `Traceback` in srv.log (empty; the daemon logs to var/log/pellmon.log) or web.log: VERIFIED. pellmon.log contains one traceback: raspberrygpio (disabled plugin) fails to import RPi off-Pi; see findings.
- Cleanup: no burner_sim/Pellmonsrv/Pellmonweb/session dbus-daemon left. pgrep only showed pre-existing system dbus-daemon (PID 183, systemd-activated, not spawned by me).

## Findings (not fixed)
1. First rrdtool update ~2 s after start fails once with `could not lock RRD`: race with the Cleaning/Consumption/SiloLevel `rrdtool graph` calls at activation. Transient, logged at INFO, later updates succeed. No retry exists.
2. plugins/silolevel/__init__.py:231 `range(len(data)/dec)` (float) and float indexing: TypeError once more than 50 points exist. On the /flotsilolevel path, outside the scoped path; needs `//`.
3. Loading disabled raspberrygpio off-Pi logs an ERROR with full traceback on every start (plugin loader, harmless on Pi).
4. Plan verify command used PowerShell; unavailable here.
5. Grep audit found no other unicode(), maketrans, iteritems, xrange, keys()[i] uses outside .py2bak.
6. Not exercised: SiloLevel/Consumption web JSON endpoints with real data, NBE, real hardware.
7. A system-reminder mid-run showed pellmonsrv.py's on-disk header as "GPL version 2" and other differences from what I edited; I did not investigate or touch it (my commits contain only my hunks).
