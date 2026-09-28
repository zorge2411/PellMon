# -*- coding: utf-8 -*-
"""openweathermap plugin: pyowm 3 port, activation, D-Bus contract."""

import logging

import pytest

from pyowm.commons import exceptions as owm_exceptions

from Pellmonsrv.database import Keyval_storage
from Pellmonsrv.plugins import openweathermap as owm_plugin
from Pellmonsrv.plugins.openweathermap import settings as owm_settings

REAL_KEY = 'a1b2c3d4e5f6a7b8'  # 16 chars, matches the API key regex
PLACEHOLDER_KEY = 'x' * 32

BASE_CONF = {
    'apikey': PLACEHOLDER_KEY,
    'unit': 'celsius',
    'owm1_item': 'outside_temp',
    'owm1_data': 'temperature',
    'owm1_longname': 'Outside temperature',
    'owm1_description': 'Outside temperature from Openweathermap.com',
    'owm1_unit': '°C',
    'owm2_item': 'wind',
    'owm2_data': 'wind_speed',
    'owm2_longname': 'Wind speed',
    'owm2_description': 'Wind speed from Openweathermap.com',
    'owm2_unit': 'm/s',
    'owm3_item': 'wind_direction',
    'owm3_data': 'wind_direction',
    'owm3_longname': 'Wind direction',
    'owm3_description': 'Wind direction from Openweathermap.com',
    'owm3_unit': '°',
    'owm4_item': 'humidity',
    'owm4_data': 'humidity',
    'owm4_longname': 'Relative humidity',
    'owm4_description': 'Relative humidity from Openweathermap.com',
    'owm4_unit': '%',
    'owm5_item': 'apparent_temperature',
    'owm5_data': 'feelslike',
    'owm5_longname': 'Apparent temperature',
    'owm5_description': 'Apparent temperature calculated from temperature, windspeed and humidity',
    'owm5_unit': '°C',
}


# ---- test doubles: never construct a real pyowm.OWM ----------------------

class FakeWeather(object):
    def __init__(self, temp_c, wind, humidity):
        self._temp_c = temp_c
        self._wind = wind
        self.humidity = humidity

    def temperature(self, unit='kelvin'):
        if unit == 'celsius':
            t = self._temp_c
        elif unit == 'fahrenheit':
            t = self._temp_c * 9 / 5 + 32
        else:
            t = self._temp_c + 273.15
        return {'temp': t}

    def wind(self, unit='meters_sec'):
        return dict(self._wind)


class FakeObservation(object):
    def __init__(self, weather):
        self.weather = weather


class FakeManager(object):
    def __init__(self, weather=None, raise_exc=None):
        self.weather = weather
        self.raise_exc = raise_exc
        self.calls = []

    def weather_at_place(self, location):
        self.calls.append(location)
        assert isinstance(location, str)
        if self.raise_exc is not None:
            raise self.raise_exc
        return FakeObservation(self.weather)


class FakeOWM(object):
    def __init__(self, apikey=None, weather=None, raise_exc=None):
        self.apikey = apikey
        self.manager = FakeManager(weather, raise_exc)

    def weather_manager(self):
        return self.manager


class FakeDb(dict):
    def insert(self, item):
        self[item.name] = item


def factory_for(weather=None, raise_exc=None):
    calls = []

    def factory(apikey):
        calls.append(apikey)
        return FakeOWM(apikey, weather=weather, raise_exc=raise_exc)
    factory.calls = calls
    return factory


def _feelslike_c(temp_c, wind_speed, humidity):
    t, w, h = temp_c, wind_speed, humidity
    return t + 0.348 * ((h / 100) * 6.105 * (2.7182 ** ((17.27 * t) / (237.7 + t)))) - 0.7 * w


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = Keyval_storage(str(tmp_path / 'kv.db'))
    monkeypatch.setattr(Keyval_storage, 'keyval_storage', s, raising=False)
    return s


