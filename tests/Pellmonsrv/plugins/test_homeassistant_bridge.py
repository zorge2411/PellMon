# -*- coding: utf-8 -*-
"""Bridge behaviour against the in-memory fakes (D-04..D-19)."""

import json
import socket
import ssl

import pytest

from fake_mqtt import FakeClientFactory, FakeDb, FakeItem
from Pellmonsrv.plugins.homeassistant import bridge as bridge_module
from Pellmonsrv.plugins.homeassistant import entities
from Pellmonsrv.plugins.homeassistant.bridge import Bridge

PASSWORD_SENTINEL = 'S3cretSentinelPw'

CFG = {'enabled': True, 'host': 'broker.local', 'port': 1883, 'username': 'user',
       'tls': False, 'tls_verify': True, 'prefix': 'scotte',
       'discovery_prefix': 'homeassistant', 'device_id': 'dev1',
       'device_name': 'Dev', 'node_id': '', 'uid_prefix': '',
       'allow_commands': False, 'refresh': 60}


class ManualClock(object):
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class Env(object):
    def __init__(self, db, factory, clock, bridge):
        self.db = db
        self.factory = factory
        self.clock = clock
        self.bridge = bridge

    @property
    def client(self):
        return self.factory.last

    def configure(self, **over):
        cfg = dict(CFG)
        cfg.update(over)
        self.bridge.reconfigure(cfg, PASSWORD_SENTINEL)
        self.bridge.handle_all()

    def connect(self, **over):
        self.configure(**over)
        self.client.fire_connect(0)
        self.bridge.handle_all()

    def settle(self):
        self.clock.advance(2.5)
        self.bridge.tick()

    def states(self):
        return dict((t, p) for (t, p, q, r) in self.client.published if t.endswith('/state'))


def make_env(db=None):
    db = db if db is not None else FakeDb.make_scotte_db()
    factory = FakeClientFactory()
    clock = ManualClock()
    wall = ManualClock()
    wall.now = 5000.0
    b = Bridge(db, factory, snapshot=db.snapshot, clock=clock, wall_clock=wall)
    e = Env(db, factory, clock, b)
    e.wall = wall
    return e


@pytest.fixture
def env():
    return make_env()


def test_no_socket_and_lazy_paho_import():
    src = open(bridge_module.__file__, encoding='utf-8').read()
    for line in src.splitlines():
        assert not line.startswith('import paho') and not line.startswith('from paho')
    assert 'CallbackAPIVersion.VERSION2' in src
    assert 'threading.Timer' not in src and 'enable_logger' not in src


def test_reconfigure_creates_client_and_connects(env):
    env.configure()
    assert len(env.factory.calls) == 1
    call = env.factory.calls[0]
    assert call['client_id'] == 'pellmon-dev1'
    assert call['will_topic'] == 'scotte/status'
    assert call['password'] == PASSWORD_SENTINEL
    assert env.client.connect_calls == [('broker.local', 1883, 60)]
    assert env.client.loop_started
    assert env.bridge.status_dict()['state'] == 'connecting'


def test_disabled_creates_no_client_and_stops_running_client(env):
    env.configure(enabled=False)
    assert env.factory.clients == []
    assert env.bridge.status_dict()['state'] == 'off'
    env.connect()
    client = env.client
    env.configure(enabled=False)
    assert (('scotte/status', 'offline', 1, True)) in client.published
    assert client.disconnect_calls == 1
    assert client.loop_stopped
    assert env.bridge.status_dict()['state'] == 'off'


@pytest.mark.parametrize('exc,reason', [
    (ConnectionRefusedError(), 'connection refused'),
    (socket.gaierror(), 'host not found'),
    (TimeoutError(), 'timed out'),
    (ssl.SSLCertVerificationError(), 'certificate could not be verified'),
    (ssl.SSLError(), 'TLS handshake failed'),
])
def test_connect_errors_map_and_retry_with_backoff(exc, reason):
    env = make_env()
    env.factory.connect_error = exc
    env.configure()
    st = env.bridge.status_dict()
    assert st['state'] == 'disconnected' and st['reason'] == reason
    assert len(env.factory.calls) == 1
    # back-off 1, 2, 4 ... 60
    delays = [1, 2, 4, 8, 16, 32, 60, 60]
    calls = 1
    for d in delays:
        env.clock.advance(d - 0.5)
        env.bridge.tick()
        assert len(env.factory.calls) == calls
        env.clock.advance(0.5)
        env.bridge.tick()
        calls += 1
        assert len(env.factory.calls) == calls


