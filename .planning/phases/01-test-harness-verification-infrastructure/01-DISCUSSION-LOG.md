# Phase 1: Test Harness & Verification Infrastructure - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-17
**Phase:** 1-Test Harness & Verification Infrastructure
**Areas discussed:** Test layout & tooling, Import-check strategy, Hardware I/O isolation

**Mode:** `--auto` — all gray areas auto-selected, recommended option chosen for each without user prompts (per `workflow.discuss_mode` = "discuss" default flow, run in `--auto` single-pass mode).

---

## Test layout & tooling

| Option | Description | Selected |
|--------|-------------|----------|
| `tests/` mirroring `src/` | Standard pytest top-level layout, keeps `src/` as a clean install tree | ✓ |
| Tests colocated in `src/` | Tests live next to the modules they test | |

| Option | Description | Selected |
|--------|-------------|----------|
| New `requirements-dev.txt` | Test deps excluded from production Docker image | ✓ |
| Add to main `requirements.txt` | Single file, but bloats production image with test tooling | |

| Option | Description | Selected |
|--------|-------------|----------|
| New `pytest.ini` | No `pyproject.toml` exists in repo; simplest addition | ✓ |
| New `pyproject.toml` with `[tool.pytest.ini_options]` | Would introduce a new config file type for one purpose | |

**Notes:** [auto] Selected recommended defaults per pytest convention and the repo's existing `requirements.txt`/`requirements-wsl.txt` split precedent.

---

## Import-check strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Pytest test module discovering plugins via `.pellmon-plugin` descriptors | Runs in the same `pytest`/CI gate; no plugin list to hand-maintain | ✓ |
| Standalone script (extend `test-imports.py` in place) | Matches existing pattern but stays a separate, unintegrated check | |

**User's choice:** [auto] Pytest-based dynamic discovery (recommended — integrates with the single pytest/CI gate Phase 5 will wire up).
**Notes:** Existing `test-imports.py` is left as-is (out of phase scope to remove), just superseded as the source of truth.

---

## Hardware I/O isolation

| Option | Description | Selected |
|--------|-------------|----------|
| `pytest-socket --disable-socket` globally via `pytest.ini` | Any accidental real socket call fails loudly by default | ✓ |
| Opt-in per test | More flexible but risks silent real network calls in untouched tests | |

**User's choice:** [auto] Global `--disable-socket` (recommended — directly satisfies the phase's 4th success criterion).

---

## Claude's Discretion

- Exact test file naming/organization for Scotte/NBE protocol round-trip test content (actual bug-fix-verifying tests are Phase 4's job; this phase only needs the harness/fixtures demonstrated working).
- Location of shared `conftest.py` fixtures for mocked serial/UDP.

## Deferred Ideas

None — discussion stayed within phase scope.
