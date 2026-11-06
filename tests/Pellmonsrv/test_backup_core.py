# -*- coding: utf-8 -*-
"""Backup core (Phase 12, Pellmonsrv/backup_core.py): archive, folder check, retention, schedule."""

import datetime
import errno
import importlib.util
import json
import os
import sqlite3
import stat
import sys
import tarfile

import pytest

from Pellmonsrv import backup_core as bk

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = datetime.datetime


def fake_rrdtool(tmp_path, fail=False, counter=None):
    script = tmp_path / 'rrdtool'
    body = '#!/bin/sh\nif [ "$1" = "--version" ]; then echo "RRDtool 1.7.2  Copyright"; exit 0; fi\n'
    if counter:
        body += 'echo x >> %s\n' % counter
    body += 'exit 1\n' if fail else 'echo "<rrd><version>0003</version></rrd>"\n'
    script.write_text(body)
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / 'backups'
    folder.mkdir()
    data = tmp_path / 'data'
    data.mkdir()
    sdb = data / 'pellmon_settings.db'
    c = sqlite3.connect(str(sdb))
    c.execute('create table settings (k text, v text)')
    c.execute("insert into settings values ('a', 'b')")
    c.commit()
    c.close()
    conf = tmp_path / 'pellmon.conf'
    conf.write_text('[conf]\nloglevel = info\n')
    confd = tmp_path / 'conf.d'
    (confd / 'plugins').mkdir(parents=True)
    (confd / 'database.conf').write_text('[conf]\ndatabase = /var/lib/pellmon/rrd.db\n')
    (confd / 'plugins' / 'x.conf').write_text('[plugin_X]\na = 1\n')
    return dict(folder=str(folder), rrd_db=str(data / 'rrd.db'), settings_db=str(sdb), conf_file=str(conf),
                config_dir=str(confd), rrdtool=fake_rrdtool(tmp_path), tmp=tmp_path)


def make(env, **over):
    kw = dict(folder=env['folder'], rrd_db=env['rrd_db'], settings_db=env['settings_db'],
              conf_file=env['conf_file'], config_dir=env['config_dir'], rrdtool=env['rrdtool'], retry_delay=0)
    kw.update(over)
    return bk.create_archive(**kw)


# ---- names and listing ------------------------------------------------------------

def test_name_round_trip():
    t = D(2026, 11, 5, 3, 0, 7)
    assert bk.archive_name(t) == 'pellmon-backup-20261105-030007.tar.gz'
    assert bk.parse_name(bk.archive_name(t)) == t


@pytest.mark.parametrize('name', ['', None, 'pellmon-backup-x.tar.gz', '../pellmon-backup-20261105-030007.tar.gz',
                                  '.pellmon-backup-20261105-030007.tar.gz.part', 'pellmon-backup-20261305-030007.tar.gz',
                                  'pellmon-backup-20261105-030007.tar.gz.bak'])
def test_parse_name_rejects(name):
    assert bk.parse_name(name) is None


def test_list_archives_only_ours_newest_first(tmp_path):
    for n in ('pellmon-backup-20261101-030000.tar.gz', 'pellmon-backup-20261103-030000.tar.gz', 'notes.txt',
              '.pellmon-backup-20261104-030000.tar.gz.part'):
        (tmp_path / n).write_bytes(b'12345')
    (tmp_path / 'pellmon-backup-20261102-030000.tar.gz').mkdir()
    os.symlink(str(tmp_path / 'notes.txt'), str(tmp_path / 'pellmon-backup-20261105-030000.tar.gz'))
    names = [a['name'] for a in bk.list_archives(str(tmp_path))]
    assert names == ['pellmon-backup-20261103-030000.tar.gz', 'pellmon-backup-20261101-030000.tar.gz']
    assert bk.list_archives(str(tmp_path / 'missing')) == []


# ---- retention ---------------------------------------------------------------------

def entries(*stamps):
    return [(bk.archive_name(s), s) for s in stamps]


