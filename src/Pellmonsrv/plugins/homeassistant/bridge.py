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

# MQTT bridge to Home Assistant. One worker thread owns all publishing,
# commands and reconnects; paho's network thread callbacks only enqueue.

import json
import logging
import queue
import re
import socket
import ssl
import threading
import time

from . import entities, settings
from .tester import (REASONS, map_reason, ConnectionTester, CONNECT_TIMEOUT,
                     REASON_LOST)

logger = logging.getLogger('pellMon')

# Command limits (tunable defaults, RESEARCH A5)
CMD_PAYLOAD_MAX = 32
CMD_DEDUPE_SECONDS = 2
CMD_ITEM_INTERVAL = 5
CMD_GLOBAL_PER_MINUTE = 10
CMD_QUEUE_MAX = 20
CMD_OFF_LOG_INTERVAL = 60

RETRY_MAX = 60

_INT_RE = re.compile(r'[+-]?[0-9]{1,6}(\.0+)?')


def paho_available():
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        return False
    return hasattr(mqtt, 'CallbackAPIVersion')


def default_paho_factory(cfg, password, client_id, will_topic, on_connect, on_disconnect, on_message):
    """Build a configured paho 2.x client (callback API v2). Not connected, loop not started."""
    import paho.mqtt.client as mqtt
    if not hasattr(mqtt, 'CallbackAPIVersion'):
        raise RuntimeError('paho-mqtt >= 2.0 required')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id, clean_session=True)
    if cfg.get('username'):
        client.username_pw_set(cfg['username'], password or None)
    if cfg.get('tls'):
        if cfg.get('tls_verify', True):
            client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        else:
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
    if will_topic:
        client.will_set(will_topic, 'offline', qos=1, retain=True)
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.max_queued_messages_set(200)
    if hasattr(client, 'connect_timeout'):
        client.connect_timeout = CONNECT_TIMEOUT
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


