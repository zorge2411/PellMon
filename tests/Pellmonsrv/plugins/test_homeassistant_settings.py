# -*- coding: utf-8 -*-
"""Home Assistant settings validator and storage tests (D-03, D-11, D-12)."""

import json
import logging
import pathlib

import pytest

from Pellmonsrv.database import Keyval_storage
from Pellmonsrv.plugins.homeassistant import settings as S
from Pellmonsrv.plugins.homeassistant.settings import (
    DEFAULTS, TLS_VERIFY_MARKER, validate, validate_password, effective,
    load, load_password, has_password, save, public_view)

SENTINEL = 's3cret-XYZ'


def _store(tmp_path):
    return Keyval_storage(str(tmp_path / 'test.db'))


def _ok(**kw):
    d = {'host': 'h', 'device_id': 'dev1', 'device_name': 'Dev'}
    d.update(kw)
    return d


def _err(field, value, **extra):
    d = _ok(**extra)
    d[field] = value
    return validate(d)[1]


def test_defaults():
    assert DEFAULTS == {
        'enabled': False, 'host': '', 'port': 1883, 'username': '', 'tls': False,
        'tls_verify': True, 'prefix': 'scotte', 'discovery_prefix': 'homeassistant',
        'device_id': '', 'device_name': '', 'node_id': '', 'uid_prefix': '',
        'allow_commands': False, 'refresh': 60}


def test_validate_empty_is_defaults():
    clean, errors = validate({})
    assert errors == {}
    assert clean == DEFAULTS


def test_enabled_requires_three_fields():
    clean, errors = validate({'enabled': 'on'})
    assert set(errors) == {'host', 'device_id', 'device_name'}
    assert errors['host'] == S.MSG_ERR_HOST
    assert errors['device_id'] == S.MSG_ERR_DEVICE_ID
    assert errors['device_name'] == S.MSG_ERR_DEVICE_NAME


def test_for_test_requires_host_only():
    clean, errors = validate({'enabled': 'on'}, for_test=True)
    assert 'host' in errors
    clean, errors = validate({'host': 'h'}, for_test=True)
    assert errors == {}


@pytest.mark.parametrize('host', ['mqtt.example.com', '192.168.1.10', 'fd00::1'])
def test_host_ok(host):
    assert validate({'host': host, 'enabled': 'on', 'device_id': 'a', 'device_name': 'b'})[1] == {}


@pytest.mark.parametrize('host', ['[fd00::1]', 'mqtt://x', 'a b', '', 'a' * 254])
def test_host_bad(host):
    assert 'host' in validate({'host': host, 'enabled': 'on', 'device_id': 'a', 'device_name': 'b'})[1]


def test_host_bad_when_disabled_and_nonempty():
    assert 'host' in validate({'host': '[fd00::1]'})[1]


@pytest.mark.parametrize('port', ['1883', 1, 65535])
def test_port_ok(port):
    clean, errors = validate({'port': port})
    assert 'port' not in errors
    assert clean['port'] == int(port)


@pytest.mark.parametrize('port', ['0', '65536', 'abc', True])
def test_port_bad(port):
    assert validate({'port': port})[1]['port'] == S.MSG_ERR_PORT


def test_username():
    assert 'username' not in validate({'username': ''})[1]
    assert 'username' not in validate({'username': 'u' * 128})[1]
    assert validate({'username': 'u' * 129})[1]['username'] == S.MSG_ERR_USERNAME
    assert 'username' in validate({'username': 'a\x01b'})[1]
    assert 'username' in validate({'username': 'a\nb'})[1]


@pytest.mark.parametrize('field', ['prefix', 'discovery_prefix'])
def test_prefixes(field):
    for good in ('scotte', 'home/burner', 'a_b-c'):
        assert field not in validate({field: good})[1]
    for bad in ('', '/scotte', 'scotte/', 'a//b', 'a#', 'a+b', 'a b', '$SYS', 'a' * 65):
        assert field in validate({field: bad})[1], bad


def test_device_id():
    assert 'device_id' not in validate({'device_id': 'abc_DEF-1'})[1]
    for bad in ('a b', 'a.b', 'a' * 65):
        assert 'device_id' in validate({'device_id': bad})[1]


def test_device_name():
    assert 'device_name' not in validate({'device_name': 'x' * 64})[1]
    assert 'device_name' in validate({'device_name': 'x' * 65, 'enabled': 'on'})[1]
    assert 'device_name' in validate({'device_name': 'a\tb'})[1]


@pytest.mark.parametrize('field', ['node_id', 'uid_prefix'])
def test_optional_ids(field):
    assert field not in validate({field: ''})[1]
    assert field not in validate({field: 'a_B-1'})[1]
    assert validate({field: 'a b'})[1][field] == S.MSG_ERR_NODE_ID


def test_refresh():
    for good in (10, 3600, '60'):
        assert 'refresh' not in validate({'refresh': good})[1]
    for bad in (9, 3601, 'x'):
        assert validate({'refresh': bad})[1]['refresh'] == S.MSG_ERR_REFRESH


