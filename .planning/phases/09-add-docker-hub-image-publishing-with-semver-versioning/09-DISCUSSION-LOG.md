# Phase 9 Discussion Log

Discuss-phase was skipped under --auto plan-phase. RESEARCH.md flagged genuine open questions the user had to answer (not guessable from the codebase), so they were asked directly instead of assumed.

| Area | Question | Selected |
|------|----------|----------|
| Docker Hub target | Which account/image name? | peterscholer74/pellmon |
| Version unification | Unify app version and image tag, or keep independent? | Unify (single VERSION file, reconcile configure.ac/version.py.in) |
| Automation level | CI-automated on tag push, or fully manual? | CI-automated on tag push; version bump stays a manual local step |
| Pi architecture | amd64+arm/v7, or also arm64? | amd64 + arm/v7 only |
