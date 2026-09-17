# Phase 2: Exception Visibility Retrofit - Context

**Gathered:** 2026-09-17
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase makes existing failures visible — it does NOT fix any underlying bugs (import breakage is Phase 3, protocol bugs are Phase 4, security is Phase 5). It is a purely observability change: replace bare `except:`/silent-swallow patterns with `except Exception:` + `logger.exception(...)` in the specific failure-critical paths named by ROADMAP.md, and replace ad hoc `print()` calls with proper logging across `src/`. Phase 1's test suite must produce byte-for-byte identical pass/fail results before and after this phase — only log output changes.

</domain>

<decisions>
## Implementation Decisions

### Logger naming convention
- **D-01:** Keep the existing shared `logger = getLogger('pellMon')` convention (per `.planning/codebase/CONVENTIONS.md` — all Pellmonsrv modules already share this one named logger) rather than switching to `__name__`-based per-module loggers. REQUIREMENTS.md's OBS-03 wording ("`logging.getLogger(__name__)` calls") is interpreted as directional guidance toward "use the `logging` module properly," not a literal mandate to fragment the logger namespace mid-migration — introducing per-module loggers would be a structural change with no observability benefit here and adds unnecessary risk to a "no logic altered" phase. New files without an existing convention (e.g. `daemon.py` if touched) also use `getLogger('pellMon')` for consistency.

