"""tools/pi_check.sh: the Pi deployment check, run against a stand-in docker and curl."""
import json
import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "pi_check.sh"

DOCKER_STUB = r'''#!/usr/bin/env python3
import json, os, sys
rules = json.load(open(os.environ["STUB_RULES"]))
args = sys.argv[1:]
with open(os.environ["STUB_CALLS"], "a") as f:
    f.write(json.dumps(args) + "\n")
def answer(rule):
    sys.stdout.write(rule.get("out", ""))
    sys.exit(rule.get("rc", 0))
if args[:1] == ["info"]:
    answer(rules.get("info", {}))
if args[:1] == ["inspect"]:
    answer(rules.get("inspect:" + args[-1], {}))
if args[:1] == ["logs"]:
    answer(rules.get("logs", {}))
if args[:1] == ["exec"]:
    stdin = "" if sys.stdin.isatty() else sys.stdin.read()
    text = " ".join(args[2:]) + "\n" + stdin
    for rule in rules.get("exec", []):
        if rule["match"] in text:
            answer(rule)
    sys.exit(1)
sys.exit(1)
'''

CURL_STUB = r'''#!/usr/bin/env python3
import json, os, sys
codes = json.loads(os.environ.get("STUB_WEB", "{}"))
url = sys.argv[-1]
path = "/" + url.split("//", 1)[1].split("/", 1)[1] if url.count("/") > 2 else "/"
sys.stdout.write("%03d" % codes.get(path, 200))
'''

NOW = 1_800_000_000
STATE_OK = ("CONFIGURED=1\nCFG_enabled=True\nCFG_frequency=daily\nCFG_time=03:00\nCFG_weekday=6\nCFG_keep_daily=14\n"
            "CFG_keep_weekly=8\nCFG_subfolder=\nCFG_require_other_disk=True\nST_last_file=pellmon-backup-20261105-030000.tar.gz\n"
            "ST_last_size=3145728\nST_reason=\nST_last_ok_AGE_H=5.2\nST_last_attempt_AGE_H=5.2\n")
ARCHIVE_LINE = "1800000000.0 3145728 600 /backups/pellmon-backup-20261105-030000.tar.gz\n"
MEMBERS = "config/\nconfig/pellmon.conf\nmanifest.json\npellmon_settings.db\nrrd.xml\n"


def healthy_rules():
    insp = {"out": "running|healthy|0\n"}
    return {
        "info": {},
        "inspect:pellmon-dbus": insp, "inspect:pellmonsrv": insp, "inspect:pellmonweb": insp,
        "logs": {"out": "x\nActivated plugins: ScotteCom, HomeAssistant, Openweathermap, Backup\nBackup written: a.tar.gz (3072 kB), 0 old archive(s) removed\n"},
        "exec": [
            {"match": "cat /app/VERSION", "out": "2.7.0\n"},
            {"match": 'date +"%Z', "out": "CET +0100\n"},
            {"match": "id -u", "out": "999\n"},
            {"match": "test -d /backups"},
            {"match": 'echo ok > "$f"'},
            {"match": "stat -c %d /backups"},
            {"match": "rrdtool --version", "out": "RRDtool 1.7.2  Copyright by Tobias Oetiker\n"},
            {"match": "CONFIGURED", "out": STATE_OK},
            {"match": "find /backups", "out": ARCHIVE_LINE},
            {"match": "gzip -t"},
            {"match": "tar tzf", "out": MEMBERS},
            {"match": "rrdtool restore", "out": "filename = \"t.rrd\"\nrrd_version = \"0003\"\nsettings integrity: ok\n"},
            {"match": "rrdtool last", "out": "%d\n" % (NOW - 5)},
            {"match": "date +%s", "out": "%d\n" % NOW},
            {"match": "stat -c %a /var/lib/pellmon/pellmon_settings.db", "out": "600\n"},
        ],
    }


def rule(rules, match, **kw):
    """replace the exec rule that matches `match`"""
    for r in rules["exec"]:
        if r["match"] == match:
            r.pop("out", None)
            r.pop("rc", None)
            r.update(kw)
            return
    raise KeyError(match)


