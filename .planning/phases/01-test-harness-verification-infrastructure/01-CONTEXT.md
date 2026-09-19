# Phase 1: Test Harness & Verification Infrastructure - Context

**Gathered:** 2026-09-17
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase builds the hardware-free automated test infrastructure (pytest suite + broadened import-check) that every later phase in this migration depends on as its pass/fail signal. It does NOT fix any of the known bugs (import errors, bytes/str TypeError, plaintext logging, etc.) — those are Phases 2-5. This phase only makes it possible to *detect* them reliably and to verify future fixes.

</domain>

<decisions>
## Implementation Decisions

### Test layout & tooling
- **D-01:** New top-level `tests/` directory mirroring `src/` package structure (e.g. `tests/Pellmonsrv/test_database.py`, `tests/Pellmonweb/test_auth.py`), not tests colocated inside `src/`. Standard pytest convention; keeps `src/` clean for the Autotools/Docker packaging that already treats it as the install tree.
- **D-02:** Test dependencies (`pytest`, `pytest-mock`, `pytest-socket`, `pytest-cov`) go in a new `requirements-dev.txt`, not the main `requirements.txt`. Keeps the production Docker image (`Dockerfile` installs from `requirements.txt`) lean — matches the existing `requirements.txt` / `requirements-wsl.txt` split pattern already used in this repo.
- **D-03:** Pytest config lives in a new `pytest.ini` at repo root (no `pyproject.toml` exists in this repo, so no reason to introduce one just for pytest config).

### Import-check strategy
- **D-04:** The broadened import-check (TEST-02) is a proper pytest test module (`tests/test_plugin_imports.py`), not a standalone script. It dynamically discovers plugins by reading every `src/Pellmonsrv/plugins/*.pellmon-plugin` descriptor file (INI format, `[Core] Module = <name>`) and asserts each corresponding plugin module imports without error — this way it runs as part of the same `pytest` invocation and the same CI gate as everything else, with no separate script to maintain. The existing root `test-imports.py` can stay as-is (it's out of this phase's scope to remove it) but is superseded as the source of truth by the new pytest-based check.

### Hardware I/O isolation
- **D-05:** `pytest-socket` is enabled globally via `addopts = --disable-socket` in `pytest.ini`, so any test that makes a real (unmocked) network call fails loudly by default (satisfies the phase's 4th success criterion). Tests that need mocked serial I/O use pyserial's own `loop://` URL handler (no extra dependency); tests that need mocked UDP use `unittest.mock`/`pytest-mock` — no real socket is opened even for tests, so `--disable-socket` stays on with no per-test opt-outs expected in this phase.

### Claude's Discretion
- Exact test file naming/organization within `tests/Pellmonsrv/plugins/` for the Scotte and NBE protocol round-trip tests (deferred to planning/execution — Phase 4 is where the actual protocol round-trip test *content* gets written against real bug fixes; this phase only needs the harness and mock fixtures to exist and be demonstrated working, e.g. via a smoke-level round-trip test).
- Whether `conftest.py` fixtures for mocked serial/UDP live at `tests/conftest.py` (shared) or a more scoped location — planner/executor can decide based on how many test modules end up needing them.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Codebase map
- `.planning/codebase/STACK.md` — current dependency/tooling state, confirms no test framework or lockfile exists today
- `.planning/codebase/STRUCTURE.md` — directory layout; `src/Pellmonsrv/plugins/*.pellmon-plugin` descriptor format for plugin discovery
- `.planning/codebase/CONCERNS.md` — full detail on the "migration complete" false-confidence issue and the specific bugs this test harness needs to be able to catch

### Research (this milestone)
- `.planning/research/STACK.md` — pytest + pytest-mock + pytest-socket + pytest-cov recommendation, pyserial `loop://` for serial mocking, mypy/ruff notes (mypy/ruff are NOT in this phase's scope — Phase 2/3 territory, noted here only as context)
- `.planning/research/PITFALLS.md` — "imports cleanly ≠ ported" false-confidence trap; this phase exists specifically to close that gap
- `.planning/research/SUMMARY.md` — overall phase-dependency rationale (why test harness must come first)

### Project-level
- `.planning/PROJECT.md` — Core Value and Active requirements
- `.planning/REQUIREMENTS.md` — TEST-01, TEST-02, TEST-03 full requirement text
- `.planning/ROADMAP.md` — Phase 1 success criteria (authoritative acceptance bar for this phase)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `test-imports.py` (repo root) — existing ad hoc smoke script; shows the 4 core modules that already import cleanly (`Pellmonsrv.pellmonsrv`, `Pellmonsrv.database`, `Pellmonweb.pellmonweb`, `Pellmonweb.pellmonconf`). New pytest-based import-check should cover at least this same set plus every plugin.
- `src/Pellmonsrv/plugins/*.pellmon-plugin` — INI-format descriptor files already enumerate every plugin and its module name; this is the enumeration source for the dynamic import-check, no need to hardcode a plugin list.
- `pyserial>=3.5` (already a pinned dependency in `requirements.txt`) — ships `serial.serial_for_url('loop://')`, PySerial's own supported test/loopback mechanism.

### Established Patterns
- Two-file requirements split (`requirements.txt` / `requirements-wsl.txt`) — precedent for adding `requirements-dev.txt` as a third, non-production file.
- `config/pellmon.conf` / `conf.d/*.conf` parsed via `configparser` — the `.pellmon-plugin` descriptor files use the same INI format, so `configparser` is the natural way to parse them for plugin discovery in the import-check.

### Integration Points
- None yet — this phase is additive-only (new `tests/`, `pytest.ini`, `requirements-dev.txt`); it does not modify `src/` at all.

</code_context>

<specifics>
## Specific Ideas

No specific requirements beyond the decisions above — auto-mode discussion selected the recommended option for every gray area identified. Open to standard pytest conventions throughout.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (mypy/ruff adoption, CI wiring, and actual protocol bug fixes are already scoped to their own later phases per ROADMAP.md and were not re-litigated here.)

</deferred>

---

*Phase: 1-Test Harness & Verification Infrastructure*
*Context gathered: 2026-09-17*
