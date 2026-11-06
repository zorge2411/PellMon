"""Get/SetBackupSettings, GetBackupStatus, StartBackup, TestBackupFolder D-Bus methods."""
import json
import logging
from types import SimpleNamespace

import pytest

SECRET = '/very/secret/path'


class FakePlugin(object):
    def __init__(self):
        self.calls = []
        self.raise_on = None

    def _maybe_raise(self, name):
        if self.raise_on == name:
            raise ValueError(SECRET)

    def get_settings_dict(self):
        self._maybe_raise('get')
        return {'enabled': True, 'available': True, 'root': '/backups'}

    def apply_settings(self, data):
        self.calls.append(('apply', data))
        self._maybe_raise('apply')
        return {'ok': True, 'errors': {}}

    def status_dict(self):
        self._maybe_raise('status')
        return {'available': True, 'state': 'ok'}

    def start_now(self):
        self.calls.append(('start',))
        self._maybe_raise('start')
        return {'ok': True, 'reason': ''}

    def test_folder(self):
        self._maybe_raise('test')
        return {'ok': True, 'reason': '', 'free_bytes': 5}


@pytest.fixture
def fake():
    return FakePlugin()


@pytest.fixture
def svc(daemon_module, fake, monkeypatch):
    conf = SimpleNamespace(database=SimpleNamespace(protocols=[SimpleNamespace(name='Backup', plugin_object=fake)]))
    monkeypatch.setattr(daemon_module, 'conf', conf)
    return daemon_module.MyDBUSService


@pytest.fixture
def absent(daemon_module, monkeypatch):
    conf = SimpleNamespace(database=SimpleNamespace(protocols=[]))
    monkeypatch.setattr(daemon_module, 'conf', conf)
    return daemon_module.MyDBUSService


def test_delegation(svc, fake):
    assert json.loads(svc.GetBackupSettings(None)) == fake.get_settings_dict()
    d = {'enabled': True, 'time': '03:00'}
    assert json.loads(svc.SetBackupSettings(None, json.dumps(d))) == {'ok': True, 'errors': {}}
    assert ('apply', d) in fake.calls
    assert json.loads(svc.GetBackupStatus(None)) == fake.status_dict()
    assert json.loads(svc.StartBackup(None)) == {'ok': True, 'reason': ''}
    assert json.loads(svc.TestBackupFolder(None))['free_bytes'] == 5


def test_absent_plugin(absent):
    assert json.loads(absent.GetBackupSettings(None)) == {'available': False}
    assert json.loads(absent.GetBackupStatus(None)) == {'available': False}
    assert json.loads(absent.SetBackupSettings(None, '{}'))['available'] is False
    assert json.loads(absent.StartBackup(None))['ok'] is False
    assert json.loads(absent.TestBackupFolder(None))['ok'] is False


def test_conf_none(daemon_module, monkeypatch):
    monkeypatch.setattr(daemon_module, 'conf', None)
    assert json.loads(daemon_module.MyDBUSService.GetBackupStatus(None)) == {'available': False}


@pytest.mark.parametrize('bad', ['not json', '[1, 2]', '"str"', '5'])
def test_invalid_input_rejected(svc, fake, bad):
    assert json.loads(svc.SetBackupSettings(None, bad))['ok'] is False
    assert fake.calls == []


def test_plugin_exceptions_are_contained_and_not_leaked(svc, fake, caplog):
    outputs = []
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        for name, call in (('apply', lambda: svc.SetBackupSettings(None, '{}')), ('get', lambda: svc.GetBackupSettings(None)),
                           ('status', lambda: svc.GetBackupStatus(None)), ('start', lambda: svc.StartBackup(None)),
                           ('test', lambda: svc.TestBackupFolder(None))):
            fake.raise_on = name
            outputs.append(call())
    assert all(SECRET not in o for o in outputs) and SECRET not in caplog.text
    assert len([r for r in caplog.records if r.levelno == logging.ERROR]) == 5


def test_backup_is_always_loaded(daemon_module):
    assert 'Backup' in daemon_module.ALWAYS_LOADED_PLUGINS
