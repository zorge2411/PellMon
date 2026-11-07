# -*- coding: utf-8 -*-
"""Backup plugin (Phase 12): settings contract, running, scheduling, status."""

import logging
import os
import sqlite3
import threading
import time
from types import SimpleNamespace

import pytest

from Pellmonsrv import backup_core as core
from Pellmonsrv.database import Keyval_storage, init_keyval_storage
from Pellmonsrv.plugins.backup import backupplugin


def fake_rrdtool(tmp_path, fail=False):
    script = tmp_path / 'rrdtool'
    body = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "RRDtool 1.7.2"; exit 0; fi\n'
    body += 'exit 1\n' if fail else 'echo "<rrd/>"\n'
    script.write_text(body)
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def env(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    sdb = str(data / 'pellmon_settings.db')
    init_keyval_storage(sdb)
    root = tmp_path / 'backups'
    root.mkdir()
    conf = tmp_path / 'pellmon.conf'
    conf.write_text('[conf]\n')
    confd = tmp_path / 'conf.d'
    confd.mkdir()
    (confd / 'a.conf').write_text('[x]\n')
    yield dict(data=data, root=str(root), sdb=sdb, conf=str(conf), confd=str(confd), tmp=tmp_path)
    Keyval_storage.keyval_storage = None


def make(env, fail=False, **cfg):
    p = backupplugin()
    p.autostart = False
    daemon_conf = SimpleNamespace(db=str(env['data'] / 'rrd.db'), keyval_db=env['sdb'], conf_file=env['conf'],
                                  config_dir=env['confd'])
    p.activate({'folder': env['root']}, {'conf': daemon_conf}, None)
    p.rrdtool = fake_rrdtool(env['tmp'], fail)
    p.retry_delay = 0
    clean, errors = __import__('Pellmonsrv.plugins.backup.settings', fromlist=['x']).validate(
        dict({'enabled': True, 'require_other_disk': False}, **cfg))
    assert errors == {}
    assert p.apply_settings(clean)['ok']
    return p


def archives(env, sub=''):
    return sorted(os.listdir(os.path.join(env['root'], sub))) if os.path.isdir(os.path.join(env['root'], sub)) else []


# ---- settings contract ------------------------------------------------------------------

def test_fresh_plugin_is_off_with_defaults(env):
    p = backupplugin()
    p.autostart = False
    p.activate({}, {'conf': SimpleNamespace(db='/x/rrd.db', keyval_db=env['sdb'], conf_file=None, config_dir=None)}, None)
    s = p.get_settings_dict()
    assert s['enabled'] is False and s['available'] is True and s['root'] == '/backups'
    assert p.status_dict()['state'] == 'disabled'


def test_apply_settings_validates_and_persists(env):
    p = make(env)
    bad = p.apply_settings({'enabled': True, 'time': 'bad'})
    assert bad['ok'] is False and list(bad['errors']) == ['time']
    r = p.apply_settings({'enabled': True, 'subfolder': 'pi', 'keep_daily': 3, 'require_other_disk': False})
    assert r == {'ok': True, 'errors': {}}
    q = backupplugin()
    q.autostart = False
    q.activate({}, {'conf': SimpleNamespace(db='/x/rrd.db', keyval_db=env['sdb'], conf_file=None, config_dir=None)}, None)
    assert q.cfg['subfolder'] == 'pi' and q.cfg['keep_daily'] == 3 and q.cfg['enabled'] is True


def test_invalid_apply_changes_nothing(env):
    p = make(env, keep_daily=5)
    assert p.apply_settings({'keep_daily': 0})['ok'] is False
    assert p.cfg['keep_daily'] == 5


# ---- running ------------------------------------------------------------------------------

def test_run_backup_writes_archive_and_updates_state(env):
    p = make(env)
    r = p.run_backup()
    assert r['ok'] and r['name'] in archives(env)
    s = p.status_dict()
    assert s['state'] == 'ok' and s['last_file'] == r['name'] and s['archive_count'] == 1
    assert s['reason'] == '' and s['last_ok'] and s['next_run'] > time.time() - 5
    # the state survives a restart
    q = backupplugin()
    q.autostart = False
    q.activate({}, {'conf': SimpleNamespace(db='/x/rrd.db', keyval_db=env['sdb'], conf_file=None, config_dir=None)}, None)
    assert q.state['last_file'] == r['name'] and q.state['last_ok'] == p.state['last_ok']


def test_sub_folder_is_created_below_the_root(env):
    p = make(env, subfolder='pi/db')
    assert p.run_backup()['ok']
    assert len(archives(env, 'pi/db')) == 1


def test_missing_root_is_an_error_and_is_not_created(env):
    os.rmdir(env['root'])
    p = make(env)
    r = p.run_backup()
    assert r == {'ok': False, 'reason': core.REASON_FOLDER_MISSING}
    assert not os.path.exists(env['root'])
    s = p.status_dict()
    assert s['state'] == 'error' and s['reason'] == core.REASON_FOLDER_MISSING


def test_same_disk_is_refused_unless_allowed(env):
    p = make(env, require_other_disk=True)
    # data folder and backup folder are both in tmp_path: same disk
    assert p.run_backup() == {'ok': False, 'reason': core.REASON_SAME_DISK}
    assert archives(env) == []
    p.apply_settings(dict(p.cfg, require_other_disk=False))
    assert p.run_backup()['ok']


def test_failure_then_success_clears_the_error(env):
    p = make(env, fail=True)
    assert p.run_backup()['reason'] == core.REASON_RRD
    assert p.status_dict()['state'] == 'error'
    p.rrdtool = fake_rrdtool(env['tmp'], fail=False)
    time.sleep(1.1)  # new archive name (one per second)
    assert p.run_backup()['ok']
    s = p.status_dict()
    assert s['state'] == 'ok' and s['reason'] == ''


def test_retention_is_applied_after_each_backup(env):
    p = make(env, keep_daily=2, keep_weekly=0)
    for i in range(4):
        r = p.run_backup(now=time.time() + i * 86400)
        assert r['ok'], r
    assert len(archives(env)) == 2


def test_failures_are_logged_without_paths(env, caplog):
    p = make(env, fail=True)
    with caplog.at_level(logging.INFO, logger='pellMon'):
        p.run_backup()
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors == ['Backup failed: rrdtool failed']


def test_a_second_backup_while_running_is_refused(env):
    p = make(env)
    p.running = True
    assert p.run_backup() == {'ok': False, 'reason': 'a backup is already running'}
    assert p.start_now() == {'ok': False, 'reason': 'a backup is already running'}
    assert p.status_dict()['state'] == 'running'


def test_start_now_runs_in_the_background(env):
    p = make(env)
    assert p.start_now() == {'ok': True, 'reason': ''}
    deadline = time.time() + 10
    while time.time() < deadline and (p.running or not archives(env)):
        time.sleep(0.05)
    assert len(archives(env)) == 1 and p.status_dict()['state'] == 'ok'


def test_manual_backup_works_while_the_schedule_is_off(env):
    p = make(env, enabled=False)
    assert p.status_dict()['state'] == 'disabled'
    assert p.run_backup()['ok']


# ---- scheduling ----------------------------------------------------------------------------

def test_tick_does_nothing_when_disabled(env):
    p = make(env, enabled=False)
    assert p.tick() is False and archives(env) == []


def test_tick_runs_when_due_and_not_again(env):
    p = make(env)
    assert p.tick() is True
    assert len(archives(env)) == 1
    assert p.tick() is False
    assert len(archives(env)) == 1


def test_tick_retries_a_failed_backup_only_after_an_hour(env):
    p = make(env, fail=True)
    now = time.time()
    assert p.tick(now) is True and p.status_dict()['state'] == 'error'
    assert p.tick(now + 600) is False
    p.rrdtool = fake_rrdtool(env['tmp'], fail=False)
    p.state['last_attempt'] = now - 7200  # long ago
    assert p.tick(now) is True and p.state['reason'] == ''


def test_tick_does_not_start_while_running(env):
    p = make(env)
    p.running = True
    assert p.tick() is False


def test_scheduler_thread_runs_and_stops(env):
    p = make(env)
    p.startup_delay = 0.01
    p.check_interval = 0.05
    t = threading.Thread(target=p.scheduler)
    t.daemon = True
    t.start()
    deadline = time.time() + 10
    while time.time() < deadline and not archives(env):
        time.sleep(0.05)
    p.deactivate()
    t.join(5)
    assert len(archives(env)) == 1 and not t.is_alive()


def test_scheduler_exits_during_the_startup_delay(env):
    p = make(env)
    p.startup_delay = 60
    t = threading.Thread(target=p.scheduler)
    t.daemon = True
    t.start()
    p.stop_event.set()
    t.join(5)
    assert not t.is_alive() and archives(env) == []


# ---- folder test and status -------------------------------------------------------------------

def test_test_folder(env):
    p = make(env)
    r = p.test_folder()
    assert r['ok'] and r['free_bytes'] > 0 and archives(env) == []
    p.apply_settings(dict(p.cfg, require_other_disk=True))
    assert p.test_folder() == {'ok': False, 'reason': core.REASON_SAME_DISK, 'free_bytes': None}
    os.rmdir(env['root'])
    p.apply_settings(dict(p.cfg, require_other_disk=False))
    assert p.test_folder()['reason'] == core.REASON_FOLDER_MISSING


def test_status_lists_all_archives_newest_first(env):
    p = make(env)
    for i in range(25):
        open(os.path.join(env['root'], 'pellmon-backup-202611%02d-030000.tar.gz' % (i + 1)), 'wb').write(b'x' * 10)
    s = p.status_dict()
    assert s['archive_count'] == 25 and len(s['archives']) == 25
    assert s['archives'][0]['name'].startswith('pellmon-backup-20261125')
    assert s['folder'] == env['root'] and s['folder_exists'] is True


def test_status_flags_same_disk(env):
    p = make(env)
    assert p.status_dict()['same_disk'] is True  # tmp_path is one filesystem


def test_status_waiting_before_first_run_and_next_run_set(env):
    p = make(env)
    s = p.status_dict()
    assert s['state'] == 'waiting' and s['next_run'] > time.time() and s['archives'] == []


def test_plugin_is_registered_in_the_build_files():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    plugins = open(os.path.join(root, 'src', 'Pellmonsrv', 'plugins', 'Makefile.am')).read()
    assert 'backup \\' in plugins or '\tbackup\n' in plugins
    assert 'backup.pellmon-plugin' in plugins
    assert 'backup_core.py' in open(os.path.join(root, 'src', 'Pellmonsrv', 'Makefile.am')).read()
    assert os.path.isfile(os.path.join(root, 'src', 'Pellmonsrv', 'plugins', 'backup.pellmon-plugin'))


# ---- a hung NAS must not block the D-Bus thread ----------------------------------------------

def test_status_does_not_wait_for_a_hung_folder(env, monkeypatch):
    p = make(env)
    p.status_io_timeout = 0.05
    release = threading.Event()
    monkeypatch.setattr(p, '_read_listing', lambda folder: release.wait(5))
    t0 = time.time()
    s = p.status_dict()
    assert time.time() - t0 < 1.5
    assert s['folder_slow'] is True and s['archives'] == [] and s['state'] == 'waiting'
    release.set()


def test_status_uses_the_stale_listing_when_the_folder_stops_answering(env, monkeypatch):
    p = make(env)
    open(os.path.join(env['root'], 'pellmon-backup-20261101-030000.tar.gz'), 'wb').write(b'x')
    assert p.status_dict()['archive_count'] == 1 and p.status_dict()['folder_slow'] is False
    p.listing_time = 0  # expired
    p.status_io_timeout = 0.05
    release = threading.Event()
    monkeypatch.setattr(p, '_read_listing', lambda folder: release.wait(5))
    s = p.status_dict()
    assert s['folder_slow'] is True and s['archive_count'] == 1
    release.set()


def test_the_folder_is_read_at_most_every_listing_max_age(env, monkeypatch):
    p = make(env)
    calls = []
    real = p._read_listing
    monkeypatch.setattr(p, '_read_listing', lambda folder: (calls.append(1), real(folder))[1])
    p.status_dict()
    p.status_dict()
    assert len(calls) == 1
    p.listing_time = 0
    p.status_dict()
    assert len(calls) == 2


def test_new_backup_and_new_settings_refresh_the_listing(env):
    p = make(env)
    assert p.status_dict()['archive_count'] == 0
    p.run_backup()
    assert p.status_dict()['archive_count'] == 1
    p.apply_settings(dict(p.cfg, subfolder='other'))
    assert p.listing is None


def test_folder_test_gives_up_on_a_hung_folder(env, monkeypatch):
    p = make(env)
    p.test_timeout = 0.05
    release = threading.Event()
    monkeypatch.setattr(p, '_prepare_folder', lambda: release.wait(5))
    t0 = time.time()
    assert p.test_folder() == {'ok': False, 'reason': core.REASON_TIMEOUT, 'free_bytes': None}
    assert time.time() - t0 < 1.5
    release.set()
