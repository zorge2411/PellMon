# -*- coding: utf-8 -*-
"""Phase 13 restore engine (Pellmonsrv/backup_core.py): name allow-list, archive checks, extractor parity."""

import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import sys
import tarfile

import pytest

from Pellmonsrv import backup_core as bk

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location('pellmon_backup_tool', os.path.join(ROOT, 'tools', 'pellmon_backup.py'))
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX modes')
NAME = 'pellmon-backup-20260101-000000.tar.gz'
MANIFEST = json.dumps({'format': 1, 'created': '2026-01-01T00:00:00+00:00', 'machine': 'x86_64',
                       'rrdtool_version': 'RRDtool 1.7.2', 'created_by': 'test', 'rrd_path': '/secret/rrd.db',
                       'config_dir': '/secret/conf.d', 'host_config_dir': None}).encode()


def keyval_db_bytes(tmp_path, name='k.db', schema='create table keyval (id text primary key, value text, '
                                                  "confvalue text not null default '-')"):
    p = str(tmp_path / name)
    c = sqlite3.connect(p)
    c.execute(schema)
    c.commit()
    c.close()
    with open(p, 'rb') as f:
        return f.read()


def _tar_with(path, members):
    """members: (name, bytes_or_None, mode) or a ready TarInfo (with optional data)"""
    with tarfile.open(str(path), 'w:gz') as tar:
        for item in members:
            if isinstance(item, tarfile.TarInfo):
                tar.addfile(item)
                continue
            name, data, mode = item
            ti = tarfile.TarInfo(name)
            ti.mode = mode
            ti.size = len(data)
            tar.addfile(ti, io.BytesIO(data))
    return str(path)


def good_members(db, with_config=True):
    m = []
    if with_config:
        m.append(('config/pellmon.conf', b'[conf]\n', 0o644))
    m += [('manifest.json', MANIFEST, 0o644), ('pellmon_settings.db', db, 0o644), ('rrd.xml', b'<rrd/>', 0o644)]
    return m


def _special(name, typ, linkname=''):
    ti = tarfile.TarInfo(name)
    ti.type = typ
    ti.linkname = linkname
    return ti


# ---- names ----------------------------------------------------------------------------

def test_name_accepts_listed(tmp_path):
    (tmp_path / NAME).write_bytes(b'x')
    assert bk.validate_archive_name(str(tmp_path), NAME) == os.path.abspath(str(tmp_path / NAME))


@pytest.mark.parametrize('name', ['../x', 'a/b.tar.gz', NAME + '.part', 'pellmon-backup-20260102-000000.tar.gz',
                                  None, 5, NAME + '\n'])
def test_name_rejects(tmp_path, name):
    (tmp_path / NAME).write_bytes(b'x')
    with pytest.raises(bk.BackupError) as e:
        bk.validate_archive_name(str(tmp_path), name)
    assert e.value.reason == bk.REASON_ARCHIVE_NOT_FOUND


def test_name_rejects_directory(tmp_path):
    (tmp_path / NAME).mkdir()
    with pytest.raises(bk.BackupError) as e:
        bk.validate_archive_name(str(tmp_path), NAME)
    assert e.value.reason == bk.REASON_ARCHIVE_NOT_FOUND


@posix_only
def test_name_rejects_symlink(tmp_path):
    (tmp_path / 'real').write_bytes(b'x')
    os.symlink(str(tmp_path / 'real'), str(tmp_path / NAME))
    with pytest.raises(bk.BackupError) as e:
        bk.validate_archive_name(str(tmp_path), NAME)
    assert e.value.reason == bk.REASON_ARCHIVE_NOT_FOUND


# ---- extractor parity -----------------------------------------------------------------

def _malicious(tmp_path):
    kinds = {
        'traversal': [('../evil', b'x', 0o644)],
        'absolute': [('/etc/evil', b'x', 0o644)],
        'symlink': [_special('link', tarfile.SYMTYPE, '/etc/passwd')],
        'hardlink': [_special('hard', tarfile.LNKTYPE, 'manifest.json')],
        'chardev': [_special('dev', tarfile.CHRTYPE)],
        'fifo': [_special('fifo', tarfile.FIFOTYPE)],
        'oversize': [('big', b'x' * 40, 0o644)],
    }
    out = {}
    for k, members in kinds.items():
        out[k] = _tar_with(tmp_path / (k + '.tar.gz'), members)
    return out


