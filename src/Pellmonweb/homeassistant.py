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
import json
import time
import cherrypy
from logging import getLogger
from .auth import require
from .security import check_same_origin
from Pellmonsrv.plugins.homeassistant.settings import DEFAULTS, validate, validate_password, tls_verify_explicit

logger = getLogger('pellMon')

MSG_SAVED = 'Settings saved. Reconnecting to the broker...'
MSG_SAVED_COMMANDS = 'Settings saved. Home Assistant can now change burner settings.'
MSG_SAVED_OFF = 'Settings saved. Home Assistant publishing is off.'
MSG_INVALID = 'Could not save. Fix the highlighted fields and try again.'
MSG_REJECTED = 'Could not save the settings. Sign in again and retry.'
MSG_DAEMON_DOWN = ('Cannot save right now because the PellMon server is not running. '
                   'Your changes were not saved. Start the server and retry.')
MSG_AUTH_DISABLED = 'Saving is disabled until web login credentials are configured.'

TEST_OK = 'Connection successful. The broker accepted the host, port, credentials and TLS settings. Nothing was saved.'
TEST_FAILED = 'Test failed: %s. Nothing was saved.'
TEST_INVALID = 'Test failed: fix the highlighted fields first.'
TEST_REJECTED = 'Could not test the settings. Sign in again and retry.'
TEST_DAEMON_DOWN = ('Cannot test right now because the PellMon server is not running. '
                    'Your changes were not saved. Start the server and retry.')
TEST_AUTH_DISABLED = 'Testing is disabled until web login credentials are configured.'
TEST_RUNNING = 'Testing the connection...'

# daemon tester <= 8 s in total (incl. the 5 s connect timeout) < this cap < 12 s browser abort
TEST_POLL_CAP = 10

UNKNOWN_REASON = 'unknown error (see the server log)'
REASONS = frozenset(['connection refused', 'host not found', 'timed out', 'wrong username or password',
                     'not authorised', 'certificate could not be verified', 'TLS handshake failed',
                     'connection lost'])

STATUS_OFF = 'Off. Home Assistant publishing is turned off. Turn on "Enable Home Assistant MQTT" and save to connect.'
STATUS_CONNECTING = 'Connecting to %s:%s...'
STATUS_CONNECTED = 'Connected to %s:%s. Last publish: %s.'
STATUS_CONNECTED_EMPTY = 'Connected to %s:%s. No values published yet.'
STATUS_BURNER_OFFLINE = ('Connected to %s:%s, but the burner is not connected. '
                         'Home Assistant shows the entities as unavailable until it answers again.')
STATUS_DISCONNECTED = 'Disconnected from %s:%s: %s. PellMon keeps retrying automatically.'
STATUS_NOT_ACTIVE = ('The Home Assistant MQTT plugin is not active on the server. '
                     'Check the PellMon installation and restart the server.')
STATUS_DAEMON_DOWN = ('Cannot read the status because the PellMon server is not running. '
                      'Start the server to see the status.')

SAVED_MESSAGES = {'1': MSG_SAVED, 'commands': MSG_SAVED_COMMANDS, 'off': MSG_SAVED_OFF}

CHECKBOX_FIELDS = ('enabled', 'tls', 'tls_verify', 'allow_commands')
TEXT_FIELDS = ('host', 'port', 'username', 'prefix', 'discovery_prefix', 'device_id',
               'device_name', 'node_id', 'uid_prefix', 'refresh')
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
    host = status.get('host') or settings.get('host', '')
    port = status.get('port') or settings.get('port', '')
    if state == 'disabled':
        return _view('well', '', STATUS_OFF)
    if state == 'connected':
        if status.get('availability') == 'offline':
            return _view('warning', 'warning-sign', STATUS_BURNER_OFFLINE % (host, port))
        last = status.get('last_publish')
        stamp = _stamp(last, '%H:%M:%S') if last else ''
        if stamp:
            return _view('success', 'ok', STATUS_CONNECTED % (host, port, stamp),
                         title=_stamp(last, '%Y-%m-%d %H:%M:%S'))
        return _view('success', 'ok', STATUS_CONNECTED_EMPTY % (host, port))
    if state == 'disconnected':
        return _view('danger', 'remove', STATUS_DISCONNECTED % (host, port, _reason(status.get('reason'))))
    return _view('well', '', STATUS_CONNECTING % (host, port))


