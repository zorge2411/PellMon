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

# Home Assistant plugin: publishes the burner as an MQTT device. It stays inert
# (no broker connection) until it is enabled on the web page. paho is imported
# lazily by the bridge, so this module imports without it.

import atexit
import logging

from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Keyval_storage
from . import settings as ha_settings
from . import bridge as ha_bridge

TEST_FALLBACK = {'state': 'error', 'message': 'unknown error (see the server log)',
                 'available': False}


class homeassistant(protocols):
    # None means ha_bridge.default_paho_factory; tests inject a fake
    client_factory = None
    autostart = True

    def __init__(self):
        protocols.__init__(self)
        self.bridge = None
        self.available = False
        self.store = None
        self.logger = logging.getLogger('pellMon')

    def activate(self, conf, glob, db, *args, **kwargs):
        protocols.activate(self, conf, glob, db, *args, **kwargs)
        self.logger = logging.getLogger('pellMon')
        self.bridge = None
        self.available = False
        self.store = None
        try:
            self.store = Keyval_storage.keyval_storage
            self.available = self.client_factory is not None or ha_bridge.paho_available()
            factory = self.client_factory or ha_bridge.default_paho_factory
            self.bridge = ha_bridge.Bridge(db, factory, snapshot=getattr(db, 'snapshot', None),
                                           sw_version=glob.get('__version__', '_dev_'))
            add_listener = getattr(db, 'add_change_listener', None)
            if add_listener is not None:
                add_listener(self.bridge.on_changes)
            # Database.terminate is never called on SIGTERM, so publish offline at exit
            atexit.register(self.bridge.shutdown)
            if self.autostart:
                self.bridge.start()
            cfg = ha_settings.load(self.store)
            if cfg.get('enabled'):
                if self.available:
                    self.bridge.reconfigure(cfg, ha_settings.load_password(self.store))
                else:
                    self.logger.error('Home Assistant MQTT needs paho-mqtt 2.x; the plugin stays inactive')
        except Exception:
            self.logger.exception('Home Assistant plugin setup failed')

    def deactivate(self, *args, **kwargs):
        try:
            if self.bridge is not None:
                self.bridge.shutdown()
        except Exception:
            self.logger.exception('Home Assistant plugin shutdown failed')

    # ---- D-Bus contract ------------------------------------------------

    def get_settings_dict(self):
        view = ha_settings.public_view(ha_settings.load(self.store), self.store)
        view.pop('password', None)
        view['available'] = bool(self.available and self.bridge is not None)
        return view

    def _candidate(self, data, for_test):
        """Returns (clean, errors, typed_password, clear_password)"""
        data = dict(data) if isinstance(data, dict) else {}
        password = data.pop('password', None)
        clear = ha_settings._coerce_bool(data.pop('clear_password', False))
        clean, errors = ha_settings.validate(data, for_test=for_test,
                                             current=ha_settings.load(self.store))
        perr = ha_settings.validate_password(password)
        if perr:
            errors['password'] = perr
        return clean, errors, password, clear

    def apply_settings(self, data):
        try:
            if self.store is None:
                return {'ok': False, 'errors': {'_': 'settings store unavailable'}}
            clean, errors, password, clear = self._candidate(data, False)
            if errors:
                result = {'ok': False, 'errors': errors}
                if self.bridge is None:
                    result['available'] = False
                return result
            ha_settings.save(self.store, clean, password=password or None, clear_password=clear and not password)
            if self.bridge is None:
                return {'ok': True, 'errors': {}, 'available': False}
            if not self.available:
                if clean.get('enabled'):
                    self.logger.error('Home Assistant MQTT needs paho-mqtt 2.x; the plugin stays inactive')
                return {'ok': True, 'errors': {}, 'available': False}
            self.bridge.reconfigure(clean, ha_settings.load_password(self.store))
            return {'ok': True, 'errors': {}}
        except Exception:
            self.logger.exception('Home Assistant apply settings failed')
            return {'ok': False, 'errors': {}, 'available': False}

    def status_dict(self):
        if self.bridge is None:
            return {'available': False, 'state': 'off'}
        try:
            return self.bridge.status_dict()
        except Exception:
            self.logger.exception('Home Assistant status failed')
            return {'available': False, 'state': 'off'}

    def start_test(self, data):
        if self.bridge is None:
            return False
        try:
            clean, errors, password, clear = self._candidate(data, True)
            if errors:
                return False
            if not password:
                password = ha_settings.load_password(self.store)
            return bool(self.bridge.start_test(clean, password))
        except Exception:
            self.logger.exception('Home Assistant connection test failed')
            return False

    def test_result_dict(self):
        if self.bridge is None:
            return dict(TEST_FALLBACK)
        try:
            return self.bridge.test_result_dict()
        except Exception:
            self.logger.exception('Home Assistant test result failed')
            return dict(TEST_FALLBACK)
