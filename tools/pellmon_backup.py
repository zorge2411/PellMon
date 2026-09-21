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
(/etc/pellmon/conf.d). This tool runs on the host and reads the host copy
next to pellmon.conf (or --host-config-dir). The database/settings_db
values are used exactly as written (container paths in docker mode, host
paths with --local).
"""

import argparse
import configparser
import datetime
import json
import logging
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time

logger = logging.getLogger('pellmon_backup')

# executed inside the container; the two paths come from the config
_SETTINGS_BACKUP_SCRIPT = (
    "import sqlite3; s=sqlite3.connect(%r); d=sqlite3.connect(%r); s.backup(d); d.close(); s.close()")
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


def resolve_config_dir(conf_file, configured_dir, host_config_dir=None):
    if host_config_dir:
        d = os.path.abspath(os.path.expanduser(host_config_dir))
        logger.debug('conf.d: using --host-config-dir %s', d)
        return d
    if configured_dir and os.path.isdir(configured_dir):
        logger.debug('conf.d: configured config_dir %s exists on this host', configured_dir)
        return configured_dir
    sibling = os.path.join(os.path.dirname(os.path.abspath(conf_file)), 'conf.d')
    if os.path.isdir(sibling):
        logger.debug('conf.d: config_dir %s not on host, using %s', configured_dir, sibling)
        return sibling
    return None


def read_effective_config(conf_file, host_config_dir=None):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if not parser.read(conf_file):
        raise ValueError("cannot read config file %s" % conf_file)
    configured = parser.get('conf', 'config_dir', fallback=None)
    resolved = resolve_config_dir(conf_file, configured, host_config_dir)
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
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as raw:
        with tarfile.open(fileobj=raw, mode='w:gz') as tar:
            for name in sorted(os.listdir(tmp)):
                tar.add(os.path.join(tmp, name), arcname=name)
    os.chmod(out_path, 0o600)
    logger.info('wrote %s', out_path)


def _rrd_version_text(res):
    try:
        return res.stdout.decode('utf-8', 'replace').splitlines()[0]
    except Exception:
        return 'unknown'


def backup_local(cfg, out_path):
    with tempfile.TemporaryDirectory() as tmp:
        _dump_with_retry(['rrdtool', 'dump', cfg['database']], os.path.join(tmp, 'rrd.xml'))
        src = sqlite3.connect(cfg['settings_db'])
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
    members = tar.getmembers()
    for m in members:
        parts = m.name.replace('\\', '/').split('/')
        if m.name.startswith(('/', '\\')) or os.path.isabs(m.name) or '..' in parts:
            raise ValueError("unsafe path in archive: %s" % m.name)
        if m.issym() or m.islnk() or m.isdev():
            raise ValueError("unsafe link/device member in archive: %s" % m.name)
    if hasattr(tarfile, 'data_filter'):
        tar.extractall(dest, members=members, filter='data')
    else:
        tar.extractall(dest, members=members)


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


def restore_local(cfg, archive, with_config=False):
    with tempfile.TemporaryDirectory() as tmp:
        _extract_archive(archive, tmp)
        for p in (cfg['database'], cfg['settings_db']):
            os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        _run(['rrdtool', 'restore', '-f', os.path.join(tmp, 'rrd.xml'), cfg['database']])
        logger.info('rebuilt RRD %s', cfg['database'])
        sdb = os.path.join(tmp, 'pellmon_settings.db')
        if os.path.isfile(sdb):
            shutil.copyfile(sdb, cfg['settings_db'])
            os.chmod(cfg['settings_db'], 0o600)
            logger.info('restored settings database %s', cfg['settings_db'])
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
        _run(compose + ['exec', '-T', svc, 'python3', '-c', script])
        _run(compose + ['cp', '%s:%s' % (svc, _TMP_SETTINGS),
                        os.path.join(tmp, 'pellmon_settings.db')])
        _run(compose + ['exec', '-T', svc, 'rm', '-f', _TMP_SETTINGS])
        _collect_config(cfg, tmp)
        ver = _rrd_version_text(_run(compose + ['exec', '-T', svc, 'rrdtool', '--version'],
                                     capture=True, check=False))
        with open(os.path.join(tmp, 'manifest.json'), 'w') as f:
            json.dump(build_manifest(cfg, ver), f, indent=2)
        _write_archive(tmp, args.out)


def restore_docker(cfg, args):
    if not args.yes:
        print('This will OVERWRITE %s and %s inside the %s service.' %
              (cfg['database'], cfg['settings_db'], args.service))
        if not sys.stdin.isatty() or input('Type "yes" to continue: ').strip() != 'yes':
            raise ValueError('restore not confirmed (use --yes)')
    compose = _compose(args)
    svc = args.service
    with tempfile.TemporaryDirectory() as tmp:
        _extract_archive(args.archive, tmp)
        _run(compose + ['stop', svc])
        script = ('rrdtool restore -f /restore/rrd.xml %(db)s && '
                  'cp /restore/pellmon_settings.db %(sdb)s && '
                  'chown 999:999 %(db)s %(sdb)s && chmod 600 %(sdb)s') % {
                      'db': cfg['database'], 'sdb': cfg['settings_db']}
        _run(compose + ['run', '--rm', '--no-deps', '-T', '-u', 'root',
                        '-v', '%s:/restore:ro' % os.path.abspath(tmp),
                        svc, 'sh', '-c', script])
        if args.with_config:
            _restore_config(cfg, tmp)
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
        cfg = read_effective_config(args.config, args.host_config_dir)
        logger.debug('effective database: %s', cfg['database'])
        if args.command == 'backup':
            if args.local:
                backup_local(cfg, args.out)
            else:
                backup_docker(cfg, args)
        else:
            if args.local:
                restore_local(cfg, args.archive, args.with_config)
            else:
                restore_docker(cfg, args)
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as e:
        sys.stderr.write('error: %s\n' % e)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
