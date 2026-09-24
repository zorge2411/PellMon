"""Tests for GitHub Actions CI and Docker Compose configuration integrity.

Validates that:
- .github/workflows/ci.yml triggers correctly and includes required system dependencies and test commands.
- docker-compose.yml implements proper service readiness healthchecks and dependency ordering.
- Dockerfile contains appropriate readiness healthcheck configuration.
"""

from pathlib import Path
import re
import shutil
import subprocess
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_github_actions_workflow():
    """Verify .github/workflows/ci.yml configuration integrity."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.is_file(), f"CI workflow file not found at {ci_path}"

    content = ci_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Verify basic YAML syntax (no tabs, proper key-value structure)
    for idx, line in enumerate(lines, 1):
        assert "\t" not in line, f"Tab character found in line {idx} of ci.yml"

    # Verify triggers and target branches
    assert "push:" in content, "Workflow should trigger on push"
    assert "pull_request:" in content, "Workflow should trigger on pull_request"
    assert "master" in content, "Target branches must include master"
    assert "python3-migration" in content, "Target branches must include python3-migration"

    # Verify runner and interpreter strategy
    assert "ubuntu-latest" in content, "CI runner must be ubuntu-latest"
    assert "actions/setup-python" not in content, (
        "CI must use the runner's system python3 so apt-installed dbus/gi/rrdtool bindings are importable"
    )
    assert "--system-site-packages" in content, (
        "venv must use --system-site-packages to bridge to apt-installed bindings"
    )
    assert "install --upgrade pip" not in content, (
        "Self-upgrading pip fails against Debian-managed pip (Cannot uninstall pip 24.0)"
    )
    assert "/usr/lib/python3/dist-packages" not in content, (
        "dist-packages must not be injected via PYTHONPATH"
    )
    assert "PYTHONPATH: src" in content, "src must be exposed to the test steps via PYTHONPATH: src"

    # Verify Linux system packages (D-Bus, GLib, RRDtool)
    required_packages = [
        "python3-dbus",
        "python3-gi",
        "python3-gi-cairo",
        "gir1.2-glib-2.0",
        "librrd-dev",
        "rrdtool",
        "python3-rrdtool",
        "python3-venv",
    ]
    for pkg in required_packages:
        assert pkg in content, f"Required system package '{pkg}' missing from ci.yml"

    # Verify test execution commands
    assert "test-imports.py" in content, "Workflow must execute test-imports.py"
    assert re.search(r"pytest\s+tests/", content), "Workflow must execute pytest tests/"


def test_publish_workflow_permissions_and_skip_ci():
    """D-03/D-04: the publish job is master-push-only, minimally privileged, and self-quiets."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_path.read_text(encoding="utf-8")

    assert "  publish:" in content, "a top-level publish job must exist in ci.yml"
    assert "needs: test" in content, "publish must be gated on the existing test job (D-03)"
    assert "contents: write" in content, (
        "publish needs contents: write to commit VERSION and push a tag (D-04)"
    )
    assert "fetch-depth: 0" in content, (
        "full history is required for git describe/git log range queries (D-04)"
    )
    assert "[skip ci]" in content, (
        "the bump commit must carry [skip ci] so it does not re-trigger the workflow (D-04)"
    )
    assert "tools/version_bump.py decide" in content, (
        "publish must call the Plan 01 CLI to decide the bump (D-03)"
    )
    assert "github-actions[bot]" in content, "the bump commit must use the bot git identity (D-04)"
    assert "git tag -a" in content, "the release tag must be annotated (D-04)"
    assert "refs/heads/master" in content, (
        "publish must be scoped to the master branch only (D-03)"
    )

    # Negative guards
    assert "git tag -f" not in content, (
        "tag creation must never force-overwrite an existing release tag (Tampering)"
    )
    assert "--force" not in content, (
        "no step may force-push or force-tag over an existing release (Tampering)"
    )
    assert "workflow_run" not in content, (
        "publish must use a plain push: trigger, not workflow_run, for reliable [skip ci] (Pitfall 1)"
    )