def make(store, conf=None, factory=None, autostart=False, db=None):
    p = owm_plugin.owmplugin()
    p.owm_factory = factory
    p.autostart = autostart
    conf = conf if conf is not None else dict(BASE_CONF)
    db = db if db is not None else FakeDb()
    p.activate(conf, {}, db)
    return p, db


# ---- fetch_once --------------------------------------------------------

def test_fetch_once_sets_all_values(store):
    weather = FakeWeather(20.0, {'speed': 3.0, 'deg': 180}, 50)
    factory = factory_for(weather=weather)
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY), factory=factory)

    p.fetch_once()

    assert p.itemvalues['temperature'] == '20.0'
    assert p.itemvalues['wind_speed'] == '3.0'
    assert p.itemvalues['wind_direction'] == '180'
    assert p.itemvalues['humidity'] == '50'
    assert p.itemvalues['feelslike'] == '%.1f' % _feelslike_c(20.0, 3.0, 50)
    assert p.last_error == ''
    assert p.update_interval == 900
    # location passed as str, matching db['location'].value
    assert p.owm.manager.calls == [db['location'].value]
    assert isinstance(db['location'].value, str)


def test_missing_wind_deg_keeps_previous_direction_no_error(store):
    weather = FakeWeather(15.0, {'speed': 2.0}, 40)
    factory = factory_for(weather=weather)
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY), factory=factory)
    p.itemvalues['wind_direction'] = '999'

    p.fetch_once()

    assert p.itemvalues['wind_direction'] == '999'
    assert p.itemvalues['temperature'] == '15.0'
    assert p.itemvalues['wind_speed'] == '2.0'
    assert p.itemvalues['humidity'] == '40'
    assert p.itemvalues['feelslike'] == '%.1f' % _feelslike_c(15.0, 2.0, 40)
    assert p.last_error == ''


def test_fahrenheit_unit_converts_temperature_and_feelslike(store):
    weather = FakeWeather(10.0, {'speed': 1.0, 'deg': 90}, 60)
    factory = factory_for(weather=weather)
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY, unit='fahrenheit'), factory=factory)

    p.fetch_once()

    expected_temp_f = 10.0 * 9 / 5 + 32
    expected_feelslike_f = _feelslike_c(10.0, 1.0, 60) * 9 / 5 + 32
    assert p.itemvalues['temperature'] == str(expected_temp_f)
    assert p.itemvalues['feelslike'] == '%.1f' % expected_feelslike_f


@pytest.mark.parametrize('exc_cls,reason', [
    (owm_exceptions.UnauthorizedError, 'invalid API key'),
    (owm_exceptions.NotFoundError, 'location not found'),
    (owm_exceptions.TimeoutError, 'could not reach openweathermap.org'),
    (owm_exceptions.APIRequestError, 'could not reach openweathermap.org'),
    (owm_exceptions.BadGatewayError, 'could not reach openweathermap.org'),
    (owm_exceptions.InvalidSSLCertificateError, 'could not reach openweathermap.org'),
])
def test_exception_mapping_and_no_leak(store, caplog, exc_cls, reason):
    secret_url = 'http://api.openweathermap.org/data/2.5/weather?appid=%s' % REAL_KEY
    factory = factory_for(raise_exc=exc_cls(secret_url))
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY), factory=factory)

    with caplog.at_level(logging.WARNING, logger='pellMon'):
        p.fetch_once()

    assert p.last_error == reason
    assert p.update_interval == 300
    assert REAL_KEY not in caplog.text
    assert secret_url not in caplog.text
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any('Openweathermap update failed' in r.getMessage() for r in warnings)
    assert any(reason in r.getMessage() for r in warnings)


def test_unknown_exception_maps_to_unknown_reason(store, caplog):
    factory = factory_for(raise_exc=RuntimeError('boom'))
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY), factory=factory)
    with caplog.at_level(logging.WARNING, logger='pellMon'):
        p.fetch_once()
    assert p.last_error == 'unknown error (see the server log)'
    assert p.update_interval == 300