def test_bool_coercion():
    for truthy in ('on', 'true', '1', True):
        c = validate({'enabled': truthy, 'tls': truthy, 'allow_commands': truthy,
                      'host': 'h', 'device_id': 'a', 'device_name': 'b'})[0]
        assert c['enabled'] and c['tls'] and c['allow_commands']
    for falsy in ('', False, None):
        c = validate({'tls': falsy, 'allow_commands': falsy})[0]
        assert c['tls'] is False and c['allow_commands'] is False
    assert validate({})[0]['enabled'] is False


def test_tls_verify_kept_when_not_explicit():
    assert validate({})[0]['tls_verify'] is True
    assert validate({}, current={'tls_verify': True})[0]['tls_verify'] is True
    assert validate({}, current={'tls_verify': False})[0]['tls_verify'] is False
    # TLS enabled from a TLS-off page without JS: no tls_verify, no marker
    assert validate({'tls': 'on'})[0]['tls_verify'] is True
    assert validate({'tls': 'on'}, current={'tls_verify': True})[0]['tls_verify'] is True
    # a submitted tls_verify without the marker is not trusted
    assert validate({'tls': 'on', 'tls_verify': ''}, current={'tls_verify': True})[0]['tls_verify'] is True


def test_tls_verify_explicit():
    m = TLS_VERIFY_MARKER
    assert validate({'tls': 'on', m: '1'})[0]['tls_verify'] is False
    assert validate({'tls': 'on', m: '1', 'tls_verify': 'on'})[0]['tls_verify'] is True
    assert validate({'tls': 'on', m: True})[0]['tls_verify'] is False
    assert validate({'tls': 'on', m: True, 'tls_verify': True})[0]['tls_verify'] is True
    # marker present but tls off -> stored/default kept
    assert validate({m: '1'})[0]['tls_verify'] is True
    assert validate({m: '1'}, current={'tls_verify': False})[0]['tls_verify'] is False


def test_marker_never_in_clean_or_stored(tmp_path):
    clean, _ = validate({'tls': 'on', TLS_VERIFY_MARKER: '1', 'tls_verify': 'on'})
    assert TLS_VERIFY_MARKER not in clean
    store = _store(tmp_path)
    save(store, clean)
    assert TLS_VERIFY_MARKER not in store.getval('mqtt.config')


def test_validate_password():
    assert validate_password('') is None
    assert validate_password('p' * 256) is None
    assert validate_password('p' * 257) == S.MSG_ERR_PASSWORD
    assert validate_password('a\x00b') == S.MSG_ERR_PASSWORD


def test_effective():
    e = effective(dict(DEFAULTS, device_id='dev1'))
    assert e['node_id'] == 'dev1' and e['uid_prefix'] == 'dev1'
    e = effective(dict(DEFAULTS, device_id='dev1', node_id='n', uid_prefix='u'))
    assert e['node_id'] == 'n' and e['uid_prefix'] == 'u'


def test_save_load_roundtrip(tmp_path):
    store = _store(tmp_path)
    clean, errors = validate(_ok(enabled='on', port='8883', tls='on'), current=None)
    assert errors == {}
    save(store, clean, password=SENTINEL)
    assert load(store) == clean
    assert load_password(store) == SENTINEL
    assert has_password(store)
    assert SENTINEL not in store.getval('mqtt.config')


def test_password_keep_and_clear(tmp_path):
    store = _store(tmp_path)
    clean, _ = validate(_ok())
    save(store, clean, password=SENTINEL)
    save(store, clean, password='')
    assert load_password(store) == SENTINEL
    save(store, clean, clear_password=True)
    assert not has_password(store)


def test_load_defaults_and_corrupt(tmp_path, caplog):
    store = _store(tmp_path)
    assert load(store) == DEFAULTS
    assert load(None) == DEFAULTS
    store.writeval('mqtt.config', '{corrupt-text-MARK')
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        assert load(store) == DEFAULTS
    warns = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warns) == 1
    assert 'MARK' not in caplog.text


def test_public_view_no_secret(tmp_path, caplog):
    store = _store(tmp_path)
    clean, _ = validate(_ok())
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        save(store, clean, password=SENTINEL)
        cfg = load(store)
        view = public_view(cfg, store)
    assert view['has_password'] is True
    assert 'password' not in view
    assert SENTINEL not in json.dumps(view)
    assert SENTINEL not in caplog.text
    assert set(DEFAULTS) <= set(view)


def test_ui_spec_messages_verbatim():
    src = pathlib.Path(S.__file__).read_text(encoding='utf-8')
    for msg in (S.MSG_ERR_HOST, S.MSG_ERR_PORT, S.MSG_ERR_USERNAME, S.MSG_ERR_PASSWORD,
                S.MSG_ERR_PREFIX, S.MSG_ERR_DISCOVERY_PREFIX, S.MSG_ERR_DEVICE_ID,
                S.MSG_ERR_DEVICE_NAME, S.MSG_ERR_REFRESH):
        assert msg in src
    assert S.MSG_ERR_HOST == 'Enter the broker host name or IP address, without mqtt:// and without spaces.'
    assert S.MSG_ERR_REFRESH == 'Refresh interval must be between 10 and 3600 seconds.'
    assert S.MSG_ERR_PORT == 'Port must be a number from 1 to 65535.'