@pytest.fixture
def env(tmp_path):
    shm = Path("/dev/shm")
    if not shm.is_dir():
        pytest.skip("needs a second filesystem (/dev/shm)")
    repo = tmp_path / "repo"
    (repo / "pdata" / "data").mkdir(parents=True)
    (repo / "VERSION").write_text("2.7.0\n")
    backups = Path(subprocess.check_output(["mktemp", "-d", "-p", str(shm), "pellmon-check-XXXXXX"]).decode().strip())
    for name, body in (("docker", DOCKER_STUB), ("curl", CURL_STUB)):
        p = tmp_path / name
        p.write_text(body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    yield dict(tmp=tmp_path, repo=repo, backups=backups)
    subprocess.call(["rm", "-rf", str(backups)])


def run(env, rules=None, web=None, extra=(), backup_dir=None, env_file=None):
    rules = rules if rules is not None else healthy_rules()
    rules_file = env["tmp"] / "rules.json"
    rules_file.write_text(json.dumps(rules))
    calls = env["tmp"] / "calls.log"
    calls.write_text("")
    if env_file is not None:
        (env["repo"] / ".env").write_text(env_file)
    e = dict(os.environ, DOCKER=str(env["tmp"] / "docker"), CURL=str(env["tmp"] / "curl"),
             STUB_RULES=str(rules_file), STUB_CALLS=str(calls), STUB_WEB=json.dumps(web or {}), NO_COLOR="1")
    args = [str(SCRIPT), "--no-color", "--repo", str(env["repo"]), "--data-dir", str(env["repo"] / "pdata")]
    if env_file is None:
        args += ["--backup-dir", str(backup_dir or env["backups"])]
    args += list(extra)
    res = subprocess.run(args, capture_output=True, text=True, timeout=60, env=e)
    res.calls = [json.loads(l) for l in calls.read_text().splitlines() if l.strip()]
    return res


def lines(res, tag):
    prefix = "[ OK ]" if tag == "OK" else "[%s]" % tag
    return [l for l in res.stdout.splitlines() if l.startswith(prefix)]


# ---- the script itself ----

def test_script_is_executable_and_valid_bash():
    assert os.access(SCRIPT, os.X_OK)
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_help_and_unknown_option():
    res = subprocess.run([str(SCRIPT), "--help"], capture_output=True, text=True)
    assert res.returncode == 0 and "tools/pi_check.sh" in res.stdout and "--skip-restore" in res.stdout
    res = subprocess.run([str(SCRIPT), "--bogus"], capture_output=True, text=True)
    assert res.returncode == 2 and "unknown option" in res.stderr


# ---- scenarios ----

def test_healthy_system_passes(env):
    res = run(env)
    assert res.returncode == 0, res.stdout
    assert not lines(res, "FAIL")
    out = res.stdout
    for needle in ("plugin Backup is active", "newest archive passes gzip -t", "archive contains rrd.xml",
                   "rrdtool restore of the archive works", "the daemon user can create and delete files",
                   "backup folder is on a different disk", "the RRD is being updated",
                   "last successful backup 5.2 h ago", "/backup/ answers 200", "pellmonsrv image version: 2.7.0"):
        assert needle in out, needle
    assert "0 failures" in out and "Still to do by hand" in out


def test_everything_is_read_only(env):
    res = run(env)
    for args in res.calls:
        assert args[0] in ("info", "inspect", "logs", "exec"), args
        if args[0] == "exec":
            cmd = " ".join(args)
            for forbidden in ("kill", "restart", "stop ", "compose", "drop ", "delete from", "update keyval", "insert "):
                assert forbidden not in cmd, cmd
            if " rm " in cmd or "rm -f" in cmd or "rm -rf" in cmd:
                assert "/backups/.pi-check-" in cmd or "/tmp/pi-check." in cmd or "$d" in cmd, cmd


def test_backup_plugin_not_active_is_a_failure(env):
    rules = healthy_rules()
    rules["logs"] = {"out": "Activated plugins: ScotteCom, HomeAssistant, Openweathermap\n"}
    res = run(env, rules)
    assert res.returncode == 1
    assert any("plugin Backup is not active" in l for l in lines(res, "FAIL"))


def test_container_missing_and_unhealthy(env):
    rules = healthy_rules()
    rules["inspect:pellmonweb"] = {"out": ""}
    rules["inspect:pellmonsrv"] = {"out": "running|unhealthy|0\n"}
    res = run(env, rules)
    fails = " ".join(lines(res, "FAIL"))
    assert "pellmonweb does not exist" in fails and "pellmonsrv is running but unhealthy" in fails
    assert res.returncode == 1


def test_docker_unreachable_stops_early(env):
    rules = healthy_rules()
    rules["info"] = {"rc": 1}
    res = run(env, rules)
    assert res.returncode == 1 and "cannot talk to the Docker daemon" in res.stdout
    assert all(a[0] == "info" for a in res.calls)


def test_stale_image_version_warns(env):
    rules = healthy_rules()
    rule(rules, "cat /app/VERSION", out="2.6.0\n")
    res = run(env, rules)
    assert any("image is 2.6.0 but this checkout says 2.7.0" in l for l in lines(res, "WARN"))
    assert res.returncode == 0


def test_tracebacks_warn(env):
    rules = healthy_rules()
    rules["logs"]["out"] += "Traceback (most recent call last):\n  File x\nValueError\n"
    assert any("traceback" in l for l in lines(run(env, rules), "WARN"))


def test_unwritable_backup_folder_in_the_container(env):
    rules = healthy_rules()
    rule(rules, 'echo ok > "$f"', rc=1, out="sh: 1: cannot create /backups/.pi-check-1: Permission denied\n")
    res = run(env, rules)
    assert res.returncode == 1
    assert any("cannot write to /backups" in l and "Permission denied" in l for l in lines(res, "FAIL"))


def test_folder_not_mounted_in_the_container(env):
    rules = healthy_rules()
    rule(rules, "test -d /backups", rc=1)
    assert any("/backups is not mounted in the container" in l for l in lines(run(env, rules), "FAIL"))


def test_same_disk_on_host_and_in_container(env):
    rules = healthy_rules()
    rule(rules, "stat -c %d /backups", rc=1)
    same = env["repo"] / "pdata" / "backups"
    same.mkdir()
    res = run(env, rules, backup_dir=same)
    fails = " ".join(lines(res, "FAIL"))
    assert "SAME disk as the data" in fails and "inside the container /backups is on the same disk" in fails
    assert res.returncode == 1


def test_missing_backup_folder_on_the_host(env):
    res = run(env, backup_dir=env["tmp"] / "nowhere")
    assert any("does not exist on the host" in l for l in lines(res, "FAIL"))


def test_env_file_is_used_for_the_folder_and_port(env):
    env_file = 'TZ=UTC\nPELLMON_BACKUP_DIR="%s"\nPELLMON_DATA_DIR=%s\nPELLMON_WEB_PORT=9000\n' % (env["backups"], env["repo"] / "pdata")
    res = run(env, env_file=env_file)
    assert "PELLMON_BACKUP_DIR = %s" % env["backups"] in res.stdout
    assert "backup folder is on a different disk" in res.stdout


def test_no_archives_yet_warns(env):
    rules = healthy_rules()
    rule(rules, "find /backups", out="")
    res = run(env, rules)
    assert any("no backup archives in /backups yet" in l for l in lines(res, "WARN"))
    assert res.returncode == 0
    assert not any("rrdtool restore" in " ".join(c) for c in res.calls)


def test_damaged_and_incomplete_archives(env):
    rules = healthy_rules()
    rule(rules, "gzip -t", rc=1)
    rule(rules, "tar tzf", out="manifest.json\nrrd.xml\n")
    res = run(env, rules)
    fails = " ".join(lines(res, "FAIL"))
    assert "damaged (gzip -t failed)" in fails and "archive is missing pellmon_settings.db" in fails
    assert res.returncode == 1


def test_restore_round_trip_failure(env):
    rules = healthy_rules()
    rule(rules, "rrdtool restore", rc=1, out="ERROR: bad xml\n")
    res = run(env, rules)
    assert any("restore round trip failed" in l and "bad xml" in l for l in lines(res, "FAIL"))


def test_skip_restore(env):
    res = run(env, extra=["--skip-restore"])
    assert "restore round trip skipped" in res.stdout
    assert not any("rrdtool restore" in " ".join(c) for c in res.calls)
    assert res.returncode == 0


def test_archive_mode_other_than_600_warns(env):
    rules = healthy_rules()
    rule(rules, "find /backups", out=ARCHIVE_LINE.replace(" 600 ", " 644 "))
    assert any("archive mode is 644" in l for l in lines(run(env, rules), "WARN"))


def test_last_backup_failed_is_a_failure(env):
    rules = healthy_rules()
    rule(rules, "CONFIGURED", out=STATE_OK.replace("ST_reason=", "ST_reason=folder missing (is the NAS mounted?)"))
    res = run(env, rules)
    assert any("last backup attempt failed: folder missing (is the NAS mounted?)" in l for l in lines(res, "FAIL"))


def test_stale_and_never_run_automatic_backups_warn(env):
    rules = healthy_rules()
    rule(rules, "CONFIGURED", out=STATE_OK.replace("ST_last_ok_AGE_H=5.2", "ST_last_ok_AGE_H=100.0"))
    assert any("100.0 h ago" in l for l in lines(run(env, rules), "WARN"))
    rule(rules, "CONFIGURED", out=STATE_OK.replace("ST_last_ok_AGE_H=5.2", "ST_last_ok_AGE_H="))
    assert any("no successful backup recorded yet" in l for l in lines(run(env, rules), "WARN"))


def test_weekly_schedule_allows_a_longer_gap(env):
    rules = healthy_rules()
    out = STATE_OK.replace("CFG_frequency=daily", "CFG_frequency=weekly").replace("ST_last_ok_AGE_H=5.2", "ST_last_ok_AGE_H=100.0")
    rule(rules, "CONFIGURED", out=out)
    res = run(env, rules)
    assert not any("100.0 h ago" in l for l in lines(res, "WARN"))
    assert any("last successful backup 100.0 h ago" in l for l in lines(res, "OK"))


def test_never_configured_and_disabled_are_informational(env):
    rules = healthy_rules()
    rule(rules, "CONFIGURED", out="CONFIGURED=0\n")
    res = run(env, rules)
    assert "never been saved" in res.stdout and res.returncode == 0
    rule(rules, "CONFIGURED", out=STATE_OK.replace("CFG_enabled=True", "CFG_enabled=False"))
    res = run(env, rules)
    assert "automatic backups are off" in res.stdout and res.returncode == 0


def test_rrd_not_updating_and_loose_settings_mode_warn(env):
    rules = healthy_rules()
    rule(rules, "rrdtool last", out="%d\n" % (NOW - 5000))
    rule(rules, "stat -c %a /var/lib/pellmon/pellmon_settings.db", out="644\n")
    warns = " ".join(lines(run(env, rules), "WARN"))
    assert "last updated 5000 s ago" in warns and "settings database mode is 644" in warns


def test_web_pages(env):
    res = run(env, web={"/backup/": 404, "/weather/": 303, "/homeassistant/": 500})
    assert any("/backup/ answers 404" in l for l in lines(res, "FAIL"))
    assert any("/weather/ redirects (303" in l for l in lines(res, "OK"))
    assert any("/homeassistant/ answers 500" in l for l in lines(res, "WARN"))
    assert res.returncode == 1
    res = run(env, web={"/": 0})
    assert any("did not answer" in l for l in lines(res, "FAIL"))


def test_summary_lists_failures_and_warnings(env):
    rules = healthy_rules()
    rule(rules, "gzip -t", rc=1)
    rule(rules, "stat -c %a /var/lib/pellmon/pellmon_settings.db", out="666\n")
    res = run(env, rules)
    tail = res.stdout.split("== Summary ==")[1]
    assert "Failures:" in tail and "newest archive is damaged" in tail
    assert "Warnings:" in tail and "settings database mode is 666" in tail
