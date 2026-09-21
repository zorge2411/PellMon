"""Tests for tools/pellmon_backup.py (D-10): backup/restore of RRD + settings DB + config."""

import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sqlite3
import sys
import tarfile
import types
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "tools" / "pellmon_backup.py"
_spec = importlib.util.spec_from_file_location("pellmon_backup", _PATH)
pellmon_backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pellmon_backup)

needs_rrdtool = pytest.mark.skipif(shutil.which('rrdtool') is None,
                                   reason='rrdtool not installed')
posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='POSIX modes')


def _write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _container_style(tmp_path, dbval='/var/lib/pellmon/rrd.db'):
    if os.path.isdir('/etc/pellmon/conf.d'):
        pytest.skip('real install present at /etc/pellmon/conf.d')
    conf = _write(tmp_path / 'config' / 'pellmon.conf',
                  '[conf]\ndatabase = /x/pellmon.rrd\nconfig_dir = /etc/pellmon/conf.d\n')
    _write(tmp_path / 'config' / 'conf.d' / 'database.conf',
           '[conf]\ndatabase = %s\n' % dbval)
    return conf


def test_conf_d_overrides_pellmon_conf(tmp_path):
    conf = _write(tmp_path / 'pellmon.conf',
                  '[conf]\ndatabase = /x/pellmon.rrd\nconfig_dir = %s\n' % (tmp_path / 'conf.d'))
    _write(tmp_path / 'conf.d' / 'database.conf', '[conf]\ndatabase = /y/rrd.db\n')
    cfg = pellmon_backup.read_effective_config(str(conf))
    assert cfg['database'] == '/y/rrd.db'
    assert cfg['settings_db'] == '/y/pellmon_settings.db'


def test_container_config_dir_falls_back_to_host_sibling(tmp_path):
    conf = _container_style(tmp_path, '/y/rrd.db')
    assert pellmon_backup.read_effective_config(str(conf))['database'] == '/y/rrd.db'
    other = _write(tmp_path / 'other' / 'database.conf', '[conf]\ndatabase = /z/rrd.db\n')
    cfg = pellmon_backup.read_effective_config(str(conf), host_config_dir=str(other.parent))
    assert cfg['database'] == '/z/rrd.db'


def test_host_config_dir_option_reaches_helper(tmp_path, monkeypatch):
    conf = _container_style(tmp_path)
    other = _write(tmp_path / 'other' / 'database.conf', '[conf]\ndatabase = /z/rrd.db\n')
    seen = {}

    def fake_backup(cfg, out):
        seen.update(cfg)

    monkeypatch.setattr(pellmon_backup, 'backup_local', fake_backup)
    rc = pellmon_backup.main(['backup', '--local', '--config', str(conf),
                              '--host-config-dir', str(other.parent),
                              '--out', str(tmp_path / 'o.tgz')])
    assert rc == 0
    assert seen['database'] == '/z/rrd.db'


def test_missing_database_is_an_error(tmp_path, capsys):
    conf = _write(tmp_path / 'pellmon.conf',
                  '[conf]\nconfig_dir = %s\n' % (tmp_path / 'conf.d'))
    (tmp_path / 'conf.d').mkdir()
    out = tmp_path / 'out.tgz'
    rc = pellmon_backup.main(['backup', '--local', '--config', str(conf), '--out', str(out)])
    err = capsys.readouterr().err
    assert rc != 0
    assert str(conf) in err and 'database' in err
    assert 'pellmon.rrd' not in err and 'rrd.db' not in err
    assert not out.exists()


def _make_rrd_setup(tmp_path):
    from Pellmonsrv.database import Keyval_storage
    data = tmp_path / 'data'
    data.mkdir()
    rrd = data / 'rrd.db'
    subprocess.run(['rrdtool', 'create', str(rrd), '--step', '10',
                    'DS:t:GAUGE:40:U:U', 'RRA:AVERAGE:0.5:1:100'], check=True)
    settings = data / 'pellmon_settings.db'
    Keyval_storage(str(settings)).writeval('k', 'v1')
    conf = _write(tmp_path / 'config' / 'pellmon.conf',
                  '[conf]\ndatabase = %s\nconfig_dir = %s\n' % (rrd, tmp_path / 'config' / 'conf.d'))
    (tmp_path / 'config' / 'conf.d').mkdir()
    return conf, rrd, settings, Keyval_storage


@needs_rrdtool
def test_local_round_trip(tmp_path):
    conf, rrd, settings, Keyval = _make_rrd_setup(tmp_path)
    archive = tmp_path / 'b.tar.gz'
    assert pellmon_backup.main(['backup', '--local', '--config', str(conf),
                                '--out', str(archive)]) == 0
    if sys.platform != 'win32':
        assert stat.S_IMODE(os.stat(archive).st_mode) == 0o600
    with tarfile.open(archive) as t:
        names = t.getnames()
    for n in ('rrd.xml', 'pellmon_settings.db', 'manifest.json'):
        assert n in names
    assert any(n == 'config' or n.startswith('config/') for n in names)
    rrd.unlink()
    settings.unlink()
    assert pellmon_backup.main(['restore', '--local', '--yes', '--config', str(conf), str(archive)]) == 0
    info = subprocess.run(['rrdtool', 'info', str(rrd)], capture_output=True, text=True).stdout
    assert 'ds[t]' in info and 'step = 10' in info
    assert Keyval(str(settings)).readval('k') == 'v1'


