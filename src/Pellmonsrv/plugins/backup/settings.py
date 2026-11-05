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

# Backup settings model: the single authoritative validator used by the daemon and the web
# controller. Stdlib only (no plugin machinery), so the web process can import it.

import json
import logging
import os
import re

logger = logging.getLogger('pellMon')

KEY_CONFIG = 'backup.config'
KEY_STATE = 'backup.state'

DEFAULTS = {
    'enabled': False,
    'subfolder': '',
    'frequency': 'daily',
    'time': '03:00',
    'weekday': 6,
    'keep_daily': 14,
    'keep_weekly': 8,
    'require_other_disk': True,
}

FREQUENCIES = ('daily', 'weekly')
WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
KEEP_DAILY_RANGE = (1, 365)
KEEP_WEEKLY_RANGE = (0, 104)

MSG_ERR_SUBFOLDER = ('Use letters, digits, dot, dash and underscore, with / between folders '
                     '(no ..). Leave it empty to use the backup folder itself.')
MSG_ERR_FREQUENCY = 'Choose daily or weekly.'
MSG_ERR_TIME = 'Enter the time as HH:MM, for example 03:00.'
MSG_ERR_WEEKDAY = 'Choose a day of the week.'
MSG_ERR_KEEP_DAILY = 'Enter a whole number from %d to %d.' % KEEP_DAILY_RANGE
MSG_ERR_KEEP_WEEKLY = 'Enter a whole number from %d to %d.' % KEEP_WEEKLY_RANGE

_SUBFOLDER_RE = re.compile(r'[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*')
_HHMM_RE = re.compile(r'([01]?\d|2[0-3]):([0-5]\d)')
_TRUE = ('on', 'true', '1', 'yes')


def _coerce_bool(value):
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _TRUE
    if isinstance(value, int) and not isinstance(value, bool):
        return value == 1
    return False


def _coerce_int(value):
    """int from an int or a string of digits, None for anything else"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r'\s*[0-9]+\s*', value):
        return int(value)
    return None


def _normal_time(text):
    m = _HHMM_RE.fullmatch(text.strip()) if isinstance(text, str) else None
    return '%02d:%02d' % (int(m.group(1)), int(m.group(2))) if m else None


def valid_subfolder(text):
    if text == '':
        return True
    if len(text) > 100 or not _SUBFOLDER_RE.fullmatch(text):
        return False
    return all(part not in ('.', '..') for part in text.split('/'))


def validate(data):
    """Validate raw settings input. Returns (clean, errors); errors maps a field name to its message."""
    data = data if isinstance(data, dict) else {}
    clean = dict(DEFAULTS)
    errors = {}

    clean['enabled'] = _coerce_bool(data.get('enabled', DEFAULTS['enabled']))
    clean['require_other_disk'] = _coerce_bool(data.get('require_other_disk', DEFAULTS['require_other_disk']))

    sub = data.get('subfolder', '')
    sub = '' if sub is None else (sub if isinstance(sub, str) else str(sub))
    sub = sub.strip().strip('/')
    if valid_subfolder(sub):
        clean['subfolder'] = sub
    else:
        errors['subfolder'] = MSG_ERR_SUBFOLDER

    freq = data.get('frequency', DEFAULTS['frequency'])
    freq = freq.strip().lower() if isinstance(freq, str) else ''
    if freq in FREQUENCIES:
        clean['frequency'] = freq
    else:
        errors['frequency'] = MSG_ERR_FREQUENCY

    t = _normal_time(data.get('time', DEFAULTS['time']))
    if t:
        clean['time'] = t
    else:
        errors['time'] = MSG_ERR_TIME

    wd = _coerce_int(data.get('weekday', DEFAULTS['weekday']))
    if wd is not None and 0 <= wd <= 6:
        clean['weekday'] = wd
    else:
        errors['weekday'] = MSG_ERR_WEEKDAY

    for key, (lo, hi), msg in (('keep_daily', KEEP_DAILY_RANGE, MSG_ERR_KEEP_DAILY),
                               ('keep_weekly', KEEP_WEEKLY_RANGE, MSG_ERR_KEEP_WEEKLY)):
        n = _coerce_int(data.get(key, DEFAULTS[key]))
        if n is not None and lo <= n <= hi:
            clean[key] = n
        else:
            errors[key] = msg
    return clean, errors


def folder_for(root, subfolder):
    """root joined with the sub-folder, None if the result would leave root"""
    root = os.path.normpath(root)
    path = os.path.normpath(os.path.join(root, subfolder or ''))
    if path != root and not path.startswith(root.rstrip(os.sep) + os.sep):
        return None
    return path


def load(store):
    """Stored settings merged over DEFAULTS; DEFAULTS when nothing is stored or it is invalid"""
    if store is None:
        return dict(DEFAULTS)
    try:
        raw = store.getval(KEY_CONFIG, '')
        if not raw:
            return dict(DEFAULTS)
        stored = json.loads(raw)
        if not isinstance(stored, dict):
            raise ValueError('not a dict')
        clean, errors = validate(stored)
        if errors:
            raise ValueError('invalid')
        return clean
    except Exception:
        logger.warning('stored Backup settings are invalid, using defaults')
        return dict(DEFAULTS)


def save(store, clean):
    store.writeval(KEY_CONFIG, json.dumps(dict((k, clean[k]) for k in DEFAULTS if k in clean)))


STATE_DEFAULTS = {'last_ok': None, 'last_attempt': None, 'reason': '', 'last_file': '', 'last_size': 0}


def load_state(store):
    state = dict(STATE_DEFAULTS)
    if store is None:
        return state
    try:
        raw = store.getval(KEY_STATE, '')
        if raw:
            stored = json.loads(raw)
            if isinstance(stored, dict):
                for key in STATE_DEFAULTS:
                    if key in stored:
                        state[key] = stored[key]
    except Exception:
        logger.warning('stored Backup state is invalid, ignoring it')
    return state


def save_state(store, state):
    store.writeval(KEY_STATE, json.dumps(dict((k, state.get(k)) for k in STATE_DEFAULTS)))


def public_view(cfg):
    return dict(cfg)
