---
phase: quick-260919-d5l
plan: 01
status: complete
requirements: [CI-FIX-01]
key-files:
  modified:
    - .github/workflows/ci.yml
    - tests/test_ci_docker_config.py
commits:
  - 6764a3e
---

# Quick 260919-d5l: Fix CI workflow (system python venv)

CI now runs on the runner's system python3 inside a `--system-site-packages` venv. `actions/setup-python`, the job-level `PYTHONPATH` and the pip self-upgrade are removed. `PYTHONPATH: src` is set only on the two test steps. `python3-venv` was added to the apt list, and a step verifies `import dbus, gi, rrdtool`.

`tests/test_ci_docker_config.py` now asserts this contract in place of the old `"3.11"` check.

## Verification
- `pytest tests/test_ci_docker_config.py`: 3 passed.
- WSL Debian dry-run in a throwaway venv (Python 3.13.5): requirements installed cleanly and system bindings imported. `test-imports.py` passed, and the suite gave 196 passed, 1 skipped.
- Pushed with a plain push (no force). `gh pr checks 2` shows both CI runs (push and pull_request) passing. PR not merged.

## Deviations
None. Iterations needed: 1.

## Notes
WSL Debian ships Python 3.13, while the ubuntu-latest system Python may differ. The green CI run covers the actual runner.
