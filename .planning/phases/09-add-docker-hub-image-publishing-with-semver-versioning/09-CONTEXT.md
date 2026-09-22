# Phase 9: Add Docker Hub image publishing with semver versioning - Context

**Gathered:** 2026-09-22
**Status:** Ready for planning
**Source:** Discuss skipped under --auto; decisions captured via targeted AskUserQuestion after RESEARCH.md surfaced open questions (no free-text discussion log beyond this).

<domain>
## Phase Boundary

Publish the PellMon Docker image to Docker Hub, with the published tag driven by semantic versioning derived from Conventional Commits (per `docs/versioning-and-publish-reference.md`, ported to this repo's Linux/CI environment). Reconciles the app's own version reporting with the published image tag. Does not change PellMon's application behavior; touches only build/release tooling, CI, and version bookkeeping.

</domain>

<decisions>
## Implementation Decisions

### Docker Hub target
- **D-01:** Publish to `peterscholer74/pellmon` on Docker Hub. Tags: `:latest` and `:{version}`.

### Version unification
- **D-02:** Introduce a single `VERSION` file (plain text, `MAJOR.MINOR.PATCH`) as the one source of truth. Wire `configure.ac`'s `AC_INIT` version and `version.py.in`'s `@VERSION@` substitution to read from it (or keep them in sync via the release process — planner's call how, but the end state is one number everywhere: app `__version__`, git tag, Docker image tag). This requires a one-time reconciliation: `configure.ac` currently says `0.7.0`, the latest git tag is `v1.0.0`. Bump to a new coherent number (planner/user picks the exact value, e.g. `1.0.1` or `2.0.0`) as part of this phase's first release, not silently pick one without flagging it.

### Automation level
- **D-03:** CI-automated on git tag push. Pushing a `vX.Y.Z` tag triggers a GitHub Actions workflow that builds the multi-arch image and pushes `:latest` and `:X.Y.Z` to Docker Hub. Bumping the version and creating/pushing the tag remains a manual local step: a bash port of `increment-version.ps1` (reads Conventional Commit prefixes since the last tag, decides major/minor/patch, rewrites `VERSION`), run by the developer, who then commits `VERSION` and pushes the tag.
- Recommended stack (from RESEARCH.md, cited against Docker's own docs): `docker/setup-qemu-action`, `docker/setup-buildx-action`, `docker/login-action`, `docker/build-push-action`, triggered on tag push (not every PR/push to master). Docker Hub credentials go in GitHub Actions secrets (a Docker Hub Personal Access Token), never committed.

### Platforms
- **D-04:** Build and publish for `linux/amd64` and `linux/arm/v7` (matches the Pi 3A+ hardware actually tested, 32-bit OS, and existing dev/CI amd64). No `linux/arm64` in this phase.

### Local dev workflow
- **D-05:** Docker Hub publish is an additional distribution channel, not a replacement for local development. `docker compose build` / local builds must keep working unchanged; nothing in `docker-compose.yml`'s existing `pull_policy: never` local-build path is broken by this phase.

### Claude's Discretion
- Exact bash script structure/naming for the version-bump tool (e.g. `scripts/bump-version.sh`), and whether to also keep a thin `publish.sh` for local/manual publishing as a fallback to the CI path.
- Whether to reconcile `configure.ac`/`version.py.in` by templating them from `VERSION` at build time, or by a small pre-commit/CI check that fails if they drift — planner picks the mechanism that fits the existing Autotools `.in` substitution pattern.
- Exact reconciled version number (must not silently drop to a lower/arbitrary number; must be justified against the existing `0.7.0` vs `v1.0.0` conflict).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Base reference (ported, not copied verbatim — see D-03/D-04 deviations)
- `docs/versioning-and-publish-reference.md` — full spec of `increment-version.ps1`/`publish.ps1` semantics (semver bump algorithm, Conventional Commits priority order, exit codes). The bump ALGORITHM (step 2c priority order: BREAKING CHANGE > feat: > fix: > no-op) is locked; the IMPLEMENTATION (PowerShell, single-arch, no CI) is explicitly NOT what this phase ships — see D-03/D-04.

### Existing project state to reconcile
- `configure.ac` (`AC_INIT([PellMon], [0.7.0])`) and `src/Pellmonsrv/version.py.in` (`@VERSION@` substitution) — current app version source, currently out of sync with the latest git tag `v1.0.0`.
- `.github/workflows/` — existing CI workflow(s); the new publish-on-tag workflow should live alongside these, not replace the test workflow.
- `docker-compose.yml`, `Dockerfile` — current single-arch local build path; must remain functional (D-05).

No other external specs.

</canonical_refs>

<specifics>
## Specific Ideas

Docker Hub account: `peterscholer74`, image name `pellmon`. No other specific ideas given (no discuss-phase run).

</specifics>

<deferred>
## Deferred Ideas

- `linux/arm64` support — explicitly deferred (D-04); revisit if a 64-bit Pi OS or Pi 4/5 target appears.
- GHCR/other-registry publishing — reference doc's registry-agnostic porting notes exist but were not requested; Docker Hub only for this phase.

</deferred>

---

*Phase: 09-add-docker-hub-image-publishing-with-semver-versioning*
*Context gathered: 2026-09-22 (targeted questions after --auto research, no full discuss-phase)*
