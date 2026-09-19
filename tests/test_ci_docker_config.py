"""Tests for GitHub Actions CI and Docker Compose configuration integrity.

Validates that:
- .github/workflows/ci.yml triggers correctly and includes required system dependencies and test commands.
- docker-compose.yml implements proper service readiness healthchecks and dependency ordering.
- Dockerfile contains appropriate readiness healthcheck configuration.
"""

from pathlib import Path
import re
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
