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


# ---- restore: RRD rebuild, layout, swap ------------------------------------------------

FAKE_RRDTOOL = """#!/bin/sh
cmd="$1"
case "$cmd" in
  restore)
    if [ -n "$FAKE_FAIL_RESTORE" ] || [ -e "$3" ]; then echo broken >&2; exit 1; fi
    cp "$2" "$3" ;;
  info) cat "$2" ;;
  last) sed -n 's/^last_update = //p' "$2" ;;
  dump) cat "$2" ;;
  --version) echo "RRDtool 1.7.2 fake" ;;
  *) exit 2 ;;
esac
"""


def fake_rrd_tool(tmp_path, fail_restore=False):
    p = tmp_path / 'fakerrdtool'
    body = FAKE_RRDTOOL
    if fail_restore:
        body = body.replace('if [ -n "$FAKE_FAIL_RESTORE" ]', 'if true')
    p.write_bytes(body.encode())
    p.chmod(0o755)
    return str(p)


def fake_rrd_bytes(step=60, ds=('a', 'b'), last=1700000000):
    lines = ['step = %d' % step] + ['ds[%s].index = %d' % (n, i) for i, n in enumerate(ds)]
    lines.append('last_update = %d' % last)
    return ('\n'.join(lines) + '\n').encode()


def fake_rrd(path, **kw):
    with open(str(path), 'wb') as f:
        f.write(fake_rrd_bytes(**kw))
    return str(path)


def settings_db(path, rows=()):
    c = sqlite3.connect(str(path))
    c.execute("create table keyval (id text primary key, value text, confvalue text not null default '-')")
    for k, v in rows:
        c.execute('insert into keyval (id, value) values (?, ?)', (k, v))
    c.commit()
    c.close()
    return str(path)


def read_keyval(path):
    c = sqlite3.connect(str(path))
    try:
        return dict(c.execute('select id, value from keyval').fetchall())
    finally:
        c.close()


class World(object):
    pass


def make_world(tmp_path, live_ds=('a', 'b'), arch_ds=('a', 'b'), arch_last=1700000000, arch_step=60, live_step=60,
               two_dirs=False):
    w = World()
    w.data = tmp_path / 'data'
    w.data.mkdir()
    w.rrd_db = fake_rrd(w.data / 'pellmon.rrd', step=live_step, ds=live_ds, last=1600000000)
    if two_dirs:
        (tmp_path / 'nv').mkdir()
        w.nvdb = fake_rrd(tmp_path / 'nv' / 'pellmon.rrd', step=live_step, ds=live_ds, last=1600000000)
    else:
        w.nvdb = w.rrd_db
    w.settings = settings_db(w.data / 'pellmon_settings.db',
                             [('backup.config', 'LIVE-CONF'), ('backup.state', 'LIVE-STATE'), ('x', 'live-x')])
    arch_db = settings_db(tmp_path / 'arch.db', [('backup.config', 'ARCH-CONF'), ('x', 'arch-x')])
    with open(arch_db, 'rb') as f:
        db_bytes = f.read()
    w.arch_rrd = fake_rrd_bytes(step=arch_step, ds=arch_ds, last=arch_last)
    w.archive = _tar_with(tmp_path / NAME, [('manifest.json', MANIFEST, 0o644), ('pellmon_settings.db', db_bytes, 0o644),
                                            ('rrd.xml', w.arch_rrd, 0o644)])
    w.rrdtool = fake_rrd_tool(tmp_path)
    return w


def snapshot(w):
    out = {}
    for p in set([w.rrd_db, w.nvdb, w.settings]):
        with open(p, 'rb') as f:
            out[p] = (f.read(), os.stat(p).st_mtime_ns)
    return out


def leftovers(w):
    found = []
    for d in set([os.path.dirname(w.rrd_db), os.path.dirname(w.nvdb)]):
        for n in os.listdir(d):
            if n.endswith('.restore-new') or n == '.restore-tmp' or n.endswith('.pre-restore'):
                found.append(n)
    return found


def restore(w, **kw):
    return bk.restore_archive(w.archive, w.rrd_db, w.nvdb, w.settings, rrdtool=w.rrdtool, now=1700000100, **kw)


