# Pitfalls Research

**Domain:** Finishing a Python 2→3 migration on a hardware-protocol daemon (manual byte/string frame packing, XTEA-encrypted UDP protocol, serial protocol, dynamic plugin loader, bare-except-heavy codebase)
**Researched:** 2026-09-17
**Confidence:** HIGH (codebase findings are static-analysis-verified against this exact repo; general Python 2/3 porting pitfalls are HIGH confidence per official porting docs; process-ordering recommendations are MEDIUM, synthesized from general test/legacy-code practice)

## Critical Pitfalls

### Pitfall 1: "It Imports" Is Treated As "It Works"

**What goes wrong:**
A migration is declared complete because a smoke script successfully imports the top-level modules. The actual protocol/plugin code — which is loaded dynamically at runtime by a plugin manager, not at module import time — is never exercised, and the most bug-dense code (byte/string boundary logic) ships broken. This is not hypothetical here: `test-imports.py` imports 4 modules; it never imports `Scotteprotocol`, `nbeprotocol`, `scottecom`, or `nbecom`, and both of those plugin packages are confirmed broken by `ModuleNotFoundError` at activation time (per `.planning/codebase/CONCERNS.md`).

**Why it happens:**
Import success is cheap to check and produces a clean pass/fail signal, so it gets used as a stand-in for "the port works." But Python's import statement only exercises module-level code (top-level assignments, class/def statements, decorator evaluation) — it does not execute function bodies, so a `TypeError` from bytes/str mixing inside `Proxy.get()` or a `NameError` from a leftover `unicode()` call is invisible until that specific code path runs.

**How to avoid:**
Never treat "imports cleanly" as a completion signal for plugin/protocol code. Define "ported" per plugin as: imports cleanly AND has at least one executed test that calls its core methods (`activate()`, frame encode/decode, `getItem`/`setItem`) with mocked I/O. Extend or replace `test-imports.py` to import every plugin package (with dummy config), not just the four top-level modules already covered.

**Warning signs:**
- A "migration complete" claim (commit message or doc) that cites only an import-check script as evidence.
- Plugin `__init__.py` files with `sys.path.append` shims that mask import errors in unrelated peer directories (as scottecom's does — it fixes its own directory but not the separate `Scotteprotocol` package's internal imports).
- Zero references to `nbecom`, `scottecom`, `Scotteprotocol`, or `nbeprotocol` in the test/verification script.

**Phase to address:**
Should be the first phase — before any further "fix and move on" work — establish a verification harness (mocked serial/UDP) that actually exercises plugin activation and protocol round-trips, so every subsequent bug-fix phase has a real pass/fail signal instead of relying on manual inspection.

---

### Pitfall 2: Mechanical `str`↔`bytes` Substitution Instead of Semantic Reasoning

**What goes wrong:**
In Python 2, `str` was simultaneously "text" and "bytes" — `.encode()`/`.decode()` were nearly no-ops for ASCII data and code was routinely sloppy about which one it meant. A mechanical port (adding `.encode()`/`.decode()` calls to make old code "just work") produces exactly the class of bug already found here: `response.payload.encode('ascii').split('=', 1)[1]` in `nbeprotocol/protocol.py:144` — `payload` is already a `str` (decoded at `frames.py:176`), so encoding it to `bytes` and then splitting on a `str` separator (`'='`) raises `TypeError` in Python 3, because Python 3 refuses to silently mix `bytes` and `str` the way Python 2 did.

**Why it happens:**
The `.py2bak` diff signature for this codebase shows a "convert line, keep pattern" porting style (`Queue`→`queue`, `file()`→`open()`, etc.) rather than "understand what the data actually is." For manual binary frame packing (checksums, fixed-width headers, XTEA payloads) this pattern is dangerous because the *same variable* is sometimes bytes (raw wire data) and sometimes str (post-decode) at different points, and Python 2's implicit coercion hid every place that was ambiguous.