def test_connack_refusals():
    for code, reason in ((134, 'wrong username or password'), (135, 'not authorised')):
        env = make_env()
        env.configure()
        env.client.fire_connect(code)
        env.bridge.handle_all()
        st = env.bridge.status_dict()
        assert st['state'] == 'disconnected' and st['reason'] == reason


def test_on_connect_subscribes_and_publishes_discovery(env):
    env.connect()
    c = env.client
    subs = dict(c.subscriptions)
    assert subs['homeassistant/status'] == 1
    present = entities.present_entities(env.db.keys())
    cmd = [e for e in present if entities.needs_commands(e)]
    assert len(cmd) == 12
    for e in cmd:
        assert subs['scotte/%s/set' % e.object_id] == 1
    assert 'scotte/burner_on/set' not in subs and 'scotte/burner_off/set' not in subs
    assert c.published_to('scotte/status') == [('online', 1, True)]
    msgs = entities.discovery_messages(bridge_module.settings.effective(CFG), present,
                                       False, env.db, '_dev_')
    for topic, payload in msgs:
        assert c.published_to(topic) == [(payload, 1, True)]
    assert env.states() == {}


def test_qos_and_retain_rules(env):
    env.connect()
    env.settle()
    for topic, payload, qos, retain in env.client.published:
        if topic.endswith('/state'):
            assert (qos, retain) == (0, False)
        elif topic.endswith('/config') or topic.endswith('/status'):
            assert (qos, retain) == (1, True)


def test_states_after_settle(env):
    env.connect()
    env.bridge.tick()
    assert env.states() == {}
    env.settle()
    states = env.states()
    assert states['scotte/power_percent/state'] == '64'
    assert states['scotte/boiler_temp/state'] == '56.9'
    assert states['scotte/boiler_temp_set/state'] == '65'
    assert states['scotte/mode/state'] == 'Running'
    assert 'scotte/reset_alarm/state' not in states
    assert len(states) == 9 + 10


def test_availability_follows_burner_connection(env):
    env.connect()
    env.settle()
    c = env.client
    env.db['burner_connection'].value = 'no_connection'
    n = len(c.published)
    env.bridge.tick()
    assert c.published[n:] == [('scotte/status', 'offline', 1, True)]
    env.bridge.tick()
    env.settle()
    assert len(c.published) == n + 1
    assert env.bridge.status_dict()['availability'] == 'offline'
    env.db['burner_connection'].value = 'connected'
    env.bridge.tick()
    assert c.last_payload('scotte/status') == 'online'
    before = len([1 for p in c.published if p[0].endswith('/state')])
    env.settle()
    assert len([1 for p in c.published if p[0].endswith('/state')]) > before


def test_demo_and_missing_burner_item():
    env = make_env()
    env.connect()
    env.db['burner_connection'].value = 'demo'
    env.bridge.tick()
    assert env.client.last_payload('scotte/status') == 'offline'
    assert env.bridge.status_dict()['burner'] == 'demo'
    env.settle()
    assert env.states() == {}

    env = make_env(FakeDb.make_scotte_db(exclude=('burner_connection',)))
    env.connect()
    assert env.client.last_payload('scotte/status') == 'offline'
    assert env.bridge.status_dict()['burner'] == 'unsupported'
    assert not [t for t, p, q, r in env.client.published if t.endswith('/config')]


def test_change_publishes_once_and_dedupes(env):
    env.connect()
    env.settle()
    c = env.client
    n = len(c.published)
    env.bridge.on_changes([{'name': 'boiler_temp', 'value': '57'}])
    env.bridge.handle_all()
    assert c.published[n:] == [('scotte/boiler_temp/state', '57', 0, False)]
    env.bridge.on_changes([{'name': 'boiler_temp', 'value': '57'}])
    env.bridge.handle_all()
    assert len(c.published) == n + 1
    env.bridge.on_changes([{'name': 'burner_on', 'value': '1'}, {'name': 'nonsense', 'value': '2'}])
    env.bridge.handle_all()
    assert len(c.published) == n + 1


