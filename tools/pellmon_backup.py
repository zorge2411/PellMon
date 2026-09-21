#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

PellMon backup / restore.

Produces one .tar.gz holding the RRD as a portable XML dump (raw RRD files
are not portable between machine types, e.g. PC to Raspberry Pi), a
consistent copy of the settings database and the config folder.

    pellmon_backup.py backup  [--local] [--out FILE]
    pellmon_backup.py restore [--local] [--with-config] [--yes] FILE

Default mode drives the running docker compose stack (rrdtool and python3
are taken from the pellmon image, no host rrdtool or sqlite3 needed);
--local works on direct paths.

SECURITY: the archive contains password hashes and the settings database
(future MQTT secret). It is created mode 0600; keep it off shared storage.

NOTE: [conf] config_dir in pellmon.conf is the path INSIDE the container
(/etc/pellmon/conf.d). In docker mode this tool runs on the host and reads the
host copy next to pellmon.conf (or --host-config-dir), never a same-named host
directory; with --local the configured config_dir is used first. The database/settings_db
values are used exactly as written (container paths in docker mode, host
paths with --local).
"""

import argparse
import configparser
import datetime
import json
import logging
import os
import pathlib
import platform
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

logger = logging.getLogger('pellmon_backup')

# executed inside the container; the two paths come from the config
# read-only URI: a wrong path must fail instead of silently creating an empty database;
# umask 077 keeps the temporary copy (password hashes/secrets) private inside the container
_SETTINGS_BACKUP_SCRIPT = (
    "import os,sqlite3,urllib.parse; os.umask(0o077); "
    "s=sqlite3.connect('file:'+urllib.parse.quote(%r)+'?mode=ro', uri=True); "
    "d=sqlite3.connect(%r); s.backup(d); d.close(); s.close()")
# refuse absurd archives (tar bomb); a multi-year RRD dump is far below this
MAX_EXTRACT_BYTES = 4 * 1024 ** 3
_TMP_SETTINGS = '/tmp/pellmon_settings_backup.db'


def _run(argv, stdout=None, check=True, capture=False):
    """Single choke point for external commands: list argv, never a shell."""
    logger.debug('run: %r', argv)
    kw = {}
    if capture:
        kw['stdout'] = subprocess.PIPE
        kw['stderr'] = subprocess.PIPE
    elif stdout is not None:
        kw['stdout'] = stdout
    return subprocess.run(argv, check=check, **kw)


def resolve_config_dir(conf_file, configured_dir, host_config_dir=None, local=False):
    if host_config_dir:
        d = os.path.abspath(os.path.expanduser(host_config_dir))
        logger.debug('conf.d: using --host-config-dir %s', d)
        return d
    # --local: config_dir is a real host path. Docker mode: it is the in-container path, and a
    # same-named directory that happens to exist on the host must not shadow ./config/conf.d.
    if local and configured_dir and os.path.isdir(configured_dir):
        logger.debug('conf.d: configured config_dir %s exists on this host', configured_dir)
        return configured_dir
    sibling = os.path.join(os.path.dirname(os.path.abspath(conf_file)), 'conf.d')
    if os.path.isdir(sibling):
        logger.debug('conf.d: config_dir %s not on host, using %s', configured_dir, sibling)
        return sibling
    return None


def read_effective_config(conf_file, host_config_dir=None, local=False):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if not parser.read(conf_file):
        raise ValueError("cannot read config file %s" % conf_file)
    configured = parser.get('conf', 'config_dir', fallback=None)
    resolved = resolve_config_dir(conf_file, configured, host_config_dir, local)
    if resolved:
        for root, dirs, files in os.walk(resolved):
            dirs.sort()
            for name in sorted(files):
                if name.endswith('.conf'):
                    parser.read(os.path.join(root, name))
    database = parser.get('conf', 'database', fallback=None)
    if not database:
        raise ValueError("no 'database' value found in %s or %s" %
                         (conf_file, resolved or '<no conf.d dir found>'))
    settings_db = parser.get('conf', 'settings_db', fallback=None) or \
        os.path.join(os.path.dirname(database), 'pellmon_settings.db')
    for key, value in (('database', database), ('settings_db', settings_db)):
        if value.startswith('-'):
            raise ValueError("%s value %r must not start with '-'" % (key, value))
    return {'database': database, 'settings_db': settings_db,
            'config_dir': configured, 'host_config_dir': resolved,
            'conf_file': conf_file}


def build_manifest(cfg, rrd_version):
    return {
        'format': 1,
        'created': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'rrd_filename': os.path.basename(cfg['database']),
        'rrd_path': cfg['database'],
        'settings_filename': os.path.basename(cfg['settings_db']),
        'machine': platform.machine(),
        'rrdtool_version': rrd_version,
        'config_dir': cfg['config_dir'],
        'host_config_dir': cfg['host_config_dir'],
    }


def _dump_with_retry(argv, xml_path):
    last = None
    for attempt in range(3):
        try:
            with open(xml_path, 'wb') as f:
                _run(argv, stdout=f)
            return
        except subprocess.CalledProcessError as e:
            last = e
            logger.warning('rrdtool dump failed (attempt %d), retrying', attempt + 1)
            time.sleep(1)
    raise last


def _collect_config(cfg, tmp):
    dest = os.path.join(tmp, 'config')
    os.makedirs(dest)
    shutil.copy2(cfg['conf_file'], os.path.join(dest, os.path.basename(cfg['conf_file'])))
    if cfg['host_config_dir']:
        shutil.copytree(cfg['host_config_dir'], os.path.join(dest, 'conf.d'), symlinks=False)
    else:
        logger.warning('no conf.d directory found, config archived without it')


def _write_archive(tmp, out_path):
    # O_EXCL: never truncate/reuse an existing file or follow a symlink; the archive holds
    # password hashes, so it is 0600 from the moment it exists
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with tarfile.open(fileobj=raw, mode='w:gz') as tar:
                for name in sorted(os.listdir(tmp)):
                    tar.add(os.path.join(tmp, name), arcname=name)
    except BaseException:
        _remove_quiet(out_path)
        raise
    logger.info('wrote %s', out_path)


def _rrd_version_text(res):
    try:
        return res.stdout.decode('utf-8', 'replace').splitlines()[0]
    except Exception:
        return 'unknown'


def backup_local(cfg, out_path):
    _require_rrdtool()
    if not os.path.isfile(cfg['settings_db']):
        raise ValueError('settings database %s not found (not creating an empty one)' % cfg['settings_db'])
    with tempfile.TemporaryDirectory() as tmp:
        _dump_with_retry(['rrdtool', 'dump', cfg['database']], os.path.join(tmp, 'rrd.xml'))
        src = sqlite3.connect(pathlib.Path(os.path.abspath(cfg['settings_db'])).as_uri() + '?mode=ro', uri=True)
        dst = sqlite3.connect(os.path.join(tmp, 'pellmon_settings.db'))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        _collect_config(cfg, tmp)
        ver = _rrd_version_text(_run(['rrdtool', '--version'], capture=True, check=False))
        with open(os.path.join(tmp, 'manifest.json'), 'w') as f:
            json.dump(build_manifest(cfg, ver), f, indent=2)
        _write_archive(tmp, out_path)


def _safe_extract(tar, dest):
    """Validate and extract member by member (no extractall on any Python version): only regular
    files and directories, no traversal, capped total size, no setuid/sticky bits."""
    members = tar.getmembers()
    total = 0
    for m in members:
        parts = m.name.replace('\\', '/').split('/')
        if m.name.startswith(('/', '\\')) or os.path.isabs(m.name) or '..' in parts:
            raise ValueError("unsafe path in archive: %s" % m.name)
        if not (m.isreg() or m.isdir()):
            raise ValueError("unsafe link/device member in archive: %s" % m.name)
        if m.isreg():
            total += m.size
            if total > MAX_EXTRACT_BYTES:
                raise ValueError("archive is too large (more than %d bytes)" % MAX_EXTRACT_BYTES)
    real_dest = os.path.realpath(dest)
    for m in members:
        parts = [q for q in m.name.replace('\\', '/').split('/') if q not in ('', '.')]
        if not parts:
            continue
        target = os.path.realpath(os.path.join(dest, *parts))
        if target != real_dest and not target.startswith(real_dest + os.sep):
            raise ValueError("unsafe path in archive: %s" % m.name)
        if m.isdir():
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        mode = (m.mode & 0o755) | 0o600
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
        with os.fdopen(fd, 'wb') as out:
            shutil.copyfileobj(tar.extractfile(m), out)
        os.chmod(target, mode)


def _extract_archive(archive, tmp):
    with tarfile.open(archive, 'r:*') as tar:
        _safe_extract(tar, tmp)
    if not os.path.isfile(os.path.join(tmp, 'rrd.xml')):
        raise ValueError("archive %s has no rrd.xml" % archive)


def _restore_config(cfg, tmp):
    src = os.path.join(tmp, 'config')
    if not os.path.isdir(src):
        logger.warning('archive has no config/ folder')
        return
    cf = os.path.join(src, os.path.basename(cfg['conf_file']))
    if os.path.isfile(cf):
        shutil.copy2(cf, cfg['conf_file'])
        logger.info('restored %s', cfg['conf_file'])
    cd = os.path.join(src, 'conf.d')
    if os.path.isdir(cd) and cfg['host_config_dir']:
        shutil.copytree(cd, cfg['host_config_dir'], dirs_exist_ok=True)
        logger.info('restored %s', cfg['host_config_dir'])


def _require_rrdtool():
    if shutil.which('rrdtool') is None:
        raise ValueError("rrdtool was not found in PATH (install it, or drop --local to use docker)")


def _confirm(message, yes):
    """Destructive operations need --yes or an interactive 'yes'."""
    if yes:
        return
    print(message)
    if not sys.stdin.isatty() or input('Type "yes" to continue: ').strip() != 'yes':
        raise ValueError('restore not confirmed (use --yes)')


def _remove_quiet(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _create_private(path):
    """Create a fresh file that is 0600 from the very first moment."""
    _remove_quiet(path)
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)


def _verify_sqlite(path):
    try:
        con = sqlite3.connect(path)
        try:
            ok = con.execute('PRAGMA integrity_check').fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        raise ValueError('restored settings database is not a valid SQLite file: %s' % e)
    if not ok or ok[0] != 'ok':
        raise ValueError('restored settings database failed the integrity check')


def _keep_pre_restore(path):
    """Copy the file about to be replaced to <path>.pre-restore (0600, overwriting an older one)."""
    if not os.path.isfile(path):
        return
    dst = path + '.pre-restore'
    fd = _create_private(dst)
    with os.fdopen(fd, 'wb') as out, open(path, 'rb') as src:
        shutil.copyfileobj(src, out)
    logger.info('previous %s kept as %s', path, dst)


def restore_local(cfg, archive, with_config=False, yes=False):
    _require_rrdtool()
    db = os.path.abspath(cfg['database'])
    sdb = os.path.abspath(cfg['settings_db'])
    _confirm('This will OVERWRITE %s and %s (the old files are kept as .pre-restore).' % (db, sdb), yes)
    with tempfile.TemporaryDirectory() as tmp:
        _extract_archive(archive, tmp)
        for p in (db, sdb):
            os.makedirs(os.path.dirname(p), exist_ok=True)
        staged = []
        new_db, new_sdb = db + '.restore-new', sdb + '.restore-new'
        try:
            _remove_quiet(new_db)
            _run(['rrdtool', 'restore', os.path.join(tmp, 'rrd.xml'), new_db])
            _run(['rrdtool', 'info', new_db], capture=True)
            staged.append((db, new_db))
            src_sdb = os.path.join(tmp, 'pellmon_settings.db')
            if os.path.isfile(src_sdb):
                with os.fdopen(_create_private(new_sdb), 'wb') as out, open(src_sdb, 'rb') as src:
                    shutil.copyfileobj(src, out)
                _verify_sqlite(new_sdb)
                staged.append((sdb, new_sdb))
            else:
                logger.warning('archive has no settings database, the current one is left as it is')
            for target, new in staged:
                _keep_pre_restore(target)
                os.replace(new, target)
                logger.info('restored %s', target)
        finally:
            for new in (new_db, new_sdb):
                _remove_quiet(new)
        if with_config:
            _restore_config(cfg, tmp)
        logger.info('restart the daemon: it reads the RRD lastupdate only at startup')


def _compose(args):
    return ['docker', 'compose', '-f', args.compose_file]


def backup_docker(cfg, args):
    compose = _compose(args)
    svc = args.service
    with tempfile.TemporaryDirectory() as tmp:
        _dump_with_retry(compose + ['exec', '-T', svc, 'rrdtool', 'dump', cfg['database']],
                         os.path.join(tmp, 'rrd.xml'))
        script = _SETTINGS_BACKUP_SCRIPT % (cfg['settings_db'], _TMP_SETTINGS)
        try:
            _run(compose + ['exec', '-T', svc, 'python3', '-c', script])
            _run(compose + ['cp', '%s:%s' % (svc, _TMP_SETTINGS),
                            os.path.join(tmp, 'pellmon_settings.db')])
        finally:
            # the temporary copy holds secrets: never leave it behind, even on failure
            _run(compose + ['exec', '-T', svc, 'rm', '-f', _TMP_SETTINGS], check=False)
        _collect_config(cfg, tmp)
        ver = _rrd_version_text(_run(compose + ['exec', '-T', svc, 'rrdtool', '--version'],
                                     capture=True, check=False))
        with open(os.path.join(tmp, 'manifest.json'), 'w') as f:
            json.dump(build_manifest(cfg, ver), f, indent=2)
        _write_archive(tmp, args.out)


def _container_restore_script(db, sdb):
    """sh script run as root in the service image; everything is staged next to the target and
    verified before the (atomic) rename, the old files are kept as .pre-restore."""
    q = shlex.quote
    check = ('import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); '
             'sys.exit(0 if c.execute("PRAGMA integrity_check").fetchone()[0]=="ok" else 1)')
    return '\n'.join([
        'set -e',
        'umask 077',
        'db=%s; sdb=%s' % (q(db), q(sdb)),
        'rm -f "$db.restore-new" "$sdb.restore-new"',
        'rrdtool restore /restore/rrd.xml "$db.restore-new"',
        'rrdtool info "$db.restore-new" >/dev/null',
        'chmod 644 "$db.restore-new"; chown 999:999 "$db.restore-new"',
        'if [ -f /restore/pellmon_settings.db ]; then',
        '  cp /restore/pellmon_settings.db "$sdb.restore-new"',
        '  python3 -c %s "$sdb.restore-new"' % q(check),
        '  chmod 600 "$sdb.restore-new"; chown 999:999 "$sdb.restore-new"',
        'fi',
        'if [ -f "$db" ]; then cp "$db" "$db.pre-restore"; chmod 600 "$db.pre-restore"; fi',
        'if [ -f "$sdb.restore-new" ] && [ -f "$sdb" ]; then cp "$sdb" "$sdb.pre-restore"; chmod 600 "$sdb.pre-restore"; fi',
        'mv -f "$db.restore-new" "$db"',
        'if [ -f "$sdb.restore-new" ]; then mv -f "$sdb.restore-new" "$sdb"; fi',
    ])


def restore_docker(cfg, args):
    _confirm('This will OVERWRITE %s and %s inside the %s service '
             '(the old files are kept as .pre-restore).' %
             (cfg['database'], cfg['settings_db'], args.service), args.yes)
    compose = _compose(args)
    svc = args.service
    if args.with_config and cfg['host_config_dir'] and not os.access(cfg['host_config_dir'], os.W_OK):
        raise ValueError('%s is not writable by you; fix that or drop --with-config '
                         '(nothing was changed)' % cfg['host_config_dir'])
    with tempfile.TemporaryDirectory() as tmp:
        _extract_archive(args.archive, tmp)
        _run(compose + ['stop', svc])
        try:
            _run(compose + ['run', '--rm', '--no-deps', '-T', '-u', 'root',
                            '-v', '%s:/restore:ro' % os.path.abspath(tmp),
                            svc, 'sh', '-c', _container_restore_script(cfg['database'], cfg['settings_db'])])
            if args.with_config:
                _restore_config(cfg, tmp)
        except Exception as e:
            restart = ' '.join(compose + ['up', '-d', svc])
            sys.stderr.write(
                'restore FAILED after the %s service was stopped: %s\n'
                'The RRD and settings database are replaced only at the very end, so they are '
                'either untouched or the previous copies are kept as <file>.pre-restore.\n'
                'Trying to start the service again; if that fails run:\n  %s\n' % (svc, e, restart))
            try:
                _run(compose + ['up', '-d', svc])
            except Exception as e2:
                sys.stderr.write('could not restart the service (%s); run: %s\n' % (e2, restart))
            raise
        _run(compose + ['up', '-d', svc])
        logger.info('service restarted: the daemon reloads lastupdate only at startup')


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Back up / restore PellMon persistent data')
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('backup', 'restore'):
        s = sub.add_parser(name)
        s.add_argument('--config', default='./config/pellmon.conf')
        s.add_argument('--host-config-dir', default=None,
                       help='host directory holding conf.d; defaults to <dirname of --config>/conf.d '
                            'because [conf] config_dir is the in-container path')
        s.add_argument('--local', action='store_true', help='use direct paths instead of docker compose')
        s.add_argument('--compose-file', default='./docker-compose.yml')
        s.add_argument('--service', default='pellmonsrv')
        s.add_argument('--verbose', action='store_true')
        if name == 'backup':
            s.add_argument('--out', default='pellmon-backup-%s.tar.gz' %
                           datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        else:
            s.add_argument('archive')
            s.add_argument('--with-config', action='store_true')
            s.add_argument('--yes', action='store_true')
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        stream=sys.stderr, format='%(asctime)s %(message)s')
    try:
        cfg = read_effective_config(args.config, args.host_config_dir, args.local)
        logger.debug('effective database: %s', cfg['database'])
        if args.command == 'backup':
            if os.path.lexists(args.out):
                raise ValueError('%s already exists; choose another --out or remove it first' % args.out)
            if args.local:
                backup_local(cfg, args.out)
            else:
                backup_docker(cfg, args)
        else:
            if args.local:
                restore_local(cfg, args.archive, args.with_config, args.yes)
            else:
                restore_docker(cfg, args)
    except (ValueError, OSError, EOFError, sqlite3.Error,
            subprocess.CalledProcessError, tarfile.TarError) as e:
        sys.stderr.write('error: %s\n' % e)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
