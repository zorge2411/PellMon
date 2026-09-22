# Versioning & Docker Publish Scripts — Reference

Precise, implementation-level documentation of `increment-version.ps1` and `publish.ps1`
(PowerShell, Windows/pwsh), written to be reused or reimplemented in another project.
Source of truth: the actual scripts as of this writing — every rule below is read directly
from their logic, not inferred from usage.

Companion script `restart-container.ps1` is described briefly at the end since it's the
natural consumer of `publish.ps1`'s output, but is not the main subject of this doc.

---

## System overview

Three cooperating pieces, no shared library code — each is a standalone `.ps1`:

| Piece | Role |
|---|---|
| `VERSION` | Plain text file, single line: `MAJOR.MINOR.PATCH` (three dot-separated integers, no `v` prefix). The single source of truth for "what version is this". |
| `increment-version.ps1` | Reads git commit history since the last tag, decides a semver bump (major/minor/patch) from Conventional Commits prefixes, rewrites `VERSION`. Optionally creates a git tag. Never commits, never pushes. |
| `publish.ps1` | Reads `VERSION`, builds a Docker image, tags it `:latest` and `:{version}`, pushes both to a registry. Never touches git or `VERSION`. |

Nothing here is automatically chained — a human (or an orchestrating script) runs them in
sequence and commits the `VERSION` change in between.

---

## `increment-version.ps1`

### Purpose
Removes the manual decision of "is this a major/minor/patch bump" by reading Conventional
Commit prefixes out of git history since the last release tag.

### Parameters
| Name | Type | Default | Meaning |
|---|---|---|---|
| `-Type` | `'major' \| 'minor' \| 'patch'` | none (auto-detect) | Force a specific bump, skipping commit analysis entirely. |
| `-UpdateTag` | `bool` | `$false` | If `$true`, create an annotated git tag `v{newVersion}` after updating `VERSION`. Tag is created **locally only** — not pushed. |

### Preconditions
- Must be run from a directory containing a `VERSION` file.
- `VERSION`'s content, after `.Trim()`, must split on `.` into **exactly 3** parts, each parseable as `[int]`. Anything else (missing file, `1.2`, `1.2.3.4`, non-numeric) is a hard error.
- If `-Type` is omitted, must be run inside a git repository (uses `git describe` / `git log`; a repo with zero commits or zero tags is fine — see algorithm).

### Algorithm (exact)

```
1. Read VERSION, trim, split on "." → (major, minor, patch) as integers.
   FAIL (exit 1) if file missing or split count != 3.

2. IF -Type was NOT supplied:
     a. lastTag = `git describe --tags --abbrev=0` (stderr suppressed; empty/null if no tags — not an error)
     b. commits = `git log "{lastTag}..HEAD" --pretty=%B`  if lastTag exists
                  `git log --pretty=%B`                    if no lastTag (i.e. whole history)
        NOTE: this is the raw multi-line git output. In PowerShell, capturing external-command
        stdout into a variable yields an ARRAY of lines (or a single string if only one line).
        The regex checks below use `-match`, which — applied to an array — returns true if
        ANY element (any line, i.e. any commit message anywhere in the range) matches. So this
        is "does ANY commit in range match", not "does the latest commit match".
     c. Evaluate in this exact priority order, FIRST hit wins:
          i.   commits -match "BREAKING CHANGE"              (plain substring, case-sensitive)
                 → Type = "major"
          ii.  commits -match "^feat(\(.+\))?:"               (line starts with feat: or feat(scope):)
                 → Type = "minor"
          iii. commits -match "^fix(\(.+\))?:"                (line starts with fix: or fix(scope):)
                 → Type = "patch"
          iv.  none matched
                 → print current version, EXIT 0 (success, no-op — "nothing to release")

3. Apply the bump to the in-memory (major, minor, patch):
     major:  major += 1; minor = 0; patch = 0
     minor:  minor += 1; patch = 0
     patch:  patch += 1

4. newVersion = "{major}.{minor}.{patch}"
   Overwrite VERSION file with newVersion (Set-Content — replaces entire file content).

5. IF -UpdateTag $true:
     `git tag -a "v{newVersion}" -m "Release {newVersion}"`
     (annotated tag, LOCAL ONLY — caller must `git push --tags` separately)

6. Print human-readable summary + suggested next command (`.\publish.ps1`).
```