class HomeAssistant(object):
    def __init__(self, lookup, dbus, credentials=None):
        self.lookup = lookup
        self.dbus = dbus
        self.credentials = credentials
        self._sleep = time.sleep
        self._clock = time.monotonic

    # ---- helpers ----

    def _collect(self, form):
        """Raw form values; a checkbox is 'on' when submitted, the tls_verify_field marker is passed as-is.
        A missing tls_verify is deliberately not turned into False here (validate() decides)."""
        raw = {}
        for key in CHECKBOX_FIELDS:
            if key in form and str(_last(form[key])).strip().lower() not in _OFF_VALUES:
                raw[key] = 'on'
        if 'tls_verify_field' in form:
            raw['tls_verify_field'] = _last(form['tls_verify_field'])
        for key in TEXT_FIELDS:
            if key in form:
                raw[key] = _last(form[key])
        return raw

    def _load(self):
        """Returns (settings, has_password, available, daemon_down); DEFAULTS on any problem"""
        try:
            data = self.dbus.mqtt_get_settings()
        except Exception:
            return dict(DEFAULTS), False, True, True
        if not isinstance(data, dict) or data.get('available') is False:
            return dict(DEFAULTS), False, False, False
        settings = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in data:
                settings[key] = data[key]
        return settings, bool(data.get('has_password')), True, False

    def _status(self, settings, daemon_down):
        if daemon_down:
            return status_view(settings, None, daemon_down=True)
        try:
            status = self.dbus.mqtt_status()
        except Exception:
            return status_view(settings, None, daemon_down=True)
        return status_view(settings, status)

    def _render(self, **overrides):
        settings, has_password, available, daemon_down = self._load()
        ctx = dict(username=cherrypy.session.get('_cp_username'),
                   webroot=cherrypy.request.script_name,
                   active_page='homeassistant',
                   settings=settings,
                   has_password=has_password,
                   password_reentered=False,
                   errors={},
                   msg='',
                   msg_level='',
                   test_msg='',
                   test_level='',
                   auth_configured=bool(self.credentials),
                   available=available,
                   daemon_down=daemon_down)
        ctx['status'] = self._status(settings, daemon_down)
        ctx.update(overrides)
        return self.lookup.get_template('homeassistant.html').render(**ctx)

    def _check(self, form, for_test=False):
        """Validate the form. Returns (raw, clean, errors, password)"""
        raw = self._collect(form)
        password = _last(form.get('password', ''))
        if not isinstance(password, str):
            password = ''
        clean, errors = validate(raw, for_test=for_test, current=None)
        perr = validate_password(password)
        if perr:
            errors['password'] = perr
        return raw, clean, errors, password

    def _echo(self, raw, clean, errors):
        echo = dict(clean)
        for key in errors:
            if key in raw and key in echo:
                echo[key] = raw[key]
        return echo

    def _payload(self, raw, clean, password, form, with_clear):
        payload = dict(clean)
        payload['tls_verify_field'] = bool(tls_verify_explicit(raw))
        if password:
            payload['password'] = password
        elif with_clear and 'clear_password' in form and \
                str(_last(form['clear_password'])).strip().lower() not in _OFF_VALUES:
            payload['clear_password'] = True
        return payload

    def _reject(self, what):
        cherrypy.response.status = 403
        logger.warning('rejected cross-origin Home Assistant settings %s: origin=%r host=%r', what,
                       cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                       cherrypy.request.headers.get('Host'))

    # ---- routes ----

    @cherrypy.expose
    @require()
    def index(self, saved=''):
        msg = SAVED_MESSAGES.get(saved) if isinstance(saved, str) else None
        if msg:
            return self._render(msg=msg, msg_level='success')
        settings, has_password, available, daemon_down = self._load()
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
        raw, clean, errors, password = self._check(form)
        if errors:
            return self._render(msg=MSG_INVALID, msg_level='danger', errors=errors,
                                settings=self._echo(raw, clean, errors),
                                password_reentered=bool(password))
        if not self.credentials:
            return self._render(msg=MSG_AUTH_DISABLED, msg_level='warning', settings=clean,
                                password_reentered=bool(password))
        payload = self._payload(raw, clean, password, form, True)
        previous = {}
        try:
            try:
                previous = self.dbus.mqtt_get_settings() or {}
            except Exception:
                previous = {}
            result = self.dbus.mqtt_set_settings(payload)
        except Exception:
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger', settings=clean,
                                password_reentered=bool(password))
        if not isinstance(result, dict) or not result.get('ok'):
            daemon_errors = result.get('errors') if isinstance(result, dict) else None
            if isinstance(daemon_errors, dict) and daemon_errors:
                return self._render(msg=MSG_INVALID, msg_level='danger', errors=daemon_errors,
                                    settings=self._echo(raw, clean, daemon_errors),
                                    password_reentered=bool(password))
            return self._render(msg=MSG_DAEMON_DOWN, msg_level='danger', settings=clean,
                                password_reentered=bool(password))
        if not clean['enabled']:
            saved = 'off'
        elif clean['allow_commands'] and not (isinstance(previous, dict) and previous.get('allow_commands')):
            saved = 'commands'
        else:
            saved = '1'
        raise cherrypy.HTTPRedirect(cherrypy.request.script_name + '/homeassistant/?saved=' + saved, 303)

    @cherrypy.expose
    @require()
    def test(self, **form):
        as_json = _last(form.pop('format', '')) == 'json'
        if cherrypy.request.method != 'POST':
            return self._test_reply(as_json, 'rejected', TEST_REJECTED, render=dict(msg=MSG_REJECTED, msg_level='danger'))
        if not check_same_origin():
            self._reject('test')
            return self._test_reply(as_json, 'rejected', TEST_REJECTED)
        raw, clean, errors, password = self._check(form, for_test=True)
        echo = dict(settings=self._echo(raw, clean, errors), password_reentered=bool(password))
        if errors:
            return self._test_reply(as_json, 'invalid', TEST_INVALID, errors=errors, **echo)
        if not self.credentials:
            return self._test_reply(as_json, 'auth_disabled', TEST_AUTH_DISABLED, **echo)
        payload = self._payload(raw, clean, password, form, False)
        try:
            started = self.dbus.mqtt_test_start(payload)
        except Exception:
            return self._test_reply(as_json, 'daemon_down', TEST_DAEMON_DOWN, **echo)
        if not started:
            return self._test_reply(as_json, 'error', TEST_FAILED % UNKNOWN_REASON, **echo)
        started_at = self._clock()
        while True:
            try:
                result = self.dbus.mqtt_test_result()
            except Exception:
                return self._test_reply(as_json, 'daemon_down', TEST_DAEMON_DOWN, **echo)
            state = result.get('state') if isinstance(result, dict) else None
            if state == 'ok':
                return self._test_reply(as_json, 'ok', TEST_OK, **echo)
            if state == 'error':
                return self._test_reply(as_json, 'error', TEST_FAILED % _reason(result.get('message')), **echo)
            if self._clock() - started_at >= TEST_POLL_CAP:
                return self._test_reply(as_json, 'error', TEST_FAILED % 'timed out', **echo)
            self._sleep(0.5)

    def _test_reply(self, as_json, state, message, errors=None, render=None, **echo):
        level = 'success' if state == 'ok' else 'danger'
        if as_json:
            cherrypy.response.headers['Content-Type'] = 'application/json'
            return json.dumps(dict(state=state, message=message, level=level, errors=errors or {}))
        ctx = dict(test_msg=message, test_level=level, errors=errors or {})
        ctx.update(echo)
        if render:
            ctx.update(render)
        return self._render(**ctx)

    @cherrypy.expose
    @require()
    def status(self):
        settings, has_password, available, daemon_down = self._load()
        if daemon_down:
            view = status_view(settings, None, daemon_down=True)
        else:
            try:
                view = status_view(settings, self.dbus.mqtt_status())
            except Exception:
                view = status_view(settings, None, daemon_down=True)
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return json.dumps(view)


def _last(value):
    if isinstance(value, (list, tuple)):
        return value[-1] if value else ''
    return value