@pytest.mark.parametrize('member', ['../evil', '/etc/evil'])
def test_restore_rejects_traversal(tmp_path, member):
    conf = _write(tmp_path / 'pellmon.conf',
                  '[conf]\ndatabase = %s\nconfig_dir = %s\n' % (tmp_path / 'd' / 'rrd.db', tmp_path / 'cd'))
    bad = tmp_path / 'bad.tar.gz'
    with tarfile.open(bad, 'w:gz') as t:
        ti = tarfile.TarInfo(member)
        ti.size = 4
        t.addfile(ti, io.BytesIO(b'evil'))
    rc = pellmon_backup.main(['restore', '--local', '--config', str(conf), str(bad)])
    assert rc != 0
    assert not (tmp_path.parent / 'evil').exists()
    assert not os.path.exists('/etc/evil')


def test_restore_rejects_symlink(tmp_path):
    conf = _write(tmp_path / 'pellmon.conf',
                  '[conf]\ndatabase = %s\nconfig_dir = %s\n' % (tmp_path / 'd' / 'rrd.db', tmp_path / 'cd'))
    bad = tmp_path / 'bad.tar.gz'
    with tarfile.open(bad, 'w:gz') as t:
        ti = tarfile.TarInfo('link')
        ti.type = tarfile.SYMTYPE
        ti.linkname = '/etc/passwd'
        t.addfile(ti)
    assert pellmon_backup.main(['restore', '--local', '--config', str(conf), str(bad)]) != 0


def _fake_run(calls):
    def fake(argv, **kw):
        assert kw.get('shell') is not True
        calls.append(argv)
        out = kw.get('stdout')
        if out is not None and hasattr(out, 'write'):
            out.write(b'<rrd/>')
        return types.SimpleNamespace(returncode=0, stdout=b'rrdtool 1.7', stderr=b'')
    return fake


def test_docker_backup_argv(tmp_path, monkeypatch):
    conf = _container_style(tmp_path)
    calls = []
    monkeypatch.setattr(pellmon_backup, '_run', _fake_run(calls))
    # the docker cp of the settings copy is faked: create the destination file
    real_run = pellmon_backup._run

    def run_and_touch(argv, **kw):
        r = real_run(argv, **kw)
        if len(argv) > 5 and argv[4] == 'cp':
            open(argv[-1], 'wb').close()
        return r
    monkeypatch.setattr(pellmon_backup, '_run', run_and_touch)
    cf = str(tmp_path / 'docker-compose.yml')
    out = tmp_path / 'o.tgz'
    rc = pellmon_backup.main(['backup', '--compose-file', cf, '--config', str(conf),
                              '--out', str(out)])
    assert rc == 0
    expected = ['docker', 'compose', '-f', cf, 'exec', '-T', 'pellmonsrv',
                'rrdtool', 'dump', '/var/lib/pellmon/rrd.db']
    assert expected in calls
    assert all(isinstance(a, str) for c in calls for a in c)


def test_docker_restore_stops_then_starts(tmp_path, monkeypatch):
    conf = _container_style(tmp_path)
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'rrd.xml').write_text('<rrd/>')
    (src / 'pellmon_settings.db').write_bytes(b'x')
    (src / 'manifest.json').write_text('{}')
    arc = tmp_path / 'a.tgz'
    with tarfile.open(arc, 'w:gz') as t:
        for n in ('rrd.xml', 'pellmon_settings.db', 'manifest.json'):
            t.add(src / n, arcname=n)
    calls = []
    monkeypatch.setattr(pellmon_backup, '_run', _fake_run(calls))
    cf = str(tmp_path / 'docker-compose.yml')
    rc = pellmon_backup.main(['restore', '--compose-file', cf, '--config', str(conf),
                              '--yes', str(arc)])
    assert rc == 0
    pre = ['docker', 'compose', '-f', cf]
    assert calls[0] == pre + ['stop', 'pellmonsrv']
    assert calls[-1] == pre + ['up', '-d', 'pellmonsrv']
    assert any(c[4] == 'run' for c in calls)


