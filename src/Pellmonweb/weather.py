#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2014  Anders Nylund

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
from Pellmonsrv.plugins.openweathermap.settings import DEFAULTS, validate

logger = getLogger('pellMon')

MSG_SAVED = 'Settings saved. The weather is updated within a few seconds.'
MSG_SAVED_OFF = 'Settings saved. OpenWeatherMap is off.'
MSG_INVALID = 'Could not save. Fix the highlighted fields and try again.'
MSG_REJECTED = 'Could not save the settings. Sign in again and retry.'
MSG_DAEMON_DOWN = ('Cannot save right now because the PellMon server is not running. '
                   'Your changes were not saved. Start the server and retry.')
MSG_NOT_ACTIVE = ('Cannot save because the OpenWeatherMap plugin is not active on the server. '
                  'Your changes were not saved. Update PellMon and restart the server.')
MSG_AUTH_DISABLED = 'Saving is disabled until web login credentials are configured.'

SAVED_MESSAGES = {'1': MSG_SAVED, 'off': MSG_SAVED_OFF}

UNKNOWN_REASON = 'unknown error (see the server log)'
REASONS = frozenset(['invalid API key', 'location not found', 'could not reach openweathermap.org'])

STATUS_OFF = 'Off. OpenWeatherMap is turned off. Turn on "Enable OpenWeatherMap" and save to fetch the weather.'
STATUS_NO_KEY = 'Waiting. Enter an API key and save to fetch the weather.'
STATUS_WAITING = 'Fetching the weather for %s...'
STATUS_OK = 'Updated. Last update for %s: %s.'
STATUS_ERROR = 'Update failed. %s. PellMon retries every 5 minutes.'
STATUS_NOT_ACTIVE = ('The OpenWeatherMap plugin is not active on the server. '
                     'Check the PellMon installation and restart the server.')
STATUS_DAEMON_DOWN = ('Cannot read the status because the PellMon server is not running. '
                      'Start the server to see the status.')

CHECKBOX_FIELDS = ('enabled', 'clear_apikey')
TEXT_FIELDS = ('location', 'unit', 'apikey')
_OFF_VALUES = ('', '0', 'false', 'off', 'no')


def _view(level, glyph, copy, title='', split=True):
    if split:
        word, text = copy.split(' ', 1)
    else:
        word, text = '', copy
    return dict(level=level, glyph=glyph, word=word, text=text, title=title)


def _reason(value):
    return value if value in REASONS else UNKNOWN_REASON


def _stamp(value, fmt):
    try:
        return time.strftime(fmt, time.localtime(float(value)))
    except Exception:
        return ''


def status_view(settings, status, daemon_down=False):
    """Map the daemon status (plus the settings) to the status line: {level, glyph, word, text, title}"""
    if daemon_down:
        return _view('warning', 'warning-sign', STATUS_DAEMON_DOWN, split=False)
    if not isinstance(status, dict) or status.get('available') is False:
        return _view('warning', 'warning-sign', STATUS_NOT_ACTIVE, split=False)
    settings = settings if isinstance(settings, dict) else {}
    state = status.get('state')
    location = status.get('location') or settings.get('location', '')
    if state == 'disabled':
        return _view('well', '', STATUS_OFF)
    if state == 'no_key':
        return _view('well', '', STATUS_NO_KEY)
    if state == 'waiting':
        return _view('well', '', STATUS_WAITING % location)
    if state == 'ok':
        last = status.get('last_fetch')
        stamp = _stamp(last, '%H:%M:%S') if last else ''
        return _view('success', 'ok', STATUS_OK % (location, stamp),
                     title=_stamp(last, '%Y-%m-%d %H:%M:%S'))
    if state == 'error':
        return _view('danger', 'remove', STATUS_ERROR % _reason(status.get('reason')))
    return _view('well', '', STATUS_NO_KEY)


