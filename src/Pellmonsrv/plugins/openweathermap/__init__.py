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

# Openweathermap plugin: fetches outside weather from openweathermap.org
# using pyowm 3. It stays inert (no fetching) until it is enabled on the
# web page or a non-placeholder key is present in the conf file. pyowm is
# imported lazily so this module imports without it.

import time
import threading
from logging import getLogger
from threading import Timer

from Pellmonsrv.plugin_categories import protocols
from Pellmonsrv.database import Getsetitem, Storeditem, Keyval_storage
from . import settings as owm_settings

logger = getLogger('pellMon')

# reason -> update_interval (seconds) after a failed fetch
_ERROR_RETRY_INTERVAL = 300
_OK_INTERVAL = 900

REASON_UNKNOWN = 'unknown error (see the server log)'


def _reason_for(exc):
    """Map a pyowm exception instance to a stable reason string, without
    ever including str(exc): pyowm request errors can embed the request URL
    with the API key in the query string (appid=<key>)."""
    try:
        from pyowm.commons import exceptions as owm_exceptions
    except ImportError:
        owm_exceptions = None

    if owm_exceptions is not None:
        if isinstance(exc, owm_exceptions.UnauthorizedError):
            return 'invalid API key'
        if isinstance(exc, owm_exceptions.NotFoundError):
            return 'location not found'
        if isinstance(exc, (owm_exceptions.TimeoutError, owm_exceptions.APIRequestError,
                            owm_exceptions.BadGatewayError, owm_exceptions.InvalidSSLCertificateError)):
            return 'could not reach openweathermap.org'
    return REASON_UNKNOWN


