# -*- coding: utf-8 -*-
"""homeassistant plugin: activation, D-Bus contract, live reconfigure, guards."""

import atexit
import logging

import pytest

from fake_mqtt import FakeClientFactory, FakeDb
from Pellmonsrv.database import Keyval_storage
from Pellmonsrv.plugins import homeassistant as ha_plugin
from Pellmonsrv.plugins.homeassistant import settings as ha_settings

SECRET = 's3cret-XYZ'
VALID = {'enabled': True, 'host': 'broker.lan', 'device_id': 'dev_1',
         'device_name': 'Burner', 'password': SECRET}


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = Keyval_storage(str(tmp_path / 'kv.db'))
    monkeypatch.setattr(Keyval_storage, 'keyval_storage', s, raising=False)
    return s


@pytest.fixture
def exits(monkeypatch):
    calls = []
    monkeypatch.setattr(atexit, 'register', lambda f, *a, **k: calls.append(f))
    return calls


@pytest.fixture
def factory():
    return FakeClientFactory()


def make(factory, db=None):
    p = ha_plugin.homeassistant()
    p.client_factory = factory
    p.autostart = False
    db = db or FakeDb.make_scotte_db()
    p.activate({}, {'__version__': '9.9'}, db)
    return p, db


def test_activate_registers_listener_and_atexit(store, exits, factory):
    p, db = make(factory)
    assert db.listeners == [p.bridge.on_changes]
    assert p.bridge.shutdown in exits
    p.bridge.handle_all()
    assert factory.calls == []


def test_get_settings_dict(store, exits, factory):
    p, _ = make(factory)
    d = p.get_settings_dict()
    assert 'password' not in d
    assert d['has_password'] is False
    assert d['available'] is True
    for k, v in ha_settings.DEFAULTS.items():
        assert d[k] == v


def test_apply_settings_live_reconnect(store, exits, factory, caplog):
    caplog.set_level(logging.DEBUG)
    p, _ = make(factory)
    assert p.apply_settings(dict(VALID)) == {'ok': True, 'errors': {}}
    assert ha_settings.load(store)['host'] == 'broker.lan'
    assert ha_settings.has_password(store)
    p.bridge.handle_all()
    assert factory.calls[-1]['password'] == SECRET
    assert factory.calls[-1]['cfg']['host'] == 'broker.lan'
    assert 'password' not in p.get_settings_dict()
    assert SECRET not in caplog.text


def test_password_keep_and_clear(store, exits, factory):
    p, _ = make(factory)
    p.apply_settings(dict(VALID))
    d = dict(VALID, password='')
    assert p.apply_settings(d)['ok']
    assert ha_settings.load_password(store) == SECRET
    d = dict(VALID, password='', clear_password=True)
    assert p.apply_settings(d)['ok']
    assert ha_settings.load_password(store) == ''


def test_invalid_port_stores_nothing(store, exits, factory):
    p, _ = make(factory)
    r = p.apply_settings(dict(VALID, port='99999'))
    assert r['ok'] is False and 'port' in r['errors']
    assert ha_settings.load(store) == ha_settings.DEFAULTS
    p.bridge.handle_all()
    assert factory.calls == []


def test_tls_verify_rules(store, exits, factory):
    p, _ = make(factory)
    base = dict(VALID, tls=True, tls_verify=True, tls_verify_field=True)
    assert p.apply_settings(base)['ok']
    assert ha_settings.load(store)['tls_verify'] is True
    # TLS off and no marker: keep stored
    assert p.apply_settings(dict(VALID, tls=False))['ok']
    assert ha_settings.load(store)['tls_verify'] is True
    # explicit False stored
    assert p.apply_settings(dict(base, tls_verify=False))['ok']
    assert ha_settings.load(store)['tls_verify'] is False
    assert p.apply_settings(dict(VALID, tls=False))['ok']
    assert ha_settings.load(store)['tls_verify'] is False
    # tls ticked on a TLS-off page (marker false, no value): stored kept
    assert p.apply_settings(dict(VALID, tls=True, tls_verify_field=False))['ok']
    assert ha_settings.load(store)['tls_verify'] is False


def test_tls_enabled_from_off_defaults_true(store, exits, factory):
    p, _ = make(factory)
    assert p.apply_settings(dict(VALID, tls=True, tls_verify_field=False))['ok']
    assert ha_settings.load(store)['tls_verify'] is True
    assert p.start_test({'host': 'broker.lan', 'port': 1883, 'tls': True,
                         'tls_verify_field': False}) is True
    p.bridge._get_tester()  # tester runs the fake factory in isolation
    import time
    for _ in range(50):
        if factory.calls:
            break
        time.sleep(0.05)
    assert factory.calls and factory.calls[-1]['cfg']['tls_verify'] is True


def test_start_test_password_choice(store, exits, factory):
    p, _ = make(factory)
    p.apply_settings(dict(VALID))
    seen = []
    p.bridge.start_test = lambda cfg, pw: seen.append((cfg['host'], pw)) or True
    assert p.start_test({'host': 'broker.lan', 'port': 1883, 'password': ''})
    assert p.start_test({'host': 'broker.lan', 'port': 1883, 'password': 'typed'})
    assert seen == [('broker.lan', SECRET), ('broker.lan', 'typed')]
    assert p.start_test({'host': 'bad host', 'port': 1883}) is False


def test_status_and_test_result_delegate(store, exits, factory):
    p, _ = make(factory)
    assert p.status_dict() == p.bridge.status_dict()
    assert 'state' in p.test_result_dict()
    assert 'password' not in p.status_dict()


def test_store_unavailable(monkeypatch, exits, factory):
    monkeypatch.setattr(Keyval_storage, 'keyval_storage', None, raising=False)
    p, _ = make(factory)
    assert p.get_settings_dict()['enabled'] is False
    assert p.apply_settings(dict(VALID)) == {'ok': False, 'errors': {'_': 'settings store unavailable'}}


@pytest.fixture
def broken(store, exits, factory, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('boom')
    monkeypatch.setattr(ha_plugin.ha_bridge, 'Bridge', boom)
    return make(factory)[0]


def test_bridge_constructor_failure(broken, caplog, factory):
    assert broken.bridge is None
    assert broken.get_settings_dict()['available'] is False
    assert broken.status_dict() == {'available': False, 'state': 'off'}
    assert broken.start_test({'host': 'broker.lan', 'port': 1883}) is False
    assert factory.calls == []
    assert broken.test_result_dict() == {'state': 'error',
                                         'message': 'unknown error (see the server log)',
                                         'available': False}
    assert broken.apply_settings(dict(VALID)) == {'ok': True, 'errors': {}, 'available': False}
    r = broken.apply_settings(dict(VALID, port='0'))
    assert r['ok'] is False and r['errors'] and r['available'] is False
    broken.deactivate()
    assert SECRET not in caplog.text


def test_delegate_exception_caught(store, exits, factory, monkeypatch, caplog):
    p, _ = make(factory)

    def boom(*a, **k):
        raise RuntimeError('boom')
    monkeypatch.setattr(p.bridge, 'status_dict', boom)
    monkeypatch.setattr(p.bridge, 'test_result_dict', boom)
    assert p.status_dict() == {'available': False, 'state': 'off'}
    assert p.test_result_dict()['available'] is False
    assert 'boom' in caplog.text or 'failed' in caplog.text


def test_deactivate_shuts_down(store, exits, factory):
    p, _ = make(factory)
    called = []
    p.bridge.shutdown = lambda: called.append(1)
    p.deactivate()
    assert called == [1]