### Exit codes / side effects
- **Exit 1**: `VERSION` missing, or malformed (not exactly 3 dot-separated integers).
- **Exit 0, no changes**: no commit since last tag (or in whole history, if no tag) matched `feat:`/`fix:`/`BREAKING CHANGE`. `VERSION` is left untouched.
- **Success**: `VERSION` overwritten with the new version string. Optionally, one new local (unpushed) annotated git tag. **The script does not `git add`/`git commit` the `VERSION` change itself** — that is the caller's job.
- Never touches a git remote. Never modifies files other than `VERSION`.

### Non-obvious rules worth calling out for a reimplementation
- **Priority, not chronology**: if the commit range contains both a `feat:` commit and a `BREAKING CHANGE` mention (in any commit, in any order), the result is `major` — the check is independent existence, not "which commit is newest".
- **No `docs:`/`chore:`/other-prefix handling** beyond the three patterns above — anything not matching `feat:`, `fix:`, or containing `BREAKING CHANGE` is silently ignored (contributes to neither major, minor, nor patch).
- **`BREAKING CHANGE` match is a bare substring test**, not anchored to line start and not requiring the Conventional Commits `BREAKING CHANGE:` footer colon — `"see BREAKING CHANGE below"` would also trigger it.
- **`feat`/`fix` matches require the prefix at the START of a line** (`^`), so `"this is a feat: not really"` mid-sentence would NOT match, but a commit body line `feat(ui): new button` would.
- **Encoding gotcha**: if this script (or any `.ps1`) contains non-ASCII characters (em-dash, checkmark, curly quotes, etc.) and is saved as UTF-8 **without a BOM**, Windows PowerShell 5.1 (not PowerShell 7/pwsh) reads it using the system codepage instead of UTF-8, corrupting those multi-byte sequences and producing cascading "missing terminator" / "missing closing brace" parse errors — sometimes many lines away from the actual bad character. Fix: save with a UTF-8 BOM, or keep script content pure ASCII. This is a real failure mode encountered while building this pipeline, not a hypothetical.

---

## `publish.ps1`

### Purpose
Docker build → tag → push, in one command, defaulting its version tag to whatever `VERSION` currently says.

### Parameters
| Name | Type | Default | Meaning |
|---|---|---|---|
| `-DockerUsername` | `string` | project-specific (registry namespace) | Prefix for the pushed image name, e.g. `myuser/myapp`. |
| `-ImageName` | `string` | project-specific | Local build tag AND the second half of the remote image name. |
| `-Tag` | `string` | none → falls back to `VERSION` file, trimmed | The version tag to publish alongside `:latest`. |
| `-Push` | `bool` | `$true` | If `$false`, build+tag locally only; skip the push step (dry run). |

### Preconditions
- Docker CLI + running daemon available.
- A `Dockerfile` in the current working directory (build context is `.`, no `-f` override, no build args).
- For `-Push $true`: an active `docker login` session with **write** access to `{DockerUsername}/{ImageName}` on the registry (implicitly Docker Hub — no registry host prefix is ever added to the tag strings).

### Algorithm (exact)

```
1. Resolve Tag:
     Tag param if given
     else: read+trim VERSION file
     else (neither available): FAIL (exit 1)

2. `docker build -t {ImageName} .`
   FAIL (propagate docker's exit code) on non-zero.

3. Compute two remote-qualified tag strings (no registry host prefix — implicit Docker Hub):
     remoteLatest = "{DockerUsername}/{ImageName}:latest"
     remoteTagged = "{DockerUsername}/{ImageName}:{Tag}"
   `docker tag {ImageName} {remoteLatest}`
   `docker tag {ImageName} {remoteTagged}`
   (non-destructive — the bare local `{ImageName}:latest` tag from step 2 still exists too)

4. IF Push:
     `docker push {remoteLatest}`   → FAIL immediately on non-zero exit (most common cause:
                                       not logged in as the account that owns the repo, or the
                                       repo doesn't exist / token lacks write scope — surfaces
                                       as "push access denied ... insufficient_scope")
     `docker push {remoteTagged}`   → same failure handling, independently checked
```

### Exit codes / side effects
- **Exit 1**: no `-Tag` given and no `VERSION` file present.
- **Exit = docker's own exit code**: build failure, or either push failure (checked separately per tag — a failure on `:latest` stops before attempting `:{Tag}`).
- After a successful run, **3 local image tags exist** and are never cleaned up: bare `{ImageName}`, `{DockerUsername}/{ImageName}:latest`, `{DockerUsername}/{ImageName}:{Tag}`.
- Touches only Docker state — never git, never the `VERSION` file. Assumes the caller already decided what `VERSION` should say (typically by running `increment-version.ps1` first).

