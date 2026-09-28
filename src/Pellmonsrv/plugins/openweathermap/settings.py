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

# Openweathermap settings model: the single authoritative validator used by
# the daemon and the web controller. Stdlib only.

import json
import re
import logging

logger = logging.getLogger('pellMon')

KEY_CONFIG = 'owm.config'
KEY_APIKEY = 'owm.apikey'

DEFAULTS = {
    'enabled': False,
    'unit': 'celsius',
}

UNITS = ('celsius', 'fahrenheit')

MSG_ERR_APIKEY = 'API key must be 16 to 64 letters or digits.'
MSG_ERR_APIKEY_MISSING = 'Enter your OpenWeatherMap API key to turn the plugin on.'
MSG_ERR_LOCATION = 'Enter a location such as copenhagen,dk or 2100,dk (up to 100 characters).'
MSG_ERR_UNIT = 'Choose Celsius or Fahrenheit.'

_APIKEY_RE = re.compile(r'[A-Za-z0-9]{16,64}')
_TRUE = ('on', 'true', '1', 'yes')


def _coerce_bool(value):
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _TRUE
    if isinstance(value, int) and not isinstance(value, bool):
        return value == 1
    return False


def _has_control(text):
    for ch in text:
        o = ord(ch)
        if o < 32 or o == 127:
            return True
    return False


def _text(data, key, default=''):
    v = data.get(key, default)
    if v is None:
        return ''
    if not isinstance(v, str):
        return str(v)
    return v


def is_placeholder(key):
    """True when the key is empty or made only of 'x' characters"""
    if key is None:
        return True
    stripped = key.strip().lower()
    if stripped == '':
        return True
    return set(stripped) == {'x'}


def validate(data, has_stored_key):
    """Validate raw settings input. Returns (clean, errors); errors maps
    field name to the UI-SPEC message."""
    data = data if isinstance(data, dict) else {}
    clean = dict(DEFAULTS)
    errors = {}

    clean['enabled'] = _coerce_bool(data.get('enabled', DEFAULTS['enabled']))
    enabled = clean['enabled']

    unit = _text(data, 'unit', DEFAULTS['unit']).strip().lower()
    if unit in UNITS:
        clean['unit'] = unit
    else:
        errors['unit'] = MSG_ERR_UNIT

    location = _text(data, 'location').strip()
    if location == '' or len(location) > 100 or _has_control(location):
        errors['location'] = MSG_ERR_LOCATION
    else:
        clean['location'] = location

    apikey = data.get('apikey', None)
    has_new_key = False
    if apikey is not None:
        apikey = apikey.strip() if isinstance(apikey, str) else str(apikey).strip()
        if apikey != '':
            if _APIKEY_RE.fullmatch(apikey):
                clean['apikey'] = apikey
                has_new_key = True
            else:
                errors['apikey'] = MSG_ERR_APIKEY

    clean['clear_apikey'] = _coerce_bool(data.get('clear_apikey', False))

    if enabled and 'apikey' not in errors:
        keeping_stored_key = has_stored_key and not clean['clear_apikey']
        if not has_new_key and not keeping_stored_key:
            errors['apikey'] = MSG_ERR_APIKEY_MISSING

    return clean, errors


def load(store, conf):
    """Stored settings merged over DEFAULTS. With nothing stored, seed from
    conf: unit from conf['unit'] when valid, enabled from a non-placeholder
    conf apikey. DEFAULTS on any problem."""
    conf = conf if isinstance(conf, dict) else {}
    if store is None:
        return dict(DEFAULTS)
    try:
        raw = store.getval(KEY_CONFIG, '')
        if not raw:
            seeded = dict(DEFAULTS)
            unit = conf.get('unit', DEFAULTS['unit'])
            if isinstance(unit, str) and unit.strip().lower() in UNITS:
                seeded['unit'] = unit.strip().lower()
            seeded['enabled'] = not is_placeholder(conf.get('apikey', ''))
            return seeded
        stored = json.loads(raw)
        if not isinstance(stored, dict):
            raise ValueError('not a dict')
        merged = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in stored:
                merged[key] = stored[key]
        if merged['unit'] not in UNITS:
            raise ValueError('invalid unit')
        merged['enabled'] = bool(merged['enabled'])
        return merged
    except Exception:
        logger.warning('stored Openweathermap settings are invalid, using defaults')
        return dict(DEFAULTS)


def load_apikey(store, conf):
    """The stored API key if present, else the conf apikey unless it is a
    placeholder, else the empty string."""
    conf = conf if isinstance(conf, dict) else {}
    if store is not None:
        stored = store.getval(KEY_APIKEY, '')
        if stored:
            return stored
    conf_key = conf.get('apikey', '')
    if not is_placeholder(conf_key):
        return conf_key
    return ''


def save(store, clean, apikey=None, clear_apikey=False):
    """Store only enabled and unit as JSON. Location stays in the existing
    'location' Storeditem. The apikey is stored separately, never together
    with the rest of the config."""
    stored = dict((k, clean[k]) for k in DEFAULTS if k in clean)
    store.writeval(KEY_CONFIG, json.dumps(stored))
    if clear_apikey:
        store.writeval(KEY_APIKEY, '')
    elif apikey:
        store.writeval(KEY_APIKEY, apikey)


def public_view(cfg, has_key):
    view = dict(cfg)
    view.pop('apikey', None)
    view['has_apikey'] = bool(has_key)
    return view