@posix_only
def test_validate_rrd_layout_parses_step_and_index_order(tmp_path):
    tool_path = fake_rrd_tool(tmp_path)
    p = tmp_path / 'x.rrd'
    p.write_text('step = 30\nds[b].index = 1\nds[a].index = 0\nds[c].index = 2\nlast_update = 5\n')
    assert bk.rrd_layout(tool_path, str(p)) == (30, ['a', 'b', 'c'])
    assert bk.rrd_last(tool_path, str(p)) == 5


@posix_only
def test_validate_build_rrd_failure(tmp_path):
    t = fake_rrd_tool(tmp_path, fail_restore=True)
    xml = fake_rrd(tmp_path / 'in.xml')
    out = str(tmp_path / 'out.rrd')
    with pytest.raises(bk.BackupError) as e:
        bk.build_rrd(t, xml, out)
    assert e.value.reason == bk.REASON_RESTORE_RRD
    assert not os.path.exists(out)


def test_validate_build_rrd_missing_binary(tmp_path):
    with pytest.raises(bk.BackupError) as e:
        bk.build_rrd(str(tmp_path / 'nonexistent-rrdtool'), str(tmp_path / 'a'), str(tmp_path / 'b'))
    assert e.value.reason == bk.REASON_RRD_MISSING


