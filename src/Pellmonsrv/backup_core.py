#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Backup core: creates the same archive as tools/pellmon_backup.py (rrd.xml, pellmon_settings.db,
# config/, manifest.json in one .tar.gz) into a folder, keeps a limited number of old archives and
# does the schedule arithmetic. Stdlib plus the rrdtool binary. No D-Bus, no plugin machinery,
# so it is easy to test. Failures are BackupError with a fixed reason string: paths and exception
# text never reach the web page.

import datetime
import errno
import json
import logging
import os
import pathlib
import platform
import re
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import zlib

logger = logging.getLogger('pellMon')

PREFIX = 'pellmon-backup-'
SUFFIX = '.tar.gz'
NAME_RE = re.compile(r'^pellmon-backup-(\d{8})-(\d{6})\.tar\.gz$')

REASON_FOLDER_MISSING = 'folder missing (is the NAS mounted?)'
REASON_NOT_WRITABLE = 'folder not writable'
REASON_NO_SPACE = 'out of space'
REASON_SAME_DISK = 'folder is on the same disk as the database (is the NAS or USB drive mounted?)'
REASON_TIMEOUT = 'folder did not answer (is the NAS reachable?)'
REASON_RRD = 'rrdtool failed'
REASON_RRD_MISSING = 'rrdtool not found'
REASON_SETTINGS = 'settings database unreadable'
REASON_VERIFY = 'archive could not be verified'
REASON_UNKNOWN = 'unknown error (see the server log)'
REASON_ARCHIVE_NOT_FOUND = 'archive not found'
REASON_ARCHIVE_DAMAGED = 'archive unreadable or damaged'
REASON_ARCHIVE_UNSAFE = 'archive unsafe'
REASON_ARCHIVE_INCOMPLETE = 'archive has no RRD or settings'
REASON_RESTORE_SPACE = 'not enough free space to restore'
REASON_RESTORE_RRD = 'rrdtool restore failed'
REASON_LAYOUT = 'archive RRD layout does not match this installation'
REASON_FUTURE = 'archive is newer than the system clock'
REASON_ARCHIVE_SETTINGS = 'settings database in archive is damaged'
REASON_RESTORE_BUSY = 'restore already running'
REASON_SWAP = 'swap failed (previous data restored)'
REASONS = frozenset([REASON_FOLDER_MISSING, REASON_NOT_WRITABLE, REASON_NO_SPACE, REASON_SAME_DISK, REASON_TIMEOUT, REASON_RRD,
                     REASON_RRD_MISSING, REASON_SETTINGS, REASON_VERIFY, REASON_UNKNOWN,
                     REASON_ARCHIVE_NOT_FOUND, REASON_ARCHIVE_DAMAGED, REASON_ARCHIVE_UNSAFE,
                     REASON_ARCHIVE_INCOMPLETE, REASON_RESTORE_SPACE, REASON_RESTORE_RRD, REASON_LAYOUT,
                     REASON_FUTURE, REASON_ARCHIVE_SETTINGS, REASON_RESTORE_BUSY, REASON_SWAP])

RRD_DUMP_ATTEMPTS = 3
RRD_DUMP_TIMEOUT = 900

MAX_EXTRACT_BYTES = 4 * 1024 ** 3
MANIFEST_MAX_BYTES = 64 * 1024
RESTORE_SPACE_MARGIN = 64 * 1024 ** 2
RESTORE_MEMBERS = ('manifest.json', 'pellmon_settings.db', 'rrd.xml')
MANIFEST_FIELDS = ('created', 'machine', 'rrdtool_version', 'created_by')
STAGING_DIR = '.restore-tmp'
NEW_SUFFIX = '.restore-new'
PRE_SUFFIX = '.pre-restore'


class BackupError(Exception):
    """A failed backup step; reason is one of REASONS"""

    def __init__(self, reason):
        Exception.__init__(self, reason)
        self.reason = reason


def call_with_timeout(fn, seconds):
    """Run fn in a helper thread and wait at most `seconds`. Returns (finished, value); an exception
    in fn is raised here. A hung NAS must never block the daemon's D-Bus thread: the helper thread
    is abandoned (it is a daemon thread) when it does not finish."""
    box = {}

    def target():
        try:
            box['value'] = fn()
        except BaseException as e:  # handed to the caller
            box['error'] = e
    t = threading.Thread(target=target, name='backup-io')
    t.daemon = True
    t.start()
    t.join(seconds)
    if t.is_alive():
        return False, None
    if 'error' in box:
        raise box['error']
    return True, box.get('value')


