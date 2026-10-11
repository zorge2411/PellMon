# 11-05 Summary (partial: awaiting real-Pi verification)

Done:
- DEPLOY-PI.md: entity table for all additions, silo / consumption / fill-level semantics, updated "commands off" text; docs test derives the expected rows from `ENTITIES`.
- Web page and browser tests only carry an entity count in a stub, nothing to change. CHANGELOG.md is not maintained since 2017 (versions come from conventional commits), so no entry.
- Full suite: 851 passed, 88 skipped (browser tests skipped without PELLMON_BROWSER_TESTS=1).

Not done in this environment:
- tests/browser could not run: the stub server imports `gi` (PyGObject), which is not importable here (errors identical with and without Phase 11; Pellmonweb was not modified). Run it in CI.
- Human verification on the Pi (Scotte 6.34), see 11-05-PLAN.md checkpoint.
