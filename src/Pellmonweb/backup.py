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
import time
import cherrypy
from logging import getLogger
from .auth import require
from .security import check_same_origin
from Pellmonsrv.plugins.backup.settings import DEFAULTS, WEEKDAYS, validate
import json
from Pellmonsrv.backup_core import REASONS, REASON_UNKNOWN, NAME_RE, REASON_RESTORE_BUSY

# mirrors Pellmonsrv.plugins.backup.REASON_BUSY (a test pins the equality)
BACKUP_BUSY_REASON = 'a backup is already running'

logger = getLogger('pellMon')

MSG_SAVED = 'Settings saved.'
MSG_SAVED_OFF = 'Settings saved. Automatic backups are off.'
MSG_INVALID = 'Could not save. Fix the highlighted fields and try again.'
MSG_REJECTED = 'Could not do that. Sign in again and retry.'
MSG_DAEMON_DOWN = ('Cannot do that right now because the PellMon server is not running. '
                   'Your changes were not saved. Start the server and retry.')
MSG_NOT_ACTIVE = ('Cannot do that because the Backup plugin is not active on the server. '
                  'Update PellMon and restart the server.')
MSG_AUTH_DISABLED = 'Saving is disabled until web login credentials are configured.'
MSG_STARTED = 'Backup started. It usually takes a minute or two. Reload this page to see the result.'
MSG_BUSY = 'A backup is already running.'
MSG_START_FAILED = 'The backup could not be started.'
MSG_TEST_OK = 'The folder is ready for backups.'
MSG_TEST_OK_FREE = 'The folder is ready for backups. %s free.'
MSG_TEST_FAILED = 'The folder cannot be used: %s.'

MSG_RESTORE_STARTED = 'Restore started. Keep this page open: it shows each step and reconnects after the server restarts.'
MSG_RESTORE_BUSY = 'A restore is already running.'
MSG_RESTORE_BACKUP_BUSY = 'A backup is running. Wait until it has finished, then restore.'
MSG_RESTORE_FAILED_START = 'The restore could not be started: %s.'
MSG_RESTORE_NOT_FOUND = 'That backup was not found in the backup folder.'
MSG_PREVIEW_FAILED = 'The backup cannot be restored: %s.'
MSG_CONFIRM_WORD = 'Type RESTORE in capital letters to confirm.'

DONE_MESSAGES = {'saved': (MSG_SAVED, 'success'), 'off': (MSG_SAVED_OFF, 'success'),
                 'started': (MSG_STARTED, 'success'), 'busy': (MSG_BUSY, 'warning'),
                 'failed': (MSG_START_FAILED, 'danger'),
                 'restoring': (MSG_RESTORE_STARTED, 'success'), 'restore_busy': (MSG_RESTORE_BUSY, 'warning'),
                 'restore_backup_busy': (MSG_RESTORE_BACKUP_BUSY, 'warning')}

STEP_TEXT = {'checking': 'checking the archive', 'extracting': 'unpacking the archive',
             'building': 'rebuilding the database with rrdtool',
             'swapping': 'replacing the database and settings', 'restarting': 'restarting the server'}
TEXT_RESTARTING = 'Restarting the server... This page reconnects by itself.'
TEXT_RESTORED = ('Restored from %s at %s. The previous data is kept as .pre-restore files in the data folder. '
                 'Configuration files were not restored.')
TEXT_MANUAL = ('Restored from %s. Restart the PellMon server now to load the restored data. '
               'The previous data is kept as .pre-restore files in the data folder.')
TEXT_RESTORE_FAILED = 'The restore from %s failed: %s. Your data was not changed.'

STATUS_OFF = 'Off. Automatic backups are off. Turn on "Enable automatic backups" and save, or use Back up now.'
STATUS_WAITING = 'Waiting. The first backup starts within a minute.'
STATUS_RUNNING = 'Running. A backup is being written. Reload this page to see the result.'
STATUS_OK = 'Done. Last backup %s (%s).'
STATUS_NEXT = ' Next backup %s.'
STATUS_ERROR = 'Failed. The last backup failed: %s.'
STATUS_RETRY = ' PellMon retries every hour.'
STATUS_NOT_ACTIVE = ('The Backup plugin is not active on the server. '
                     'Check the PellMon installation and restart the server.')