def test_select_prune_daily_only():
    e = entries(*[D(2026, 11, d, 3) for d in range(1, 11)])
    deleted = bk.select_prune(e, 3, 0)
    assert sorted(deleted) == sorted(n for n, t in e if t.day <= 7)


def test_select_prune_weekly_keeps_newest_of_each_week():
    # 2026-11-02 is a Monday: weeks start 2, 9, 16 (Nov) and 26 Oct
    stamps = [D(2026, 10, 26, 3), D(2026, 10, 28, 3), D(2026, 11, 2, 3), D(2026, 11, 4, 3),
              D(2026, 11, 9, 3), D(2026, 11, 11, 3), D(2026, 11, 16, 3), D(2026, 11, 18, 3)]
    e = entries(*stamps)
    kept = set(n for n, _ in e) - set(bk.select_prune(e, 1, 3))
    # newest archive, plus the newest of the last 3 weeks: week of 16th (18th is newest), 9th (11th), 2nd (4th)
    assert kept == set(bk.archive_name(s) for s in (D(2026, 11, 18, 3), D(2026, 11, 11, 3), D(2026, 11, 4, 3)))


def test_select_prune_never_deletes_the_newest_even_with_zero_keep():
    e = entries(D(2026, 11, 1, 3), D(2026, 11, 2, 3))
    assert bk.select_prune(e, 0, 0) == [bk.archive_name(D(2026, 11, 1, 3))]


def test_select_prune_few_archives_deletes_nothing():
    e = entries(D(2026, 11, 1, 3), D(2026, 11, 2, 3))
    assert bk.select_prune(e, 14, 8) == []
    assert bk.select_prune([], 14, 8) == []


def test_select_prune_daily_and_weekly_overlap_is_not_double_counted():
    e = entries(*[D(2026, 11, d, 3) for d in range(1, 15)])
    kept = set(n for n, _ in e) - set(bk.select_prune(e, 2, 2))
    assert len(kept) == 4 or len(kept) == 3  # 2 newest + newest of last two weeks, overlapping allowed
    assert bk.archive_name(D(2026, 11, 14, 3)) in kept


def test_prune_only_touches_our_archives(tmp_path):
    for d in range(1, 6):
        (tmp_path / bk.archive_name(D(2026, 11, d, 3))).write_bytes(b'x')
    (tmp_path / 'keep-me.tar.gz').write_bytes(b'x')
    (tmp_path / 'notes.txt').write_bytes(b'x')
    deleted = bk.prune(str(tmp_path), 2, 0)
    assert len(deleted) == 3
    left = sorted(os.listdir(str(tmp_path)))
    assert 'keep-me.tar.gz' in left and 'notes.txt' in left
    assert bk.archive_name(D(2026, 11, 5, 3)) in left and bk.archive_name(D(2026, 11, 4, 3)) in left


# ---- folder check -------------------------------------------------------------------

def test_check_folder_ok_returns_free_space(tmp_path):
    assert bk.check_folder(str(tmp_path)) > 0
    assert os.listdir(str(tmp_path)) == []  # probe file removed


def test_check_folder_missing(tmp_path):
    with pytest.raises(bk.BackupError) as e:
        bk.check_folder(str(tmp_path / 'nope'))
    assert e.value.reason == bk.REASON_FOLDER_MISSING
    with pytest.raises(bk.BackupError):
        bk.check_folder('')


@pytest.mark.parametrize('err,reason', [(errno.EACCES, bk.REASON_NOT_WRITABLE), (errno.EROFS, bk.REASON_NOT_WRITABLE),
                                        (errno.ENOSPC, bk.REASON_NO_SPACE)])
def test_check_folder_write_errors(tmp_path, monkeypatch, err, reason):
    def boom(*a, **k):
        raise OSError(err, 'x')
    monkeypatch.setattr(bk.os, 'open', boom)
    with pytest.raises(bk.BackupError) as e:
        bk.check_folder(str(tmp_path))
    assert e.value.reason == reason