@pytest.mark.parametrize('kind', ['traversal', 'absolute', 'symlink', 'hardlink', 'chardev', 'fifo', 'oversize'])
def test_extract_parity(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(tool, 'MAX_EXTRACT_BYTES', 10)
    monkeypatch.setattr(bk, 'MAX_EXTRACT_BYTES', 10)
    path = _malicious(tmp_path)[kind]
    d1, d2 = tmp_path / 'd1', tmp_path / 'd2'
    d1.mkdir()
    d2.mkdir()
    with tarfile.open(path, 'r:gz') as t:
        with pytest.raises(ValueError):
            tool._safe_extract(t, str(d1))
    with tarfile.open(path, 'r:gz') as t:
        with pytest.raises(bk.BackupError) as e:
            bk.safe_extract(t, str(d2))
    assert e.value.reason == bk.REASON_ARCHIVE_UNSAFE
    assert os.listdir(str(d2)) == []
    assert not (tmp_path / 'evil').exists()


def test_extract_only_needed_members(tmp_path):
    path = _tar_with(tmp_path / 'a.tar.gz', good_members(b'db'))
    dest = tmp_path / 'dest'
    dest.mkdir()
    with tarfile.open(path, 'r:gz') as t:
        bk.safe_extract(t, str(dest), only=bk.RESTORE_MEMBERS)
    assert sorted(os.listdir(str(dest))) == sorted(bk.RESTORE_MEMBERS)
    assert not (dest / 'config').exists()


@posix_only
def test_extract_modes(tmp_path):
    path = _tar_with(tmp_path / 'a.tar.gz', [('rrd.xml', b'x', 0o6755)])
    dest = tmp_path / 'dest'
    dest.mkdir()
    with tarfile.open(path, 'r:gz') as t:
        bk.safe_extract(t, str(dest))
    mode = stat.S_IMODE(os.stat(str(dest / 'rrd.xml')).st_mode)
    assert mode & 0o7000 == 0
    assert mode & 0o600 == 0o600


def test_extract_never_uses_extractall(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError('extractall used')
    monkeypatch.setattr(tarfile.TarFile, 'extractall', boom)
    path = _tar_with(tmp_path / 'a.tar.gz', good_members(b'db'))
    dest = tmp_path / 'dest'
    dest.mkdir()
    with tarfile.open(path, 'r:gz') as t:
        bk.safe_extract(t, str(dest), only=bk.RESTORE_MEMBERS)
    assert (dest / 'rrd.xml').exists()


# ---- validation -----------------------------------------------------------------------

def test_validate_good(tmp_path):
    path = _tar_with(tmp_path / 'a.tar.gz', good_members(b'db'))
    info = bk.check_archive(path)
    assert info['has_config'] is True
    assert info['sizes']['rrd.xml'] == 6
    assert info['manifest']['machine'] == 'x86_64'


@pytest.mark.parametrize('fn', ['check_archive', 'preview_archive'])
def test_validate_damaged_gzip(tmp_path, fn):
    path = _tar_with(tmp_path / 'a.tar.gz', good_members(b'x' * 100000))
    data = open(path, 'rb').read()
    with open(path, 'wb') as f:
        f.write(data[:len(data) // 2])
    with pytest.raises(bk.BackupError) as e:
        getattr(bk, fn)(path)
    assert e.value.reason == bk.REASON_ARCHIVE_DAMAGED


def test_validate_not_gzip(tmp_path):
    p = tmp_path / 'a.tar.gz'
    p.write_bytes(b'not a gzip at all')
    with pytest.raises(bk.BackupError) as e:
        bk.check_archive(str(p))
    assert e.value.reason == bk.REASON_ARCHIVE_DAMAGED


@pytest.mark.parametrize('drop', ['rrd.xml', 'pellmon_settings.db', 'manifest.json'])
def test_validate_missing_member(tmp_path, drop):
    members = [m for m in good_members(b'db') if m[0] != drop]
    path = _tar_with(tmp_path / 'a.tar.gz', members)
    with pytest.raises(bk.BackupError) as e:
        bk.check_archive(path)
    assert e.value.reason == bk.REASON_ARCHIVE_INCOMPLETE


@pytest.mark.parametrize('manifest', [b'not json', b'x' * (bk.MANIFEST_MAX_BYTES + 1), b'{"format": 2}', b'[1]'],
                         ids=['notjson', 'toolarge', 'format2', 'list'])
def test_validate_bad_manifest(tmp_path, manifest):
    members = [('manifest.json', manifest, 0o644), ('pellmon_settings.db', b'db', 0o644), ('rrd.xml', b'<rrd/>', 0o644)]
    path = _tar_with(tmp_path / 'a.tar.gz', members)
    with pytest.raises(bk.BackupError) as e:
        bk.check_archive(path)
    assert e.value.reason == bk.REASON_ARCHIVE_DAMAGED


def test_validate_unsafe_member(tmp_path):
    path = _tar_with(tmp_path / 'a.tar.gz', good_members(b'db') + [('../evil', b'x', 0o644)])
    with pytest.raises(bk.BackupError) as e:
        bk.check_archive(path)
    assert e.value.reason == bk.REASON_ARCHIVE_UNSAFE


def test_preview_whitelist(tmp_path):
    long = json.dumps({'format': 1, 'machine': 'm' * 500, 'rrd_path': '/p', 'config_dir': '/c',
                       'host_config_dir': '/h', 'created': 5}).encode()
    members = [('config/x', b'1', 0o644), ('manifest.json', long, 0o644), ('rrd.xml', b'<rrd/>', 0o644)]
    info = bk.preview_archive(_tar_with(tmp_path / 'a.tar.gz', members))
    assert info['has_config'] is True
    assert set(info['manifest']) <= set(bk.MANIFEST_FIELDS)
    assert len(info['manifest']['machine']) == 200
    assert info['manifest']['created'] == '5'
    assert 'rrd_path' not in info['manifest']


def test_preview_no_manifest(tmp_path):
    path = _tar_with(tmp_path / 'a.tar.gz', [('rrd.xml', b'<rrd/>', 0o644)])
    with pytest.raises(bk.BackupError) as e:
        bk.preview_archive(path)
    assert e.value.reason == bk.REASON_ARCHIVE_INCOMPLETE


def test_validate_settings_db_ok(tmp_path):
    bk.verify_sqlite(str(_write(tmp_path, 'ok.db', keyval_db_bytes(tmp_path))))


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_validate_settings_db_bad(tmp_path):
    cases = {
        'random': os.urandom(4096),
        'notable': keyval_db_bytes(tmp_path, 'n.db', 'create table other (a text)'),
        'nocols': keyval_db_bytes(tmp_path, 'c.db', 'create table keyval (a text, b text)'),
    }
    for name, data in cases.items():
        p = _write(tmp_path, 'x-' + name + '.db', data)
        with pytest.raises(bk.BackupError) as e:
            bk.verify_sqlite(str(p))
        assert e.value.reason == bk.REASON_ARCHIVE_SETTINGS, name


def test_reasons_registered():
    assert len(bk.REASONS) == 21 and bk.REASON_SWAP in bk.REASONS


# ---- staging --------------------------------------------------------------------------

@posix_only
def test_staging_fresh(tmp_path):
    old = tmp_path / bk.STAGING_DIR
    old.mkdir()
    (old / 'junk').write_bytes(b'x')
    s = bk.prepare_staging(str(tmp_path))
    assert s == str(old)
    assert os.listdir(s) == []
    assert stat.S_IMODE(os.stat(s).st_mode) == 0o700


def test_staging_leftovers(tmp_path):
    (tmp_path / bk.STAGING_DIR).mkdir()
    rrd, nvdb, sdb = [str(tmp_path / n) for n in ('rrd.db', 'nv.db', 's.db')]
    for p in (rrd, sdb):
        open(p, 'wb').write(b'live')
        open(p + bk.PRE_SUFFIX, 'wb').write(b'pre')
    for p in (rrd, nvdb, sdb):
        open(p + bk.NEW_SUFFIX, 'wb').write(b'new')
    bk.clean_restore_leftovers(str(tmp_path), [rrd, nvdb, sdb, None])
    assert sorted(os.listdir(str(tmp_path))) == ['rrd.db', 'rrd.db.pre-restore', 's.db', 's.db.pre-restore']
    bk.clean_restore_leftovers(str(tmp_path), [rrd, None])  # nothing left: must not raise


@posix_only
def test_staging_symlink(tmp_path):
    victim = tmp_path / 'victim'
    victim.mkdir()
    (victim / 'keep').write_bytes(b'x')
    data = tmp_path / 'data'
    data.mkdir()
    os.symlink(str(victim), str(data / bk.STAGING_DIR))
    s = bk.prepare_staging(str(data))
    assert not os.path.islink(s)
    assert (victim / 'keep').exists()


def test_staging_space_refused(tmp_path, monkeypatch):
    rrd = tmp_path / 'rrd.db'
    rrd.write_bytes(b'x' * 1000)
    sizes = {'rrd.xml': 500, 'pellmon_settings.db': 100}
    needed = 600 + 2000 + bk.RESTORE_SPACE_MARGIN
    Usage = shutil._ntuple_diskusage

    def usage(free):
        return lambda p: Usage(10 ** 12, 0, free)
    monkeypatch.setattr(shutil, 'disk_usage', usage(needed - 1))
    with pytest.raises(bk.BackupError) as e:
        bk.check_restore_space(str(tmp_path), sizes, str(rrd))
    assert e.value.reason == bk.REASON_RESTORE_SPACE
    monkeypatch.setattr(shutil, 'disk_usage', usage(needed))
    bk.check_restore_space(str(tmp_path), sizes, str(rrd))
    # live rrd missing counts as 0
    monkeypatch.setattr(shutil, 'disk_usage', usage(600 + bk.RESTORE_SPACE_MARGIN))
    bk.check_restore_space(str(tmp_path), sizes, str(tmp_path / 'missing.db'))

    def boom(p):
        raise OSError(5, 'io')
    monkeypatch.setattr(shutil, 'disk_usage', boom)
    bk.check_restore_space(str(tmp_path), sizes, str(rrd))
