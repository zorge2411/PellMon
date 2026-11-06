# -*- coding: utf-8 -*-
"""Backup plugin restore glue (Phase 13): preview, single-flight worker, exclusion, swap hooks,
watchdog, self-restart, result persistence."""

import datetime
import io
import json
import os
import signal
import tarfile
import threading
import time
from types import SimpleNamespace

import pytest

from Pellmonsrv import backup_core as core
from Pellmonsrv.database import Keyval_storage, init_keyval_storage
from Pellmonsrv.plugins import backup as backup_mod
from Pellmonsrv.plugins.backup import backupplugin

NAME = 'pellmon-backup-20260101-120000.tar.gz'


@pytest.fixture
def env(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    sdb = str(data / 'pellmon_settings.db')
    init_keyval_storage(sdb)
    root = tmp_path / 'backups'
    root.mkdir()
    yield dict(data=data, root=str(root), sdb=sdb, tmp=tmp_path)
    Keyval_storage.keyval_storage = None


def add_archive(env, when=None):
    name = core.archive_name(when or datetime.datetime(2026, 1, 1, 12, 0, 0))
    manifest = json.dumps({'format': 1, 'created': '2026-01-01T12:00:00+00:00', 'machine': 'x86_64',
                           'rrdtool_version': '1.7', 'rrd_filename': 'rrd.db'}).encode()
    with tarfile.open(os.path.join(env['root'], name), 'w:gz') as tar:
        for member, content in (('manifest.json', manifest), ('pellmon_settings.db', b'x'), ('rrd.xml', b'<rrd/>')):
            info = tarfile.TarInfo(member)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return name


def make(env, in_docker=False):
    p = backupplugin()
    p.autostart = False
    p.exit_after_restore = False
    p.retry_delay = 0
    daemon_conf = SimpleNamespace(db=str(env['data'] / 'rrd.db'), nvdb=str(env['data'] / 'rrd.db'),
                                  keyval_db=env['sdb'], conf_file=None, config_dir=None,
                                  pollData=[{'ds_name': 'a'}, {'ds_name': 'b'}])
    glob = {'conf': daemon_conf, 'restore_lock': threading.Lock()}
    p.activate({'folder': env['root']}, glob, None)
    p.in_docker = in_docker
    p.daemon_conf = daemon_conf
    p.glob_ref = glob
    return p


def wait_for(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def fake_restore(monkeypatch, behaviour=None):
    calls = []

    def fake(path, rrd_db, nvdb, settings_db, rrdtool='rrdtool', locks=(), progress=None,
             should_continue=None, on_swapped=None, poll_ds_names=None, now=None):
        calls.append(dict(path=path, locks=list(locks)))
        if behaviour:
            return behaviour(progress, should_continue, on_swapped)
        for step in ('checking', 'extracting', 'building', 'swapping'):
            progress(step)
        on_swapped()
        return {'pre_restore': ['rrd.db.pre-restore'], 'manifest': {}}

    monkeypatch.setattr(core, 'restore_archive', fake)
    return calls


def held(gate):
    def behaviour(progress, should_continue, on_swapped):
        gate.wait(5)
        raise core.BackupError(core.REASON_LAYOUT)
    return behaviour


def finished(p):
    return wait_for(lambda: p.restore['state'] in ('done', 'restarting', 'failed') and
                    (p.restoring is False or p.restore['state'] != 'failed'))


# ---- start / validation ----------------------------------------------------------------

def test_restore_start_returns_at_once(env, monkeypatch):
    name = add_archive(env)
    p = make(env)
    gate = threading.Event()

    def blocking(progress, should_continue, on_swapped):
        progress('extracting')
        gate.wait(5)
        raise core.BackupError(core.REASON_LAYOUT)

    fake_restore(monkeypatch, blocking)
    r = p.start_restore(name)
    assert r == {'ok': True, 'reason': ''}
    assert wait_for(lambda: p.restore['state'] == 'extracting')
    assert p.restoring is True
    gate.set()
    assert wait_for(lambda: not p.restoring)


@pytest.mark.parametrize('bad', ['../x', '', 'foo.tar.gz', None, 5])
def test_restore_invalid_name(env, monkeypatch, bad):
    add_archive(env)
    p = make(env)
    calls = fake_restore(monkeypatch)
    before = threading.active_count()
    assert p.start_restore(bad) == {'ok': False, 'reason': core.REASON_ARCHIVE_NOT_FOUND}
    assert calls == [] and threading.active_count() == before
    assert p.restoring is False and p.restore['state'] == 'idle'


def test_restore_unknown_name_checked_against_listing(env, monkeypatch):
    # well-formed name that is not in the folder: immediate failure, no worker, state untouched
    add_archive(env)
    p = make(env)
    calls = fake_restore(monkeypatch)
    before = threading.active_count()
    r = p.start_restore('pellmon-backup-20250101-000000.tar.gz')
    assert r == {'ok': False, 'reason': core.REASON_ARCHIVE_NOT_FOUND}
    assert calls == [] and threading.active_count() == before
    assert p.restoring is False and p.restore['state'] == 'idle'


def test_restore_single_flight(env, monkeypatch):
    name = add_archive(env)
    p = make(env)
    gate = threading.Event()
    fake_restore(monkeypatch, held(gate))
    assert p.start_restore(name)['ok']
    assert p.start_restore(name) == {'ok': False, 'reason': core.REASON_RESTORE_BUSY}
    gate.set()
    wait_for(lambda: not p.restoring)
    p.running = True
    assert p.start_restore(name) == {'ok': False, 'reason': backup_mod.REASON_BUSY}


def test_restore_blocks_backups(env, monkeypatch):
    name = add_archive(env)
    p = make(env)
    p.cfg = dict(p.cfg, enabled=True)
    gate = threading.Event()
    fake_restore(monkeypatch, held(gate))
    assert p.start_restore(name)['ok']
    assert p.tick(time.time() + 10 ** 7) is False
    assert p.start_now() == {'ok': False, 'reason': core.REASON_RESTORE_BUSY}
    assert p.run_backup()['reason'] == core.REASON_RESTORE_BUSY
    gate.set()
    wait_for(lambda: not p.restoring)


# ---- outcomes --------------------------------------------------------------------------

def test_restore_success_docker(env, monkeypatch):
    name = add_archive(env)
    p = make(env, in_docker=True)
    calls = fake_restore(monkeypatch)
    killed = []
    monkeypatch.setattr(os, 'kill', lambda *a: killed.append(a))
    assert p.start_restore(name)['ok']
    assert wait_for(lambda: p.restore['state'] == 'restarting')
    assert p.restore['step'] == 5
    assert p.daemon_conf.restore_done is True
    res = core.read_result(str(env['data']))
    assert res['ok'] is True and res['restart'] == 'auto' and res['name'] == name
    assert calls[0]['locks'][0] is p.glob_ref['restore_lock']
    assert calls[0]['locks'][1] is Keyval_storage.keyval_storage.lock
    assert p.restoring is True  # stays set until the restart
    assert killed == []


def test_restore_success_manual(env, monkeypatch):
    name = add_archive(env)
    p = make(env, in_docker=False)
    p.exit_after_restore = True
    fake_restore(monkeypatch)
    killed = []
    monkeypatch.setattr(os, 'kill', lambda *a: killed.append(a))
    assert p.start_restore(name)['ok']
    assert wait_for(lambda: p.restore['state'] == 'done')
    assert core.read_result(str(env['data']))['restart'] == 'manual'
    time.sleep(0.1)
    assert killed == []


def test_restore_exit_sends_sigterm(env, monkeypatch):
    name = add_archive(env)
    p = make(env, in_docker=True)
    p.exit_after_restore = True
    p.restart_delay = 0
    fake_restore(monkeypatch)
    killed = []
    monkeypatch.setattr(os, 'kill', lambda *a: killed.append(a))
    assert p.start_restore(name)['ok']
    assert wait_for(lambda: len(killed) == 1)
    assert killed == [(os.getpid(), signal.SIGTERM)]


def test_restore_failure(env, monkeypatch):
    name = add_archive(env)
    p = make(env)

    def boom(progress, should_continue, on_swapped):
        raise core.BackupError(core.REASON_LAYOUT)

    fake_restore(monkeypatch, boom)
    assert p.start_restore(name)['ok']
    assert wait_for(lambda: p.restore['state'] == 'failed' and not p.restoring)
    assert p.restore['reason'] == core.REASON_LAYOUT
    assert core.read_result(str(env['data']))['ok'] is False
    assert p.start_now()['ok'] is True  # backups are accepted again
    wait_for(lambda: not p.running)


def test_restore_unexpected_error_is_not_leaked(env, monkeypatch):
    name = add_archive(env)
    p = make(env)

    def boom(progress, should_continue, on_swapped):
        raise ValueError('secret /path')

    fake_restore(monkeypatch, boom)
    assert p.start_restore(name)['ok']
    assert wait_for(lambda: p.restore['state'] == 'failed' and not p.restoring)
    assert p.restore['reason'] == core.REASON_UNKNOWN
    assert 'secret' not in json.dumps(p.restore)


def test_restore_watchdog(env, monkeypatch):
    name = add_archive(env)
    p = make(env)
    p.restore_watchdog = 0.2

    def slow(progress, should_continue, on_swapped):
        progress('extracting')
        time.sleep(0.5)
        if not should_continue():
            raise core.BackupError(core.REASON_ARCHIVE_DAMAGED)

    fake_restore(monkeypatch, slow)
    assert p.start_restore(name)['ok']
    assert wait_for(lambda: p.restore['state'] == 'failed')
    assert wait_for(lambda: not p.restoring)
    assert p.restore['reason'] == core.REASON_ARCHIVE_DAMAGED


# ---- preview ---------------------------------------------------------------------------

def test_restore_preview(env, monkeypatch):
    name = add_archive(env)
    p = make(env)
    r = p.preview_backup(name)
    assert r['ok'] is True and r['name'] == name and r['size'] > 0
    assert r['manifest']['machine'] == 'x86_64' and r['restart'] == 'manual'
    assert r['has_config'] is False and isinstance(r['time'], float)
    assert p.preview_backup('pellmon-backup-20250101-000000.tar.gz') == \
        {'ok': False, 'reason': core.REASON_ARCHIVE_NOT_FOUND}
    p.preview_timeout = 0.1
    monkeypatch.setattr(core, 'preview_archive', lambda path: time.sleep(1))
    assert p.preview_backup(name) == {'ok': False, 'reason': core.REASON_TIMEOUT}