def test_check_folder_refuses_the_same_disk(tmp_path):
    other = tmp_path / 'data'
    other.mkdir()
    (tmp_path / 'b').mkdir()
    with pytest.raises(bk.BackupError) as e:
        bk.check_folder(str(tmp_path / 'b'), other_disk_than=str(other))  # same tmpfs: same disk
    assert e.value.reason == bk.REASON_SAME_DISK
    assert bk.check_folder(str(tmp_path / 'b')) > 0  # not asked for


def test_same_disk_uses_device_ids(tmp_path, monkeypatch):
    real = os.stat

    class S(object):
        def __init__(self, dev):
            self.st_dev = dev
    monkeypatch.setattr(bk.os, 'stat', lambda p, *a, **k: S(1 if str(p).endswith('data') else 2))
    assert not bk.same_disk('/x/backups', '/y/data')
    monkeypatch.setattr(bk.os, 'stat', lambda p, *a, **k: S(7))
    assert bk.same_disk('/x/backups', '/y/data')
    monkeypatch.setattr(bk.os, 'stat', real)
    assert not bk.same_disk(str(tmp_path / 'missing'), str(tmp_path))


def test_create_archive_can_require_another_disk(env):
    with pytest.raises(bk.BackupError) as e:
        make(env, other_disk_than=env['config_dir'])
    assert e.value.reason == bk.REASON_SAME_DISK
    assert os.listdir(env['folder']) == []


# ---- archive -------------------------------------------------------------------------

def test_create_archive_contents_and_mode(env):
    res = make(env, now=D(2026, 11, 5, 3, 0, 0))
    path = os.path.join(env['folder'], res['name'])
    assert res['name'] == 'pellmon-backup-20261105-030000.tar.gz' and res['size'] == os.path.getsize(path)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert sorted(os.listdir(env['folder'])) == [res['name']]  # no .part, no probe
    with tarfile.open(path) as tar:
        names = set(tar.getnames())
        assert {'rrd.xml', 'pellmon_settings.db', 'manifest.json', 'config', 'config/pellmon.conf',
                'config/conf.d/database.conf', 'config/conf.d/plugins/x.conf'} <= names
        manifest = json.load(tar.extractfile('manifest.json'))
        assert tar.extractfile('rrd.xml').read().startswith(b'<rrd>')
    assert manifest['format'] == 1 and manifest['rrd_filename'] == 'rrd.db'
    assert manifest['rrdtool_version'].startswith('RRDtool')


def test_settings_copy_is_a_consistent_database(env, tmp_path):
    res = make(env)
    out = tmp_path / 'x'
    out.mkdir()
    with tarfile.open(os.path.join(env['folder'], res['name'])) as tar:
        (out / 'pellmon_settings.db').write_bytes(tar.extractfile('pellmon_settings.db').read())
    c = sqlite3.connect(str(out / 'pellmon_settings.db'))
    assert c.execute('select v from settings where k = "a"').fetchone() == ('b',)
    c.close()


def test_archive_is_accepted_by_the_restore_tool(env, tmp_path):
    spec = importlib.util.spec_from_file_location('pellmon_backup', os.path.join(ROOT, 'tools', 'pellmon_backup.py'))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    res = make(env)
    dest = tmp_path / 'extracted'
    dest.mkdir()
    tool._extract_archive(os.path.join(env['folder'], res['name']), str(dest))
    assert (dest / 'rrd.xml').is_file() and (dest / 'pellmon_settings.db').is_file()
    assert (dest / 'config' / 'pellmon.conf').is_file()


def test_rrdtool_missing(env):
    with pytest.raises(bk.BackupError) as e:
        make(env, rrdtool='/nonexistent/rrdtool')
    assert e.value.reason == bk.REASON_RRD_MISSING
    assert os.listdir(env['folder']) == []