**How to avoid:**
For every protocol module (`Scotteprotocol/`, `nbeprotocol/`), do a line-by-line audit of each variable's type at each stage: raw socket/serial read → `bytes`; after `.decode()` → `str`; before `.encode()`/`socket.send()`/`serial.write()` → must be `bytes` again. Do not add `.encode()`/`.decode()` calls to "make an error go away" without tracing where the value came from. Treat every `%`-formatted frame-building line and every checksum/XTEA byte-math line as suspect, since these mix arithmetic on bytes/integers with string formatting that behaved permissively in Python 2.

**Warning signs:**
- Any line mixing `.encode()`/`.decode()` with `%`-formatting in the same expression.
- `TypeError: a bytes-like object is required, not 'str'` (or the reverse) at runtime — this is the signature error for this bug class, not a corner case.
- Checksum/XTEA code indexing into `bytes` expecting a one-character `str` result (Python 2 behavior) instead of an `int` (Python 3 behavior) — e.g. `some_bytes[i]` used where `chr(some_bytes[i])` or `bytes([some_bytes[i]])` is actually needed.
- `ord()` calls on values that are already `int` in Python 3 (harmless but a signal the code wasn't re-reasoned, just patched).

**Phase to address:**
Dedicated phase for protocol module hardening (Scotteprotocol + nbeprotocol), gated behind the mocked-I/O test harness from Pitfall 1 so each fix can be verified by a round-trip encode/decode test using captured or synthetic frame byte sequences, not by re-reading the code and hoping.

---

### Pitfall 3: Bare `except:` Turns Every New Regression Into Silence

**What goes wrong:**
The codebase has ~148+ bare `except:` / broad `except Exception:` occurrences, concentrated exactly in the modules being actively fixed (`pellmonsrv.py`: 27, `Scotteprotocol/protocol.py`: 19). If bug-fixing work proceeds *before* these are addressed, a fix that introduces a new bug (e.g., an off-by-one in a checksum, a wrong byte order) will be caught by the same bare `except:` that hid the original bug — the plugin will just silently "not work" again, with no new information gained. This already happened once: the `unicode()` `NameError` in the Calculate plugin is caught by an adjacent `except Exception as e:` that logs at `info` level and returns the sentinel string `'error'`, masking the root cause (per CONCERNS.md).

**Why it happens:**
Broad excepts were originally added for legitimate best-effort/non-fatal fallback behavior (e.g., "if this optional plugin item lookup fails, skip it"). During a migration, that same swallowing behavior hides the ported code's genuine breakage, and it will just as effectively hide the *next* round of bugs introduced while fixing the first round — so "fix bugs, then verify" produces false-negative verification.

**How to avoid:**
Add error visibility (convert bare `except:` to `except Exception:` + `logger.exception(...)`) as an early, low-risk phase — before or in the same phase as the protocol bug fixes, not after. This is a mechanical, behavior-preserving change (it doesn't alter control flow, only adds logging) and is safe to do first. Doing it first means every subsequent bug-fix attempt gets immediate, visible feedback (a traceback in the log) instead of a silent `'error'` return, which is the entire point of finishing the migration correctly rather than repeating the original mistake.

**Warning signs:**
- A bug fix "resolves" an issue and the plugin still doesn't produce data — check whether a bare/broad except is silently absorbing a *different* exception than the one intended to be fixed.
- Log output at `info` level for what are actually plugin activation failures (this codebase's existing convention per CONVENTIONS.md: `logger.info('%s plugin error: %s'...)` — an anti-pattern to not propagate further into new code).
- Plugin manager (`yapsy/PluginManager.py`) logging plugin load failures tersely or not at all, so "the server started fine" is consistent with a configured plugin never having activated.

**Phase to address:**
Should be sequenced first or in parallel with the protocol fixes — specifically: fix plugin-loading and protocol-parsing bare excepts *before* or *simultaneously with* fixing the underlying `TypeError`/`NameError` bugs, so each subsequent fix has a working feedback loop. See "Safest Order of Operations" below for full sequencing rationale.

---

### Pitfall 4: Dynamic Plugin Loader Swallows Import Failures As "Plugin Just Not Available"

**What goes wrong:**
Because plugins are discovered and imported dynamically by `yapsy` at runtime (not statically at the top of `pellmonsrv.py`), an import failure inside a plugin package doesn't crash the server — it typically results in the plugin being silently skipped, with the server continuing to run and reporting nothing obviously wrong. Combined with Pitfall 3, a broken plugin can persist through multiple "migration complete" claims because there is no loud failure mode to notice; the daemon looks healthy, D-Bus is up, the web UI loads, but the ScotteCom/NBEcom items are simply absent from the item list.

**Why it happens:**
Plugin systems are deliberately designed to be fault-isolating (one broken plugin shouldn't take down the whole daemon) — but that same design goal, taken to its current implementation in this codebase, removed the developer's ability to *notice* the isolation happened. There's a difference between "isolate the failure so the daemon survives" and "isolate the failure so nobody ever sees it," and this codebase currently does the latter.

**How to avoid:**
When touching `yapsy/PluginManager.py`'s plugin activation/import path, add `logger.exception()` (not `logger.info()`) at every point a plugin's import or `activate()` call fails, and ensure that failure is visible in a way an operator/developer would actually see it (server log at `ERROR` level, plus ideally a startup summary listing "N plugins configured, M activated successfully, plugins X/Y failed: reasons"). Fault isolation should mean "the daemon survives and tells you loudly," not "the daemon survives and says nothing."

**Warning signs:**
- Enabling a plugin in `config/pellmon.conf` and the corresponding sensor/burner data simply never appears, with no corresponding ERROR/WARNING in logs.
- Plugin activation wrapped in a bare `except:` with no logging call inside it at all (worse than logging at the wrong level).

**Phase to address:**
Same phase as Pitfall 3 (error-visibility retrofit) — this is really the plugin-manager-specific instance of the general bare-except problem, and should be fixed alongside it, before the protocol-level bug-fixing phase relies on "the server ran without errors" as any kind of signal.

---

### Pitfall 5: Retrofitting Logging Changes Test/Verification Behavior Mid-Stream, Masking Which Fix Did What

**What goes wrong:**
If exception logging is added *while simultaneously* fixing protocol bugs in the same commit/phase, it becomes impossible to tell whether a given log line newly appearing is (a) a pre-existing silent failure now made visible, or (b) a new regression introduced by the same change. This muddies the verification signal exactly when it's most needed.

**Why it happens:**
It's tempting to "clean up as you go" — add a `logger.exception()` right where you're already editing a function to fix a bug. But this conflates two different kinds of change (behavior-preserving observability change vs. behavior-changing bug fix) into one diff, making it hard to bisect regressions later.

**How to avoid:**
Sequence as two distinct, separately-verifiable phases:
1. **Observability phase (do first):** Convert bare/broad excepts to `except Exception:` + `logger.exception(...)` with *zero other behavior changes*. Run the existing (or newly extended) import/activation test harness before and after — the set of "plugins that activate successfully" must be identical before and after this phase; only the log output should change. This proves the logging retrofit itself introduced no regressions and establishes a trustworthy signal for phase 2.
2. **Bug-fix phase (do second):** Fix the actual `TypeError`/`NameError`/import bugs, using the now-visible tracebacks from phase 1 as the primary diagnostic tool, and the mocked protocol round-trip tests (Pitfall 1) as the pass/fail gate.

Do not interleave "fix a bug" and "add logging to the function I'm touching" in the same commit for the protocol modules — the bare-except cleanup should land as its own reviewable, low-risk changeset first.

**Warning signs:**
- A single commit/PR diff that both changes `except:` to `except Exception as e: logger.exception(...)` AND changes the logic inside the try block.
- Inability to answer "was this exception happening before my change?" during code review.

**Phase to address:**
Enforce this ordering at the roadmap level: one phase (or at minimum one clearly separated set of commits) for exception-visibility retrofit, verified against the unchanged plugin-activation baseline, strictly before the phase that fixes the underlying protocol bugs.

---

### Pitfall 6: Trusting the `.py2bak` Diff As Proof of Correctness

**What goes wrong:**
Because `.py2bak` files preserve the pre-migration Python 2 source, it's tempting to treat "the diff against `.py2bak` looks like a standard, known-safe migration pattern" (e.g., `Queue`→`queue`, `except X, e:`→`except X as e:`) as sufficient evidence the port is correct. But the confirmed bugs in this codebase (`unicode()` leftover, bytes/str split `TypeError`, unbuffered text I/O) show that some lines were migrated using the wrong pattern, or not touched at all when they should have been, and a diff review alone did not catch it — these bugs shipped in the "porting complete" commit.

**Why it happens:**
Diff review against a known-pattern list is good at catching "did you forget to update this line" but bad at catching "you updated it, but the semantics are subtly wrong" (e.g., `buffering=0` staying in `'a+'` text mode instead of switching to binary mode, per `daemon.py:69` — this is a case where *nothing* about the diff looks wrong at a glance, because `open()` replacing `file()` is exactly the expected pattern, but the mode argument's now-illegal combination was missed).

**How to avoid:**
Use `.py2bak` diffs as a starting point for locating *what changed*, never as proof that a change is *correct*. Correctness proof requires either running the code path or a targeted unit test. Once a module's `.py` is confirmed correct via actual execution (not just diff review), delete its `.py2bak` per the existing project convention — don't let stale `.py2bak` files linger as false reassurance after the real verification (test execution) has happened.

**Warning signs:**
- A module's port is considered "done" based solely on someone reading the `.py2bak`→`.py` diff.
- `.py2bak` files still present for modules that have already been execution-verified (should have been deleted per project convention — their continued presence is itself a signal the module hasn't actually been confirmed).

**Phase to address:**
Applies across all phases touching migrated code — treat as a review-process rule, not a single phase. Codify as a completion gate: "a module's Python 3 port is done" requires an executed test, not a diff read.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Leave bare `except:` in non-critical, cosmetic paths (e.g., UI formatting fallbacks) while fixing critical paths (plugin loading, protocol parsing) first | Faster delivery of the visible fixes | Some silent failures remain outside the hardened paths | Acceptable for this milestone — explicitly scoped to "most failure-critical paths" per PROJECT.md; document which excepts were deliberately left alone and why |
| Verify protocol fixes only via mocked I/O, not physical hardware | Unblocks work without needing a burner on hand | Genuine hardware quirks (serial timing, real XTEA key exchange behavior, actual UDP broadcast responses) remain unverified | Acceptable given PROJECT.md constraint that hardware isn't available; must be flagged in docs as "unit-verified, not hardware-verified" so it isn't later mistaken for full verification |
| Keep `sys.path.append` shims in some plugin `__init__.py` files rather than converting every plugin to explicit relative imports in one pass | Smaller, faster diffs per plugin fixed | Reintroduces the exact import-shadowing risk (duplicate `frames`/`protocol` module names across packages) that caused the original ScotteCom/NBEcom breakage | Never acceptable long-term for the two protocol packages already flagged (`Scotteprotocol`, `nbeprotocol`) — these must convert to explicit relative imports; acceptable short-term only for plugins not currently broken and not touched this milestone |
| Ship the exception-logging retrofit without also adding structured/leveled logging (still using `logger.info` for what are really errors) | Faster to land, matches existing style | Log noise makes it hard to distinguish real errors from routine info in ops, undermining the whole point of the retrofit | Acceptable only as an interim step if leveled logging is a fast, immediate follow-up — not acceptable as a permanent end state given this milestone's explicit goal of making failures visible |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| yapsy dynamic plugin loading | Assuming "server started, no crash" means all configured plugins activated | Add and check an explicit activation summary/log; treat plugin activation as a first-class thing to verify, not an implicit side effect of server startup |
| NBE UDP protocol with XTEA encryption | Treating decrypted/decoded payload as reusable in both `bytes` and `str` form interchangeably (source of the confirmed `protocol.py:144/146` bug) | Pin down the type contract per function boundary: decode once at the frame-parsing boundary, keep everything downstream as `str` (or `bytes`, pick one) consistently; encode only immediately before `socket.send()` |
| Scotte serial protocol | Assuming `pyserial`'s Python 3 API behaves identically to Python 2 usage patterns for byte-level `.read()`/`.write()` (Python 3 pyserial returns `bytes`, not `str`) | Audit every `self.ser.read(...)`/`self.ser.write(...)` call site in `Scotteprotocol/protocol.py` for what type it now produces/expects, not just whether the call itself still runs |
| Plugin config (`config/pellmon.conf`) enabling hardware plugins | Testing only with plugins disabled (avoiding the broken ones) and calling that "the server works" | Explicitly test with `ScotteCom = yes` and `NBEcom = yes` (the latter is enabled by default) using mocked I/O, since these are exactly the paths known to be broken |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging full request/credential data in exception handlers added during the visibility retrofit | Turning "swallowed silently" into "logged in plaintext" for the password-logging bug already present (`auth.py:147,150`) | When adding `logger.exception()`/`logger.error()` broadly, explicitly exclude or redact credential-bearing variables; don't let the blanket "add logging everywhere" pass also amplify the existing plaintext password logging issue — fix that specific line, don't just leave it now MORE visible in logs |
| Treating `shell=True` Exec plugin path as low-risk because "it's just for the migration, fix it later" | Shell injection surface persists into the "production-ready" milestone deliverable | Fix alongside other exec-plugin touches in this milestone, using the `shell=False` pattern already proven in the same file's writescript path |

## "Looks Done But Isn't" Checklist

- [ ] **"Migration complete" commit/doc claims:** Often mean "core modules import" — verify by checking whether the test script actually imports and exercises every plugin package, not just top-level daemon modules.
- [ ] **Plugin "supports X protocol":** Often means "the plugin file exists and has the right class shape" — verify by actually calling `activate()` with mocked I/O and confirming it returns real data, not just that instantiation didn't throw.
- [ ] **"Bare excepts replaced with proper handling":** Often means only the most obviously broken few were touched — verify by grepping the actual count of remaining bare `except:` in the specific files touched this milestone (pellmonsrv.py, Scotteprotocol/protocol.py, plugin __init__.py files) and confirming it matches what was scoped.
- [ ] **"Byte/string bug fixed":** Often means the one reported symptom (e.g. the `TypeError` at line 144) was patched — verify by checking adjacent lines in the same function/module for the same `.encode()`+`%`-format or split-on-wrong-type pattern, since these bugs cluster.
- [ ] **"Server starts successfully":** Often means D-Bus/CherryPy came up — verify plugin activation counts/logs separately; a running server with zero active hardware plugins is not "done."
- [ ] **".py2bak removed":** Often done prematurely based on diff review alone — verify the corresponding `.py` module has an executed (not just read) test passing before deleting its backup.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|------------------|
| Discovering a bare except hid a new regression after both changes were combined in one commit | MEDIUM | Bisect using the mocked-I/O test harness; if impossible to isolate cleanly, revert the combined commit and re-apply as two separate commits (logging first, then bug fix), re-verifying the plugin-activation baseline between them |
| A "fixed" protocol module still fails against real hardware despite passing mocked tests | MEDIUM-HIGH | Capture the actual failing byte sequence from a hardware session (serial capture / UDP packet capture) and add it as a new regression fixture to the mocked test suite, rather than debugging live against hardware repeatedly |
| `.py2bak` deleted prematurely and a regression needs the original Python 2 behavior for reference | LOW | Recover from git history (`git log --follow`, `git show <pre-migration-commit>:path`) — the file was tracked in git before deletion, so history is not actually lost |
| Plugin silently not activating in production after deployment despite passing dev-time mocked tests | MEDIUM | With the visibility retrofit in place, check server logs for the now-surfaced `logger.exception()` output first; if visibility work wasn't done yet, that itself is the root cause to fix before debugging further |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|---------------|
| "It imports" false confidence | Phase 1: Build mocked-I/O plugin activation + protocol round-trip test harness | Harness imports and activates every plugin package (including ScotteCom, NBEcom) with mocked serial/UDP, not just the 4 top-level modules |
| Bare `except:` silencing regressions | Phase 2 (before/alongside protocol fixes): Exception-visibility retrofit in plugin loading + protocol parsing paths | Re-run Phase 1 harness before/after the retrofit — activation results must be identical; only log output changes |
| Dynamic plugin loader swallowing import failures | Same as above (Phase 2) — yapsy `PluginManager.py` specifically | Deliberately break a plugin import and confirm an ERROR-level log line appears, not just silence |
| Mechanical bytes/str substitution bugs | Phase 3: Protocol module hardening (Scotteprotocol, nbeprotocol) | Round-trip encode/decode unit tests per frame type pass; the confirmed `protocol.py:144/146` bug and its siblings are fixed and covered |
| Interleaving observability and bug-fix changes | Enforced across Phase 2 vs Phase 3 boundary | Phase 2 and Phase 3 land as separable commit sets/PRs; Phase 2 has zero logic changes, only exception handling |
| Trusting `.py2bak` diffs as correctness proof | Ongoing completion-gate rule, all phases | Definition of done for any migrated module requires an executed test result, not a diff review note |
| Security issues (plaintext password logging, shell injection) getting masked/amplified by the visibility retrofit | Phase 2 (explicitly scoped exclusion) + dedicated security fix in same or adjacent phase | Confirm no credential values appear in new `logger.exception()` output; confirm Exec plugin uses `shell=False` |

## Sources

- `.planning/codebase/CONCERNS.md` (this repo, static-analysis-verified confirmed bugs — ScotteCom/NBEcom broken imports, bytes/str `TypeError`, `unicode()` leftover, unbuffered text I/O crash, bare-except counts, plugin manager fragility) — HIGH confidence, primary source
- `.planning/codebase/CONVENTIONS.md` (this repo — migration diff signature, error-handling/logging conventions) — HIGH confidence, primary source
- `.planning/PROJECT.md` (this repo — active requirements, scope, constraints) — HIGH confidence, primary source
- [Common migration problems — Supporting Python 3: An in-depth guide](http://python3porting.com/problems.html) — MEDIUM/HIGH confidence, official-adjacent porting reference on str/bytes separation
- [struct — Interpret bytes as packed binary data — Python 3 documentation](https://docs.python.org/3/library/struct.html) — HIGH confidence, official docs
- [Strings — Conservative Python 3 Porting Guide](https://portingguide.readthedocs.io/en/latest/strings.html) — MEDIUM confidence, community porting guide, corroborates str/bytes mixing prohibition
- [Python 3 Pitfalls (obspy wiki)](https://github.com/obspy/obspy/wiki/Python-3-Pitfalls) — MEDIUM confidence, real-world scientific/protocol-adjacent porting experience
- General knowledge of test-ordering/legacy-refactoring practice (characterization-testing-before-refactoring principle) applied to this codebase's specific situation — MEDIUM confidence, standard practice reasoning rather than a single authoritative source

---
*Pitfalls research for: Python 2→3 migration completion, hardware-protocol daemon domain*
*Researched: 2026-09-17*