### Bare-except sweep scope
- **D-02:** Scope OBS-01/OBS-02's bare-except → `logger.exception()` conversion to exactly the files ROADMAP.md's success criteria name: `src/Pellmonsrv/yapsy/PluginManager.py` (plugin load/activation, confirmed at lines 210, 274-281, 289 — this is the OBS-01 target and the root cause of ScotteCom/NBEcom failures being silently invisible), `src/Pellmonsrv/pellmonsrv.py`, `src/Pellmonsrv/plugins/calculate/__init__.py`. The remaining ~140+ bare/broad excepts elsewhere in `src/` (per CONCERNS.md's tech-debt audit) are explicitly OUT of scope for this phase — noted as a deferred idea, not silently dropped.
- **D-03:** Within `PluginManager.py`, convert line 210's bare `except:` (plugin descriptor parse failure — low severity, stays at `logger.debug` but with `logger.exception` for the traceback) and lines 274-281's plugin-load `except Exception as e: print(e)` block (the critical one — must become `logger.exception(...)` at `error` level, this is literally what makes "plugin activation failure hides real failures" visible). Line 289's bare `except:` (subclass-check probe inside a tight loop testing every symbol against every category) stays a narrow `except TypeError:` (the only exception `issubclass()` can raise for a non-class argument) rather than `except Exception:` + logging, since logging on every non-matching symbol in that inner loop would be extremely noisy and isn't a real failure — only exception types that indicate a hidden bug should be loud.

### Print-statement sweep boundary
- **D-04:** The OBS-03 print-statement sweep applies to `src/Pellmonsrv/` and `src/Pellmonweb/` runtime modules only (including the two `print()` calls already found in `PluginManager.py:275,279` as part of the OBS-01 fix above, and `database.py:113,170`'s `print(e)` fallback per CONVENTIONS.md's explicit callout of that inconsistency). Root-level tooling/CLI scripts (`test-imports.py`, `convert-to-py3.py`, `pellmoncli`/`src/pellmoncli.in` argparse output) are excluded as "intentional CLI output" per ROADMAP's own success-criteria wording.

### Exception logging call style
- **D-05:** Use `logger.exception(msg)` (not `logger.error(msg, exc_info=True)`) — matches ROADMAP.md's explicit wording ("via `logger.exception(...)`") and is idiomatic Python for logging inside an `except` block, since it implicitly captures `sys.exc_info()`.

### Claude's Discretion
- Exact log message wording for each converted except block (keep close to the existing `%`-formatted message where one exists, e.g. `'%s plugin error: %s'%(plugin_name, str(e))` at `pellmonsrv.py`, just route it through `logger.exception` instead of `logger.info`).
- Whether to keep `logger.info` calls for already-informational (non-error) log lines untouched — only bare/broad `except` blocks and stray `print()` calls are in scope, not a wholesale log-level audit.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Codebase map
- `.planning/codebase/CONCERNS.md` — full tech-debt audit of bare `except:` occurrences (148+ across `src/`) and the specific "plugin activation error handling hides real failures" fragile-area writeup that OBS-01 exists to fix
- `.planning/codebase/CONVENTIONS.md` — shared `getLogger('pellMon')` logger convention, `print(e)` fallback inconsistency in `database.py`, `%`-formatting log message style
- `.planning/codebase/ARCHITECTURE.md` — "Error Handling" section: plugin activation failures already caught individually per-plugin (`pellmonsrv.py:93-103`) so one broken plugin doesn't block others; this phase makes those catches loud, not different in control flow

### Project-level
- `.planning/PROJECT.md` — Core Value and Active requirements (this phase's OBS-* items)
- `.planning/REQUIREMENTS.md` — OBS-01, OBS-02, OBS-03 full requirement text
- `.planning/ROADMAP.md` — Phase 2 success criteria (authoritative acceptance bar; the "before/after identical test results" criterion is the primary safety check)
- `.planning/phases/01-test-harness-verification-infrastructure/01-VALIDATION.md` — the exact `pytest` commands (green baseline, full-truth run) this phase's before/after comparison must reproduce byte-for-byte identically except for log output

### Source files confirmed by direct read (this session)
- `src/Pellmonsrv/yapsy/PluginManager.py:208-212` (descriptor parse, bare `except:`), `:274-281` (plugin load/exec, `except Exception as e: print(e)` — the critical OBS-01 target), `:287-290` (subclass probe, bare `except:` inside a hot inner loop)
- `src/Pellmonsrv/pellmonsrv.py` — confirmed `except Exception as e:` pattern already dominant (lines 98, 127, 265, 267, 288, 326, 336) plus narrower `except AttributeError`/`except KeyError`/`except ValueError`/`except IOError` and one bare `except:` at line 256

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Phase 1's `tests/test_plugin_imports.py` and the broader `tests/` suite — the before/after comparison mechanism for this phase's primary safety check (ROADMAP success criterion 1). No new test infrastructure needed.
- Existing `logger = getLogger('pellMon')` instances already present in 15+ files (per CONVENTIONS.md) — the pattern to replicate, not invent.

### Established Patterns
- `except Exception as e:` + `logger.info('%s plugin error: %s'%(...))` is the dominant existing pattern in `pellmonsrv.py` — this phase's job is narrowly to (a) upgrade the bare/broad-`except:` outliers to at least `except Exception:`, and (b) upgrade the log call from `.info`/`.debug`/`print` to `.exception` in the specific files scoped above, not to rewrite every existing `except Exception as e:` block that's already reasonably visible.
- Debug-mode re-raise pattern already exists in `pellmonsrv.py` (`if conf.command == 'debug': raise else: logger.info(...)`) — worth preserving/mirroring in `PluginManager.py` if the executor finds it natural, but not a hard requirement.

### Integration Points
- `PluginManager.py`'s plugin-load exec block is the single most impactful change — it's the direct explanation for why ScotteCom/NBEcom's broken imports (confirmed in Phase 1's `known_broken`-marked tests) produce no operator-visible signal today. This phase does not fix those imports, but after this phase, running the daemon with those plugins enabled will log a full traceback instead of silently doing nothing.

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the decisions above — auto-mode discussion selected the recommended option for every gray area identified, grounded in direct reads of the actual source files.

</specifics>

<deferred>
## Deferred Ideas

- Full repo-wide bare-except sweep (~140+ remaining occurrences outside the 3 files named in ROADMAP.md) — explicitly out of scope for this phase (D-02); could become its own future phase or ongoing hardening task if desired.
- Wholesale log-level audit (fixing `logger.info` calls that should be `logger.warning`/`logger.error` per CONVENTIONS.md's callout) — only bare/broad excepts and stray prints are in scope here, not a general logging-level cleanup.

</deferred>

---

*Phase: 2-Exception Visibility Retrofit*
*Context gathered: 2026-09-17*
