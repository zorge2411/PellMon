---
status: complete
quick_id: 260919-atb
commits: [6ca5c40, ee6d273, 02b748f]
---

# Quick 260919-atb: graph command injection, pellmonconf traversal, pellmoncli py3

- Task 1 (6ca5c40): new `src/Pellmonweb/rrdcommand.py` (stdlib-only `build_graph_command`, regex allowlists); `graph()` now uses argv + `shell=False`; dead string pre-formatting removed. 42 tests pass.
- Task 2 (ee6d273): `Pellmonconf._resolve()` allowlist on `self.dirs` plus realpath containment; `source()`/`save()` use it; `source()` returns the display name. Tests written but NOT runnable on this machine (see below).
- Task 3 (02b748f): `src/pellmoncli.in` ported (print calls, `input`, tab indent); compile gate test passes.

## Test results
- Baseline (before): 3 failed, 80 passed, 7 skipped, 6 errors (`--continue-on-collection-errors`).
- After: 3 failed, 127 passed, 7 skipped, 7 errors. Same 3 failures and 6 errors as baseline; the one added error is the new `test_pellmonconf_path_traversal.py`.
- Cause: `cherrypy` (and `Crypto`) are not installed in this Windows env, and importing `Pellmonweb.pellmonconf` runs `Pellmonweb/__init__` which needs cherrypy. Same reason `test_auth*.py` error at baseline. The rrdcommand test loads the module by file path so it runs anyway. Not installed by me.
- The pellmonconf logic was verified ad hoc with stubbed cherrypy/mako (traversal, absolute paths, None, '' rejected; allowed save/source work). The pytest module still needs a run where cherrypy is installed (WSL/CI).

## Deviations / notes
- Pre-existing quirk: `Pellmonconf.__init__` raises NoOptionError if `[conf] config_dir` is missing; test fixture supplies it. Not fixed (out of scope).
- `pellmonconf.py` and `pellmoncli.in` had small uncommitted user edits (shebang, `html.escape` import, etc.); committing those files with explicit paths included them. Noted in the commit messages.
- `graphtime += timespan/2` changed to `//2` so graphtime stays an int for the builder.
- LINE1 legend text is no longer wrapped in literal quotes (needed with shell=False).
- Not run: real rrdtool invocation (not available).