class owmplugin(protocols):
    # None means construct a real pyowm.OWM(apikey); tests inject a fake factory
    owm_factory = None
    autostart = True

    def __init__(self):
        protocols.__init__(self)
        self.available = False
        self.store = None
        self.owm = None
        self.cfg = dict(owm_settings.DEFAULTS)
        self.lock = threading.Lock()
        self.last_fetch = None
        self.last_error = ''
        self.itemrefs = []
        self.storeditems = {}
        self.itemvalues = {}
        self.location_item = None
        self.update_interval = 5
        self.store_interval = 10

    def activate(self, conf, glob, db, *args, **kwargs):
        protocols.activate(self, conf, glob, db, *args, **kwargs)
        self.itemrefs = []
        self.storeditems = {}
        self.itemvalues = {}
        self.owm = None
        self.last_fetch = None
        self.last_error = ''

        try:
            import pyowm  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

        self.store = Keyval_storage.keyval_storage

        def additem(i, item_type='R'):
            i.tags = ['All', 'Basic', 'Openweathermap']
            i.type = item_type
            i.min = ''
            i.max = ''
            self.db.insert(i)
            self.itemrefs.append(i)

        def update_location(*args, **kwargs):
            self.update_interval = 1
            self.store_interval = 10

        config = {}
        for index_key, value in self.conf.items():
            if '_' in index_key:
                index, key = index_key.split('_')
                try:
                    config[index][key] = value
                except KeyError:
                    config[index] = {key: value}

        for index, itemconf in config.items():
            try:
                itemname = itemconf.pop('item')
                itemvalue = itemconf.pop('value', '0')
                itemdata = itemconf.pop('data')

                storeditem = Storeditem('owm_stored_' + itemdata, itemvalue)
                self.db.insert(storeditem)
                self.storeditems[itemdata] = storeditem
                self.itemvalues[itemdata] = storeditem.value

                i = Getsetitem(itemname, itemvalue, getter=lambda item, d=itemdata: self.itemvalues[d])

                for key, value in itemconf.items():
                    setattr(i, key, value)
                additem(i)

            except KeyError:
                pass

        loc_item = Storeditem('location', 'copenhagen,dk', setter=update_location)
        loc_item.description = 'Set your location: town,countrycode or zipcode,countrycode'
        additem(loc_item, 'R/W')
        self.location_item = loc_item

        self.reconfigure(owm_settings.load(self.store, self.conf), owm_settings.load_apikey(self.store, self.conf))

        if self.cfg.get('enabled') and not self.available:
            logger.error('Openweathermap needs the pyowm module; the plugin stays inactive')

        if self.autostart:
            t = Timer(0, self.update_thread)
            t.daemon = True
            t.start()

    def reconfigure(self, cfg, apikey):
        with self.lock:
            self.cfg = dict(cfg)
            if self.cfg.get('enabled') and apikey and self.available:
                factory = self.owm_factory or self._default_factory
                self.owm = factory(apikey)
            else:
                self.owm = None
            self.last_error = ''
            self.update_interval = 1

    def _default_factory(self, apikey):
        import pyowm
        return pyowm.OWM(apikey)

    def fetch_once(self):
        """Fetch the current weather and update itemvalues. Never raises."""
        owm = self.owm
        if owm is None:
            return
        try:
            location = str(self.location_item.value) if self.location_item is not None else ''
            manager = owm.weather_manager()
            observation = manager.weather_at_place(location)
            weather = observation.weather

            unit = self.cfg.get('unit', 'celsius')
            temperature = weather.temperature(unit)
            self.itemvalues['temperature'] = str(temperature['temp'])

            wind = weather.wind()
            self.itemvalues['wind_speed'] = str(wind.get('speed'))
            if 'deg' in wind:
                self.itemvalues['wind_direction'] = str(wind['deg'])

            self.itemvalues['humidity'] = str(weather.humidity)

            # feelslike must be computed in Celsius; convert afterwards if needed
            t_c = weather.temperature('celsius')['temp']
            w = float(self.itemvalues['wind_speed'])
            h = float(self.itemvalues['humidity'])
            feelslike_c = t_c + 0.348 * ((h / 100) * 6.105 * (2.7182 ** ((17.27 * t_c) / (237.7 + t_c)))) - 0.7 * w
            if unit == 'fahrenheit':
                feelslike = feelslike_c * 9 / 5 + 32
            else:
                feelslike = feelslike_c
            self.itemvalues['feelslike'] = '%.1f' % feelslike
        except Exception as e:
            reason = _reason_for(e)
            self.last_error = reason
            logger.warning('Openweathermap update failed: %s (%s)' % (reason, type(e).__name__))
            self.update_interval = _ERROR_RETRY_INTERVAL
        else:
            self.last_error = ''
            self.last_fetch = time.time()
            self.update_interval = _OK_INTERVAL

    def update_thread(self):
        self.store_interval = 10
        while True:
            time.sleep(1)
            self.update_interval -= 1
            self.store_interval -= 1
            if self.update_interval <= 0:
                if self.owm is not None:
                    self.fetch_once()
                else:
                    self.update_interval = _OK_INTERVAL
            if self.store_interval <= 0:
                for itemdata, storeditem in self.storeditems.items():
                    if itemdata in self.itemvalues:
                        storeditem.value = self.itemvalues[itemdata]
                self.store_interval = 7200

    # ---- D-Bus contract ------------------------------------------------

    def get_settings_dict(self):
        has_key = bool(owm_settings.load_apikey(self.store, self.conf))
        view = owm_settings.public_view(self.cfg, has_key)
        view['location'] = self.location_item.value if self.location_item is not None else ''
        view['available'] = self.available
        return view

    def apply_settings(self, data):
        try:
            if self.store is None:
                return {'ok': False, 'errors': {'_': 'settings store unavailable'}}
            has_stored_key = bool(owm_settings.load_apikey(self.store, self.conf))
            clean, errors = owm_settings.validate(data, has_stored_key)
            if errors:
                return {'ok': False, 'errors': errors}

            apikey = clean.pop('apikey', None)
            clear_apikey = clean.pop('clear_apikey', False)
            location = clean.pop('location', None)

            owm_settings.save(self.store, clean, apikey=apikey, clear_apikey=clear_apikey)

            if location is not None and self.location_item is not None and \
                    self.location_item.value != location:
                self.location_item.value = location

            effective_key = owm_settings.load_apikey(self.store, self.conf)
            self.reconfigure(clean, effective_key)

            result = {'ok': True, 'errors': {}}
            if not self.available:
                result['available'] = False
            return result
        except Exception:
            logger.exception('Openweathermap apply settings failed')
            return {'ok': False, 'errors': {}, 'available': False}

    def status_dict(self):
        location = self.location_item.value if self.location_item is not None else ''
        if not self.cfg.get('enabled'):
            state = 'disabled'
        elif not bool(owm_settings.load_apikey(self.store, self.conf)):
            state = 'no_key'
        elif self.owm is None:
            state = 'no_key'
        elif self.last_error:
            state = 'error'
        elif self.last_fetch is None:
            state = 'waiting'
        else:
            state = 'ok'
        return {'available': self.available, 'state': state, 'last_fetch': self.last_fetch,
                'reason': self.last_error, 'location': location}