def _reason_for_oserror(e):
    if e.errno in (errno.ENOSPC, getattr(errno, 'EDQUOT', errno.ENOSPC)):
        return REASON_NO_SPACE
    if e.errno in (errno.ENOENT, errno.ENOTDIR):
        return REASON_FOLDER_MISSING
    return REASON_NOT_WRITABLE


# ---- names, listing, retention ---------------------------------------------------

def archive_name(now=None):
    now = now or datetime.datetime.now()
    return PREFIX + now.strftime('%Y%m%d-%H%M%S') + SUFFIX


def parse_name(name):
    """The local time encoded in an archive name, None for any other name"""
    m = NAME_RE.match(name or '')
    if not m:
        return None
    try:
        return datetime.datetime.strptime(m.group(1) + m.group(2), '%Y%m%d%H%M%S')
    except ValueError:
        return None


def list_archives(folder):
    """[{'name', 'size', 'time'}] newest first; only regular files named like our archives"""
    out = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                t = parse_name(entry.name)
                if t is None:
                    continue
                try:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    size = entry.stat(follow_symlinks=False).st_size
                except OSError:
                    continue
                out.append({'name': entry.name, 'size': size, 'time': t.timestamp()})
    except OSError:
        return []
    out.sort(key=lambda e: e['time'], reverse=True)
    return out


def select_prune(entries, keep_daily, keep_weekly):
    """Names to delete. entries: [(name, datetime)]. Keeps the newest keep_daily archives (at
    least one) and the newest archive of each of the last keep_weekly ISO weeks that have one."""
    ordered = sorted(entries, key=lambda e: e[1], reverse=True)
    keep = set(name for name, _t in ordered[:max(int(keep_daily), 1)])
    weeks = set()
    for name, t in ordered:
        week = t.isocalendar()[:2]
        if week in weeks:
            continue
        if len(weeks) >= int(keep_weekly):
            break
        weeks.add(week)
        keep.add(name)
    return [name for name, _t in ordered if name not in keep]


def prune(folder, keep_daily, keep_weekly):
    """Delete old archives per retention; returns the deleted names. Nothing else is touched."""
    entries = [(a['name'], datetime.datetime.fromtimestamp(a['time'])) for a in list_archives(folder)]
    deleted = []
    for name in select_prune(entries, keep_daily, keep_weekly):
        try:
            os.unlink(os.path.join(folder, name))
            deleted.append(name)
        except OSError as e:
            logger.warning('backup: could not delete old archive %s: %s' % (name, errno.errorcode.get(e.errno, e.errno)))
    return deleted


# ---- folder check ------------------------------------------------------------------

def same_disk(a, b):
    """True when both paths are on the same filesystem (a bind mount of an unmounted NAS folder
    is an empty directory on the same disk as the database)"""
    try:
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def check_folder(folder, other_disk_than=None):
    """Make sure the folder exists and is writable, and, when other_disk_than is given, that it is
    on a different disk. Returns the free bytes (None if unknown), raises BackupError otherwise."""
    if not folder or not os.path.isdir(folder):
        raise BackupError(REASON_FOLDER_MISSING)
    if other_disk_than and same_disk(folder, other_disk_than):
        raise BackupError(REASON_SAME_DISK)
    probe = os.path.join(folder, '.pellmon-write-test-%d' % os.getpid())
    try:
        fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            os.write(fd, b'pellmon')
        finally:
            os.close(fd)
        os.unlink(probe)
    except OSError as e:
        try:
            os.unlink(probe)
        except OSError:
            pass
        raise BackupError(_reason_for_oserror(e))
    try:
        return shutil.disk_usage(folder).free
    except OSError:
        return None


# ---- archive -------------------------------------------------------------------------

