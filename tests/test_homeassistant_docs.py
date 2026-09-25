"""Doc guard: DEPLOY-PI.md and HARDWARE-BRINGUP.md must carry the Home Assistant statements."""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY = (REPO_ROOT / "DEPLOY-PI.md").read_text(encoding="utf-8")
BRINGUP = (REPO_ROOT / "HARDWARE-BRINGUP.md").read_text(encoding="utf-8")


def test_deploy_guide_has_home_assistant_section():
    assert "Home Assistant / MQTT" in DEPLOY
    assert "p15 = HomeAssistant" in DEPLOY
    assert "config/conf.d/enabled_plugins.conf" in DEPLOY
    assert "switch off the old publisher" in DEPLOY.lower()
    assert "IP address" in DEPLOY


def test_deploy_guide_documents_behaviour_changes():
    assert "Burner ON" in DEPLOY and "Burner OFF" in DEPLOY
    assert "Allow commands" in DEPLOY


def test_deploy_guide_documents_password_storage_and_acl():
    assert "ACL" in DEPLOY
    assert "settings database" in DEPLOY
    assert "backup" in DEPLOY.lower()


def test_bringup_has_home_assistant_checklist():
    assert "Home Assistant" in BRINGUP
    assert "tools/burner_sim.py" in BRINGUP
    assert "offline" in BRINGUP
    assert "serial link" in BRINGUP
    assert "setpoint" in BRINGUP


def test_no_real_device_identifiers_in_docs():
    for name, text in (("DEPLOY-PI.md", DEPLOY), ("HARDWARE-BRINGUP.md", BRINGUP)):
        assert not re.search(r"[0-9a-f]{32}", text), name