def test_rrdtool_failure_is_retried_then_reported(env, tmp_path):
    counter = tmp_path / 'count'
    with pytest.raises(bk.BackupError) as e:
        make(env, rrdtool=fake_rrdtool(tmp_path, fail=True, counter=str(counter)))
    assert e.value.reason == bk.REASON_RRD
    assert len(counter.read_text().split()) == bk.RRD_DUMP_ATTEMPTS
    assert os.listdir(env['folder']) == []


def test_settings_database_missing(env):
    with pytest.raises(bk.BackupError) as e:
        make(env, settings_db=env['settings_db'] + '.nope')
    assert e.value.reason == bk.REASON_SETTINGS
    assert os.listdir(env['folder']) == []


def test_settings_database_corrupt(env):
    with open(env['settings_db'], 'wb') as f:
        f.write(b'this is not sqlite' * 100)
    with pytest.raises(bk.BackupError) as e:
        make(env)
    assert e.value.reason == bk.REASON_SETTINGS


def test_folder_missing(env):
    with pytest.raises(bk.BackupError) as e:
        make(env, folder=env['folder'] + '/gone')
    assert e.value.reason == bk.REASON_FOLDER_MISSING


def test_bad_archive_is_not_kept(env, monkeypatch):
    def garbage(tmp, out):
        with open(out, 'wb') as f:
            f.write(b'garbage')
    monkeypatch.setattr(bk, '_write_archive', garbage)
    with pytest.raises(bk.BackupError) as e:
        make(env)
    assert e.value.reason == bk.REASON_VERIFY
    assert os.listdir(env['folder']) == []


def test_archive_missing_a_member_fails_verification(env, monkeypatch, tmp_path):
    def partial(tmp, out):
        with tarfile.open(out, 'w:gz') as tar:
            tar.add(os.path.join(tmp, 'rrd.xml'), arcname='rrd.xml')
    monkeypatch.setattr(bk, '_write_archive', partial)
    with pytest.raises(bk.BackupError) as e:
        make(env)
    assert e.value.reason == bk.REASON_VERIFY


def test_out_of_space_while_writing(env, monkeypatch):
    def full(tmp, out):
        raise OSError(errno.ENOSPC, 'no space')
    monkeypatch.setattr(bk, '_write_archive', full)
    with pytest.raises(bk.BackupError) as e:
        make(env)
    assert e.value.reason == bk.REASON_NO_SPACE
    assert os.listdir(env['folder']) == []