def test_publish_workflow_multiarch_and_tags():
    """D-01/D-02/D-07: multi-arch Docker Hub publish with credentials via docker/login-action."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    content = ci_path.read_text(encoding="utf-8")

    assert "peterscholer74/pellmon:latest" in content, "must push the :latest tag (D-01)"
    assert "peterscholer74/pellmon:" in content and "steps.bump.outputs.version" in content, (
        "must push the :{version} tag derived from the bump step's output (D-01)"
    )
    assert "linux/amd64,linux/arm64,linux/arm/v7" in content, (
        "must build all three target platforms, including 32-bit ARM for older/32-bit-OS Pis "
        "(D-02, amended after a real 32-bit Pi failed to pull the amd64+arm64-only image)"
    )
    assert "docker/setup-qemu-action@" in content, "must register QEMU binfmt handlers (D-02)"
    assert "docker/setup-buildx-action@" in content, "must create a buildx builder (D-02)"
    assert "docker/login-action@" in content, "must authenticate via the maintained login action (D-07)"
    assert "docker/build-push-action@" in content, "must build+push via the maintained action (D-01/D-02)"
    assert "secrets.DOCKERHUB_USERNAME" in content, "Docker Hub username must come from a secret (D-07)"
    assert "secrets.DOCKERHUB_TOKEN" in content, "Docker Hub token must come from a secret (D-07)"
    assert "push: true" in content, "the build-push-action step must actually push (D-01)"

    # Negative guards
    assert "docker login -p" not in content, (
        "credentials must flow through docker/login-action, never an echoing shell step (D-07)"
    )
    assert "--password " not in content, (
        "credentials must flow through docker/login-action, never a raw --password flag (D-07)"
    )
    assert "ghcr.io" not in content, "Docker Hub only this phase; GHCR is a deferred idea"


def test_docker_healthchecks():
    """Verify docker-compose.yml healthchecks and dependency conditions."""
    compose_path = REPO_ROOT / "docker-compose.yml"
    assert compose_path.is_file(), f"docker-compose.yml not found at {compose_path}"

    content = compose_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    # Verify basic YAML syntax (no tabs)
    for idx, line in enumerate(lines, 1):
        assert "\t" not in line, f"Tab character found in line {idx} of docker-compose.yml"

    # Verify pellmonsrv healthcheck checks D-Bus ping
    assert "org.pellmon.int" in content, "pellmonsrv healthcheck must target org.pellmon.int"
    assert "dbus-send" in content, "pellmonsrv healthcheck must use dbus-send"
    assert "Peer.Ping" in content, "pellmonsrv healthcheck must perform Peer.Ping"

    # Verify pellmonweb service_healthy dependency
    assert "condition: service_healthy" in content, (
        "pellmonweb must depend on pellmonsrv with condition: service_healthy"
    )

    # Verify pellmonweb healthcheck tests HTTP port 8081
    assert re.search(r"curl.*http://localhost:8081/", content), (
        "pellmonweb healthcheck must query http://localhost:8081/"
    )


def test_dockerfile_healthcheck():
    """Verify Dockerfile contains the appropriate healthcheck configuration."""
    dockerfile_path = REPO_ROOT / "Dockerfile"
    assert dockerfile_path.is_file(), f"Dockerfile not found at {dockerfile_path}"

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in content, "Dockerfile must define a HEALTHCHECK"
    assert "curl -f http://localhost:8081/" in content, (
        "Dockerfile HEALTHCHECK must probe HTTP 8081"
    )


def _service_block(content, name):
    """Return the text of one top-level service in docker-compose.yml."""
    match = re.search(r"^  %s:\r?\n(.*?)(?=^  \S|^\S|\Z)" % re.escape(name), content, flags=re.M | re.S)
    assert match, "service %s not found in docker-compose.yml" % name
    return match.group(1)


def test_compose_raspberry_pi_fixes():
    """Regressions found deploying to a real Raspberry Pi 3A+.

    - The health check used `dbus-send --session --address=...`, an invalid option
      combination that always exits 1, so pellmonsrv never became healthy and
      pellmonweb (depends_on: service_healthy) never started.
    - A blanket edit turned the daemon's `dbus-daemon --session --address=` into
      `--bus=`, which dbus-daemon rejects (crash loop). Each command needs its own form.
      dbus-daemon itself now runs in its own `pellmon-dbus` service (split out so a
      pellmonsrv restart doesn't kill/recreate the shared bus and strand pellmonweb's
      one-shot D-Bus connection) -- the flag-combination regression this guards against
      moved with it.
    - The non-root pellmon user needs the serial device's group (SERIAL_GID).
    - The non-root user has no home dir, so Fontconfig needs XDG_CACHE_HOME.
    """
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    srv = _service_block(content, "pellmonsrv")
    web = _service_block(content, "pellmonweb")
    dbus_svc = _service_block(content, "pellmon-dbus")

    assert "dbus-send --bus=unix:path=" in srv, "health check must use dbus-send --bus=ADDRESS"
    assert "dbus-send --session --address" not in content, (
        "dbus-send does not accept --session together with --address (health check always fails)"
    )
    assert "dbus-daemon --session --address=unix:path=" in dbus_svc, (
        "dbus-daemon needs --session --address=; --bus= makes it print usage and exit"
    )
    assert "dbus-daemon --session --address=unix:path=" not in srv, (
        "dbus-daemon must not be started inside pellmonsrv's command -- that couples the "
        "shared bus's lifecycle to pellmonsrv's, so restarting pellmonsrv kills/recreates "
        "the whole bus and permanently strands pellmonweb's one-shot D-Bus connection"
    )
    assert "dbus-daemon --bus=" not in content

    assert re.search(r"group_add:\s*\r?\n\s*- \"\$\{SERIAL_GID(:-\d+)?\}\"", srv), (
        "pellmonsrv must add the serial device group via SERIAL_GID"
    )
    assert "XDG_CACHE_HOME=/tmp" in srv and "XDG_CACHE_HOME=/tmp" in web

    for name, block in (("pellmonsrv", srv), ("pellmonweb", web)):
        match = re.search(r"start_period:\s*(\d+)s", block)
        assert match, "%s healthcheck needs a start_period" % name
        assert int(match.group(1)) >= 60, "%s start_period too short for a Raspberry Pi" % name


def test_dbus_daemon_lifecycle_independent_of_pellmonsrv_restarts():
    """Regression: `docker compose stop pellmonsrv && docker compose start pellmonsrv`
    (Phase 8 checklist step 7) permanently broke pellmonweb's main page with a 500
    (DbusNotConnected: server not running), confirmed on real Pi hardware 2026-09-23.

    Root cause: dbus-daemon ran inline inside pellmonsrv's own command, so restarting
    pellmonsrv killed and recreated the entire shared D-Bus bus, not just the
    org.pellmon.int service on it. pellmonweb opens exactly one D-Bus connection for its
    whole process lifetime (Dbus_handler.start() in pellmonweb.py) and has no path to
    reconnect once the bus daemon itself is replaced -- its watch_name_owner callback
    only detects a service appearing/disappearing on a STABLE bus.

    Fix: dbus-daemon now runs as its own `pellmon-dbus` service with an independent
    `restart: unless-stopped` policy, so pellmonsrv restarting never touches the bus.
    """
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    srv = _service_block(content, "pellmonsrv")
    dbus_svc = _service_block(content, "pellmon-dbus")

    assert "restart: unless-stopped" in dbus_svc, (
        "pellmon-dbus needs its own restart policy independent of pellmonsrv/pellmonweb"
    )
    assert re.search(r"depends_on:\s*\r?\n(?:.*\r?\n)*?\s*pellmon-dbus:\s*\r?\n\s*condition: service_healthy", srv), (
        "pellmonsrv must wait for pellmon-dbus to be healthy before starting, "
        "since it no longer starts the bus daemon itself"
    )
    assert "DBUS_SESSION_BUS_ADDRESS=unix:path=/var/run/pellmon/bus_socket" in srv, (
        "pellmonsrv must point at the shared bus socket owned by pellmon-dbus, not a "
        "socket it creates itself"
    )


def test_env_example_documents_serial_gid():
    env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^SERIAL_GID=\d+\s*$", env, flags=re.M), ".env.example must define SERIAL_GID"


DATA = "${PELLMON_DATA_DIR:-./pellmon-data}"


def test_compose_persists_data_on_the_host():
    """D-01/D-02/D-03/D-04: RRD data and logs are host bind mounts, not named volumes."""
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    srv = _service_block(content, "pellmonsrv")
    web = _service_block(content, "pellmonweb")

    assert DATA + "/data:/var/lib/pellmon" in srv
    assert DATA + "/logs:/var/log/pellmon" in srv
    assert DATA + "/data:/var/lib/pellmon:ro" in web, "web must mount the data folder read-only (D-04)"
    assert re.search(re.escape(DATA + "/logs:/var/log/pellmon") + r"\s*$", web, flags=re.M), (
        "web logs mount must be writable"
    )

    assert "pellmon-data:" not in content, "named volume pellmon-data must be gone (D-03)"
    assert "pellmon-logs:" not in content, "named volume pellmon-logs must be gone (D-03)"
    assert "pellmon-run:" in content
    assert "- pellmon-run:/var/run/pellmon" in srv
    assert "- pellmon-run:/var/run/pellmon" in web


def test_compose_init_service_fixes_ownership():
    """D-06: a one-shot root init service creates and chowns the persistent paths."""
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    init = _service_block(content, "pellmon-init")
    assert "user: root" in init
    assert 'restart: "no"' in init
    assert "image: pellmon:latest" in init
    # WR-01: only pellmonsrv builds the image; two builders race to tag pellmon:latest
    assert "build:" not in init
    assert "pull_policy: never" in init
    assert "build:" in _service_block(content, "pellmonsrv")
    assert "build:" not in _service_block(content, "pellmonweb")
    assert "mkdir -p" in init
    assert "chown -R 999:999" in init
    for target in ("/var/lib/pellmon", "/var/log/pellmon"):
        assert target in init, "init service must handle %s" % target
    # WR-03: the host user edits config/conf.d over SFTP; init must not take it over
    assert "conf.d" not in init, "init must neither mount nor chown config/conf.d"

    srv = _service_block(content, "pellmonsrv")
    assert "pellmon-init:" in srv
    assert "condition: service_completed_successfully" in srv
    assert "PELLMON_REQUIRE_DATADIR=1" in srv


def test_compose_conf_d_writable_for_web_only():
    """D-08: only pellmonweb may write conf.d; pellmon.conf stays read-only for both."""
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    srv = _service_block(content, "pellmonsrv")
    web = _service_block(content, "pellmonweb")

    assert "./config/conf.d:/etc/pellmon/conf.d" in web
    assert "./config/conf.d:/etc/pellmon/conf.d:ro" not in web
    assert "./config/conf.d:/etc/pellmon/conf.d:ro" in srv
    for block in (srv, web):
        assert "./config/pellmon.conf:/etc/pellmon/pellmon.conf:ro" in block


def test_dockerfile_pins_pellmon_uid_gid():
    """WR-02: compose (chown 999:999) and the docs assume uid/gid 999, so the image must pin it."""
    text = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert re.search(r"groupadd\s+-r\s+-g\s+999\s+pellmon", text)
    assert re.search(r"useradd\s+-r\s+-u\s+999\s+-g\s+pellmon\s+pellmon", text)


def test_env_example_documents_data_dir():
    """D-01/D-05: .env.example documents PELLMON_DATA_DIR."""
    env = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^PELLMON_DATA_DIR=\./pellmon-data\s*$", env, flags=re.M), (
        ".env.example must define PELLMON_DATA_DIR=./pellmon-data"
    )
    assert "absolute" in env


def test_data_dir_is_ignored_by_git_and_docker():
    """D-05: the runtime data folder never enters git or the Docker build context."""
    for name in (".gitignore", ".dockerignore"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "pellmon-data/" in text, "%s must ignore pellmon-data/" % name


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not installed")
def test_compose_config_parses():
    """docker-compose.yml must be valid for `docker compose config`."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(REPO_ROOT / "docker-compose.yml"), "config", "-q"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip("docker compose unavailable: %s" % exc)
    assert result.returncode == 0, result.stderr


