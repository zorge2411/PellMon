# Releasing PellMon

This document covers the automated Docker Hub publish pipeline: the one-time manual
setup it depends on, how a release actually happens, the commit-message rules that
drive it, how to preview the next version locally, the two deviations from the
reference algorithm it was ported from, and how to troubleshoot a failed run.

## One-time setup (manual, cannot be automated)

None of the following steps can be performed from code. They must be done once by a
human with access to the Docker Hub account and the GitHub repository settings, before
the first publish run.

1. **Create the Docker Hub repository `peterscholer74/pellmon`.** Docker Hub does not
   reliably auto-create a repository on a token-authenticated push. This is the most
   common first-publish failure, surfacing as `insufficient_scope: authorization
   failed` or `repository does not exist`. Create it at Docker Hub -> Repositories ->
   Create repository, named exactly `peterscholer74/pellmon`, before the first CI run.

2. **Generate a Docker Hub personal access token with Read & Write scope.** Go to
   Docker Hub -> Account Settings -> Personal access tokens -> Generate new token.
   Use an access token, not the account password.

3. **Add two GitHub Actions repository secrets, named exactly:**
   - `DOCKERHUB_USERNAME`
   - `DOCKERHUB_TOKEN`

   Under repo Settings -> Secrets and variables -> Actions -> New repository secret.
   `DOCKERHUB_USERNAME` is the Docker Hub account name that owns
   `peterscholer74/pellmon`; `DOCKERHUB_TOKEN` is the access token from step 2.

4. **Set Workflow permissions to "Read and write permissions".** Go to repo Settings
   -> Actions -> General -> Workflow permissions. Without this, the bump commit's
   `git push` step fails with a plain 403 rather than a helpful scope error, because
   the default `GITHUB_TOKEN` is read-only.

5. **Check for branch protection on `master` that could block a bot push.** Go to repo
   Settings -> Branches and confirm no protection rule rejects a `github-actions[bot]`
   push (or add a bypass for it). If protection cannot be relaxed, the fallback is a
   fine-grained personal access token (PAT) stored as a secret and used as the
   `token:` input on the checkout step in the `publish` job, in place of the default
   `GITHUB_TOKEN`.

## How a release happens

Every push to `master` runs the `test` job in `.github/workflows/ci.yml`. If it
passes, the `publish` job runs next:

1. `python3 tools/version_bump.py decide` inspects commit messages since the last
   `v*` tag (or full history if no tag exists yet) and decides the bump.
2. If a bump is needed, it writes the new value into `VERSION`, then the workflow
   commits it as `chore: bump version to X.Y.Z [skip ci]`, creates an annotated tag
   `vX.Y.Z`, and pushes both the commit and the tag to `master`.
3. `docker/setup-qemu-action` and `docker/setup-buildx-action` prepare a multi-arch
   builder, `docker/login-action` authenticates to Docker Hub using the two secrets
   above, and `docker/build-push-action` builds and pushes
   `peterscholer74/pellmon:latest` and `peterscholer74/pellmon:X.Y.Z` for
   `linux/amd64`, `linux/arm64` (64-bit Pi OS), and `linux/arm/v7` (32-bit Pi OS —
   added after `2.0.0` shipped without it and failed `docker compose pull` on a
   32-bit Raspberry Pi with "no matching manifest for linux/arm/v7").

`VERSION` at the repo root is the sole source of truth for the published image tag.
`configure.ac`'s `AC_INIT([PellMon], [0.7.0])` is legacy Autotools versioning that is
deliberately **not** kept in sync with `VERSION` — they are two independent numbers.
`VERSION` was seeded at `1.0.0` for this pipeline's first release.

If no commit in range matches any of the three bump rules below, the `publish` job's
`decide` step reports `bump=none` and every later step is skipped: no commit, no tag,
no image push. A no-op, not a failure.

## Commit message rules

| Rule | Match | Bump |
|------|-------|------|
| 1 | Any commit message containing the substring `BREAKING CHANGE` (case-sensitive, anywhere in the message) | major |
| 2 | Else, any commit message with a line starting `feat:` or `feat(scope):` | minor |
| 3 | Else, any commit message with a line starting `fix:` or `fix(scope):` | patch |
| — | Else | no release (no commit, no tag, no image push) |

Priority is existence-based, not chronological: if the commit range contains both a
`fix:` commit and a `BREAKING CHANGE` mention (in either order), the result is major.

## Previewing the next version locally

```bash
python tools/version_bump.py decide --dry-run
python tools/version_bump.py decide --dry-run --type minor
```

`--dry-run` computes and prints the bump and next version but writes nothing to
`VERSION`. `--type` forces a specific bump type, skipping commit-message analysis,
useful for testing the tool itself.

## Known deviations from the reference algorithm

- **This CI commits and tags `VERSION`; the reference script never did.** The
  reference `increment-version.ps1` computed the next version but left committing it
  to the caller ("that's the caller's job"). This pipeline's `publish` job commits
  `VERSION`, creates the annotated tag, and pushes both directly (D-04) — a
  deliberate extension for full automation, not an oversight.

- **The image tags are pushed atomically, not independently.** The reference
  `publish.ps1` pushed `:latest` and `:{version}` as two separate `docker push`
  calls, and treated a failure on the first as fatal before even attempting the
  second (fail-fast, independent per-tag outcome). `docker/build-push-action`
  (buildx) pushes every tag in `tags:` as part of one atomic multi-platform manifest
  operation — there is no "push `:latest`, stop on failure, then push `:{version}`"
  two-step. Per-tag failure isolation does not exist in this pipeline. This is an
  accepted consequence of the multi-arch requirement (D-02), not a bug.

## Troubleshooting

| Signature | Cause |
|-----------|-------|
| `403` / `protected branch hook declined` on the git push step | Workflow permissions not set to "Read and write", or branch protection on `master` is blocking `github-actions[bot]` — see setup steps 4 and 5 |
| `insufficient_scope` on the Docker push step | The Docker Hub repository `peterscholer74/pellmon` does not exist yet, or the token is read-only — see setup steps 1 and 2 |
| Two back-to-back workflow runs for one release | The `[skip ci]` marker on the bump commit is not being honoured — confirm the bump commit message contains `[skip ci]` exactly |
| `ValueError` about `VERSION` | `VERSION` must contain exactly three dot-separated integers after stripping whitespace, with no `v` prefix — check its exact contents |

## Deploying a published image

Once an image is published, see `DEPLOY-PI.md` section "6. Updating, backups,
troubleshooting" for pulling and running it (`docker compose pull && docker compose
up -d`) instead of building locally.