# ---- activate ------------------------------------------------------------

def test_activate_placeholder_apikey_does_not_raise_disabled(store):
    p, db = make(store, conf=dict(BASE_CONF, apikey=PLACEHOLDER_KEY))
    assert p.owm is None
    assert p.status_dict()['state'] == 'disabled'


def test_activate_real_conf_apikey_seeds_enabled_and_uses_key(store):
    factory = factory_for(weather=FakeWeather(1.0, {'speed': 1.0, 'deg': 1}, 1))
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY), factory=factory)
    assert p.cfg['enabled'] is True
    assert p.owm is not None
    assert factory.calls == [REAL_KEY]


def test_activate_without_pyowm_does_not_raise(store, monkeypatch):
    monkeypatch.setitem(__import__('sys').modules, 'pyowm', None)
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY))
    assert p.get_settings_dict()['available'] is False


# ---- apply_settings / get_settings_dict / status_dict ---------------------

@pytest.mark.parametrize('data', [
    {'enabled': True, 'location': 'copenhagen,dk', 'unit': 'celsius'},  # no key at all
    {'enabled': True, 'location': 'copenhagen,dk', 'unit': 'kelvin2', 'apikey': REAL_KEY},
    {'enabled': True, 'location': '', 'unit': 'celsius', 'apikey': REAL_KEY},
    {'enabled': True, 'location': 'bad\x01loc', 'unit': 'celsius', 'apikey': REAL_KEY},
    {'enabled': True, 'location': 'copenhagen,dk', 'unit': 'celsius', 'apikey': 'abc'},
])
def test_apply_settings_invalid_stores_nothing(store, data):
    p, db = make(store, conf=dict(BASE_CONF, apikey=PLACEHOLDER_KEY))
    result = p.apply_settings(data)
    assert result['ok'] is False
    assert result['errors']
    assert store.getval(owm_settings.KEY_CONFIG, '') == ''
    assert store.getval(owm_settings.KEY_APIKEY, '') == ''


def test_apply_settings_valid_stores_key_and_updates_location(store):
    factory = factory_for(weather=FakeWeather(5.0, {'speed': 1.0, 'deg': 5}, 30))
    p, db = make(store, conf=dict(BASE_CONF, apikey=PLACEHOLDER_KEY), factory=factory)

    result = p.apply_settings({'enabled': True, 'location': 'aarhus,dk', 'unit': 'celsius', 'apikey': REAL_KEY})

    assert result == {'ok': True, 'errors': {}}
    settings = p.get_settings_dict()
    assert settings['has_apikey'] is True
    assert 'apikey' not in settings
    assert db['location'].value == 'aarhus,dk'
    stored_cfg = owm_settings.load(store, {})
    assert stored_cfg['unit'] == 'celsius'
    assert stored_cfg['enabled'] is True


def test_apply_settings_clear_apikey_removes_stored_key(store):
    factory = factory_for(weather=FakeWeather(5.0, {'speed': 1.0, 'deg': 5}, 30))
    p, db = make(store, conf=dict(BASE_CONF, apikey=PLACEHOLDER_KEY), factory=factory)
    p.apply_settings({'enabled': True, 'location': 'aarhus,dk', 'unit': 'celsius', 'apikey': REAL_KEY})
    assert p.get_settings_dict()['has_apikey'] is True

    result = p.apply_settings({'enabled': False, 'location': 'aarhus,dk', 'unit': 'celsius', 'clear_apikey': True})

    assert result['ok'] is True
    assert p.get_settings_dict()['has_apikey'] is False
    assert store.getval(owm_settings.KEY_APIKEY, '') == ''


def test_get_settings_dict_never_includes_apikey(store):
    factory = factory_for(weather=FakeWeather(5.0, {'speed': 1.0, 'deg': 5}, 30))
    p, db = make(store, conf=dict(BASE_CONF, apikey=REAL_KEY), factory=factory)
    d = p.get_settings_dict()
    assert 'apikey' not in d
    assert d['available'] is True