def _local_restore_env(tmp_path, monkeypatch):
    """A local config, an existing RRD/settings pair and an archive that can be restored."""
    data = tmp_path / 'data'
    data.mkdir()
    rrd = data / 'rrd.db'
    rrd.write_bytes(b'OLD-RRD')
    settings = data / 'pellmon_settings.db'
    con = sqlite3.connect(str(settings))
    con.execute('create table keyval (id text, value text)')
    con.execute("insert into keyval values ('k', 'old')")
    con.commit()
    con.close()
    conf = _write(tmp_path / 'config' / 'pellmon.conf',
                  '[conf]' + chr(10) + 'database = %s' % rrd + chr(10) + 'config_dir = %s' % (tmp_path / 'config' / 'conf.d') + chr(10))
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'rrd.xml').write_text('<rrd/>')
    newdb = src / 'pellmon_settings.db'
    con = sqlite3.connect(str(newdb))
    con.execute('create table keyval (id text, value text)')
    con.execute("insert into keyval values ('k', 'new')")
    con.commit()
    con.close()
    arc = tmp_path / 'a.tgz'
    with tarfile.open(arc, 'w:gz') as t:
        for n in ('rrd.xml', 'pellmon_settings.db'):
            t.add(src / n, arcname=n)
    monkeypatch.setattr(pellmon_backup, '_require_rrdtool', lambda: None)
    return conf, rrd, settings, arc


def _fake_rrdtool(fail_restore=False):
    def fake(argv, **kw):
        if argv[:2] == ['rrdtool', 'restore']:
            if fail_restore:
                raise subprocess.CalledProcessError(1, argv)
            Path(argv[-1]).write_bytes(b'NEW-RRD')
        return types.SimpleNamespace(returncode=0, stdout=b'', stderr=b'')
    return fake


def test_failed_local_restore_leaves_originals_intact(tmp_path, monkeypatch, capsys):
    conf, rrd, settings, arc = _local_restore_env(tmp_path, monkeypatch)
    monkeypatch.setattr(pellmon_backup, '_run', _fake_rrdtool(fail_restore=True))
    rc = pellmon_backup.main(['restore', '--local', '--yes', '--config', str(conf), str(arc)])
    assert rc != 0
    assert rrd.read_bytes() == b'OLD-RRD'
    con = sqlite3.connect(str(settings))
    assert con.execute("select value from keyval where id='k'").fetchone()[0] == 'old'
    con.close()
    assert sorted(os.listdir(rrd.parent)) == ['pellmon_settings.db', 'rrd.db']


def test_local_restore_keeps_pre_restore_copies(tmp_path, monkeypatch):
    conf, rrd, settings, arc = _local_restore_env(tmp_path, monkeypatch)
    (rrd.parent / 'rrd.db.pre-restore').write_bytes(b'ANCIENT')
    monkeypatch.setattr(pellmon_backup, '_run', _fake_rrdtool())
    rc = pellmon_backup.main(['restore', '--local', '--yes', '--config', str(conf), str(arc)])
    assert rc == 0
    assert rrd.read_bytes() == b'NEW-RRD'
    assert (rrd.parent / 'rrd.db.pre-restore').read_bytes() == b'OLD-RRD'
    pre = rrd.parent / 'pellmon_settings.db.pre-restore'
    con = sqlite3.connect(str(pre))
    assert con.execute("select value from keyval where id='k'").fetchone()[0] == 'old'
    con.close()
    con = sqlite3.connect(str(settings))
    assert con.execute("select value from keyval where id='k'").fetchone()[0] == 'new'
    con.close()
    if sys.platform != 'win32':
        for p in (rrd.parent / 'rrd.db.pre-restore', pre, settings):
            assert stat.S_IMODE(os.stat(p).st_mode) == 0o600, p
    assert not [n for n in os.listdir(rrd.parent) if n.endswith('.restore-new')]


def test_local_restore_without_yes_refuses_non_interactive(tmp_path, monkeypatch, capsys):
    conf, rrd, settings, arc = _local_restore_env(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(pellmon_backup, '_run', _fake_run(calls))
    monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
    rc = pellmon_backup.main(['restore', '--local', '--config', str(conf), str(arc)])
    assert rc != 0
    assert 'not confirmed' in capsys.readouterr().err
    assert rrd.read_bytes() == b'OLD-RRD'
    assert calls == []


def test_docker_restore_failure_restarts_and_explains(tmp_path, monkeypatch, capsys):
    conf = _container_style(tmp_path)
    src = tmp_path / 'src'
    src.mkdir()
    (src / 'rrd.xml').write_text('<rrd/>')
    arc = tmp_path / 'a.tgz'
    with tarfile.open(arc, 'w:gz') as t:
        t.add(src / 'rrd.xml', arcname='rrd.xml')
    calls = []
    ok = _fake_run(calls)

    def run(argv, **kw):
        if 'run' in argv[:6]:
            calls.append(argv)
            raise subprocess.CalledProcessError(1, argv)
        return ok(argv, **kw)
    monkeypatch.setattr(pellmon_backup, '_run', run)
    cf = str(tmp_path / 'docker-compose.yml')
    rc = pellmon_backup.main(['restore', '--compose-file', cf, '--config', str(conf),
                              '--yes', str(arc)])
    assert rc != 0
    assert calls[-1] == ['docker', 'compose', '-f', cf, 'up', '-d', 'pellmonsrv']
    err = capsys.readouterr().err
    assert 'up -d pellmonsrv' in err and 'pre-restore' in err