def test_deploy_guide_documents_persistent_data():
    """D-01/D-10/D-11: the deploy guide explains the host data folder, backup and migration."""
    text = (REPO_ROOT / "DEPLOY-PI.md").read_text(encoding="utf-8")
    for needle in ("PELLMON_DATA_DIR", "pellmon-data/data", "pellmon_backup.py",
                   "docker volume ls", "pellmon-init"):
        assert needle in text, "DEPLOY-PI.md must mention %s" % needle
    assert "pellmon_pellmon-logs" not in text
    # WR-08/WR-09: the volume copy must run as root; no hard-coded serial gid; no spliced sentence
    assert "--user root" in text
    assert "--group-add 46" not in text
    assert "contains After a restore" not in text
    assert "lives in the `pellmon-data` volume" not in text


def test_releasing_doc_documents_manual_setup():
    """D-01/D-04/D-05/D-07/D-09: RELEASING.md names every blocking manual prerequisite."""
    text = (REPO_ROOT / "RELEASING.md").read_text(encoding="utf-8")
    for needle in (
        "DOCKERHUB_USERNAME",
        "DOCKERHUB_TOKEN",
        "peterscholer74/pellmon",
        "Read and write permissions",
        "[skip ci]",
        "BREAKING CHANGE",
        "tools/version_bump.py",
        "DEPLOY-PI.md",
        "branch protection",
    ):
        assert needle in text, "RELEASING.md must document %r" % needle


