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
    - The non-root pellmon user needs the serial device's group (SERIAL_GID).
    - The non-root user has no home dir, so Fontconfig needs XDG_CACHE_HOME.
    """
    content = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    srv = _service_block(content, "pellmonsrv")
    web = _service_block(content, "pellmonweb")

    assert "dbus-send --bus=unix:path=" in srv, "health check must use dbus-send --bus=ADDRESS"
    assert "dbus-send --session --address" not in content, (
        "dbus-send does not accept --session together with --address (health check always fails)"
    )
    assert "dbus-daemon --session --address=unix:path=" in srv, (
        "dbus-daemon needs --session --address=; --bus= makes it print usage and exit"
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
    assert "build:" in init and "context: ." in init
    assert "mkdir -p" in init
    assert "chown -R 999:999" in init
    for target in ("/var/lib/pellmon", "/var/log/pellmon", "/etc/pellmon/conf.d"):
        assert target in init, "init service must handle %s" % target

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
    assert "lives in the `pellmon-data` volume" not in text


def test_conf_example_does_not_conflict_with_conf_d():
    """The RRD path is owned by conf.d/database.conf; the example must not set another."""
    text = (REPO_ROOT / "config" / "pellmon.conf.example").read_text(encoding="utf-8")
    lines = [l for l in text.splitlines() if not l.strip().startswith("#")]
    assert not [l for l in lines if re.match(r"^\s*database\s*=", l)], (
        "pellmon.conf.example must not set database (conf.d/database.conf is authoritative)"
    )
    assert any(re.match(r"^\s*config_dir\s*=", l) for l in lines)
    assert any(re.match(r"^\s*logfile\s*=", l) for l in lines)
