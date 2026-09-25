#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2013  Anders Nylund
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Fixed reason set, exception/reason-code mapping and the isolated connection
# test. Stdlib only: this module never imports the bridge or paho.

import logging
import secrets
import socket
import ssl
import threading
import time

logger = logging.getLogger('pellMon')

# Timeout chain: paho connect 5 s -> tester total 8 s -> web poll cap 10 s -> browser abort 12 s
CONNECT_TIMEOUT = 5.0
TEST_TOTAL_SECONDS = 8.0

REASON_REFUSED = 'connection refused'
REASON_HOST = 'host not found'
REASON_TIMEOUT = 'timed out'
REASON_AUTH = 'wrong username or password'
REASON_NOT_AUTH = 'not authorised'
REASON_CERT = 'certificate could not be verified'
REASON_TLS = 'TLS handshake failed'
REASON_LOST = 'connection lost'
REASON_UNKNOWN = 'unknown error (see the server log)'

REASONS = (REASON_REFUSED, REASON_HOST, REASON_TIMEOUT, REASON_AUTH, REASON_NOT_AUTH,
           REASON_CERT, REASON_TLS, REASON_LOST, REASON_UNKNOWN)


def map_reason(obj):
    """Map an exception or a CONNACK/reason code to one of REASONS. Never
    includes text from the exception (it could contain credentials)."""
    if isinstance(obj, BaseException):
        if isinstance(obj, ssl.SSLCertVerificationError):
            return REASON_CERT
        if isinstance(obj, ssl.SSLError):
            return REASON_TLS
        if isinstance(obj, ConnectionRefusedError):
            return REASON_REFUSED
        if isinstance(obj, socket.gaierror):
            return REASON_HOST
        if isinstance(obj, (TimeoutError, socket.timeout)):
            return REASON_TIMEOUT
        return REASON_UNKNOWN
    value = getattr(obj, 'value', obj)
    if isinstance(value, bool) or not isinstance(value, int):
        return REASON_UNKNOWN
    if value in (4, 134):
        return REASON_AUTH
    if value in (5, 135):
        return REASON_NOT_AUTH
    if value in (3, 136):
        return REASON_REFUSED
    return REASON_UNKNOWN


class ConnectionTester(object):
    """One-at-a-time start-and-poll connection test. Uses its own random client id,
    never publishes or subscribes, and finishes within total_timeout seconds."""

    def __init__(self, client_factory, clock=time.monotonic, total_timeout=TEST_TOTAL_SECONDS,
                 thread_factory=threading.Thread, event_factory=threading.Event):
        self._factory = client_factory
        self._clock = clock
        self._total = total_timeout
        self._thread_factory = thread_factory
        self._event_factory = event_factory
        self._lock = threading.Lock()
        self._result = {'state': 'idle', 'message': ''}

    def start(self, cfg, password):
        with self._lock:
            if self._result['state'] == 'running':
                return False
            self._result = {'state': 'running', 'message': ''}
        t = self._thread_factory(target=self.run_once, args=(dict(cfg), password))
        try:
            t.daemon = True
        except Exception:
            pass
        t.start()
        return True

    def result_dict(self):
        with self._lock:
            return dict(self._result)

    def _finish(self, state, message):
        with self._lock:
            self._result = {'state': state, 'message': message}

    def run_once(self, cfg, password):
        deadline = self._clock() + self._total
        outcome = {}
        done = self._event_factory()

        def on_connect(client, userdata, flags, reason_code, properties=None):
            outcome['rc'] = reason_code
            done.set()

        def on_disconnect(client, userdata, *args):
            if 'rc' not in outcome:
                outcome['lost'] = True
                done.set()

        def on_message(client, userdata, message):
            pass

        client = None
        started = False
        try:
            client_id = 'pellmon-test-' + secrets.token_hex(4)
            client = self._factory(cfg, password, client_id, None,
                                   on_connect, on_disconnect, on_message)
            client.connect(cfg['host'], cfg['port'], 60)
            remaining = deadline - self._clock()
            if remaining <= 0:
                self._finish('error', REASON_TIMEOUT)
                return
            client.loop_start()
            started = True
            if not done.wait(remaining):
                self._finish('error', REASON_TIMEOUT)
            elif outcome.get('lost'):
                self._finish('error', REASON_LOST)
            else:
                rc = outcome['rc']
                failed = getattr(rc, 'is_failure', None)
                if failed is None:
                    failed = rc != 0
                if failed:
                    self._finish('error', map_reason(rc))
                else:
                    self._finish('ok', '')
        except Exception as e:
            reason = map_reason(e)
            logger.warning('Home Assistant connection test failed: %s', reason)
            self._finish('error', reason)
        finally:
            if client is not None:
                try:
                    client.disconnect()
                except Exception:
                    pass
                if started:
                    try:
                        client.loop_stop()
                    except Exception:
                        pass
