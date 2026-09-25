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


# ---- commands from Home Assistant (D-06..D-09) --------------------------

import logging  # noqa: E402


def _cmd(env, obj, payload, retain=False):
    env.client.fire_message('scotte/%s/set' % obj, payload, retain=retain)
    env.bridge.handle_all()


def _cmd_env(**over):
    e = make_env()
    e.connect(allow_commands=True, **over)
    e.settle()
    return e


def _cmd_records(caplog):
    return [r for r in caplog.records if 'Home Assistant command' in r.getMessage()]


def _disabled_warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING
            and 'commands are disabled' in r.getMessage()]


@pytest.mark.parametrize('commands', [True, False])
def test_subscriptions_explicit_topics_regardless_of_commands(commands):
    e = make_env()
    e.connect(allow_commands=commands)
    topics = [t for t, q in e.client.subscriptions]
    sets = sorted(t for t in topics if t.endswith('/set'))
    present = entities.present_entities(e.db.keys())
    want = sorted('scotte/%s/set' % x.object_id for x in present if entities.needs_commands(x))
    assert sets == want and len(sets) == 12
    assert all(q == 1 for t, q in e.client.subscriptions)
    assert not [t for t in topics if '#' in t or '+' in t]
    assert not [t for t in topics if 'burner_on' in t or 'burner_off' in t]


def test_commands_off_drops_with_one_warning(caplog):
    e = make_env()
    e.connect()
    e.settle()
    caplog.set_level(logging.DEBUG, logger='pellMon')
    n = len(e.client.published)
    _cmd(e, 'boiler_temp_set', '60')
    assert e.db.writes == []
    assert len(e.client.published) == n
    warns = _disabled_warnings(caplog)
    assert len(warns) == 1 and 'scotte/boiler_temp_set/set' in warns[0].getMessage()
    _cmd(e, 'boiler_temp_set', '61')
    assert len(_disabled_warnings(caplog)) == 1
    e.clock.advance(61)
    _cmd(e, 'boiler_temp_set', '62')
    assert len(_disabled_warnings(caplog)) == 2
    assert e.db.writes == []


def test_toggle_commands_via_reconfigure():
    e = make_env()
    e.connect()
    _cmd(e, 'boiler_temp_set', '60')
    assert e.db.writes == []
    e.connect(allow_commands=True)
    _cmd(e, 'boiler_temp_set', '60')
    assert e.db.writes == [('boiler_temp_set', '60')]
    e.connect(allow_commands=False)
    _cmd(e, 'boiler_temp_min', '20')
    assert e.db.writes == [('boiler_temp_set', '60')]


def test_retained_ignored(caplog):
    e = _cmd_env()
    _cmd(e, 'boiler_temp_set', '60', retain=True)
    assert e.db.writes == []
    assert 'retained' in _cmd_records(caplog)[-1].getMessage()


def test_bad_payloads_and_entities_ignored():
    e = _cmd_env()
    _cmd(e, 'boiler_temp_set', '6' * 40)
    e.client.fire_message('scotte/boiler_temp_set/set', b'\xff\xfe')
    e.bridge.handle_all()
    _cmd(e, 'no_such_entity', '60')
    _cmd(e, 'burner_on', 'PRESS')
    _cmd(e, 'burner_off', 'PRESS')
    _cmd(e, 'power_percent', '60')
    assert e.db.writes == []
    e2 = make_env(FakeDb.make_scotte_db(exclude=('chimney_draught',)))
    e2.connect(allow_commands=True)
    _cmd(e2, 'chimney_draught', '5')
    assert e2.db.writes == []


def test_number_accept_and_readback():
    e = _cmd_env()
    _cmd(e, 'boiler_temp_set', '60')
    assert e.db.writes == [('boiler_temp_set', '60')]
    assert e.client.published_to('scotte/boiler_temp_set/state')[-1] == ('60', 0, False)
    e.clock.advance(10)
    _cmd(e, 'boiler_temp_set', '61.0')
    assert e.db.writes[-1] == ('boiler_temp_set', '61')


@pytest.mark.parametrize('payload', ['60.5', 'nan', 'inf', 'abc', '39', '86', '', '1e2'])
def test_number_rejected_and_snapped_back(payload):
    e = _cmd_env()
    before = len(e.client.published_to('scotte/boiler_temp_set/state'))
    _cmd(e, 'boiler_temp_set', payload)
    assert e.db.writes == []
    published = e.client.published_to('scotte/boiler_temp_set/state')
    assert len(published) == before + 1 and published[-1][0] == '65'


