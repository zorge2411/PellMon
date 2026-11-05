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
from Pellmonsrv.backup_core import REASONS, REASON_UNKNOWN

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

DONE_MESSAGES = {'saved': (MSG_SAVED, 'success'), 'off': (MSG_SAVED_OFF, 'success'),
                 'started': (MSG_STARTED, 'success'), 'busy': (MSG_BUSY, 'warning'),
                 'failed': (MSG_START_FAILED, 'danger')}

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


def archive_rows(status):
    rows = []
    for a in (status or {}).get('archives', []) if isinstance(status, dict) else []:
        rows.append(dict(name=str(a.get('name', '')), size=human_size(a.get('size')),
                         when=_stamp(a.get('time'), '%Y-%m-%d %H:%M')))
    return rows


def warnings(settings, status):
    out = []
    if isinstance(status, dict) and status.get('available') is not False:
        if status.get('folder_exists') is False:
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
                   folder=(status or {}).get('folder', root) if isinstance(status, dict) else root)
        ctx.update(overrides)
        return self.lookup.get_template('backup.html').render(**ctx)

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
            return self._render(msg=found[0], msg_level=found[1])
        _, _, daemon_down, _ = self._load()
        if daemon_down:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='warning')
        return self._render()

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