def _dump_rrd(rrdtool, rrd_db, xml_path, retry_delay=1.0):
    last = None
    for attempt in range(RRD_DUMP_ATTEMPTS):
        try:
            with open(xml_path, 'wb') as f:
                subprocess.run([rrdtool, 'dump', rrd_db], stdout=f, stderr=subprocess.PIPE,
                               check=True, timeout=RRD_DUMP_TIMEOUT)
            return
        except FileNotFoundError:
            raise BackupError(REASON_RRD_MISSING)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            last = e
            logger.warning('backup: rrdtool dump failed (attempt %d of %d)' % (attempt + 1, RRD_DUMP_ATTEMPTS))
            if attempt + 1 < RRD_DUMP_ATTEMPTS:
                time.sleep(retry_delay)
    err = getattr(last, 'stderr', None)
    if err:
        logger.warning('backup: rrdtool said: %s' % err.decode('utf-8', 'replace').strip()[:300])
    raise BackupError(REASON_RRD)


def _rrd_version(rrdtool):
    try:
        res = subprocess.run([rrdtool, '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return res.stdout.decode('utf-8', 'replace').splitlines()[0]
    except Exception:
        return 'unknown'


def _copy_settings(settings_db, tmp):
    try:
        src = sqlite3.connect(pathlib.Path(os.path.abspath(settings_db)).as_uri() + '?mode=ro', uri=True)
    except sqlite3.Error:
        raise BackupError(REASON_SETTINGS)
    dst = sqlite3.connect(os.path.join(tmp, 'pellmon_settings.db'))
    try:
        src.backup(dst)
    except sqlite3.Error:
        raise BackupError(REASON_SETTINGS)
    finally:
        dst.close()
        src.close()


def _copy_tree(src, dst):
    """Copy files only (no symlinks, no source permissions): a read-only mount must not leave
    undeletable files in the temporary folder"""
    for root, dirs, files in os.walk(src, followlinks=False):
        rel = os.path.relpath(root, src)
        target = dst if rel == '.' else os.path.join(dst, rel)
        os.makedirs(target, mode=0o700, exist_ok=True)
        for name in sorted(files):
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            shutil.copyfile(path, os.path.join(target, name))
            os.chmod(os.path.join(target, name), 0o600)


def _collect_config(conf_file, config_dir, tmp):
    dest = os.path.join(tmp, 'config')
    os.makedirs(dest, mode=0o700)
    try:
        if conf_file and os.path.isfile(conf_file):
            shutil.copyfile(conf_file, os.path.join(dest, os.path.basename(conf_file)))
        if config_dir and os.path.isdir(config_dir):
            _copy_tree(config_dir, os.path.join(dest, 'conf.d'))
    except OSError:
        logger.warning('backup: could not read the config folder, it is left out of the archive')


def build_manifest(rrd_db, settings_db, config_dir, rrd_version):
    return {
        'format': 1,
        'created': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'rrd_filename': os.path.basename(rrd_db),
        'rrd_path': rrd_db,
        'settings_filename': os.path.basename(settings_db),
        'machine': platform.machine(),
        'rrdtool_version': rrd_version,
        'config_dir': config_dir,
        'host_config_dir': None,
        'created_by': 'pellmonsrv backup plugin',
    }


def _write_archive(tmp, out_path):
    """0600 from the moment it exists, never overwrites, flushed to the medium"""
    fd = os.open(out_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as raw:
            with tarfile.open(fileobj=raw, mode='w:gz') as tar:
                for name in sorted(os.listdir(tmp)):
                    tar.add(os.path.join(tmp, name), arcname=name)
            raw.flush()
            try:
                os.fsync(raw.fileno())
            except OSError:
                pass
    except BaseException:
        try:
            os.unlink(out_path)
        except OSError:
            pass
        raise


def _verify_archive(path):
    """Read the whole archive back: it must open, decompress and contain the three key members"""
    names = set()
    try:
        with tarfile.open(path, 'r:gz') as tar:
            for member in tar:
                names.add(member.name)
                if member.isreg():
                    f = tar.extractfile(member)
                    while f.read(1 << 20):
                        pass
    except (tarfile.TarError, EOFError, OSError):
        raise BackupError(REASON_VERIFY)
    if not set(['rrd.xml', 'pellmon_settings.db', 'manifest.json']) <= names:
        raise BackupError(REASON_VERIFY)


def create_archive(folder, rrd_db, settings_db, conf_file, config_dir, now=None, rrdtool='rrdtool',
                   retry_delay=1.0, other_disk_than=None):
    """Write one backup archive into folder. Returns {'name', 'size', 'free'}; raises BackupError."""
    now = now or datetime.datetime.now()
    free = check_folder(folder, other_disk_than)
    if not settings_db or not os.path.isfile(settings_db):
        raise BackupError(REASON_SETTINGS)
    final = os.path.join(folder, archive_name(now))
    if os.path.lexists(final):
        raise BackupError(REASON_UNKNOWN)
    part = os.path.join(folder, '.' + os.path.basename(final) + '.part')
    try:
        os.unlink(part)  # left over from a run that was killed
    except OSError:
        pass
    try:
        with tempfile.TemporaryDirectory(prefix='pellmon-backup-') as tmp:
            _dump_rrd(rrdtool, rrd_db, os.path.join(tmp, 'rrd.xml'), retry_delay)
            _copy_settings(settings_db, tmp)
            _collect_config(conf_file, config_dir, tmp)
            with open(os.path.join(tmp, 'manifest.json'), 'w') as f:
                json.dump(build_manifest(rrd_db, settings_db, config_dir, _rrd_version(rrdtool)), f, indent=2)
            _write_archive(tmp, part)
            _verify_archive(part)
            os.replace(part, final)
    except BackupError:
        _remove_quiet(part)
        raise
    except OSError as e:
        _remove_quiet(part)
        logger.warning('backup: file error: %s' % errno.errorcode.get(e.errno, e.errno))
        raise BackupError(_reason_for_oserror(e))
    except Exception:
        _remove_quiet(part)
        logger.exception('backup: unexpected error')
        raise BackupError(REASON_UNKNOWN)
    return {'name': os.path.basename(final), 'size': os.path.getsize(final), 'free': free}


def _remove_quiet(path):
    try:
        os.unlink(path)
    except OSError:
        pass


# ---- restore: archive checks ---------------------------------------------------------
# The daemon image has no tools/ folder, so the hardened extractor of tools/pellmon_backup.py is
# kept here in parity (tests feed both the same malicious archives).

def validate_archive_name(folder, name):
    """Absolute path of a listed archive. The name is client input: it must full-match NAME_RE,
    appear in a fresh listing and be a regular, non-symlink file. The path is built here."""
    try:
        if not isinstance(name, str) or not NAME_RE.fullmatch(name) or '/' in name or os.sep in name:
            raise BackupError(REASON_ARCHIVE_NOT_FOUND)
        if name not in [a['name'] for a in list_archives(folder)]:
            raise BackupError(REASON_ARCHIVE_NOT_FOUND)
        path = os.path.join(folder, name)
        if not stat.S_ISREG(os.lstat(path).st_mode):
            raise BackupError(REASON_ARCHIVE_NOT_FOUND)
    except OSError:
        raise BackupError(REASON_ARCHIVE_NOT_FOUND)
    return os.path.abspath(path)


def open_archive(path):
    """TarFile on an O_NOFOLLOW fd. The raw file object is kept in tar.pellmon_raw and closed by
    close_archive(tar); callers must use that instead of tar.close() alone."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError:
        raise BackupError(REASON_ARCHIVE_NOT_FOUND)
    try:
        regular = stat.S_ISREG(os.fstat(fd).st_mode)
    except OSError:
        regular = False
    if not regular:
        os.close(fd)
        raise BackupError(REASON_ARCHIVE_NOT_FOUND)
    raw = os.fdopen(fd, 'rb')
    try:
        tar = tarfile.open(fileobj=raw, mode='r:gz')
    except (tarfile.TarError, EOFError, zlib.error, OSError):
        raw.close()
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    except BaseException:
        raw.close()
        raise
    tar.pellmon_raw = raw
    return tar


def close_archive(tar):
    try:
        tar.close()
    finally:
        raw = getattr(tar, 'pellmon_raw', None)
        if raw is not None:
            raw.close()


def _check_member(m, total):
    """The tool's member rules; returns the new running size total"""
    parts = m.name.replace('\\', '/').split('/')
    if m.name.startswith(('/', '\\')) or os.path.isabs(m.name) or '..' in parts:
        raise BackupError(REASON_ARCHIVE_UNSAFE)
    if not (m.isreg() or m.isdir()):
        raise BackupError(REASON_ARCHIVE_UNSAFE)
    if m.isreg():
        total += m.size
        if total > MAX_EXTRACT_BYTES:
            raise BackupError(REASON_ARCHIVE_UNSAFE)
    return total


def _whitelist(manifest):
    out = {}
    for key in MANIFEST_FIELDS:
        if key in manifest:
            out[key] = str(manifest[key])[:200]
    return out


def _parse_manifest(data):
    try:
        manifest = json.loads(data.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    if not isinstance(manifest, dict) or manifest.get('format') != 1:
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    return manifest


def _read_manifest_member(tar, m):
    if m.size > MANIFEST_MAX_BYTES:
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    data = tar.extractfile(m).read(MANIFEST_MAX_BYTES + 1)
    if len(data) > MANIFEST_MAX_BYTES:
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    return data


def _is_config(name):
    return name == 'config' or name.startswith('config/')


def check_archive(path):
    """Read the whole archive through (gzip CRC) and validate it. Returns
    {'manifest': whitelisted dict, 'has_config': bool, 'sizes': {member: size}}"""
    tar = open_archive(path)
    sizes = {}
    manifest_data = None
    has_config = False
    total = 0
    try:
        for m in tar:
            total = _check_member(m, total)
            if _is_config(m.name):
                has_config = True
            if not m.isreg():
                continue
            if m.name in RESTORE_MEMBERS:
                sizes[m.name] = m.size
            if m.name == 'manifest.json':
                manifest_data = _read_manifest_member(tar, m)
                continue
            f = tar.extractfile(m)
            while f.read(1 << 20):
                pass
    except (tarfile.TarError, EOFError, zlib.error, OSError):
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    finally:
        close_archive(tar)
    if manifest_data is None or 'rrd.xml' not in sizes or 'pellmon_settings.db' not in sizes:
        raise BackupError(REASON_ARCHIVE_INCOMPLETE)
    manifest = _parse_manifest(manifest_data)
    return {'manifest': _whitelist(manifest), 'has_config': has_config, 'sizes': sizes}


def preview_archive(path):
    """Cheap look at the manifest (members are sorted, it comes before the large ones)"""
    tar = open_archive(path)
    manifest_data = None
    has_config = False
    total = 0
    try:
        for m in tar:
            total = _check_member(m, total)
            if _is_config(m.name):
                has_config = True
            if m.isreg() and m.name == 'manifest.json':
                manifest_data = _read_manifest_member(tar, m)
                break
    except (tarfile.TarError, EOFError, zlib.error, OSError):
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    finally:
        close_archive(tar)
    if manifest_data is None:
        raise BackupError(REASON_ARCHIVE_INCOMPLETE)
    return {'manifest': _whitelist(_parse_manifest(manifest_data)), 'has_config': has_config}


def safe_extract(tar, dest, only=None):
    """Validate every member, then extract member by member (never extractall). With only, members
    whose first path part is not listed are validated but not written."""
    try:
        members = tar.getmembers()
        total = 0
        for m in members:
            total = _check_member(m, total)
        real_dest = os.path.realpath(dest)
        for m in members:
            parts = [q for q in m.name.replace('\\', '/').split('/') if q not in ('', '.')]
            if not parts:
                continue
            if only is not None and parts[0] not in only:
                continue
            target = os.path.realpath(os.path.join(dest, *parts))
            if target != real_dest and not target.startswith(real_dest + os.sep):
                raise BackupError(REASON_ARCHIVE_UNSAFE)
            if m.isdir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            mode = (m.mode & 0o755) | 0o600
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), mode)
            with os.fdopen(fd, 'wb') as out:
                shutil.copyfileobj(tar.extractfile(m), out)
            os.chmod(target, mode)
    except (tarfile.TarError, EOFError, zlib.error):
        raise BackupError(REASON_ARCHIVE_DAMAGED)
    except OSError as e:
        logger.warning('restore: extract file error: %s' % errno.errorcode.get(e.errno, e.errno))
        if e.errno in (errno.ENOSPC, getattr(errno, 'EDQUOT', errno.ENOSPC)):
            raise BackupError(REASON_RESTORE_SPACE)
        raise BackupError(REASON_ARCHIVE_UNSAFE)


def verify_sqlite(path):
    """The extracted settings database must be intact and have the keyval table"""
    try:
        con = sqlite3.connect(pathlib.Path(os.path.abspath(path)).as_uri() + '?mode=ro', uri=True)
        try:
            ok = con.execute('PRAGMA integrity_check').fetchone()
            cols = set(r[1] for r in con.execute('PRAGMA table_info(keyval)').fetchall())
        finally:
            con.close()
    except sqlite3.Error:
        raise BackupError(REASON_ARCHIVE_SETTINGS)
    if not ok or ok[0] != 'ok' or not set(['id', 'value']) <= cols:
        raise BackupError(REASON_ARCHIVE_SETTINGS)


# ---- restore: staging and space ------------------------------------------------------

def clean_restore_leftovers(data_dir, targets):
    """Remove a stale staging folder and *.restore-new files. Never raises."""
    try:
        staging = os.path.join(data_dir, STAGING_DIR)
        if os.path.islink(staging):
            os.unlink(staging)
        elif os.path.lexists(staging):
            shutil.rmtree(staging, ignore_errors=True)
        for target in targets or []:
            if target:
                _remove_quiet(target + NEW_SUFFIX)
    except Exception as e:
        logger.warning('restore: could not clean leftovers: %s' % e.__class__.__name__)


def prepare_staging(data_dir):
    """Fresh 0700 staging folder inside the data dir (same filesystem as the swap targets)"""
    clean_restore_leftovers(data_dir, [])
    staging = os.path.join(data_dir, STAGING_DIR)
    try:
        os.mkdir(staging, 0o700)
        os.chmod(staging, 0o700)
    except OSError as e:
        logger.warning('restore: could not create staging folder: %s' % errno.errorcode.get(e.errno, e.errno))
        if e.errno in (errno.ENOSPC, getattr(errno, 'EDQUOT', errno.ENOSPC)):
            raise BackupError(REASON_RESTORE_SPACE)
        raise BackupError(REASON_UNKNOWN)
    return staging


def check_restore_space(data_dir, member_sizes, rrd_db):
    """Refuse when free space < member sizes + 2 x live RRD + margin"""
    live = os.path.getsize(rrd_db) if rrd_db and os.path.isfile(rrd_db) else 0
    needed = sum(member_sizes.values()) + 2 * live + RESTORE_SPACE_MARGIN
    try:
        free = shutil.disk_usage(data_dir).free
    except OSError:
        logger.warning('restore: free space unknown, not checked')
        return
    if free < needed:
        raise BackupError(REASON_RESTORE_SPACE)


# ---- schedule ------------------------------------------------------------------------

FREQUENCIES = ('daily', 'weekly')
_HHMM_RE = re.compile(r'([01]?\d|2[0-3]):([0-5]\d)')


def parse_hhmm(text):
    """(hour, minute) from 'H:MM' or 'HH:MM', None when invalid"""
    m = _HHMM_RE.fullmatch((text or '').strip()) if isinstance(text, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def last_slot(now, frequency, hhmm, weekday=6):
    """The most recent scheduled time at or before now (naive local datetime).
    weekday: 0 = Monday ... 6 = Sunday, used for weekly."""
    hour, minute = parse_hhmm(hhmm)
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if frequency == 'weekly':
        slot -= datetime.timedelta(days=(slot.weekday() - int(weekday)) % 7)
        if slot > now:
            slot -= datetime.timedelta(days=7)
    elif slot > now:
        slot -= datetime.timedelta(days=1)
    return slot


def next_slot(now, frequency, hhmm, weekday=6):
    step = 7 if frequency == 'weekly' else 1
    return last_slot(now, frequency, hhmm, weekday) + datetime.timedelta(days=step)


def is_due(now_ts, last_ok_ts, last_attempt_ts, frequency, hhmm, weekday=6, retry=3600):
    """True when a backup should start: the latest slot has passed without a successful
    backup, and the last attempt for it (if any) is at least `retry` seconds old."""
    slot = last_slot(datetime.datetime.fromtimestamp(now_ts), frequency, hhmm, weekday).timestamp()
    if last_ok_ts and last_ok_ts >= slot:
        return False
    if last_attempt_ts and last_attempt_ts >= slot and now_ts - last_attempt_ts < retry:
        return False
    return True
