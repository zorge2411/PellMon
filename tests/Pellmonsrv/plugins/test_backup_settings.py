# -*- coding: utf-8 -*-
"""Backup settings model (Phase 12)."""

import json

import pytest

from Pellmonsrv.plugins.backup import settings as bs


def test_defaults_are_valid():
    clean, errors = bs.validate({})
    assert errors == {} and clean == bs.DEFAULTS
    assert bs.DEFAULTS['enabled'] is False and bs.DEFAULTS['require_other_disk'] is True


def test_valid_input_is_normalised():
    clean, errors = bs.validate({'enabled': 'on', 'subfolder': ' /pellmon/db/ ', 'frequency': 'Weekly', 'time': '3:05',
                                 'weekday': '2', 'keep_daily': '30', 'keep_weekly': '0', 'require_other_disk': 'off'})
    assert errors == {}
    assert clean == {'enabled': True, 'subfolder': 'pellmon/db', 'frequency': 'weekly', 'time': '03:05', 'weekday': 2,
                     'keep_daily': 30, 'keep_weekly': 0, 'require_other_disk': False}


@pytest.mark.parametrize('field,value', [
    ('subfolder', '../x'), ('subfolder', 'a/../b'), ('subfolder', 'a b'), ('subfolder', 'a//b'), ('subfolder', 'x' * 101),
    ('subfolder', './x'), ('subfolder', 'a;rm'), ('subfolder', '~'),
    ('frequency', 'monthly'), ('frequency', ''), ('frequency', 5),
    ('time', '24:00'), ('time', '3'), ('time', '03:60'), ('time', ''), ('time', None),
    ('weekday', 7), ('weekday', -1), ('weekday', 'sun'), ('weekday', 1.5), ('weekday', True),
    ('keep_daily', 0), ('keep_daily', 366), ('keep_daily', 'x'), ('keep_daily', 2.5), ('keep_daily', True),
    ('keep_weekly', -1), ('keep_weekly', 105), ('keep_weekly', ''),
])
def test_invalid_values_are_rejected(field, value):
    clean, errors = bs.validate({field: value})
    assert field in errors and errors[field]
    assert clean[field] == bs.DEFAULTS[field]


def test_boundaries_are_accepted():
    for key, values in (('keep_daily', (1, 365)), ('keep_weekly', (0, 104)), ('weekday', (0, 6))):
        for v in values:
            clean, errors = bs.validate({key: v})
            assert errors == {} and clean[key] == v


def test_non_dict_input():
    clean, errors = bs.validate('nonsense')
    assert errors == {} and clean == bs.DEFAULTS


def test_folder_for_stays_inside_root():
    assert bs.folder_for('/backups', '') == '/backups'
    assert bs.folder_for('/backups/', 'a/b') == '/backups/a/b'
    assert bs.folder_for('/backups', '..') is None
    assert bs.folder_for('/backups', '../etc') is None
    assert bs.folder_for('/backups', 'a/../../etc') is None
    assert bs.folder_for('/backups', '/etc') is None  # an absolute path would replace the root


class FakeStore(object):
    def __init__(self, data=None):
        self.data = dict(data or {})

    def getval(self, key, default=''):
        return self.data.get(key, default)

    def writeval(self, key, value=None, confval=None):
        self.data[key] = value


def test_save_and_load_round_trip():
    store = FakeStore()
    clean, _ = bs.validate({'enabled': True, 'subfolder': 'x', 'keep_daily': 5})
    bs.save(store, clean)
    assert bs.load(store) == clean
    assert set(json.loads(store.data[bs.KEY_CONFIG])) == set(bs.DEFAULTS)


@pytest.mark.parametrize('stored', ['not json', '[1]', '{"keep_daily": 0}', '{"time": "99:99"}'])
def test_load_falls_back_to_defaults(stored, caplog):
    assert bs.load(FakeStore({bs.KEY_CONFIG: stored})) == bs.DEFAULTS


def test_load_without_store():
    assert bs.load(None) == bs.DEFAULTS
    assert bs.load_state(None) == bs.STATE_DEFAULTS


def test_state_round_trip_ignores_unknown_keys():
    store = FakeStore()
    bs.save_state(store, {'last_ok': 5.0, 'last_attempt': 6.0, 'reason': 'x', 'last_file': 'f', 'last_size': 9, 'extra': 1})
    state = bs.load_state(store)
    assert state == {'last_ok': 5.0, 'last_attempt': 6.0, 'reason': 'x', 'last_file': 'f', 'last_size': 9}
    store.data[bs.KEY_STATE] = 'garbage'
    assert bs.load_state(store) == bs.STATE_DEFAULTS