def test_refresh_republishes_everything(env):
    env.connect()
    env.settle()
    c = env.client
    n = len([1 for p in c.published if p[0].endswith('/state')])
    env.clock.advance(30)
    env.bridge.tick()
    assert len([1 for p in c.published if p[0].endswith('/state')]) == n
    env.clock.advance(31)
    env.bridge.tick()
    assert len([1 for p in c.published if p[0].endswith('/state')]) == n * 2


def test_missing_items_not_published():
    env = make_env(FakeDb.make_scotte_db(exclude=('chimney_draught',)))
    env.connect()
    env.settle()
    assert not [t for t, p, q, r in env.client.published if 'chimney_draught' in t and p != '']
    assert not [t for t, p, q, r in env.client.published if 'chimney_draught' in t]


def test_present_set_change_republishes_discovery(env):
    env.connect()
    env.settle()
    c = env.client
    topic = 'homeassistant/number/dev1/chimney_draught/config'
    del env.db._items['chimney_draught']
    env.bridge.tick()
    env.bridge.tick()
    n = len(c.published_to(topic))
    env.db.add(FakeItem('chimney_draught', '2', min='0', max='10'))
    env.bridge.tick()
    assert len(c.published_to(topic)) == n + 1


def test_birth_republishes_and_offline_ignored(env):
    env.connect()
    env.settle()
    c = env.client
    n = len(c.published)
    c.fire_message('homeassistant/status', 'offline')
    env.bridge.handle_all()
    assert len(c.published) == n
    c.fire_message('homeassistant/status', 'online')
    env.bridge.handle_all()
    assert c.last_payload('scotte/status') == 'online'
    assert len(c.published) > n
    m = len(c.published)
    env.settle()
    assert len(c.published) > m


def test_disconnect_status_and_callbacks_only_enqueue(env):
    env.connect()
    env.settle()
    c = env.client
    n = len(c.published)
    c.fire_disconnect(7)
    assert len(c.published) == n
    assert env.bridge.status_dict()['state'] == 'connected'
    env.bridge.handle_all()
    st = env.bridge.status_dict()
    assert st['state'] == 'disconnected' and st['reason'] == 'connection lost'


def test_no_publish_while_disconnected(env):
    env.connect()
    env.settle()
    c = env.client
    c.fire_disconnect(7)
    env.bridge.handle_all()
    n = len(c.published)
    env.db['burner_connection'].value = 'no_connection'
    env.bridge.tick()
    env.bridge.on_changes([{'name': 'boiler_temp', 'value': '1'}])
    env.bridge.handle_all()
    env.clock.advance(100)
    env.bridge.tick()
    assert len(c.published) == n


def test_shutdown(env):
    env.connect()
    c = env.client
    waits = []

    class Info(object):
        def wait_for_publish(self, timeout=None):
            waits.append(timeout)

    orig = c.publish
    c.publish = lambda *a, **k: (orig(*a, **k), Info())[1]
    env.bridge.shutdown()
    assert c.published_to('scotte/status')[-1] == ('offline', 1, True)
    assert waits == [2]
    assert c.disconnect_calls == 1 and c.loop_stopped
    env.bridge.shutdown()
    assert c.disconnect_calls == 1


def test_shutdown_without_client_is_noop(env):
    env.bridge.shutdown()
    env.bridge.shutdown()
    assert env.factory.clients == []


def test_status_dict(env):
    st = env.bridge.status_dict()
    assert 'password' not in json.dumps(st).lower()
    env.connect()
    assert env.bridge.status_dict()['last_connect'] == 5000.0
    env.wall.advance(7)
    env.settle()
    st = env.bridge.status_dict()
    assert st['last_publish'] == 5007.0
    assert st['entities'] == len([1 for t, p, q, r in env.client.published
                                  if t.endswith('/config') and p])
    assert st['entities'] == 9
    assert st['availability'] == 'online' and st['burner'] == 'connected'
    assert PASSWORD_SENTINEL not in json.dumps(st)
