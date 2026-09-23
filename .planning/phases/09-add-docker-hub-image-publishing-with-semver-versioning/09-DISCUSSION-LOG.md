# Phase 9 Discussion Log

**Date:** 2026-09-23
**Source:** `/gsd:discuss-phase 9`, seeded from
`D:\Antigravity\Kombikode tool\docs\versioning-and-publish-reference.md` (user-provided
reference doc for `increment-version.ps1` / `publish.ps1`).

This log is for human reference only — not consumed by downstream agents. See
`09-CONTEXT.md` for the canonical decisions.

## Registry target

**Options presented:** provide Docker Hub namespace/image now, or use a placeholder wired
through a repo variable.

**User selection:** provide it now → `peterscholer74/pellmon`.

**Notes:** Confirmed single shared image matches existing `docker-compose.yml` convention
(`pellmon:latest` used by both `pellmonsrv` and `pellmonweb`).

## Architecture

**Options presented:** multi-arch (amd64+arm64) via `docker buildx`, or amd64-only matching
the reference script exactly.

**User selection:** Multi-arch (amd64 + arm64).

**Notes:** Driven by `CLAUDE.md` naming Raspberry Pi as a production deployment target — an
amd64-only image would not run natively there.

## Trigger & automation model

**Options presented:** GitHub Actions on push to master (recommended), local developer
scripts (mirrors the reference doc's actual manual workflow), or both.

**User selection:** GitHub Actions on push to master.

## CI write-back (git commit/tag)

**Options presented:** CI commits the VERSION bump + tags itself (deviates from the
reference doc's "never commits" rule, needed for full automation), or version bump stays a
manual local step and CI only builds/publishes on a pushed tag.

**User selection:** Yes — CI commits VERSION + tags.

**Notes:** Flagged as a deliberate deviation from the reference script's own stated behavior
("The script does not `git add`/`git commit` the `VERSION` change itself — that is the
caller's job"). Requires the repo's Actions workflow permissions set to "Read and write" —
documented in CONTEXT.md as a manual one-time setup step, since it can't be set from code.

## Deferred

- Auto-redeploy-on-publish (a `restart-container.ps1` equivalent) — deferred, PellMon already
  uses `docker compose pull && docker compose up -d` as an operator-triggered step per
  `DEPLOY-PI.md`.
- GHCR/secondary registry mirroring — not requested.
