"""Phase 12: backup folder wiring in compose, env example, ignore files and the deployment guide."""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMPOSE = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
DEPLOY = (REPO / "DEPLOY-PI.md").read_text(encoding="utf-8")
MOUNT = "${PELLMON_BACKUP_DIR:-./pellmon-backups}:/backups"


def block(name):
    m = re.search(r"^  %s:\n(.*?)(?=^  [A-Za-z][\w-]*:\n|^# ====|\Z)" % re.escape(name), COMPOSE, flags=re.M | re.S)
    assert m, name
    return m.group(1)


def test_daemon_mounts_the_backup_folder_writable():
    srv = block("pellmonsrv")
    assert MOUNT in srv
    assert MOUNT + ":ro" not in srv


def test_web_container_does_not_get_the_backup_folder():
    """The web process only talks to the daemon; it never needs (or gets) the archives"""
    assert "/backups" not in block("pellmonweb")


def test_init_service_hands_the_folder_over_without_failing():
    init = block("pellmon-init")
    assert MOUNT in init
    assert "chown 999:999 /backups" in init and "|| true" in init
    assert "chown -R 999:999 /backups" not in init, "never chown a NAS share recursively"


def test_env_example_documents_the_backup_dir():
    env = (REPO / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^PELLMON_BACKUP_DIR=\./pellmon-backups\s*$", env, flags=re.M)
    assert "NAS" in env and "same SD card" in env


@pytest.mark.parametrize("name", [".gitignore", ".dockerignore"])
def test_backup_folder_never_enters_git_or_the_build_context(name):
    assert "pellmon-backups/" in (REPO / name).read_text(encoding="utf-8")


def test_deploy_guide_documents_scheduled_backups():
    for needle in ("Scheduled backups to a NAS or USB drive", "PELLMON_BACKUP_DIR", "/etc/fstab", "nfs", "cifs",
                   "uid=999", "chown 999:999", "Test folder", "Back up now", "same disk as the database",
                   "pellmon_backup.py restore", "pellmon-backup-*.tar.gz", "force-recreate pellmonsrv",
                   "password hashes"):
        assert needle in DEPLOY, needle
    assert "There is no backup button in the web GUI yet" not in DEPLOY


def test_deploy_guide_documents_the_pi_check_script():
    for needle in ("tools/pi_check.sh", "--skip-restore", "--backup-dir", "never changes your data", "rrdtool restore"):
        assert needle in DEPLOY, needle


def test_every_failure_reason_the_page_can_show_is_explained():
    import sys
    sys.path.insert(0, str(REPO / "src"))
    from Pellmonsrv import backup_core as core
    section = DEPLOY.split("**If the page reports a failure:**")[1].split("###")[0]
    for reason in core.REASONS - {core.REASON_VERIFY, core.REASON_UNKNOWN}:
        assert reason.split(" (")[0] in section, reason


def test_deploy_guide_documents_web_restore():
    for needle in ("Restore...", "RESTORE", ".pre-restore", "--with-config", "restarts by itself",
                   "docker compose stop pellmonsrv", "layout"):
        assert needle in DEPLOY, needle