class Bridge(object):
    def __init__(self, db, client_factory, snapshot=None, clock=time.monotonic,
                 wall_clock=time.time, sw_version='_dev_', settle=2.0, tester=None):
        self._db = db
        self._factory = client_factory
        self._snapshot_fn = snapshot
        self._clock = clock
        self._wall = wall_clock
        self._sw_version = sw_version
        self._settle = settle
        self._tester = tester

        self._q = queue.Queue()
        self._cmdq = queue.Queue(maxsize=CMD_QUEUE_MAX)
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._thread = None
        self._shut = False

        self._cfg = None
        self._password = ''
        self._client = None
        self._connected = False
        self._retry_at = None
        self._retry_delay = 1
        self._avail_published = None
        self._state_due = None
        self._last_refresh = None
        self._last_payloads = {}
        self._config_topics = set()
        self._present_ids = None
        self._off_logged = {}
        self._last_write = {}
        self._write_times = []

        self._status = {
            'state': 'off', 'host': '', 'port': 0, 'reason': '',
            'last_publish': None, 'last_connect': None,
            'availability': 'offline', 'burner': 'unsupported',
            'commands_enabled': False, 'entities': 0,
        }

    # ---- public API -------------------------------------------------

    def start(self):
        if self._thread is not None:
            return
        t = threading.Thread(target=self._run, name='HomeAssistantBridge')
        t.daemon = True
        self._thread = t
        t.start()

    def stop(self):
        self.shutdown()

    def shutdown(self):
        """Idempotent; publishes retained offline, disconnects, stops the worker"""
        with self._lock:
            if self._shut:
                return
            self._shut = True
        self._stopped.set()
        try:
            self._q.put_nowait(('stop',))
        except queue.Full:
            pass
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(5)
        try:
            self._teardown(offline=True)
        except Exception:
            logger.warning('Home Assistant shutdown failed')
        self._set_status(state='off')

    def reconfigure(self, cfg, password):
        self._q.put_nowait(('reconfigure', dict(cfg), password))

    def on_changes(self, changed_params):
        """Database listener; runs on the Database thread and only enqueues"""
        try:
            self._q.put_nowait(('changes', list(changed_params)))
        except Exception:
            pass

    def handle_all(self):
        while True:
            try:
                ev = self._q.get_nowait()
            except queue.Empty:
                break
            self._handle(ev)
        self._drain_commands()

    def status_dict(self):
        with self._lock:
            return dict(self._status)

    def start_test(self, cfg, password):
        return self._get_tester().start(cfg, password)

    def test_result_dict(self):
        return self._get_tester().result_dict()

    # ---- paho callbacks (network thread: enqueue only) ---------------

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        self._q.put_nowait(('connect', client, reason_code))

    def _on_disconnect(self, client, userdata, *args):
        rc = args[1] if len(args) >= 2 else (args[0] if args else None)
        self._q.put_nowait(('disconnect', client, rc))

    def _on_message(self, client, userdata, message):
        cfg = self._cfg
        try:
            if cfg is not None and message.topic == entities.birth_topic(cfg):
                self._q.put_nowait(('birth', message.payload))
                return
            self._cmdq.put_nowait((message.topic, bytes(message.payload), bool(message.retain)))
            self._q.put_nowait(('wake',))
        except queue.Full:
            logger.warning('Home Assistant command queue full, message dropped')

    # ---- internals ---------------------------------------------------

    def _get_tester(self):
        if self._tester is None:
            self._tester = ConnectionTester(self._factory)
        return self._tester

    def _set_status(self, **kw):
        with self._lock:
            self._status.update(kw)

    def _run(self):
        while not self._stopped.is_set():
            try:
                ev = self._q.get(timeout=1.0)
                self._handle(ev)
            except queue.Empty:
                pass
            try:
                self.handle_all()
                self.tick()
            except Exception:
                logger.exception('Home Assistant bridge error')

    def _handle(self, ev):
        kind = ev[0]
        if kind == 'connect':
            self._handle_connect(ev[1], ev[2])
        elif kind == 'disconnect':
            self._handle_disconnect(ev[1], ev[2])
        elif kind == 'birth':
            self._handle_birth(ev[1])
        elif kind == 'changes':
            self._handle_changes(ev[1])
        elif kind == 'reconfigure':
            self._apply(ev[1], ev[2])

    def _enabled(self):
        return self._cfg is not None and self._cfg.get('enabled') and self._cfg.get('host')

    def _keys(self):
        try:
            return set(self._db.keys())
        except Exception:
            return set()

    def _read_all(self):
        if self._snapshot_fn is not None:
            try:
                return dict(self._snapshot_fn())
            except Exception:
                logger.warning('Home Assistant could not read the value snapshot')
        out = {}
        for name in self._keys():
            try:
                out[name] = self._db.get_text(name)
            except Exception:
                pass
        return out

    def _present(self):
        return entities.present_entities(self._keys())

    def _burner(self, snap):
        if 'burner_connection' not in self._keys():
            return 'unsupported'
        value = snap.get('burner_connection')
        if value == 'connected':
            return 'connected'
        if value == 'demo':
            return 'demo'
        return 'no_connection'

    # -- connection

    def _connect(self):
        cfg = self._cfg
        client = None
        try:
            client = self._factory(cfg, self._password, 'pellmon-%s' % cfg['node_id'],
                                   entities.availability_topic(cfg),
                                   self._on_connect, self._on_disconnect, self._on_message)
            self._client = client
            self._set_status(state='connecting', reason='')
            client.connect(cfg['host'], cfg['port'], 60)
            client.loop_start()
        except Exception as e:
            self._client = None
            reason = map_reason(e)
            logger.warning('Home Assistant MQTT connect failed: %s', reason)
            self._set_status(state='disconnected', reason=reason)
            now = self._clock()
            self._retry_at = now + self._retry_delay
            self._retry_delay = min(self._retry_delay * 2, RETRY_MAX)
            return
        self._retry_at = None

    def _handle_connect(self, client, rc):
        if client is not self._client:
            return
        failed = getattr(rc, 'is_failure', None)
        if failed is None:
            failed = rc != 0
        if failed:
            reason = map_reason(rc)
            self._connected = False
            logger.warning('Home Assistant MQTT connection refused: %s', reason)
            self._set_status(state='disconnected', reason=reason)
            return
        self._connected = True
        self._retry_delay = 1
        logger.info('Home Assistant MQTT connected to %s:%s', self._cfg['host'], self._cfg['port'])
        self._set_status(state='connected', reason='', last_connect=self._wall())
        self._on_connected()

    def _handle_disconnect(self, client, rc):
        if client is not self._client:
            return
        self._connected = False
        self._avail_published = None
        logger.warning('Home Assistant MQTT connection lost')
        self._set_status(state='disconnected', reason=REASON_LOST)

    def _on_connected(self):
        cfg = self._cfg
        client = self._client
        present = self._present()
        try:
            client.subscribe(entities.birth_topic(cfg), 1)
            for e in present:
                if entities.needs_commands(e):
                    client.subscribe(entities.command_topic(cfg, e), 1)
        except Exception:
            logger.warning('Home Assistant MQTT subscribe failed')
        self._publish_all_config(present)
        self._last_payloads = {}
        self._avail_published = None
        self._update_availability(self._clock(), force=True)

    def _handle_birth(self, payload):
        if not self._connected or bytes(payload).strip() != b'online':
            return
        logger.info('Home Assistant is online, republishing discovery')
        self._publish_all_config(self._present())
        self._last_payloads = {}
        self._update_availability(self._clock(), force=True)

    # -- publishing

    def _publish(self, topic, payload, qos, retain):
        if not self._connected or self._client is None:
            return False
        try:
            self._client.publish(topic, payload, qos=qos, retain=retain)
        except Exception:
            logger.warning('Home Assistant MQTT publish failed')
            return False
        self._set_status(last_publish=self._wall())
        return True

    def _publish_all_config(self, present):
        cfg = self._cfg
        if 'burner_connection' not in self._keys():
            self._set_status(entities=len(self._config_topics))
            return
        self._present_ids = tuple(e.object_id for e in present)
        msgs = entities.discovery_messages(cfg, present, bool(cfg.get('allow_commands')),
                                           self._db, self._sw_version)
        for topic, payload in msgs:
            if self._publish(topic, payload, 1, True):
                if payload:
                    self._config_topics.add(topic)
                else:
                    self._config_topics.discard(topic)
        self._set_status(entities=len(self._config_topics),
                         commands_enabled=bool(cfg.get('allow_commands')))

    def _update_availability(self, now, force=False):
        snap = self._read_all()
        burner = self._burner(snap)
        avail = 'online' if burner == 'connected' else 'offline'
        self._set_status(burner=burner, availability=avail)
        if not self._connected:
            return snap, avail
        if force or avail != self._avail_published:
            if self._publish(entities.availability_topic(self._cfg), avail, 1, True):
                self._avail_published = avail
                if avail == 'online':
                    self._state_due = now + self._settle
                    self._last_payloads = {}
                else:
                    self._state_due = None
        return snap, avail

    def _state_value(self, entity, snap):
        v = snap.get(entity.item)
        return None if v is None else str(v)

    def _publish_states(self, snap, force=False, only=None):
        cfg = self._cfg
        for e in self._present():
            if e.component not in ('sensor', 'number'):
                continue
            if only is not None and e.item not in only:
                continue
            value = self._state_value(e, snap)
            if value is None:
                continue
            self._publish_state(e, value, force)

    def _publish_state(self, entity, value, force=False):
        topic = entities.state_topic(self._cfg, entity)
        if not force and self._last_payloads.get(topic) == value:
            return
        if self._publish(topic, value, 0, False):
            self._last_payloads[topic] = value

    def _handle_changes(self, changed):
        if not self._connected or self._avail_published != 'online' or self._state_due is not None:
            return
        by_item = {}
        for p in changed:
            try:
                by_item[p['name']] = str(p['value'])
            except (KeyError, TypeError):
                continue
        for e in self._present():
            if e.component in ('sensor', 'number') and e.item in by_item:
                self._publish_state(e, by_item[e.item])

    def tick(self):
        if not self._enabled():
            return
        now = self._clock()
        if self._client is None:
            if self._retry_at is not None and now >= self._retry_at:
                self._connect()
            return
        if not self._connected:
            return
        snap, avail = self._update_availability(now)
        if avail != 'online' or self._avail_published != 'online':
            return
        present = self._present()
        ids = tuple(e.object_id for e in present)
        if ids != self._present_ids:
            self._resubscribe(present)
            self._publish_all_config(present)
            self._state_due = now + self._settle
        if self._state_due is not None:
            if now >= self._state_due:
                self._publish_states(snap)
                self._state_due = None
                self._last_refresh = now
            return
        if self._last_refresh is None or now - self._last_refresh >= self._cfg['refresh']:
            self._publish_states(snap, force=True)
            self._last_refresh = now

    def _resubscribe(self, present):
        try:
            for e in present:
                if entities.needs_commands(e):
                    self._client.subscribe(entities.command_topic(self._cfg, e), 1)
        except Exception:
            logger.warning('Home Assistant MQTT subscribe failed')

    # -- configuration

    def _remove_stale_config(self, new):
        """Empty retained payloads for config topics the new settings no longer publish"""
        if not (new.get('enabled') and new.get('host')):
            return
        desired = set()
        if 'burner_connection' in self._keys():
            for topic, payload in entities.discovery_messages(
                    new, self._present(), bool(new.get('allow_commands')), self._db,
                    self._sw_version):
                if payload:
                    desired.add(topic)
        for topic in sorted(self._config_topics - desired):
            if self._publish(topic, '', 1, True):
                self._config_topics.discard(topic)

    def _apply(self, cfg, password):
        new = settings.effective(cfg)
        if self._client is not None and self._connected:
            self._remove_stale_config(new)
        # retained 'offline' goes to the old availability topic (self._cfg is still the old one)
        self._teardown(offline=True)
        self._cfg = new
        self._password = password or ''
        self._retry_delay = 1
        self._retry_at = None
        self._avail_published = None
        self._state_due = None
        self._last_refresh = None
        self._last_payloads = {}
        self._present_ids = None
        self._set_status(host=self._cfg.get('host', ''), port=self._cfg.get('port', 0),
                         commands_enabled=bool(self._cfg.get('allow_commands')),
                         reason='', entities=len(self._config_topics))
        if self._enabled():
            self._connect()
        else:
            self._set_status(state='off')

    def _teardown(self, offline):
        client = self._client
        if client is None:
            return
        try:
            if self._connected and offline:
                try:
                    info = client.publish(entities.availability_topic(self._cfg), 'offline',
                                          qos=1, retain=True)
                    info.wait_for_publish(timeout=2)
                except Exception:
                    logger.warning('Home Assistant offline publish failed')
            client.disconnect()
            client.loop_stop()
        except Exception:
            logger.warning('Home Assistant MQTT disconnect failed')
        self._client = None
        self._connected = False

    def _drain_commands(self):
        while True:
            try:
                item = self._cmdq.get_nowait()
            except queue.Empty:
                break
            self._handle_command(*item)

    def _log_command(self, level, topic, item, raw, result):
        text = repr(raw)[:CMD_PAYLOAD_MAX] if raw is not None else "''"
        logger.log(level, 'Home Assistant command %s item=%s value=%s result=%s',
                   topic, item, text, result)

    def _handle_command(self, topic, payload, retain):
        cfg = self._cfg
        now = self._clock()
        if cfg is None:
            return
        # commands off: dropped here (explicit /set topics are always subscribed, D-06)
        if not cfg.get('allow_commands'):
            last = self._off_logged.get(topic)
            if last is None or now - last >= CMD_OFF_LOG_INTERVAL:
                self._off_logged[topic] = now
                logger.warning('Home Assistant command %s ignored: commands are disabled', topic)
            else:
                logger.debug('Home Assistant command %s ignored: commands are disabled', topic)
            return
        warn = logging.WARNING
        if retain:
            self._log_command(warn, topic, None, None, 'ignored (retained)')
            return
        if len(payload) > CMD_PAYLOAD_MAX:
            self._log_command(warn, topic, None, payload[:CMD_PAYLOAD_MAX], 'ignored (payload too long)')
            return
        try:
            raw = payload.decode('utf-8')
        except UnicodeDecodeError:
            self._log_command(warn, topic, None, payload, 'ignored (not UTF-8)')
            return
        head = cfg['prefix'] + '/'
        if not (topic.startswith(head) and topic.endswith('/set')):
            self._log_command(warn, topic, None, raw, 'ignored (unknown topic)')
            return
        entity = entities.entity_by_object_id(topic[len(head):-len('/set')])
        if entity is None or not entities.needs_commands(entity):
            self._log_command(warn, topic, None, raw, 'ignored (unknown entity)')
            return
        item = entity.item
        if item not in self._keys():
            self._log_command(warn, topic, item, raw, 'ignored (item not available)')
            return

        if entity.component == 'button':
            if raw != 'PRESS':
                self._log_command(warn, topic, item, raw, 'rejected')
                return
            value = '0'
        else:
            value = self._number(entity, raw)
            if value is None:
                self._log_command(warn, topic, item, raw, 'rejected')
                self._readback(entity)
                return

        limited = self._rate_limited(item, value, now)
        if limited:
            self._log_command(warn, topic, item, raw, limited)
            if entity.component == 'number':
                self._readback(entity)
            return

        try:
            self._db.set_value(item, value)
        except ValueError:
            self._log_command(warn, topic, item, raw, 'rejected')
        except Exception:
            self._log_command(warn, topic, item, raw, 'failed')
        else:
            self._log_command(logging.INFO, topic, item, raw, 'accepted')
        if entity.component == 'number':
            self._readback(entity)

    def _number(self, entity, raw):
        """Validated value as a string, or None"""
        text = raw.strip()
        if not _INT_RE.fullmatch(text):
            return None
        val = int(float(text))
        lo, hi = entities.effective_range(entity, self._db.get(entity.item))
        if val < lo or val > hi:
            return None
        if entity.item in ('min_power', 'max_power'):
            snap = self._read_all()
            other = snap.get('max_power' if entity.item == 'min_power' else 'min_power')
            try:
                other = float(other)
            except (TypeError, ValueError):
                other = None
            if other is not None:
                if entity.item == 'min_power' and val > other:
                    return None
                if entity.item == 'max_power' and val < other:
                    return None
        return str(val)

    def _rate_limited(self, item, value, now):
        last = self._last_write.get(item)
        if last is not None:
            if last[1] == value and now - last[0] < CMD_DEDUPE_SECONDS:
                return 'ignored (duplicate)'
            if now - last[0] < CMD_ITEM_INTERVAL:
                return 'ignored (rate limited)'
        self._write_times = [t for t in self._write_times if now - t < 60]
        if len(self._write_times) >= CMD_GLOBAL_PER_MINUTE:
            return 'ignored (rate limited)'
        self._last_write[item] = (now, value)
        self._write_times.append(now)
        return None

    def _readback(self, entity):
        try:
            text = self._db.get_text(entity.item)
        except Exception:
            return
        if self._connected:
            self._publish_state(entity, str(text), force=True)