def test_conf_example_does_not_conflict_with_conf_d():
    """The RRD path is owned by conf.d/database.conf; the example must not set another."""
    text = (REPO_ROOT / "config" / "pellmon.conf.example").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if not l.strip().startswith("#")]
    assert not [l for l in lines if re.match(r"^\s*database\s*=", l)], (
        "pellmon.conf.example must not set database (conf.d/database.conf is authoritative)"
    )
    assert any(re.match(r"^\s*config_dir\s*=", l) for l in lines)
    assert any(re.match(r"^\s*logfile\s*=", l) for l in lines)


def test_ci_runs_mandatory_browser_layout_tests():
    """D-06(b): the headless-browser layout run is a mandatory step of the gated test job."""
    content = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for needle in (
        "requirements-browser.txt",
        "playwright install --with-deps",
        "tests/browser",
        'PELLMON_BROWSER_TESTS: "1"',
        "--allow-unix-socket",
        "-rs",
        "actions/upload-artifact@",
        "if: always()",
    ):
        assert needle in content, "ci.yml must contain %r for the browser layout step (D-06b)" % needle

    suite_pos = content.index("Run test suite")
    browser_pos = content.index("tests/browser")
    publish_pos = content.index("  publish:")
    assert suite_pos < browser_pos < publish_pos, (
        "the browser step must sit inside the test job (after 'Run test suite', before publish) "
        "so that needs: test blocks a release on browser failures"
    )
    assert "needs: test" in content, "publish must stay gated on the test job"

    reqs = (REPO_ROOT / "requirements-browser.txt").read_text(encoding="utf-8")
    assert re.search(r"^playwright==\d", reqs, flags=re.M), "playwright must be pinned with =="
    for name in ("requirements.txt", "Dockerfile"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "playwright" not in text.lower(), "playwright must not leak into %s" % name
