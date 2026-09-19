# Phase 2: Exception Visibility Retrofit - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-17
**Phase:** 2-Exception Visibility Retrofit
**Areas discussed:** Logger naming convention, Bare-except sweep scope, Print-statement sweep boundary, Exception logging call style

**Mode:** `--auto` — all gray areas auto-selected, recommended option chosen for each without user prompts.

---

## Logger naming convention

| Option | Description | Selected |
|--------|-------------|----------|
| Keep shared `getLogger('pellMon')` | Matches existing convention across 15+ files, zero structural change | ✓ |
| Switch to `getLogger(__name__)` per module | Matches REQUIREMENTS.md's literal OBS-03 wording, but fragments logger config mid-migration | |

**Notes:** [auto] REQUIREMENTS.md wording treated as directional ("use the logging module"), not literal — codebase's established convention wins for a "no logic altered" phase.

---

## Bare-except sweep scope

| Option | Description | Selected |
|--------|-------------|----------|
| Targeted: PluginManager.py + pellmonsrv.py + calculate/__init__.py | Exactly matches ROADMAP.md's named files; small, verifiable blast radius | ✓ |
| Full repo sweep (~140+ occurrences) | Thorough but far exceeds this phase's stated scope and success criteria | |

**Notes:** [auto] Remaining bare excepts noted as a deferred idea, not silently dropped.

---

## Print-statement sweep boundary

| Option | Description | Selected |
|--------|-------------|----------|
| `src/Pellmonsrv/` + `src/Pellmonweb/` runtime modules only | Matches OBS-03's "outside intentional CLI output" carve-out | ✓ |
| Repo-wide including root tooling scripts | Would touch `test-imports.py`/`convert-to-py3.py`/`pellmoncli` which are legitimately CLI-facing | |

**Notes:** [auto] Includes `PluginManager.py:275,279` and `database.py:113,170`'s `print(e)` fallback, both confirmed by direct read.

---

## Exception logging call style

| Option | Description | Selected |
|--------|-------------|----------|
| `logger.exception(msg)` | Matches ROADMAP.md's literal wording; idiomatic for except-block use | ✓ |
| `logger.error(msg, exc_info=True)` | Equivalent effect, but not what ROADMAP.md specifies | |

**Notes:** [auto] Direct match to ROADMAP.md success criteria wording.

---

## Claude's Discretion

- Exact log message wording per converted except block (keep close to existing `%`-formatted messages where present).
- Whether to preserve/mirror the `debug`-mode re-raise pattern already in `pellmonsrv.py` when touching `PluginManager.py`.

## Deferred Ideas

- Full repo-wide bare-except sweep beyond the 3 ROADMAP-named files.
- Wholesale log-level audit (info → warning/error) beyond this phase's narrow scope.