STATUS_DAEMON_DOWN = ('Cannot read the status because the PellMon server is not running. '
                      'Start the server to see the status.')

WARN_SAME_DISK = ('The backup folder is on the same disk as the database. A backup there does not protect against '
                  'a failing disk. If you meant to use a NAS or USB drive, check that it is mounted on the host.')
WARN_NO_FOLDER = 'The backup folder does not exist yet. Is the NAS or USB drive mounted on the host?'
WARN_SLOW = 'The backup folder did not answer. Is the NAS reachable? The list below may be out of date.'

CHECKBOX_FIELDS = ('enabled', 'require_other_disk')
TEXT_FIELDS = ('subfolder', 'frequency', 'time', 'weekday', 'keep_daily', 'keep_weekly')
_OFF_VALUES = ('', '0', 'false', 'off', 'no')


def human_size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ''
    for unit in ('B', 'kB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%d %s' % (n, unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0


def _view(level, glyph, copy, title='', split=True):
    if split:
        word, text = copy.split(' ', 1)
    else:
        word, text = '', copy
    return dict(level=level, glyph=glyph, word=word, text=text, title=title)


def _reason(value):
    return value if value in REASONS else REASON_UNKNOWN


def _stamp(value, fmt):
    try:
        return time.strftime(fmt, time.localtime(float(value)))
    except Exception:
        return ''


def status_view(status, daemon_down=False):
    """Map the daemon status to the status line: {level, glyph, word, text, title}"""
    if daemon_down:
        return _view('warning', 'warning-sign', STATUS_DAEMON_DOWN, split=False)
    if not isinstance(status, dict) or status.get('available') is False:
        return _view('warning', 'warning-sign', STATUS_NOT_ACTIVE, split=False)
    state = status.get('state')
    nxt = status.get('next_run')
    next_text = (STATUS_NEXT % _stamp(nxt, '%Y-%m-%d %H:%M')) if nxt and status.get('enabled') else ''
    if state == 'running':
        return _view('well', '', STATUS_RUNNING)
    if state == 'error':
        retry = STATUS_RETRY if status.get('enabled') else ''
        return _view('danger', 'remove', STATUS_ERROR % _reason(status.get('reason')) + retry)
    if state == 'ok':
        last = status.get('last_ok')
        return _view('success', 'ok', (STATUS_OK % (_stamp(last, '%Y-%m-%d %H:%M'), human_size(status.get('last_size')))) + next_text,
                     title=status.get('last_file') or '')
    if state == 'waiting':
        return _view('well', '', STATUS_WAITING)
    return _view('well', '', STATUS_OFF)


def _valid_name(name):
    return isinstance(name, str) and NAME_RE.fullmatch(name) is not None


def _restore_view(level, text, active, step=0, steps=5, state=''):
    return dict(state=state, level=level, text=text, active=active, step=step, steps=steps)


def restore_view(status, daemon_down=False):
    """Map the daemon restore block to {state, level, text, active, step, steps}; fixed text only"""
    if daemon_down:
        return _restore_view('warning', TEXT_RESTARTING, True, state='daemon_down')
    block = status.get('restore') if isinstance(status, dict) else None
    if not isinstance(block, dict):
        return _restore_view('well', '', False, state='idle')
    state = str(block.get('state') or 'idle')
    result = block.get('result') if isinstance(block.get('result'), dict) else None
    unacked = result is not None and not result.get('acknowledged')
    try:
        step = int(block.get('step') or 0)
        steps = int(block.get('steps') or 5)
    except (TypeError, ValueError):
        step, steps = 0, 5
    name = block.get('name')
    name = name if _valid_name(name) else ''
    if state in STEP_TEXT:
        text = 'Restoring %s: step %d of %d, %s...' % (name, step, steps, STEP_TEXT[state])
        return _restore_view('well', text, True, step, steps, state)
    if state == 'done' and block.get('restart') == 'manual':
        return _restore_view('warning', TEXT_MANUAL % name, False, step, steps, state)
    if state == 'failed':
        return _restore_view('danger', TEXT_RESTORE_FAILED % (name, _reason(block.get('reason'))), False, step, steps, state)
    if unacked:
        rname = result.get('name')
        rname = rname if _valid_name(rname) else ''
        if result.get('ok'):
            return _restore_view('success', TEXT_RESTORED % (rname, _stamp(result.get('time'), '%Y-%m-%d %H:%M')),
                                 False, step, steps, state)
        return _restore_view('danger', TEXT_RESTORE_FAILED % (rname, _reason(result.get('reason'))),
                             False, step, steps, state)
    return _restore_view('well', '', False, step, steps, 'idle')


def archive_rows(status):
    rows = []
    for a in (status or {}).get('archives', []) if isinstance(status, dict) else []:
        rows.append(dict(name=str(a.get('name', '')), size=human_size(a.get('size')),
                         when=_stamp(a.get('time'), '%Y-%m-%d %H:%M')))
    return rows


def warnings(settings, status):
    out = []
    if isinstance(status, dict) and status.get('available') is not False:
        if status.get('folder_slow'):
            out.append(WARN_SLOW)
        elif status.get('folder_exists') is False:
            out.append(WARN_NO_FOLDER)
        elif status.get('same_disk'):
            out.append(WARN_SAME_DISK)
    return out


class Backup(object):
    def __init__(self, lookup, dbus, credentials=None):
        self.lookup = lookup
        self.dbus = dbus
        self.credentials = credentials

    # ---- helpers ----

    def _collect(self, form):
        """Raw form values; a checkbox is explicitly 'on' or 'off' so that unticked means off"""
        raw = {}
        for key in CHECKBOX_FIELDS:
            checked = key in form and str(_last(form[key])).strip().lower() not in _OFF_VALUES
            raw[key] = 'on' if checked else 'off'
        for key in TEXT_FIELDS:
            if key in form:
                raw[key] = _last(form[key])
        return raw

    def _load(self):
        """Returns (settings, available, daemon_down, root); DEFAULTS on any problem"""
        try:
            data = self.dbus.backup_get_settings()
        except Exception:
            return dict(DEFAULTS), True, True, '/backups'
        if not isinstance(data, dict) or data.get('available') is False:
            return dict(DEFAULTS), False, False, '/backups'
        settings = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in data:
                settings[key] = data[key]
        return settings, True, False, data.get('root') or '/backups'

    def _status(self, daemon_down):
        if daemon_down:
            return None, status_view(None, daemon_down=True)
        try:
            status = self.dbus.backup_status()
        except Exception:
            return None, status_view(None, daemon_down=True)
        return status, status_view(status)

    def _render(self, **overrides):
        settings, available, daemon_down, root = self._load()
        status, view = self._status(daemon_down)
        ctx = dict(username=cherrypy.session.get('_cp_username'),
                   webroot=cherrypy.request.script_name,
                   active_page='backup',
                   settings=settings,
                   weekdays=WEEKDAYS,
                   errors={},
                   msg='',
                   msg_level='',
                   auth_configured=bool(self.credentials),
                   available=available,
                   daemon_down=daemon_down,
                   root=root,
                   status=view,
                   warnings=warnings(settings, status),
                   archives=archive_rows(status),
                   archive_count=(status or {}).get('archive_count', 0) if isinstance(status, dict) else 0,
                   folder=(status or {}).get('folder', root) if isinstance(status, dict) else root,
                   restore=restore_view(status, daemon_down))
        block = status.get('restore') if isinstance(status, dict) else None
        result = block.get('result') if isinstance(block, dict) else None
        # per-request flag: the controller object is shared between threads
        cherrypy.request.backup_ack = isinstance(result, dict) and not result.get('acknowledged')
        ctx.update(overrides)
        return self.lookup.get_template('backup.html').render(**ctx)

    def _render_confirm(self, name, preview, error=''):
        manifest = preview.get('manifest') if isinstance(preview.get('manifest'), dict) else {}

        def field(key):
            value = manifest.get(key)
            return '' if value is None else str(value)
        return self.lookup.get_template('backup_restore.html').render(
            username=cherrypy.session.get('_cp_username'),
            webroot=cherrypy.request.script_name,
            active_page='backup',
            name=name,
            when=_stamp(preview.get('time'), '%Y-%m-%d %H:%M'),
            size=human_size(preview.get('size')),
            created=field('created'), machine=field('machine'),
            rrdtool_version=field('rrdtool_version'), created_by=field('created_by'),
            has_config=bool(preview.get('has_config')),
            restart='auto' if preview.get('restart') == 'auto' else 'manual',
            auth_configured=bool(self.credentials),
            error=error)

    def _preview_or_page(self, name):
        """(preview, None) or (None, the backup page to show instead)"""
        try:
            preview = self.dbus.backup_preview(name)
        except Exception:
            return None, self._render(msg=MSG_DAEMON_DOWN, msg_level='warning')
        if not isinstance(preview, dict) or preview.get('available') is False:
            return None, self._render(msg=MSG_NOT_ACTIVE, msg_level='danger')
        if not preview.get('ok'):
            return None, self._render(msg=MSG_PREVIEW_FAILED % _reason(preview.get('reason')), msg_level='danger')
        return preview, None

    def _echo(self, raw, clean, errors):
        echo = dict(clean)
        for key in errors:
            if key in raw and key in echo:
                echo[key] = raw[key]
        return echo

    def _reject(self, what):
        cherrypy.response.status = 403
        logger.warning('rejected cross-origin Backup %s: origin=%r host=%r', what,
                       cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                       cherrypy.request.headers.get('Host'))

    def _guard(self, what):
        """None when a POST may proceed, else the page to show instead"""
        if cherrypy.request.method != 'POST':
            return self._render(msg=MSG_REJECTED, msg_level='danger')
        if not check_same_origin():
            self._reject(what)
            return self._render(msg=MSG_REJECTED, msg_level='danger')
        if not self.credentials:
            return self._render(msg=MSG_AUTH_DISABLED, msg_level='warning')
        return None

    # ---- routes ----

    @cherrypy.expose
    @require()
    def index(self, done=''):
        found = DONE_MESSAGES.get(done) if isinstance(done, str) else None
        if found:
            page = self._render(msg=found[0], msg_level=found[1])
        else:
            _, _, daemon_down, _ = self._load()
            if daemon_down:
                return self._render(msg=MSG_DAEMON_DOWN, msg_level='warning')
            page = self._render()
        if getattr(cherrypy.request, 'backup_ack', False):
            try:
                self.dbus.backup_restore_ack()
            except Exception:
                pass
        return page

    @cherrypy.expose
    @require()
    def restore(self, name=''):
        name = _last(name)
        if not _valid_name(name):
            return self._render(msg=MSG_RESTORE_NOT_FOUND, msg_level='warning')
        preview, page = self._preview_or_page(name)
        if page is not None:
            return page
        return self._render_confirm(name, preview)

    @cherrypy.expose
    @require()
    def restore_run(self, name='', confirm='', **form):
        blocked = self._guard('restore')
        if blocked is not None:
            return blocked
        name = _last(name)
        if not _valid_name(name):
            return self._render(msg=MSG_RESTORE_NOT_FOUND, msg_level='warning')
        if str(_last(confirm)).strip() != 'RESTORE':
            preview, page = self._preview_or_page(name)
            if page is not None:
                return page
            return self._render_confirm(name, preview, error=MSG_CONFIRM_WORD)
        try:
            result = self.dbus.backup_restore(name)
        except Exception:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger')
        if isinstance(result, dict) and result.get('available') is False:
            return self._render(msg=MSG_NOT_ACTIVE, msg_level='danger')
        base = cherrypy.request.script_name + '/backup/?done='
        reason = result.get('reason', '') if isinstance(result, dict) else ''
        if isinstance(result, dict) and result.get('ok'):
            raise cherrypy.HTTPRedirect(base + 'restoring', 303)
        if reason == REASON_RESTORE_BUSY:
            raise cherrypy.HTTPRedirect(base + 'restore_busy', 303)
        if reason == BACKUP_BUSY_REASON:
            raise cherrypy.HTTPRedirect(base + 'restore_backup_busy', 303)
        return self._render(msg=MSG_RESTORE_FAILED_START % _reason(reason), msg_level='danger')

    @cherrypy.expose
    @require()
    def restore_status(self):
        try:
            view = restore_view(self.dbus.backup_status())
        except Exception:
            view = restore_view(None, daemon_down=True)
        cherrypy.response.headers['Content-Type'] = 'application/json'
        cherrypy.response.headers['Cache-Control'] = 'no-store'
        return json.dumps(view)

    @cherrypy.expose
    @require()
    def save(self, **form):
        blocked = self._guard('save')
        if blocked is not None:
            return blocked
        raw = self._collect(form)
        clean, errors = validate(raw)
        if errors:
            return self._render(msg=MSG_INVALID, msg_level='danger', errors=errors,
                                settings=self._echo(raw, clean, errors))
        try:
            result = self.dbus.backup_set_settings(clean)
        except Exception:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger', settings=clean)
        if not isinstance(result, dict) or not result.get('ok'):
            daemon_errors = result.get('errors') if isinstance(result, dict) else None
            if isinstance(daemon_errors, dict) and daemon_errors:
                return self._render(msg=MSG_INVALID, msg_level='danger', errors=daemon_errors,
                                    settings=self._echo(raw, clean, daemon_errors))
            if isinstance(result, dict) and result.get('available') is False:
                return self._render(msg=MSG_NOT_ACTIVE, msg_level='danger', settings=clean)
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger', settings=clean)
        raise cherrypy.HTTPRedirect(cherrypy.request.script_name + '/backup/?done=' +
                                    ('saved' if clean['enabled'] else 'off'), 303)

    @cherrypy.expose
    @require()
    def run(self, **form):
        blocked = self._guard('run')
        if blocked is not None:
            return blocked
        try:
            result = self.dbus.backup_start()
        except Exception:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger')
        if isinstance(result, dict) and result.get('available') is False:
            return self._render(msg=MSG_NOT_ACTIVE, msg_level='danger')
        if isinstance(result, dict) and result.get('ok'):
            done = 'started'
        elif isinstance(result, dict) and result.get('reason') == REASON_RESTORE_BUSY:
            done = 'restore_busy'
        elif isinstance(result, dict) and 'already running' in str(result.get('reason', '')):
            done = 'busy'
        else:
            done = 'failed'
        raise cherrypy.HTTPRedirect(cherrypy.request.script_name + '/backup/?done=' + done, 303)

    @cherrypy.expose
    @require()
    def test(self, **form):
        blocked = self._guard('test')
        if blocked is not None:
            return blocked
        try:
            result = self.dbus.backup_test()
        except Exception:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger')
        if isinstance(result, dict) and result.get('available') is False:
            return self._render(msg=MSG_NOT_ACTIVE, msg_level='danger')
        if isinstance(result, dict) and result.get('ok'):
            free = human_size(result.get('free_bytes')) if result.get('free_bytes') else ''
            return self._render(msg=(MSG_TEST_OK_FREE % free) if free else MSG_TEST_OK, msg_level='success')
        reason = _reason((result or {}).get('reason') if isinstance(result, dict) else '')
        return self._render(msg=MSG_TEST_FAILED % reason, msg_level='danger')


def _last(value):
    if isinstance(value, (list, tuple)):
        return value[-1] if value else ''
    return value
