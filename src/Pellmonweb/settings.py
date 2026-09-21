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
import os
import os.path
import cherrypy
from logging import getLogger
from .auth import require
from .security import check_same_origin

logger = getLogger('pellMon')

SYSTEM_IMAGES = (
    'system.svg',
    'system_nbe.svg',
    'system_nbe_2w.svg',
    'system_nbe_3w.svg',
    'system_nbe_v7.svg',
    'system_matene.svg',
)

IMAGE_NAMES = {
    'system.svg': 'Standard',
    'system_nbe.svg': 'NBE',
    'system_nbe_2w.svg': 'NBE, 2-way valve',
    'system_nbe_3w.svg': 'NBE, 3-way valve',
    'system_nbe_v7.svg': 'NBE V7',
    'system_matene.svg': 'Matene',
}

SETTING_KEY = 'web.system_image'

MSG_SAVED = 'System image saved. Reload the main page to see it.'
MSG_REJECTED = 'Could not save the image. Sign in again and retry.'
MSG_UNKNOWN = 'That image is not available. Pick one from the list and retry.'
MSG_DAEMON_DOWN = ('Cannot save right now because the PellMon server is not running. '
                   'The main page keeps its current image. Start the server and retry.')

_warned = False


def reset_warning_state():
    """Test-only: re-arm the one-warning guard of effective_image()"""
    global _warned
    _warned = False


def is_allowed(name):
    """The only gate for a caller-supplied image filename (never sanitized, only matched)"""
    return isinstance(name, str) and name in SYSTEM_IMAGES


def available_images(img_dir):
    result = []
    for name in SYSTEM_IMAGES:
        try:
            present = os.path.isfile(os.path.join(img_dir, name))
        except Exception:
            present = False
        if present:
            result.append({'file': name, 'name': IMAGE_NAMES[name]})
    return result


def effective_image(img_dir, get_setting, config_path):
    """GUI-stored choice first, else the config file image; never raises"""
    global _warned
    try:
        value = get_setting()
    except Exception:
        return config_path
    if value in ('', None, 'error'):
        return config_path
    if is_allowed(value) and os.path.isfile(os.path.join(img_dir, value)):
        return os.path.join(img_dir, value)
    if not _warned:
        _warned = True
        logger.warning('ignoring stored system image %r, falling back to %s'%(value, config_path))
    return config_path


class Settings(object):
    def __init__(self, lookup, dbus, img_dir, credentials=None):
        self.lookup = lookup
        self.dbus = dbus
        self.img_dir = img_dir
        self.credentials = credentials

    def _render(self, msg='', msg_level='', current=None):
        if current is None:
            current, _ = self._current()
        ctx = dict(username=cherrypy.session.get('_cp_username'),
                   webroot=cherrypy.request.script_name,
                   active_page='settings',
                   images=available_images(self.img_dir),
                   current=current,
                   msg=msg,
                   msg_level=msg_level,
                   auth_configured=bool(self.credentials))
        return self.lookup.get_template('settings.html').render(**ctx)

    def _current(self):
        """Returns (whitelisted stored filename or '', daemon_reachable)"""
        try:
            value = self.dbus.get_setting(SETTING_KEY)
        except Exception:
            return '', False
        return (value if is_allowed(value) else ''), True

    @cherrypy.expose
    @require()
    def index(self):
        current, ok = self._current()
        if not ok:
            return self._render(MSG_DAEMON_DOWN, 'warning', current='')
        return self._render(current=current)

    @cherrypy.expose
    @require()
    def save(self, image=''):
        if cherrypy.request.method != 'POST':
            return self._render(MSG_REJECTED, 'danger')
        if not check_same_origin():
            cherrypy.response.status = 403
            logger.warning('rejected cross-origin system image save: origin=%r host=%r',
                           cherrypy.request.headers.get('Origin') or cherrypy.request.headers.get('Referer'),
                           cherrypy.request.headers.get('Host'))
            return self._render(MSG_REJECTED, 'danger')
        if not is_allowed(image):
            logger.warning('rejected system image %r', image)
            return self._render(MSG_UNKNOWN, 'danger')
        try:
            ok = self.dbus.set_setting(SETTING_KEY, image)
        except Exception:
            ok = False
        if not ok:
            return self._render(MSG_DAEMON_DOWN, 'warning')
        return self._render(MSG_SAVED, 'success', current=image)
