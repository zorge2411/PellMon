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

# Backup plugin: writes a backup archive (RRD database, settings database, config) of this
# installation to a folder on a NAS or other mounted media on a schedule, and keeps a limited
# number of old archives. It stays idle until it is enabled on the Backup page of the web
# interface. The archive format is the one tools/pellmon_backup.py restores.

import datetime
import os
import signal
import threading
import time
from logging import getLogger

from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Keyval_storage
from Pellmonsrv import backup_core as core
from . import settings as backup_settings

logger = getLogger('pellMon')

DEFAULT_ROOT = '/backups'
REASON_BUSY = 'a backup is already running'
RESTORE_STEPS_TOTAL = 5
STEP_NUMBERS = {'checking': 1, 'extracting': 2, 'building': 3, 'swapping': 4, 'restarting': 5}
_FALLBACK_LOCK = threading.Lock()  # only used when the daemon globals have no restore_lock (tests)


class backupplugin(protocols):
    autostart = True       # tests switch the scheduler thread off
    startup_delay = 120    # seconds after start before the first schedule check
    check_interval = 30    # seconds between schedule checks
    # Folder I/O that happens on the D-Bus thread is bounded: a hung NAS (stale NFS mount) must
    # not freeze the daemon's D-Bus service and with it the web interface.
    status_io_timeout = 3.0
    test_timeout = 10.0
    listing_max_age = 30.0
    preview_timeout = 10.0     # bounded manifest preview (D-13)
    restore_watchdog = 3600.0  # must exceed core.RRD_RESTORE_TIMEOUT
    exit_after_restore = True  # tests switch this off
    restart_delay = 2.0        # seconds before SIGTERM so the page can show 'restarting'

    def __init__(self):
        protocols.__init__(self)
        self.store = None
        self.cfg = dict(backup_settings.DEFAULTS)
        self.state = dict(backup_settings.STATE_DEFAULTS)
        self.lock = threading.Lock()
        self.running = False
        self.stop_event = threading.Event()
        self.root = DEFAULT_ROOT
        self.rrd_db = None
        self.settings_db = None
        self.conf_file = None
        self.config_dir = None
        self.rrdtool = 'rrdtool'
        self.retry_delay = 1.0
        self.listing = None
        self.listing_time = 0.0
        self.restoring = False
        self.nvdb = None
        self.data_dir = None
        self.poll_ds_names = []
        self.in_docker = False
        self.restore = dict(state='idle', step=0, name='', reason='')
        self.restore_result = None
        self._restore_cancel = threading.Event()
        self._watchdog = None

    def activate(self, conf, glob, db, *args, **kwargs):
        protocols.activate(self, conf, glob, db, *args, **kwargs)
        self.stop_event.clear()
        self.store = Keyval_storage.keyval_storage
        daemon_conf = self.glob['conf']
        self.rrd_db = getattr(daemon_conf, 'db', None)
        self.settings_db = getattr(daemon_conf, 'keyval_db', None)
        self.conf_file = getattr(daemon_conf, 'conf_file', None)
        self.config_dir = getattr(daemon_conf, 'config_dir', None)
        self.root = (self.conf or {}).get('folder', DEFAULT_ROOT) or DEFAULT_ROOT
        self.cfg = backup_settings.load(self.store)
        self.state = backup_settings.load_state(self.store)
        self.nvdb = getattr(daemon_conf, 'nvdb', None) or self.rrd_db
        self.data_dir = os.path.dirname(os.path.abspath(self.nvdb)) if self.nvdb else None
        self.poll_ds_names = [d.get('ds_name') for d in (getattr(daemon_conf, 'pollData', None) or [])]
        self.in_docker = os.path.exists('/.dockerenv')
        if self.data_dir:
            core.clean_restore_leftovers(self.data_dir, [self.rrd_db, self.nvdb, self.settings_db])
            self.restore_result = core.read_result(self.data_dir)
        if self.autostart:
            t = threading.Thread(target=self.scheduler, name='backup-scheduler')
            t.daemon = True
            t.start()

    def deactivate(self):
        self.stop_event.set()
        protocols.deactivate(self)

    # ---- scheduler ----------------------------------------------------------------

    def scheduler(self):
        if self.stop_event.wait(self.startup_delay):
            return
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception('Backup scheduler error')
            if self.stop_event.wait(self.check_interval):
                return

    def tick(self, now=None):
        """Start a scheduled backup when one is due. Returns True when it ran."""
        now = time.time() if now is None else now
        cfg = self.cfg
        if not cfg.get('enabled') or self.running or self.restoring:
            return False
        if core.is_due(now, self.state.get('last_ok'), self.state.get('last_attempt'),
                       cfg['frequency'], cfg['time'], cfg['weekday']):
            self.run_backup()
            return True
        return False

    # ---- running a backup -----------------------------------------------------------

    def _folder(self):
        return backup_settings.folder_for(self.root, self.cfg.get('subfolder', ''))

    def _other_disk(self):
        if self.cfg.get('require_other_disk') and self.rrd_db:
            return os.path.dirname(os.path.abspath(self.rrd_db))
        return None

    def _prepare_folder(self):
        """The folder to write to; the backup root must already exist (it is the mount), the
        sub-folder is created. Raises BackupError."""
        folder = self._folder()
        if folder is None:
            raise core.BackupError(core.REASON_NOT_WRITABLE)
        if not os.path.isdir(self.root):
            raise core.BackupError(core.REASON_FOLDER_MISSING)
        if self.cfg.get('require_other_disk') and self._other_disk() and \
                core.same_disk(self.root, self._other_disk()):
            raise core.BackupError(core.REASON_SAME_DISK)
        if folder != os.path.normpath(self.root):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                raise core.BackupError(core._reason_for_oserror(e))
        return folder

    def run_backup(self, now=None):
        """Run one backup now, in the calling thread. Returns {'ok': bool, 'reason': str, ...}."""
        with self.lock:
            if self.restoring:
                return {'ok': False, 'reason': core.REASON_RESTORE_BUSY}
            if self.running:
                return {'ok': False, 'reason': REASON_BUSY}
            self.running = True
        started = time.time() if now is None else now
        result = {'ok': False, 'reason': core.REASON_UNKNOWN}
        try:
            folder = self._prepare_folder()
            made = core.create_archive(folder, self.rrd_db, self.settings_db, self.conf_file, self.config_dir,
                                       now=datetime.datetime.fromtimestamp(started), rrdtool=self.rrdtool,
                                       retry_delay=self.retry_delay, other_disk_than=self._other_disk())
            removed = core.prune(folder, self.cfg['keep_daily'], self.cfg['keep_weekly'])
            self.listing = None  # re-read the folder for the next status
            self.state.update(last_ok=time.time(), last_attempt=started, reason='', last_file=made['name'],
                              last_size=made['size'])
            logger.info('Backup written: %s (%d kB), %d old archive(s) removed' %
                        (made['name'], made['size'] // 1024, len(removed)))
            result = {'ok': True, 'reason': '', 'name': made['name'], 'size': made['size']}
        except core.BackupError as e:
            self.state.update(last_attempt=started, reason=e.reason)
            logger.error('Backup failed: %s' % e.reason)
            result = {'ok': False, 'reason': e.reason}
        except Exception:
            self.state.update(last_attempt=started, reason=core.REASON_UNKNOWN)
            logger.exception('Backup failed')
        finally:
            self.running = False
            try:
                backup_settings.save_state(self.store, self.state)
            except Exception:
                logger.exception('Backup could not store its state')
        return result

    def start_now(self):
        """Back up now in a background thread (for the web page). Returns at once."""
        if self.restoring:
            return {'ok': False, 'reason': core.REASON_RESTORE_BUSY}
        if self.running:
            return {'ok': False, 'reason': REASON_BUSY}
        t = threading.Thread(target=self.run_backup, name='backup-now')
        t.daemon = True
        t.start()
        return {'ok': True, 'reason': ''}

    def _test_folder_blocking(self):
        try:
            folder = self._prepare_folder()
            free = core.check_folder(folder, self._other_disk())
            return {'ok': True, 'reason': '', 'free_bytes': free}
        except core.BackupError as e:
            return {'ok': False, 'reason': e.reason, 'free_bytes': None}
        except Exception:
            logger.exception('Backup folder test failed')
            return {'ok': False, 'reason': core.REASON_UNKNOWN, 'free_bytes': None}

    def test_folder(self):
        """Check the destination without writing a backup (bounded wait)"""
        finished, result = core.call_with_timeout(self._test_folder_blocking, self.test_timeout)
        if not finished:
            return {'ok': False, 'reason': core.REASON_TIMEOUT, 'free_bytes': None}
        return result

    # ---- restore --------------------------------------------------------------------

    def _check_name(self, name):
        """The archive name must be a listed archive of the folder (allow-list, the daemon is the
        final authority); returns the archive path. Raises BackupError."""
        if not isinstance(name, str) or not core.NAME_RE.fullmatch(name):
            raise core.BackupError(core.REASON_ARCHIVE_NOT_FOUND)
        folder = self._folder()
        if folder is None:
            raise core.BackupError(core.REASON_ARCHIVE_NOT_FOUND)
        return core.validate_archive_name(folder, name)

    def _preview_blocking(self, name):
        path = self._check_name(name)
        info = core.preview_archive(path)
        return {'ok': True, 'reason': '', 'name': name, 'size': os.lstat(path).st_size,
                'time': core.parse_name(name).timestamp(), 'manifest': info['manifest'],
                'has_config': info['has_config'], 'restart': 'auto' if self.in_docker else 'manual'}

    def _bounded(self, fn):
        try:
            finished, value = core.call_with_timeout(fn, self.preview_timeout)
        except core.BackupError as e:
            return {'ok': False, 'reason': e.reason}
        except Exception:
            logger.exception('Backup preview failed')
            return {'ok': False, 'reason': core.REASON_UNKNOWN}
        if not finished:
            return {'ok': False, 'reason': core.REASON_TIMEOUT}
        return value

    def preview_backup(self, name):
        """Manifest of one archive for the confirmation dialog (bounded wait)"""
        if not isinstance(name, str) or not core.NAME_RE.fullmatch(name):
            return {'ok': False, 'reason': core.REASON_ARCHIVE_NOT_FOUND}
        return self._bounded(lambda: self._preview_blocking(name))

    def start_restore(self, name):
        """Start restoring an archive in a worker thread. Returns at once."""
        if not isinstance(name, str) or not core.NAME_RE.fullmatch(name):
            return {'ok': False, 'reason': core.REASON_ARCHIVE_NOT_FOUND}
        # allow-list check against the folder listing before any worker is spawned
        checked = self._bounded(lambda: {'ok': True, 'reason': '', 'path': self._check_name(name)})
        if not checked.get('ok'):
            return {'ok': False, 'reason': checked['reason']}
        with self.lock:
            if self.restoring:
                return {'ok': False, 'reason': core.REASON_RESTORE_BUSY}
            if self.running:
                return {'ok': False, 'reason': REASON_BUSY}
            if not self.rrd_db or not self.settings_db or not self.data_dir:
                return {'ok': False, 'reason': core.REASON_UNKNOWN}
            self.restoring = True
            self._restore_cancel.clear()
            self.restore = dict(state='checking', step=1, name=name, reason='')
        t = threading.Thread(target=self.run_restore, args=(name,), name='backup-restore')
        t.daemon = True
        w = threading.Timer(self.restore_watchdog, self._restore_watchdog_fired)
        w.daemon = True
        self._watchdog = w
        w.start()
        t.start()
        logger.info('Restore of %s started from the web page' % name)
        return {'ok': True, 'reason': ''}

    def run_restore(self, name):
        ok = False
        try:
            path = self._check_name(name)
            locks = [self.glob.get('restore_lock') or _FALLBACK_LOCK]
            if self.store is not None and hasattr(self.store, 'lock'):
                locks.append(self.store.lock)
            made = core.restore_archive(path, self.rrd_db, self.nvdb, self.settings_db, rrdtool=self.rrdtool,
                                        locks=locks, progress=self._restore_progress,
                                        should_continue=lambda: not self._restore_cancel.is_set(),
                                        on_swapped=self._mark_restore_done, poll_ds_names=self.poll_ds_names)
            ok = True
            restart = 'auto' if self.in_docker else 'manual'
            self._save_restore_result(name, True, '', restart)
            logger.warning('Restore from %s done; previous data kept as %s' %
                           (name, ', '.join(made['pre_restore'])))
            self.restore = dict(state='restarting' if self.in_docker else 'done', step=5, name=name, reason='')
            if self.in_docker and self.exit_after_restore:
                t = threading.Timer(self.restart_delay, self._exit_for_restart)
                t.daemon = True
                t.start()
        except core.BackupError as e:
            logger.error('Restore failed: %s' % e.reason)
            self._restore_failed(name, e.reason)
        except Exception:
            logger.exception('Restore failed')
            self._restore_failed(name, core.REASON_UNKNOWN)
        finally:
            if self._watchdog is not None:
                self._watchdog.cancel()
            if not ok:
                self.restoring = False

    def _restore_failed(self, name, reason):
        self.restore = dict(state='failed', step=self.restore.get('step', 0), name=name, reason=reason)
        self._save_restore_result(name, False, reason, 'auto' if self.in_docker else 'manual')

    def _save_restore_result(self, name, ok, reason, restart):
        result = dict(name=name, time=time.time(), ok=bool(ok), reason=reason, restart=restart,
                      acknowledged=False)
        self.restore_result = result
        if self.data_dir:
            core.write_result(self.data_dir, result)

    def ack_restore_result(self):
        """The web page has shown the result. A failed restore also returns the in-memory state to idle."""
        result = self.restore_result
        if result and not result.get('acknowledged'):
            result['acknowledged'] = True
            if self.data_dir:
                core.write_result(self.data_dir, result)
        if self.restore.get('state') == 'failed':
            self.restore = dict(state='idle', step=0, name='', reason='')
        return {'ok': True}

    def _restore_progress(self, step):
        self.restore = dict(self.restore, state=step, step=STEP_NUMBERS.get(step, 0))

    def _mark_restore_done(self):
        conf = self.glob.get('conf')
        if conf is not None:
            conf.restore_done = True

    def _restore_watchdog_fired(self):
        if self.restore.get('state') in ('checking', 'extracting', 'building'):
            self._restore_cancel.set()
            self.restore = dict(self.restore, state='failed', reason=core.REASON_ARCHIVE_DAMAGED)
            logger.error('Restore gave up: the archive did not finish reading in time')

    def _exit_for_restart(self):
        logger.warning('Restarting the server to load the restored data')
        os.kill(os.getpid(), signal.SIGTERM)

    # ---- D-Bus contract -------------------------------------------------------------

    def get_settings_dict(self):
        view = backup_settings.public_view(self.cfg)
        view['available'] = True
        view['root'] = self.root
        return view

    def apply_settings(self, data):
        try:
            if self.store is None:
                return {'ok': False, 'errors': {'_': 'settings store unavailable'}}
            clean, errors = backup_settings.validate(data)
            if errors:
                return {'ok': False, 'errors': errors}
            backup_settings.save(self.store, clean)
            self.cfg = clean
            self.listing = None  # the folder may have changed
            return {'ok': True, 'errors': {}}
        except Exception:
            logger.exception('Backup apply settings failed')
            return {'ok': False, 'errors': {}}

    def status_dict(self):
        cfg = self.cfg
        state = self.state
        folder = self._folder() or self.root
        last_ok, last_attempt = state.get('last_ok'), state.get('last_attempt')
        failed = bool(state.get('reason')) and (not last_ok or (last_attempt or 0) > last_ok)
        if self.running:
            name = 'running'
        elif failed:
            name = 'error'
        elif not cfg.get('enabled'):
            name = 'disabled'
        elif last_ok:
            name = 'ok'
        else:
            name = 'waiting'
        next_run = None
        if cfg.get('enabled'):
            try:
                next_run = core.next_slot(datetime.datetime.now(), cfg['frequency'], cfg['time'],
                                          cfg['weekday']).timestamp()
            except Exception:
                next_run = None
        listing, slow = self._listing(folder)
        return {
            'available': True, 'state': name, 'enabled': bool(cfg.get('enabled')), 'running': self.running,
            'last_ok': last_ok, 'last_attempt': last_attempt, 'reason': state.get('reason', ''),
            'last_file': state.get('last_file', ''), 'last_size': state.get('last_size', 0),
            'next_run': next_run, 'root': self.root, 'folder': folder,
            'folder_exists': listing['folder_exists'], 'same_disk': listing['same_disk'],
            'folder_slow': slow,
            'archive_count': listing['count'], 'archives': listing['archives'],
            'restoring': self.restoring,
            'restore': dict(self.restore, steps=RESTORE_STEPS_TOTAL,
                            restart='auto' if self.in_docker else 'manual',
                            result=(dict(self.restore_result)
                                    if self.restore_result and not self.restore_result.get('acknowledged')
                                    else None)),
        }

    def _read_listing(self, folder):
        """Blocking folder reads, run through call_with_timeout"""
        other = os.path.dirname(os.path.abspath(self.rrd_db)) if self.rrd_db else None
        exists = os.path.isdir(folder)
        archives = core.list_archives(folder) if exists else []
        return {'folder_exists': exists, 'count': len(archives), 'archives': archives,
                'same_disk': bool(other and exists and core.same_disk(folder, other))}

    def _listing(self, folder):
        """(listing, slow): the folder facts for the status, read at most every listing_max_age
        seconds and never blocking longer than status_io_timeout; a stale copy is used when the folder
        does not answer (slow is then True)"""
        if self.listing is not None and time.time() - self.listing_time < self.listing_max_age:
            return self.listing, False
        try:
            finished, value = core.call_with_timeout(lambda: self._read_listing(folder), self.status_io_timeout)
        except Exception:
            logger.exception('Backup could not read the folder')
            finished, value = True, None
        if finished and value is not None:
            self.listing, self.listing_time = value, time.time()
            return value, False
        empty = {'folder_exists': True, 'count': 0, 'archives': [], 'same_disk': False}
        return (self.listing if self.listing is not None else empty), not finished
