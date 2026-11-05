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
import threading
import time
from logging import getLogger

from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Keyval_storage
from Pellmonsrv import backup_core as core
from . import settings as backup_settings

logger = getLogger('pellMon')

DEFAULT_ROOT = '/backups'
LIST_LIMIT = 20
REASON_BUSY = 'a backup is already running'


class backupplugin(protocols):
    autostart = True       # tests switch the scheduler thread off
    startup_delay = 120    # seconds after start before the first schedule check
    check_interval = 30    # seconds between schedule checks

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
        if not cfg.get('enabled') or self.running:
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
        if self.running:
            return {'ok': False, 'reason': REASON_BUSY}
        t = threading.Thread(target=self.run_backup, name='backup-now')
        t.daemon = True
        t.start()
        return {'ok': True, 'reason': ''}

    def test_folder(self):
        """Check the destination without writing a backup"""
        try:
            folder = self._prepare_folder()
            free = core.check_folder(folder, self._other_disk())
            return {'ok': True, 'reason': '', 'free_bytes': free}
        except core.BackupError as e:
            return {'ok': False, 'reason': e.reason, 'free_bytes': None}
        except Exception:
            logger.exception('Backup folder test failed')
            return {'ok': False, 'reason': core.REASON_UNKNOWN, 'free_bytes': None}

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
        archives = core.list_archives(folder)
        other = os.path.dirname(os.path.abspath(self.rrd_db)) if self.rrd_db else None
        return {
            'available': True, 'state': name, 'enabled': bool(cfg.get('enabled')), 'running': self.running,
            'last_ok': last_ok, 'last_attempt': last_attempt, 'reason': state.get('reason', ''),
            'last_file': state.get('last_file', ''), 'last_size': state.get('last_size', 0),
            'next_run': next_run, 'root': self.root, 'folder': folder,
            'folder_exists': os.path.isdir(folder),
            'same_disk': bool(other and os.path.isdir(folder) and core.same_disk(folder, other)),
            'archive_count': len(archives), 'archives': archives[:LIST_LIMIT],
        }