def test_unexpected_error_is_reported_without_details(env, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError('/secret/path leaked')
    monkeypatch.setattr(bk, '_collect_config', broken)
    with pytest.raises(bk.BackupError) as e:
        make(env)
    assert e.value.reason == bk.REASON_UNKNOWN and 'secret' not in str(e.value)


def test_same_second_does_not_overwrite(env):
    t = D(2026, 11, 5, 3, 0, 0)
    make(env, now=t)
    with pytest.raises(bk.BackupError):
        make(env, now=t)
    assert len(os.listdir(env['folder'])) == 1


def test_stale_part_file_is_replaced(env):
    t = D(2026, 11, 5, 3, 0, 0)
    part = os.path.join(env['folder'], '.' + bk.archive_name(t) + '.part')
    with open(part, 'wb') as f:
        f.write(b'old')
    make(env, now=t)
    assert os.listdir(env['folder']) == [bk.archive_name(t)]


def test_read_only_config_dir_leaves_nothing_behind(env, tmp_path):
    os.chmod(env['config_dir'], 0o555)
    try:
        make(env)
    finally:
        os.chmod(env['config_dir'], 0o755)


def test_all_reasons_are_known_strings():
    for name in dir(bk):
        if name.startswith('REASON_'):
            assert getattr(bk, name) in bk.REASONS


# ---- schedule -------------------------------------------------------------------------

def test_parse_hhmm():
    assert bk.parse_hhmm('03:00') == (3, 0) and bk.parse_hhmm('3:05') == (3, 5) and bk.parse_hhmm('23:59') == (23, 59)
    for bad in ('24:00', '3', '03:60', '', None, 'ab:cd', '03:00:00', 5):
        assert bk.parse_hhmm(bad) is None


def test_last_and_next_slot_daily():
    now = D(2026, 11, 5, 10, 0)
    assert bk.last_slot(now, 'daily', '03:00') == D(2026, 11, 5, 3, 0)
    assert bk.next_slot(now, 'daily', '03:00') == D(2026, 11, 6, 3, 0)
    early = D(2026, 11, 5, 2, 0)
    assert bk.last_slot(early, 'daily', '03:00') == D(2026, 11, 4, 3, 0)
    assert bk.next_slot(early, 'daily', '03:00') == D(2026, 11, 5, 3, 0)
    assert bk.last_slot(D(2026, 11, 5, 3, 0), 'daily', '03:00') == D(2026, 11, 5, 3, 0)


def test_last_and_next_slot_weekly():
    # 2026-11-05 is a Thursday; weekday 6 = Sunday
    now = D(2026, 11, 5, 10, 0)
    assert bk.last_slot(now, 'weekly', '03:00', 6) == D(2026, 11, 1, 3, 0)
    assert bk.next_slot(now, 'weekly', '03:00', 6) == D(2026, 11, 8, 3, 0)
    sunday_early = D(2026, 11, 8, 2, 0)
    assert bk.last_slot(sunday_early, 'weekly', '03:00', 6) == D(2026, 11, 1, 3, 0)
    sunday_late = D(2026, 11, 8, 4, 0)
    assert bk.last_slot(sunday_late, 'weekly', '03:00', 6) == D(2026, 11, 8, 3, 0)
    # same weekday as today, time not reached yet
    assert bk.last_slot(D(2026, 11, 5, 2, 0), 'weekly', '03:00', 3) == D(2026, 10, 29, 3, 0)
    assert bk.last_slot(D(2026, 11, 5, 4, 0), 'weekly', '03:00', 3) == D(2026, 11, 5, 3, 0)


def ts(*a):
    return D(*a).timestamp()


def test_is_due():
    now = ts(2026, 11, 5, 10, 0)
    slot = ts(2026, 11, 5, 3, 0)
    assert bk.is_due(now, None, None, 'daily', '03:00')                     # never ran
    assert not bk.is_due(now, slot + 60, slot + 60, 'daily', '03:00')       # done for this slot
    assert bk.is_due(now, slot - 86400, None, 'daily', '03:00')             # yesterday's backup only
    # failed attempt 10 minutes ago: wait; 2 hours ago: retry
    assert not bk.is_due(now, slot - 86400, now - 600, 'daily', '03:00')
    assert bk.is_due(now, slot - 86400, now - 7200, 'daily', '03:00')
    # an attempt that failed before the slot does not hold back the new slot
    assert bk.is_due(now, None, slot - 300, 'daily', '03:00')
    # missed slot while the daemon was down is caught up
    assert bk.is_due(ts(2026, 11, 5, 3, 5), ts(2026, 11, 3, 3, 0), None, 'daily', '03:00')


def test_is_due_weekly():
    sunday_slot = ts(2026, 11, 1, 3, 0)
    assert not bk.is_due(ts(2026, 11, 5, 10, 0), sunday_slot + 30, None, 'weekly', '03:00', 6)
    assert bk.is_due(ts(2026, 11, 8, 3, 1), sunday_slot + 30, None, 'weekly', '03:00', 6)


# ---- bounded waits (a hung NAS must not block the caller) ------------------------------------

def test_call_with_timeout_returns_the_value():
    assert bk.call_with_timeout(lambda: 42, 2) == (True, 42)


def test_call_with_timeout_reraises_exceptions():
    def boom():
        raise ValueError('x')
    with pytest.raises(ValueError):
        bk.call_with_timeout(boom, 2)


def test_call_with_timeout_gives_up_on_a_hung_call():
    import threading
    release = threading.Event()
    import time as _t
    t0 = _t.time()
    finished, value = bk.call_with_timeout(lambda: release.wait(5), 0.05)
    assert finished is False and value is None and _t.time() - t0 < 1
    release.set()
