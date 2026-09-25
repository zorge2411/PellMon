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