def test_validate_build_rrd_timeout_kwarg(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        seen['argv'] = argv
    monkeypatch.setattr(bk.subprocess, 'run', fake_run)
    bk.build_rrd('rrdtool', 'in.xml', str(tmp_path / 'o'))
    assert seen['timeout'] == bk.RRD_RESTORE_TIMEOUT
    assert seen['argv'][:2] == ['rrdtool', 'restore']


def test_validate_layout():
    base = (60, ['a', 'b'])
    bk.check_layout(base, (60, ['a', 'b']), None)
    for other in [(60, ['b', 'a']), (60, ['a', 'b', 'c']), (60, ['a']), (30, ['a', 'b'])]:
        with pytest.raises(bk.BackupError) as e:
            bk.check_layout(other, base, None)
        assert e.value.reason == bk.REASON_LAYOUT
    bk.check_layout(base, None, ['a', 'b'])
    with pytest.raises(bk.BackupError):
        bk.check_layout(base, None, ['a', 'c'])
    bk.check_layout(base, None, [])


def test_swap_carry_over(tmp_path):
    live = settings_db(tmp_path / 'live.db', [('backup.config', 'L1'), ('backup.state', 'L2')])
    staged = settings_db(tmp_path / 'staged.db', [('backup.config', 'S1'), ('other', 'o')])
    bk.carry_over_settings(live, staged)
    assert read_keyval(staged) == {'backup.config': 'L1', 'backup.state': 'L2', 'other': 'o'}


def test_swap_carry_over_missing_rows(tmp_path):
    live = settings_db(tmp_path / 'live.db', [('zzz', '1')])
    staged = settings_db(tmp_path / 'staged.db', [('backup.config', 'S1')])
    bk.carry_over_settings(live, staged)
    assert read_keyval(staged) == {'backup.config': 'S1'}
    bk.carry_over_settings(str(tmp_path / 'nolive.db'), staged)
    assert read_keyval(staged) == {'backup.config': 'S1'}


@posix_only
def test_swap_success(tmp_path):
    w = make_world(tmp_path)
    old_rrd = open(w.rrd_db, 'rb').read()
    old_set = open(w.settings, 'rb').read()
    steps = []
    res = restore(w, progress=steps.append)
    assert steps == list(bk.RESTORE_STEPS)
    assert open(w.rrd_db, 'rb').read() == w.arch_rrd
    assert open(w.rrd_db + '.pre-restore', 'rb').read() == old_rrd
    assert open(w.settings + '.pre-restore', 'rb').read() == old_set
    assert sorted(res['pre_restore']) == ['pellmon.rrd.pre-restore', 'pellmon_settings.db.pre-restore']
    assert stat.S_IMODE(os.stat(w.rrd_db + '.pre-restore').st_mode) == 0o600
    kv = read_keyval(w.settings)
    assert kv['backup.config'] == 'LIVE-CONF' and kv['backup.state'] == 'LIVE-STATE' and kv['x'] == 'arch-x'
    assert not [n for n in leftovers(w) if not n.endswith('.pre-restore')]


@posix_only
def test_swap_nvdb(tmp_path):
    w = make_world(tmp_path, two_dirs=True)
    res = restore(w)
    assert open(w.rrd_db, 'rb').read() == w.arch_rrd
    assert open(w.nvdb, 'rb').read() == w.arch_rrd
    assert os.path.isfile(w.nvdb + '.pre-restore') and os.path.isfile(w.rrd_db + '.pre-restore')
    assert len(res['pre_restore']) == 3
    assert not os.path.exists(str(tmp_path / 'nv' / '.restore-tmp'))


@posix_only
def test_swap_keeps_mode(tmp_path):
    w = make_world(tmp_path)
    os.chmod(w.rrd_db, 0o644)
    os.chmod(w.settings, 0o640)
    restore(w)
    assert stat.S_IMODE(os.stat(w.rrd_db).st_mode) == 0o644
    assert stat.S_IMODE(os.stat(w.settings).st_mode) == 0o600


@posix_only
def test_swap_lock_held(tmp_path, monkeypatch):
    import threading
    w = make_world(tmp_path)
    l1, l2 = threading.Lock(), threading.Lock()
    seen = []
    real = os.replace

    def checking(a, b):
        seen.append((l1.locked(), l2.locked()))
        return real(a, b)
    monkeypatch.setattr(bk.os, 'replace', checking)
    after = []
    restore(w, locks=(l1, l2), on_swapped=lambda: after.append((l1.locked(), l2.locked())))
    assert seen and all(s == (True, True) for s in seen)
    assert after == [(True, True)]
    assert not l1.locked() and not l2.locked()


@posix_only
def test_swap_should_continue_false(tmp_path):
    w = make_world(tmp_path)
    before = snapshot(w)
    with pytest.raises(bk.BackupError):
        restore(w, should_continue=lambda: False)
    assert snapshot(w) == before
    assert leftovers(w) == []


@posix_only
@pytest.mark.parametrize('kind', ['gzip', 'no_rrd', 'no_settings', 'bad_sqlite', 'rrd_fail', 'layout', 'future', 'space'])
def test_validate_failures_leave_live_untouched(tmp_path, monkeypatch, kind):
    kw = {}
    if kind == 'layout':
        kw['arch_ds'] = ('a', 'c')
    if kind == 'future':
        kw['arch_last'] = 1700000100 + bk.FUTURE_TOLERANCE + 1
    w = make_world(tmp_path, **kw)
    if kind == 'gzip':
        with open(w.archive, 'r+b') as f:
            f.seek(40)
            f.write(b'\xff' * 50)
    elif kind in ('no_rrd', 'no_settings', 'bad_sqlite'):
        db = open(str(tmp_path / 'arch.db'), 'rb').read()
        members = [('manifest.json', MANIFEST, 0o644), ('pellmon_settings.db', db, 0o644), ('rrd.xml', w.arch_rrd, 0o644)]
        if kind == 'no_rrd':
            members = members[:2]
        elif kind == 'no_settings':
            members = [members[0], members[2]]
        else:
            members[1] = ('pellmon_settings.db', b'not a database at all' * 100, 0o644)
        _tar_with(w.archive, members)
    elif kind == 'rrd_fail':
        w.rrdtool = fake_rrd_tool(tmp_path, fail_restore=True)
    elif kind == 'space':
        class U:
            free = 1
        monkeypatch.setattr(bk.shutil, 'disk_usage', lambda p: U)
    before = snapshot(w)
    with pytest.raises(bk.BackupError) as e:
        restore(w)
    assert e.value.reason in bk.REASONS
    assert snapshot(w) == before
    assert leftovers(w) == []


@posix_only
def test_validate_future_boundary_ok(tmp_path):
    w = make_world(tmp_path, arch_last=1700000100 + bk.FUTURE_TOLERANCE)
    restore(w)
    assert open(w.rrd_db, 'rb').read() == w.arch_rrd


@posix_only
def test_swap_rollback(tmp_path, monkeypatch):
    w = make_world(tmp_path)
    before = snapshot(w)
    real = os.replace
    calls = []

    def flaky(a, b):
        calls.append(b)
        if len(calls) == 2:
            raise OSError(5, 'boom')
        return real(a, b)
    monkeypatch.setattr(bk.os, 'replace', flaky)
    with pytest.raises(bk.BackupError) as e:
        restore(w)
    assert e.value.reason == bk.REASON_SWAP
    now = snapshot(w)
    assert {k: v[0] for k, v in now.items()} == {k: v[0] for k, v in before.items()}
    assert not [n for n in leftovers(w) if n.endswith('.restore-new') or n == '.restore-tmp']


def test_result_round_trip(tmp_path):
    bk.write_result(str(tmp_path), {'name': NAME, 'time': 12.5, 'ok': False, 'reason': bk.REASON_LAYOUT,
                                    'restart': 'auto', 'acknowledged': True})
    assert bk.read_result(str(tmp_path)) == {'name': NAME, 'time': 12.5, 'ok': False, 'reason': bk.REASON_LAYOUT,
                                             'restart': 'auto', 'acknowledged': True}
    if sys.platform != 'win32':
        assert stat.S_IMODE(os.stat(str(tmp_path / bk.RESULT_FILE)).st_mode) == 0o600
    assert [n for n in os.listdir(str(tmp_path)) if n.startswith('.restore-result-')] == []


def test_result_sanitised(tmp_path):
    p = tmp_path / bk.RESULT_FILE
    p.write_text(json.dumps({'name': '../etc/passwd', 'time': 'x', 'ok': False, 'reason': '<script>',
                             'restart': 'rm', 'acknowledged': 'yes'}))
    r = bk.read_result(str(tmp_path))
    assert r == {'name': '', 'time': None, 'ok': False, 'reason': bk.REASON_UNKNOWN, 'restart': 'manual',
                 'acknowledged': False}


def test_result_rejects_bad_files(tmp_path):
    assert bk.read_result(str(tmp_path)) is None
    p = tmp_path / bk.RESULT_FILE
    p.write_text('{not json')
    assert bk.read_result(str(tmp_path)) is None
    p.write_text(json.dumps({'name': 'x' * (bk.RESULT_MAX_BYTES + 10)}))
    assert bk.read_result(str(tmp_path)) is None
    p.unlink()
    if sys.platform != 'win32':
        target = tmp_path / 'real.json'
        target.write_text('{"ok": true}')
        os.symlink(str(target), str(p))
        assert bk.read_result(str(tmp_path)) is None


@pytest.mark.skipif(shutil.which('rrdtool') is None, reason='rrdtool not installed')
def test_roundtrip(tmp_path):
    import subprocess
    import time as _t
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    dst.mkdir()
    t0 = int(_t.time()) - 600

    def make(path):
        subprocess.run(['rrdtool', 'create', str(path), '--start', str(t0 - 10), '--step', '60',
                        'DS:a:GAUGE:120:U:U', 'DS:b:GAUGE:120:U:U', 'RRA:AVERAGE:0.5:1:100'], check=True)
    make(src / 'p.rrd')
    subprocess.run(['rrdtool', 'update', str(src / 'p.rrd'), '%d:1:2' % (t0 + 60), '%d:3:4' % (t0 + 120)], check=True)
    make(dst / 'p.rrd')
    sdb = settings_db(src / 's.db', [('x', 'y')])
    folder = tmp_path / 'folder'
    folder.mkdir()
    res = bk.create_archive(str(folder), str(src / 'p.rrd'), sdb, None, None)
    live_set = settings_db(dst / 's.db', [('backup.config', 'KEEP')])
    out = bk.restore_archive(os.path.join(str(folder), res['name']), str(dst / 'p.rrd'), str(dst / 'p.rrd'), live_set)
    assert out['pre_restore']
    assert bk.rrd_layout('rrdtool', str(dst / 'p.rrd')) == bk.rrd_layout('rrdtool', str(src / 'p.rrd'))
    assert bk.rrd_last('rrdtool', str(dst / 'p.rrd')) == bk.rrd_last('rrdtool', str(src / 'p.rrd'))
    assert read_keyval(live_set)['backup.config'] == 'KEEP'
