"""GetOwmSettings / SetOwmSettings / GetOwmStatus D-Bus methods, write-only API key."""
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
        self.settings = {'location': 'copenhagen,dk', 'unit': 'celsius', 'has_apikey': True,
                         'available': True, 'enabled': True}

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
        return {'available': True, 'state': 'ok', 'last_fetch': 1.0, 'reason': '',
                'location': 'copenhagen,dk'}


@pytest.fixture
def fake():
    return FakePlugin()


@pytest.fixture
def svc(daemon_module, fake, monkeypatch, tmp_path):
    from Pellmonsrv.database import init_keyval_storage
    init_keyval_storage(str(tmp_path / "settings.db"))
    conf = SimpleNamespace(database=SimpleNamespace(
        protocols=[SimpleNamespace(name='Openweathermap', plugin_object=fake)]))
    monkeypatch.setattr(daemon_module, 'conf', conf)
    yield daemon_module.MyDBUSService
    Keyval_storage.keyval_storage = None


@pytest.fixture
def absent(daemon_module, monkeypatch):
    conf = SimpleNamespace(database=SimpleNamespace(protocols=[]))
    monkeypatch.setattr(daemon_module, 'conf', conf)
    return daemon_module.MyDBUSService


def test_delegation(svc, fake):
    assert json.loads(svc.GetOwmSettings(None)) == fake.get_settings_dict()
    d = {'enabled': True, 'location': 'aarhus,dk', 'unit': 'celsius', 'apikey': SENTINEL}
    assert json.loads(svc.SetOwmSettings(None, json.dumps(d))) == {'ok': True, 'errors': {}}
    assert ('apply', d) in fake.calls
    assert json.loads(svc.GetOwmStatus(None)) == fake.status_dict()


def test_apikey_stripped_from_get(svc, fake):
    fake.settings['apikey'] = SENTINEL
    out = svc.GetOwmSettings(None)
    assert 'apikey' not in json.loads(out)
    assert SENTINEL not in out


def test_absent_plugin(absent):
    assert json.loads(absent.GetOwmSettings(None)) == {'available': False}
    assert json.loads(absent.GetOwmStatus(None)) == {'available': False}
    r = json.loads(absent.SetOwmSettings(None, '{}'))
    assert r['ok'] is False and r['available'] is False


def test_conf_none(daemon_module, monkeypatch):
    monkeypatch.setattr(daemon_module, 'conf', None)
    assert json.loads(daemon_module.MyDBUSService.GetOwmSettings(None)) == {'available': False}


@pytest.mark.parametrize('bad', ['not json', '[1, 2]', '"str"', '5'])
def test_invalid_input_rejected(svc, fake, bad):
    r = json.loads(svc.SetOwmSettings(None, bad))
    assert r['ok'] is False
    assert fake.calls == []


def test_plugin_exception_safe_and_no_leak(svc, fake, caplog):
    fake.raise_on = 'apply'
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        r = json.loads(svc.SetOwmSettings(None, json.dumps({'apikey': SENTINEL})))
        fake.raise_on = 'get'
        json.loads(svc.GetOwmSettings(None))
    assert r['ok'] is False
    assert SENTINEL not in caplog.text
    errs = [rec for rec in caplog.records if rec.levelno == logging.ERROR]
    assert len(errs) == 2
    assert 'SetOwmSettings' in errs[0].getMessage()
    assert 'ValueError' in errs[0].getMessage()


def test_apikey_not_readable_via_getsetting(svc):
    assert svc.GetSetting(None, 'owm.apikey') == ''
    assert svc.SetSetting(None, 'owm.apikey', 'x') is False


def test_no_owm_key_in_allowed_settings(daemon_module):
    assert not any(k.startswith('owm.') for k in daemon_module.ALLOWED_SETTINGS)
