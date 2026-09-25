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

# Home Assistant / MQTT settings model: the single authoritative validator
# used by the daemon and the web controller. Stdlib only.

import json
import re
import logging

logger = logging.getLogger('pellMon')

KEY_CONFIG = 'mqtt.config'
KEY_PASSWORD = 'mqtt.password'

# Input-only marker (never stored): the page renders a hidden input with this
# name that is disabled exactly when the Verify checkbox is disabled.
TLS_VERIFY_MARKER = 'tls_verify_field'

DEFAULTS = {
    'enabled': False,
    'host': '',
    'port': 1883,
    'username': '',
    'tls': False,
    'tls_verify': True,
    'prefix': 'scotte',
    'discovery_prefix': 'homeassistant',
    'device_id': '',
    'device_name': '',
    'node_id': '',
    'uid_prefix': '',
    'allow_commands': False,
    'refresh': 60,
}

BOOL_FIELDS = ('enabled', 'tls', 'tls_verify', 'allow_commands')
INT_FIELDS = ('port', 'refresh')

MSG_ERR_HOST = 'Enter the broker host name or IP address, without mqtt:// and without spaces.'
MSG_ERR_PORT = 'Port must be a number from 1 to 65535.'
MSG_ERR_USERNAME = 'Username cannot contain control characters or be longer than 128 characters.'
MSG_ERR_PASSWORD = 'Password cannot be longer than 256 characters.'
MSG_ERR_PREFIX = 'Topic prefix cannot be empty, contain spaces, # or +, or start or end with /.'
MSG_ERR_DISCOVERY_PREFIX = 'Discovery prefix cannot be empty, contain spaces, # or +, or start or end with /.'
MSG_ERR_DEVICE_ID = 'Enter the device identifier, using only letters, digits, - and _ (up to 64 characters).'
MSG_ERR_DEVICE_NAME = 'Enter a device name of up to 64 characters.'
MSG_ERR_REFRESH = 'Refresh interval must be between 10 and 3600 seconds.'
MSG_ERR_NODE_ID = 'Use only letters, digits, - and _ (up to 64 characters), or leave the field empty.'
MSG_ERR_UID_PREFIX = 'Use only letters, digits, - and _ (up to 64 characters), or leave the field empty.'

_HOST_RE = re.compile(r'[A-Za-z0-9.\-:]{1,253}')
_PREFIX_RE = re.compile(r'[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*')
_ID_RE = re.compile(r'[A-Za-z0-9_-]{1,64}')
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


def _to_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.strip()
        if re.fullmatch(r'[0-9]{1,9}', v):
            return int(v)
    return None


def _text(data, key):
    v = data.get(key, DEFAULTS[key])
    if v is None:
        return ''
    if not isinstance(v, str):
        return str(v)
    return v


def tls_verify_explicit(data):
    """True only when TLS is on in the same input and the marker is present"""
    return _coerce_bool(data.get('tls', False)) and _coerce_bool(data.get(TLS_VERIFY_MARKER, False))


def validate_password(pw):
    """Return an error message, or None when the password is acceptable"""
    if pw is None:
        return None
    if not isinstance(pw, str):
        return MSG_ERR_PASSWORD
    if len(pw) > 256 or '\x00' in pw:
        return MSG_ERR_PASSWORD
    return None


def _valid_prefix(v):
    return len(v) <= 64 and _PREFIX_RE.fullmatch(v) is not None


