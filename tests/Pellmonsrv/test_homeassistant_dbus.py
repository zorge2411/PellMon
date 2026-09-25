"""D-12/D-13/D-19: MQTT D-Bus methods, write-only password."""
import json
import logging
from types import SimpleNamespace

import pytest

from Pellmonsrv.database import Keyval_storage

SENTINEL = 's3cret-XYZ'


class FakePlugin(object):
    def __init__(self):
        self.calls = []
        self.raise_on = None
        self.settings = {'host': 'broker', 'port': 1883, 'has_password': True, 'available': True}

    def _maybe_raise(self, name):
        if self.raise_on == name:
            raise ValueError(SENTINEL)

    def get_settings_dict(self):
        self._maybe_raise('get')
        return dict(self.settings)

    def apply_settings(self, data):
        self.calls.append(('apply', data))
        self._maybe_raise('apply')
        return {'ok': True, 'errors': {}}

    def status_dict(self):
        return {'state': 'connected', 'host': 'broker'}

    def start_test(self, data):
        self.calls.append(('test', data))
        self._maybe_raise('test')
        return True

    def test_result_dict(self):
        return {'state': 'ok', 'message': ''}


@pytest.fixture
def fake():
    return FakePlugin()


@pytest.fixture
def svc(daemon_module, fake, monkeypatch, tmp_path):
    from Pellmonsrv.database import init_keyval_storage
    init_keyval_storage(str(tmp_path / "settings.db"))
    conf = SimpleNamespace(database=SimpleNamespace(
        protocols=[SimpleNamespace(name='HomeAssistant', plugin_object=fake)]))
    monkeypatch.setattr(daemon_module, 'conf', conf)
    yield daemon_module.MyDBUSService
    Keyval_storage.keyval_storage = None


@pytest.fixture
def absent(daemon_module, monkeypatch):
    conf = SimpleNamespace(database=SimpleNamespace(protocols=[]))
    monkeypatch.setattr(daemon_module, 'conf', conf)
    return daemon_module.MyDBUSService


def test_delegation(svc, fake):
    assert json.loads(svc.GetMqttSettings(None)) == fake.get_settings_dict()
    d = {'host': 'h', 'password': 'p'}
    assert json.loads(svc.SetMqttSettings(None, json.dumps(d))) == {'ok': True, 'errors': {}}
    assert ('apply', d) in fake.calls
    assert json.loads(svc.GetMqttStatus(None)) == fake.status_dict()
    assert svc.StartMqttTest(None, json.dumps({'host': 'h'})) is True
    assert json.loads(svc.GetMqttTestResult(None)) == fake.test_result_dict()


def test_password_stripped_from_get(svc, fake):
    fake.settings['password'] = SENTINEL
    out = svc.GetMqttSettings(None)
    assert 'password' not in json.loads(out)
    assert SENTINEL not in out


def test_absent_plugin(absent):
    assert json.loads(absent.GetMqttSettings(None)) == {'available': False}
    assert json.loads(absent.GetMqttStatus(None)) == {'available': False}
    r = json.loads(absent.SetMqttSettings(None, '{}'))
    assert r['ok'] is False and r['available'] is False
    assert absent.StartMqttTest(None, '{}') is False
    r = json.loads(absent.GetMqttTestResult(None))
    assert r['state'] == 'error' and r['available'] is False


def test_conf_none(daemon_module, monkeypatch):
    monkeypatch.setattr(daemon_module, 'conf', None)
    assert json.loads(daemon_module.MyDBUSService.GetMqttSettings(None)) == {'available': False}


@pytest.mark.parametrize('bad', ['not json', '[1, 2]', '"str"', '5'])
def test_invalid_input_rejected(svc, fake, bad):
    r = json.loads(svc.SetMqttSettings(None, bad))
    assert r['ok'] is False
    assert svc.StartMqttTest(None, bad) is False
    assert fake.calls == []


def test_plugin_exception_safe_and_no_leak(svc, fake, caplog):
    fake.raise_on = 'apply'
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        r = json.loads(svc.SetMqttSettings(None, json.dumps({'password': SENTINEL})))
        fake.raise_on = 'test'
        assert svc.StartMqttTest(None, json.dumps({'password': SENTINEL})) is False
        fake.raise_on = 'get'
        json.loads(svc.GetMqttSettings(None))
    assert r['ok'] is False
    assert SENTINEL not in caplog.text
    errs = [rec for rec in caplog.records if rec.levelno == logging.ERROR]
    assert len(errs) == 3
    assert 'SetMqttSettings' in errs[0].getMessage()
    assert 'ValueError' in errs[0].getMessage()


def test_password_not_readable_via_getsetting(svc):
    assert svc.GetSetting(None, 'mqtt.password') == ''
    assert svc.SetSetting(None, 'mqtt.password', 'x') is False


def test_no_mqtt_key_in_allowed_settings(daemon_module):
    assert not any(k.startswith('mqtt.') for k in daemon_module.ALLOWED_SETTINGS)
