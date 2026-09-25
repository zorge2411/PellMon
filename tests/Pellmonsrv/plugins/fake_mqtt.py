"""In-memory test doubles for the Home Assistant MQTT bridge tests.

FakeMqttClient mirrors the paho-mqtt 2.1 (CallbackAPIVersion.VERSION2) surface the
bridge uses, so tests never open a socket. FakeDb mimics the burner item database.
"""

_REASON_NAMES = {
    0: 'Success',
    128: 'Unspecified error',
    134: 'Bad user name or password',
    135: 'Not authorized',
}


class FakeReasonCode(object):
    def __init__(self, value=0):
        self.value = value

    @property
    def is_failure(self):
        return self.value >= 128 or self.value not in (0,)

    def __eq__(self, other):
        if isinstance(other, FakeReasonCode):
            return self.value == other.value
        return self.value == other

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.value)

    def __str__(self):
        return _REASON_NAMES.get(self.value, 'Reason code %d' % self.value)


class FakeMessage(object):
    def __init__(self, topic, payload, retain=False, qos=0):
        if not isinstance(payload, bytes):
            payload = str(payload).encode('utf-8')
        self.topic = topic
        self.payload = payload
        self.retain = retain
        self.qos = qos


class FakeMessageInfo(object):
    def __init__(self, mid):
        self.rc = 0
        self.mid = mid

    def wait_for_publish(self, timeout=None):
        return None

    def is_published(self):
        return True


class FakeMqttClient(object):
    def __init__(self, client_id='', auto_connect=None, connect_error=None):
        self.client_id = client_id
        self.auto_connect = auto_connect
        self.connect_error = connect_error
        self.will = None
        self.username = None
        self.password = None
        self.tls = None
        self.tls_insecure = False
        self.reconnect_delay = None
        self.max_queued = None
        self.connect_timeout = None
        self.published = []
        self.subscriptions = []
        self.unsubscriptions = []
        self.connect_calls = []
        self.loop_started = False
        self.loop_stopped = False
        self.disconnect_calls = 0
        self.connected = False
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self._mid = 0

    def _next_mid(self):
        self._mid += 1
        return self._mid

    def will_set(self, topic, payload=None, qos=0, retain=False):
        self.will = (topic, payload, qos, retain)

    def username_pw_set(self, username, password=None):
        self.username = username
        self.password = password

    def tls_set(self, **kwargs):
        self.tls = dict(kwargs)

    def tls_insecure_set(self, flag):
        self.tls_insecure = bool(flag)

    def reconnect_delay_set(self, min_delay=1, max_delay=120):
        self.reconnect_delay = (min_delay, max_delay)

    def max_queued_messages_set(self, n):
        self.max_queued = n

    def connect(self, host, port=1883, keepalive=60):
        self.connect_calls.append((host, port, keepalive))
        if self.connect_error is not None:
            raise self.connect_error
        return 0

    def connect_async(self, host, port=1883, keepalive=60):
        return self.connect(host, port, keepalive)

    def loop_start(self):
        self.loop_started = True
        if self.auto_connect is not None:
            self.fire_connect(self.auto_connect)

    def loop_stop(self):
        self.loop_stopped = True

    def disconnect(self):
        self.disconnect_calls += 1
        self.connected = False
        return 0

    def reconnect(self):
        return 0

    def is_connected(self):
        return self.connected

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return FakeMessageInfo(self._next_mid())

    def subscribe(self, topic, qos=0):
        self.subscriptions.append((topic, qos))
        return (0, self._next_mid())

    def unsubscribe(self, topic):
        self.unsubscriptions.append(topic)
        return (0, self._next_mid())

    # test helpers
    def fire_connect(self, reason=0):
        rc = FakeReasonCode(reason)
        if not rc.is_failure:
            self.connected = True
        if self.on_connect:
            self.on_connect(self, None, {}, rc, None)

    def fire_disconnect(self, reason=0):
        self.connected = False
        if self.on_disconnect:
            self.on_disconnect(self, None, {}, FakeReasonCode(reason), None)

    def fire_message(self, topic, payload, retain=False, qos=0):
        if self.on_message:
            self.on_message(self, None, FakeMessage(topic, payload, retain, qos))

    def published_to(self, topic):
        return [(p, q, r) for (t, p, q, r) in self.published if t == topic]

    def last_payload(self, topic):
        items = self.published_to(topic)
        return items[-1][0] if items else None