def validate(data, for_test=False, current=None):
    """Validate raw settings input. Returns (clean, errors); errors maps
    field name to the UI-SPEC message. The password is never read here."""
    data = data if isinstance(data, dict) else {}
    clean = dict(DEFAULTS)
    errors = {}

    for key in ('enabled', 'tls', 'allow_commands'):
        clean[key] = _coerce_bool(data.get(key, DEFAULTS[key]))
    if tls_verify_explicit(data):
        clean['tls_verify'] = _coerce_bool(data.get('tls_verify', False))
    else:
        clean['tls_verify'] = bool((current or DEFAULTS).get('tls_verify', DEFAULTS['tls_verify']))

    enabled = clean['enabled']

    host = _text(data, 'host').strip()
    if host == '':
        if enabled or for_test:
            errors['host'] = MSG_ERR_HOST
    elif '://' in host or not _HOST_RE.fullmatch(host):
        errors['host'] = MSG_ERR_HOST
    else:
        clean['host'] = host

    port = _to_int(data.get('port', DEFAULTS['port']))
    if port is None or port < 1 or port > 65535:
        errors['port'] = MSG_ERR_PORT
    else:
        clean['port'] = port

    username = _text(data, 'username')
    if len(username) > 128 or _has_control(username):
        errors['username'] = MSG_ERR_USERNAME
    else:
        clean['username'] = username

    prefix = _text(data, 'prefix')
    if _valid_prefix(prefix):
        clean['prefix'] = prefix
    else:
        errors['prefix'] = MSG_ERR_PREFIX

    dprefix = _text(data, 'discovery_prefix')
    if _valid_prefix(dprefix):
        clean['discovery_prefix'] = dprefix
    else:
        errors['discovery_prefix'] = MSG_ERR_DISCOVERY_PREFIX

    device_id = _text(data, 'device_id')
    if device_id == '':
        if enabled:
            errors['device_id'] = MSG_ERR_DEVICE_ID
    elif _ID_RE.fullmatch(device_id):
        clean['device_id'] = device_id
    else:
        errors['device_id'] = MSG_ERR_DEVICE_ID

    device_name = _text(data, 'device_name')
    if device_name == '':
        if enabled:
            errors['device_name'] = MSG_ERR_DEVICE_NAME
    elif len(device_name) > 64 or _has_control(device_name):
        errors['device_name'] = MSG_ERR_DEVICE_NAME
    else:
        clean['device_name'] = device_name

    for key, msg in (('node_id', MSG_ERR_NODE_ID), ('uid_prefix', MSG_ERR_UID_PREFIX)):
        v = _text(data, key)
        if v == '' or _ID_RE.fullmatch(v):
            clean[key] = v
        else:
            errors[key] = msg

    refresh = _to_int(data.get('refresh', DEFAULTS['refresh']))
    if refresh is None or refresh < 10 or refresh > 3600:
        errors['refresh'] = MSG_ERR_REFRESH
    else:
        clean['refresh'] = refresh

    return clean, errors


def effective(cfg):
    """Copy of cfg with empty node_id/uid_prefix defaulting to the device id"""
    out = dict(cfg)
    if not out.get('node_id'):
        out['node_id'] = out.get('device_id', '')
    if not out.get('uid_prefix'):
        out['uid_prefix'] = out.get('device_id', '')
    return out


def load(store):
    """Stored settings merged over DEFAULTS; DEFAULTS on any problem"""
    if store is None:
        return dict(DEFAULTS)
    try:
        raw = store.getval(KEY_CONFIG, '')
        if not raw:
            return dict(DEFAULTS)
        stored = json.loads(raw)
        if not isinstance(stored, dict):
            raise ValueError('not a dict')
        merged = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in stored:
                merged[key] = stored[key]
        clean, errors = validate(merged, current=merged)
        if errors:
            raise ValueError('invalid')
        return clean
    except Exception:
        logger.warning('stored Home Assistant settings are invalid, using defaults')
        return dict(DEFAULTS)


def load_password(store):
    if store is None:
        return ''
    return store.getval(KEY_PASSWORD, '')


def has_password(store):
    return bool(load_password(store))


def save(store, clean, password=None, clear_password=False):
    stored = dict((k, clean[k]) for k in DEFAULTS if k in clean)
    store.writeval(KEY_CONFIG, json.dumps(stored))
    if clear_password:
        store.writeval(KEY_PASSWORD, '')
    elif password:
        store.writeval(KEY_PASSWORD, password)


def public_view(cfg, store):
    view = dict(cfg)
    view.pop('password', None)
    view['has_password'] = has_password(store)
    return view
