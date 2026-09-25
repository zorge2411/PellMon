# -*- coding: utf-8 -*-
"""Reason mapping and isolated connection test (D-13, D-19/C7)."""

import socket
import ssl

import pytest

from fake_mqtt import FakeClientFactory, FakeReasonCode
from Pellmonsrv.plugins.homeassistant import bridge as bridge_module
from Pellmonsrv.plugins.homeassistant import tester as tester_module
from Pellmonsrv.plugins.homeassistant.tester import (
    REASONS, map_reason, ConnectionTester, TEST_TOTAL_SECONDS, CONNECT_TIMEOUT)

CFG = {'host': 'broker.local', 'port': 1883, 'username': 'u', 'tls': False,
       'tls_verify': True, 'prefix': 'scotte', 'discovery_prefix': 'homeassistant',
       'device_id': 'dev1', 'device_name': 'Dev', 'node_id': 'dev1',
       'uid_prefix': 'dev1', 'allow_commands': False, 'refresh': 60, 'enabled': True}


class SyncThread(object):
    def __init__(self, target=None, args=()):
        self.target = target
        self.args = args
        self.daemon = False

    def start(self):
        self.target(*self.args)


class RecordingEvent(object):
    """Event that records wait timeouts and reports the preset outcome"""
    def __init__(self):
        self.is_set = False
        self.waits = []

    def set(self):
        self.is_set = True

    def wait(self, timeout=None):
        self.waits.append(timeout)
        return self.is_set


class ManualClock(object):
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _sync_tester(factory, **kw):
    return ConnectionTester(factory, thread_factory=SyncThread, **kw)


def test_constants():
    assert TEST_TOTAL_SECONDS == 8.0
    assert CONNECT_TIMEOUT == 5.0
    assert TEST_TOTAL_SECONDS < 10.0


@pytest.mark.parametrize('obj,expected', [
    (ConnectionRefusedError(), 'connection refused'),
    (socket.gaierror(), 'host not found'),
    (TimeoutError(), 'timed out'),
    (socket.timeout(), 'timed out'),
    (ssl.SSLCertVerificationError(), 'certificate could not be verified'),
    (ssl.SSLError(), 'TLS handshake failed'),
    (ValueError('secret-password'), 'unknown error (see the server log)'),
    (4, 'wrong username or password'),
    (134, 'wrong username or password'),
    (5, 'not authorised'),
    (135, 'not authorised'),
    (3, 'connection refused'),
    (136, 'connection refused'),
    (99, 'unknown error (see the server log)'),
    (FakeReasonCode(134), 'wrong username or password'),
    (FakeReasonCode(135), 'not authorised'),
])
def test_map_reason(obj, expected):
    assert map_reason(obj) == expected
    assert expected in REASONS


class DeferredThread(object):
    """Thread stand-in that only runs when told to"""
    def __init__(self, target=None, args=()):
        self.target = target
        self.args = args
        self.daemon = False
        self.started = False

    def start(self):
        self.started = True

    def run(self):
        self.target(*self.args)


def test_success_isolated_client():
    factory = FakeClientFactory(auto_connect=0)
    t = _sync_tester(factory)
    assert t.start(CFG, 'pw') is True
    assert t.result_dict() == {'state': 'ok', 'message': ''}
    client = factory.last
    assert factory.calls[0]['client_id'].startswith('pellmon-test-')
    assert factory.calls[0]['will_topic'] is None
    assert factory.calls[0]['password'] == 'pw'
    assert client.published == [] and client.subscriptions == []
    assert client.disconnect_calls == 1 and client.loop_stopped


def test_random_client_ids_differ():
    factory = FakeClientFactory(auto_connect=0)
    t = _sync_tester(factory)
    t.start(CFG, '')
    t.start(CFG, '')
    ids = [c['client_id'] for c in factory.calls]
    assert len(set(ids)) == 2
    assert factory.calls[0]['password'] == ''


def test_second_start_while_running_refused():
    factory = FakeClientFactory(auto_connect=0)
    created = []

    def thread_factory(target=None, args=()):
        th = DeferredThread(target, args)
        created.append(th)
        return th

    t = ConnectionTester(factory, thread_factory=thread_factory)
    assert t.start(CFG, 'pw') is True
    assert t.result_dict()['state'] == 'running'
    assert t.start(CFG, 'pw') is False
    assert len(created) == 1
    created[0].run()
    assert t.result_dict()['state'] == 'ok'
    assert t.start(CFG, 'pw') is True


def test_connect_error_mapped():
    factory = FakeClientFactory(connect_error=ConnectionRefusedError())
    t = _sync_tester(factory)
    t.start(CFG, 'pw')
    assert t.result_dict() == {'state': 'error', 'message': 'connection refused'}
    assert factory.last.disconnect_calls == 1


def test_connack_refusal_mapped():
    factory = FakeClientFactory(auto_connect=134)
    t = _sync_tester(factory)
    t.start(CFG, 'pw')
    assert t.result_dict() == {'state': 'error', 'message': 'wrong username or password'}


def test_no_connack_times_out():
    factory = FakeClientFactory()
    events = []

    def event_factory():
        ev = RecordingEvent()
        events.append(ev)
        return ev

    t = _sync_tester(factory, event_factory=event_factory)
    t.start(CFG, 'pw')
    assert t.result_dict() == {'state': 'error', 'message': 'timed out'}
    assert events[0].waits and events[0].waits[0] <= TEST_TOTAL_SECONDS
    assert factory.last.loop_stopped


class SlowConnectFactory(object):
    """Wraps FakeClientFactory; the client's connect() consumes clock time"""
    def __init__(self, clock, seconds):
        self.inner = FakeClientFactory(auto_connect=None)
        self.clock = clock
        self.seconds = seconds

    def __call__(self, *args):
        client = self.inner(*args)
        orig = client.connect

        def slow_connect(host, port=1883, keepalive=60):
            self.clock.advance(self.seconds)
            return orig(host, port, keepalive)

        client.connect = slow_connect
        return client


def _slow_run(seconds):
    clock = ManualClock()
    factory = SlowConnectFactory(clock, seconds)
    events = []

    def event_factory():
        ev = RecordingEvent()
        events.append(ev)
        return ev

    t = _sync_tester(factory, clock=clock, event_factory=event_factory)
    t.start(CFG, 'pw')
    return t, events, factory


def test_total_timeout_bounds_the_connack_wait():
    t, events, factory = _slow_run(6.0)
    assert events[0].waits == [2.0]
    assert 6.0 + events[0].waits[0] <= TEST_TOTAL_SECONDS
    assert t.result_dict()['message'] == 'timed out'


def test_total_timeout_exceeded_in_connect_does_not_wait():
    t, events, factory = _slow_run(9.0)
    assert events[0].waits == []
    assert t.result_dict() == {'state': 'error', 'message': 'timed out'}
    assert factory.inner.last.disconnect_calls == 1


def test_bridge_reexports_same_objects():
    assert bridge_module.map_reason is map_reason
    assert bridge_module.REASONS is REASONS
    assert bridge_module.ConnectionTester is ConnectionTester


def test_tester_module_does_not_import_bridge_or_paho():
    import ast
    tree = ast.parse(open(tester_module.__file__, encoding='utf-8').read())
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or '')
    assert not [n for n in names if 'bridge' in n or 'paho' in n]