### Non-obvious rules / porting notes
- **Registry is hardcoded to Docker Hub** by omission — there's no registry-host segment in the tag string. For GHCR/ECR/a private registry, prepend the registry host, e.g. `ghcr.io/{Org}/{ImageName}:{Tag}`, and the login step differs accordingly (`docker login ghcr.io -u ... -p ...`).
- **No multi-arch build** — a single `docker build` targets the build host's native architecture only. For multi-arch, this needs `docker buildx build --platform ... --push` instead of build-then-tag-then-push.
- **No build args, no `--no-cache`, no alternate Dockerfile path** — all implicit; a fork of this script for another project must add flags for these if the target project needs them.
- **Push failures are the overwhelmingly common failure mode** in practice — always check `docker info` / the currently-logged-in account before assuming a code bug when push fails.

---

## Companion: `restart-container.ps1` (consumer, not producer)

Not the subject of this doc, but it's the natural next step after `publish.ps1` succeeds, so noted for completeness:

- Parameters: `-ImageName` (default `{DockerUsername}/{ImageName}` equivalent, fully qualified), `-ContainerName`.
- Algorithm: `docker pull {ImageName}` → if a container named `{ContainerName}` exists, `docker stop` (10s grace) then `docker rm` it → `docker run -d --name {ContainerName} -p 8080:8080 {ImageName}` → print `docker ps` status.
- **Causes brief downtime** (stop-then-start, not blue/green or rolling). In the source project, `docker compose pull && docker compose up -d` is preferred over this script when a `docker-compose.yml` manages the container, since compose preserves the rest of the service definition (restart policy, networks, etc.) across updates.

---

## End-to-end flow (as used in the source project)

```powershell
# 1. Commit using Conventional Commits prefixes
git commit -m "feat: some new capability"

# 2. Decide + write the new version (reads git log, does NOT commit)
.\increment-version.ps1
# → prints e.g. "New: 1.3.0"; VERSION file now contains "1.3.0"

# 3. Commit the version bump (manual — the script does not do this)
git add VERSION
git commit -m "chore: bump version to 1.3.0"

# 4. Build, tag, push the Docker image (reads VERSION)
.\publish.ps1
# → pushes {DockerUsername}/{ImageName}:latest and :1.3.0

# 5. Deploy (on the target host, separately)
docker compose pull; docker compose up -d
# or: .\restart-container.ps1
```

---

## Minimal reusable pseudocode (language-agnostic, for porting to another project/toolchain)

```pseudocode
function BumpVersion(versionFilePath, forcedType = null):
    (major, minor, patch) = split_and_parse_ints(read(versionFilePath).trim(), ".")
    assert exactly 3 parts, else FAIL

    if forcedType is null:
        lastTag = try(shell("git describe --tags --abbrev=0"))          # null if none
        range = lastTag ? f"{lastTag}..HEAD" : "HEAD"
        commitLines = shell(f"git log {range} --pretty=%B").splitlines()

        if any(line contains "BREAKING CHANGE" for line in commitLines):
            forcedType = "major"
        elif any(line matches r"^feat(\(.+\))?:" for line in commitLines):
            forcedType = "minor"
        elif any(line matches r"^fix(\(.+\))?:" for line in commitLines):
            forcedType = "patch"
        else:
            return (current_version_string, changed=false)              # no-op, success

    match forcedType:
        "major": major += 1; minor = 0; patch = 0
        "minor": minor += 1; patch = 0
        "patch": patch += 1

    newVersion = f"{major}.{minor}.{patch}"
    write(versionFilePath, newVersion)
    return (newVersion, changed=true)


function PublishDockerImage(registryUser, imageName, tag = null, push = true, versionFilePath = "VERSION"):
    tag = tag or read(versionFilePath).trim()
    assert tag is not empty, else FAIL

    run_or_fail(f"docker build -t {imageName} .")

    latestRef = f"{registryUser}/{imageName}:latest"
    taggedRef = f"{registryUser}/{imageName}:{tag}"
    run(f"docker tag {imageName} {latestRef}")
    run(f"docker tag {imageName} {taggedRef}")

    if push:
        run_or_fail(f"docker push {latestRef}")   # common failure: auth/scope
        run_or_fail(f"docker push {taggedRef}")

    return taggedRef
```

Both functions are pure I/O + shell-out wrappers with no external dependencies beyond `git`
and `docker` CLIs being on `PATH` — trivial to port to Bash, Python, Node, or any other
scripting environment by translating the shell-outs and string ops 1:1.
