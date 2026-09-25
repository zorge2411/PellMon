# -*- coding: utf-8 -*-
"""Real paho 2.x client built through the default factory (API drift guard, no sockets)."""

import ssl

import pytest

mqtt = pytest.importorskip('paho.mqtt.client')

from Pellmonsrv.plugins.homeassistant import bridge  # noqa: E402

CFG = {'host': 'broker.local', 'port': 8883, 'username': 'user', 'tls': True,
       'tls_verify': True}


def _noop(*a, **k):
    pass


def _build(cfg, will_topic='scotte/status', password='pw', client_id='pellmon-test'):
    return bridge.default_paho_factory(cfg, password, client_id, will_topic, _noop, _noop, _noop)


def test_paho_available():
    assert bridge.paho_available() is True


def test_builds_client_with_will_tls_and_timeout(mocker):
    will = mocker.spy(mqtt.Client, 'will_set')
    tls = mocker.spy(mqtt.Client, 'tls_set')
    insecure = mocker.spy(mqtt.Client, 'tls_insecure_set')
    loop = mocker.spy(mqtt.Client, 'loop_start')
    client = _build(CFG)
    assert isinstance(client, mqtt.Client)
    will.assert_called_once_with(client, 'scotte/status', 'offline', qos=1, retain=True)
    assert tls.call_args.kwargs['cert_reqs'] == ssl.CERT_REQUIRED
    assert not [c for c in insecure.call_args_list if c.args[1] is True]
    loop.assert_not_called()
    assert client.connect_timeout == 5.0
    assert client._client_id == b'pellmon-test'


def test_verify_off_sets_insecure_after_tls(mocker):
    order = []
    orig_tls = mqtt.Client.tls_set
    orig_ins = mqtt.Client.tls_insecure_set

    def tls_set(self, *a, **k):
        order.append('tls_set')
        return orig_tls(self, *a, **k)

    def tls_insecure_set(self, value):
        order.append(('insecure', value))
        return orig_ins(self, value)

    mocker.patch.object(mqtt.Client, 'tls_set', tls_set)
    mocker.patch.object(mqtt.Client, 'tls_insecure_set', tls_insecure_set)
    cfg = dict(CFG, tls_verify=False)
    _build(cfg)
    assert order[0] == 'tls_set'
    assert order[-1] == ('insecure', True)


def test_no_will_topic_skips_will_set(mocker):
    will = mocker.spy(mqtt.Client, 'will_set')
    _build(dict(CFG, tls=False), will_topic=None)
    will.assert_not_called()