class FakeClientFactory(object):
    def __init__(self, auto_connect=None, connect_error=None):
        self.auto_connect = auto_connect
        self.connect_error = connect_error
        self.calls = []
        self.clients = []

    def __call__(self, cfg, password, client_id, will_topic, on_connect, on_disconnect, on_message):
        self.calls.append({'cfg': cfg, 'password': password,
                           'client_id': client_id, 'will_topic': will_topic})
        client = FakeMqttClient(client_id, self.auto_connect, self.connect_error)
        if will_topic is not None:
            client.will_set(will_topic, 'offline', qos=1, retain=True)
        if cfg.get('username'):
            client.username_pw_set(cfg['username'], password)
        if cfg.get('tls'):
            client.tls_set()
            client.tls_insecure_set(bool(cfg.get('tls_insecure')))
        client.reconnect_delay_set(1, 60)
        client.max_queued_messages_set(200)
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        self.clients.append(client)
        return client

    @property
    def last(self):
        return self.clients[-1] if self.clients else None


class FakeItem(object):
    def __init__(self, name, value, min=None, max=None):
        self.name = name
        self.value = value
        if min is not None:
            self.min = min
        if max is not None:
            self.max = max


class FakeDb(object):
    def __init__(self):
        self._items = {}
        self.writes = []
        self.fail = {}
        self.listeners = []

    def add(self, item):
        self._items[item.name] = item
        return item

    def keys(self):
        return list(self._items.keys())

    def items(self):
        return list(self._items.items())

    def __contains__(self, name):
        return name in self._items

    def __getitem__(self, name):
        return self._items[name]

    def __iter__(self):
        return iter(self._items)

    def get(self, name, default=None):
        return self._items.get(name, default)

    def get_text(self, name):
        return str(self._items[name].value)

    def set_value(self, name, value):
        if name in self.fail:
            raise self.fail[name]
        self.writes.append((name, value))
        self._items[name].value = value
        return 'OK'

    def snapshot(self):
        return dict((n, str(i.value)) for n, i in self._items.items())

    def add_change_listener(self, cb):
        self.listeners.append(cb)

    @classmethod
    def make_scotte_db(cls, exclude=()):
        db = cls()
        sensors = [('power', '64'), ('power_kW', '6.8'), ('boiler_temp', '56.9'),
                   ('chute_temp', '31.2'), ('smoke_temp', '148.0'), ('oxygen', '9.8'),
                   ('light', '120'), ('feeder_time', '3.2'), ('mode', 'Running')]
        numbers = [('boiler_temp_set', '40', '85', '65'), ('boiler_temp_min', '10', '70', '50'),
                   ('boiler_temp_diff_down', '0', '20', '5'), ('boiler_temp_diff_up', '0', '15', '3'),
                   ('chimney_draught', '0', '10', '2'), ('cleaning_interval', '1', '120', '30'),
                   ('cleaning_time', '0', '60', '10'), ('feeder_capacity', '400', '8000', '2000'),
                   ('min_power', '10', '100', '20'), ('max_power', '10', '100', '100')]
        commands = ['reset_alarm', 'reset_ignition', 'burner_on', 'burner_off']
        for name, value in sensors:
            if name not in exclude:
                db.add(FakeItem(name, value))
        for name, lo, hi, value in numbers:
            if name not in exclude:
                db.add(FakeItem(name, value, min=lo, max=hi))
        for name in commands:
            if name not in exclude:
                db.add(FakeItem(name, '0'))
        if 'burner_connection' not in exclude:
            db.add(FakeItem('burner_connection', 'connected'))
        return db