class Weather(object):
    def __init__(self, lookup, dbus, credentials=None):
        self.lookup = lookup
        self.dbus = dbus
        self.credentials = credentials

    # ---- helpers ----

    def _collect(self, form):
        """Raw form values; a checkbox is 'on' when submitted."""
        raw = {}
        for key in CHECKBOX_FIELDS:
            if key in form and str(_last(form[key])).strip().lower() not in _OFF_VALUES:
                raw[key] = 'on'
        for key in TEXT_FIELDS:
            if key in form:
                raw[key] = _last(form[key])
        return raw

    def _load(self):
        """Returns (settings, has_apikey, available, daemon_down); DEFAULTS on any problem"""
        try:
            data = self.dbus.owm_get_settings()
        except Exception:
            return dict(DEFAULTS, location=''), False, True, True
        if not isinstance(data, dict) or data.get('available') is False:
            return dict(DEFAULTS, location=''), False, False, False
        settings = dict(DEFAULTS, location='')
        for key in DEFAULTS:
            if key in data:
                settings[key] = data[key]
        if 'location' in data:
            settings['location'] = data['location']
        return settings, bool(data.get('has_apikey')), True, False

    def _status(self, settings, daemon_down):
        if daemon_down:
            return status_view(settings, None, daemon_down=True)
        try:
            status = self.dbus.owm_status()
        except Exception:
            return status_view(settings, None, daemon_down=True)
        return status_view(settings, status)

    def _render(self, **overrides):
        settings, has_apikey, available, daemon_down = self._load()
        ctx = dict(username=cherrypy.session.get('_cp_username'),
                   webroot=cherrypy.request.script_name,
                   active_page='weather',
                   settings=settings,
                   has_apikey=has_apikey,
                   apikey_reentered=False,
                   errors={},
                   msg='',
                   msg_level='',
                   auth_configured=bool(self.credentials),
                   available=available,
                   daemon_down=daemon_down)
        ctx['status'] = self._status(settings, daemon_down)
        ctx.update(overrides)
        return self.lookup.get_template('weather.html').render(**ctx)

    def _check(self, form, has_stored_key):
        """Validate the form. Returns (raw, clean, errors, apikey)"""
        raw = self._collect(form)
        apikey = _last(form.get('apikey', ''))
        if not isinstance(apikey, str):
            apikey = ''
        clean, errors = validate(raw, has_stored_key)
        return raw, clean, errors, apikey

    def _echo(self, raw, clean, errors):
        echo = dict(clean)
        echo.pop('apikey', None)
        for key in errors:
            if key in raw and key in echo:
                echo[key] = raw[key]
        return echo

    def _payload(self, clean, apikey, form):
        payload = {'enabled': clean['enabled'], 'location': clean.get('location', ''), 'unit': clean['unit']}
        if apikey:
            payload['apikey'] = apikey
        elif 'clear_apikey' in form and str(_last(form['clear_apikey'])).strip().lower() not in _OFF_VALUES:
            payload['clear_apikey'] = True
        return payload

    def _reject(self, what):
        cherrypy.response.status = 403
        logger.warning('rejected cross-origin OpenWeatherMap settings %s: origin=%r host=%r', what,
                       cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                       cherrypy.request.headers.get('Host'))

    # ---- routes ----

    @cherrypy.expose
    @require()
    def index(self, saved=''):
        msg = SAVED_MESSAGES.get(saved) if isinstance(saved, str) else None
        if msg:
            return self._render(msg=msg, msg_level='success')
        settings, has_apikey, available, daemon_down = self._load()
        if daemon_down:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='warning')
        return self._render()

    @cherrypy.expose
    @require()
    def save(self, **form):
        if cherrypy.request.method != 'POST':
            return self._render(msg=MSG_REJECTED, msg_level='danger')
        if not check_same_origin():
            self._reject('save')
            return self._render(msg=MSG_REJECTED, msg_level='danger')
        _, has_apikey, _, _ = self._load()
        raw, clean, errors, apikey = self._check(form, has_apikey)
        if errors:
            return self._render(msg=MSG_INVALID, msg_level='danger', errors=errors,
                                settings=self._echo(raw, clean, errors),
                                apikey_reentered=bool(apikey))
        if not self.credentials:
            return self._render(msg=MSG_AUTH_DISABLED, msg_level='warning', settings=self._echo(raw, clean, {}),
                                apikey_reentered=bool(apikey))
        payload = self._payload(clean, apikey, form)
        try:
            result = self.dbus.owm_set_settings(payload)
        except Exception:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger', settings=self._echo(raw, clean, {}),
                                apikey_reentered=bool(apikey))
        if not isinstance(result, dict) or not result.get('ok'):
            daemon_errors = result.get('errors') if isinstance(result, dict) else None
            if isinstance(daemon_errors, dict) and daemon_errors:
                return self._render(msg=MSG_INVALID, msg_level='danger', errors=daemon_errors,
                                    settings=self._echo(raw, clean, daemon_errors),
                                    apikey_reentered=bool(apikey))
            if isinstance(result, dict) and result.get('available') is False:
                return self._render(msg=MSG_NOT_ACTIVE, msg_level='danger', settings=self._echo(raw, clean, {}),
                                    apikey_reentered=bool(apikey))
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger', settings=self._echo(raw, clean, {}),
                                apikey_reentered=bool(apikey))
        saved = '1' if clean['enabled'] else 'off'
        raise cherrypy.HTTPRedirect(cherrypy.request.script_name + '/weather/?saved=' + saved, 303)


def _last(value):
    if isinstance(value, (list, tuple)):
        return value[-1] if value else ''
    return value