def test_item_range_intersection():
    e = _cmd_env()
    e.db['boiler_temp_set'].min = '45'
    _cmd(e, 'boiler_temp_set', '44')
    assert e.db.writes == []
    _cmd(e, 'boiler_temp_set', '45')
    assert e.db.writes == [('boiler_temp_set', '45')]


def test_min_max_power_cross_check():
    e = _cmd_env()
    e.db['max_power'].value = '50'
    _cmd(e, 'min_power', '60')
    assert e.db.writes == []
    _cmd(e, 'min_power', '40')
    assert e.db.writes == [('min_power', '40')]
    e.clock.advance(10)
    _cmd(e, 'max_power', '30')
    assert e.db.writes == [('min_power', '40')]


def test_button_press():
    e = _cmd_env()
    _cmd(e, 'reset_alarm', 'press')
    _cmd(e, 'reset_alarm', 'anything')
    assert e.db.writes == []
    _cmd(e, 'reset_alarm', 'PRESS')
    assert e.db.writes == [('reset_alarm', '0')]


@pytest.mark.parametrize('exc,result', [
    (ValueError('bad'), 'rejected'),
    (IOError('serial'), 'failed'),
])
def test_write_failures_logged_and_readback(caplog, exc, result):
    e = _cmd_env()
    e.db.fail['boiler_temp_set'] = exc
    caplog.set_level(logging.DEBUG, logger='pellMon')
    _cmd(e, 'boiler_temp_set', '60')
    rec = _cmd_records(caplog)[-1]
    assert rec.levelno == logging.WARNING and 'result=%s' % result in rec.getMessage()
    assert e.client.published_to('scotte/boiler_temp_set/state')[-1][0] == '65'


def test_one_log_line_per_command_and_no_password(caplog):
    e = _cmd_env()
    caplog.set_level(logging.DEBUG, logger='pellMon')
    _cmd(e, 'boiler_temp_set', '60')
    _cmd(e, 'boiler_temp_set', '999')
    recs = _cmd_records(caplog)
    assert len(recs) == 2
    m = recs[0].getMessage()
    assert 'scotte/boiler_temp_set/set' in m and 'item=boiler_temp_set' in m
    assert "value='60'" in m and 'result=accepted' in m
    assert 'result=rejected' in recs[1].getMessage()
    assert PASSWORD_SENTINEL not in caplog.text


def test_rate_limits():
    e = _cmd_env()
    _cmd(e, 'boiler_temp_set', '60')
    _cmd(e, 'boiler_temp_set', '60')          # duplicate within 2 s
    e.clock.advance(3)
    _cmd(e, 'boiler_temp_set', '61')          # same item within 5 s
    assert e.db.writes == [('boiler_temp_set', '60')]
    e.clock.advance(3)
    _cmd(e, 'boiler_temp_set', '61')
    assert e.db.writes[-1] == ('boiler_temp_set', '61')
    # global limit: 10 writes per minute
    e2 = _cmd_env()
    names = ['boiler_temp_set', 'boiler_temp_min', 'boiler_diff_down', 'boiler_diff_up',
             'chimney_draught', 'cleaning_interval', 'cleaning_time', 'feeder_capacity',
             'min_power', 'max_power']
    values = ['60', '20', '5', '3', '2', '30', '10', '1000', '20', '90']
    for n, v in zip(names, values):
        _cmd(e2, n, v)
    assert len(e2.db.writes) == 10
    _cmd(e2, 'reset_alarm', 'PRESS')
    assert len(e2.db.writes) == 10
    e2.clock.advance(61)
    _cmd(e2, 'reset_alarm', 'PRESS')
    assert len(e2.db.writes) == 11


def test_command_queue_bounded(caplog):
    e = _cmd_env()
    caplog.set_level(logging.DEBUG, logger='pellMon')
    for i in range(25):
        e.client.fire_message('scotte/boiler_temp_set/set', str(50 + i))
    assert e.db.writes == []
    assert [r for r in caplog.records if 'queue full' in r.getMessage()]
    e.bridge.handle_all()
    assert len(e.db.writes) <= bridge_module.CMD_GLOBAL_PER_MINUTE


def test_on_message_makes_no_db_call():
    e = _cmd_env()
    e.client.fire_message('scotte/boiler_temp_set/set', '60')
    assert e.db.writes == []
    e.bridge.handle_all()
    assert e.db.writes == [('boiler_temp_set', '60')]
