"""Self-tests for the in-memory MQTT client and burner database fakes.

No sockets are opened; pytest runs with --disable-socket.
"""
import pytest

from fake_mqtt import FakeMqttClient, FakeClientFactory, FakeDb, FakeReasonCode


def test_publish_records_and_returns_immediate_info():
    c = FakeMqttClient()
    info = c.publish("a/b", "42", qos=1, retain=True)
    assert c.published == [("a/b", "42", 1, True)]
    assert info.wait_for_publish() is None or info.is_published()
    assert info.is_published() is True
    assert c.published_to("a/b") == [("42", 1, True)]
    assert c.last_payload("a/b") == "42"


def test_fire_connect_calls_on_connect_with_five_args():
    c = FakeMqttClient()
    seen = []
    c.on_connect = lambda *args: seen.append(args)
    c.fire_connect(0)
    assert len(seen) == 1 and len(seen[0]) == 5
    rc = seen[0][3]
    assert rc.value == 0 and rc.is_failure is False
    assert c.connected is True


def test_fire_connect_failure_reason():
    c = FakeMqttClient()
    seen = []
    c.on_connect = lambda *args: seen.append(args)
    c.fire_connect(135)
    rc = seen[0][3]
    assert rc.value == 135 and rc.is_failure is True
    assert rc == 135
    assert c.connected is False


def test_fire_message_encodes_payload_and_retain():
    c = FakeMqttClient()
    seen = []
    c.on_message = lambda client, userdata, msg: seen.append(msg)
    c.fire_message("t/x", "42", retain=True)
    assert seen[0].payload == b"42"
    assert seen[0].retain is True
    assert seen[0].topic == "t/x"


def test_loop_start_auto_connect_fires_once():
    c = FakeMqttClient(auto_connect=0)
    seen = []
    c.on_connect = lambda *args: seen.append(args)
    c.loop_start()
    assert c.loop_started is True
    assert len(seen) == 1


def test_loop_start_without_auto_connect_is_silent():
    c = FakeMqttClient()
    seen = []
    c.on_connect = lambda *args: seen.append(args)
    c.loop_start()
    assert seen == []


def test_connect_error_raises():
    c = FakeMqttClient(connect_error=OSError("no route"))
    with pytest.raises(OSError):
        c.connect("h", 1883, 60)


def test_connect_records_call_and_disconnect_counts():
    c = FakeMqttClient()
    c.connect("h", 8883, 30)
    assert c.connect_calls == [("h", 8883, 30)]
    c.disconnect()
    assert c.disconnect_calls == 1 and c.connected is False


def test_subscribe_and_unsubscribe_recorded():
    c = FakeMqttClient()
    assert c.subscribe("s/#", 1)[0] == 0
    c.unsubscribe("s/#")
    assert c.subscriptions == [("s/#", 1)]
    assert c.unsubscriptions == ["s/#"]


def test_reason_code_str_and_failure_rule():
    assert FakeReasonCode(0).is_failure is False
    assert FakeReasonCode(134).is_failure is True
    assert "134" in str(FakeReasonCode(134)) or "password" in str(FakeReasonCode(134)).lower()


def test_factory_configures_client():
    f = FakeClientFactory()
    cfg = {"username": "u", "tls": True, "tls_insecure": False}
    cb = (lambda *a: None, lambda *a: None, lambda *a: None)
    client = f(cfg, "pw", "cid", "will/topic", *cb)
    assert f.last is client and f.clients == [client]
    assert client.client_id == "cid"
    assert client.will == ("will/topic", "offline", 1, True)
    assert client.username == "u" and client.password == "pw"
    assert client.tls is not None
    assert client.reconnect_delay == (1, 60)
    assert client.max_queued == 200
    assert client.on_connect is cb[0] and client.on_message is cb[2]
    assert f.calls[0]["will_topic"] == "will/topic"


def test_factory_without_will_topic_sets_no_will():
    f = FakeClientFactory()
    client = f({"username": "", "tls": False}, "", "cid", None, None, None, None)
    assert client.will is None and client.username is None and client.tls is None


def test_fake_db_defaults(fake_db):
    for name in ("power", "boiler_temp", "mode", "boiler_temp_set", "max_power",
                 "reset_alarm", "burner_on", "burner_off", "reset_ignition"):
        assert name in fake_db
    assert fake_db.get_text("burner_connection") == "connected"
    assert fake_db["boiler_temp_set"].min == "40"
    assert fake_db["boiler_temp_set"].max == "85"


def test_fake_db_set_value_records_and_fails_on_demand(fake_db):
    assert fake_db.set_value("boiler_temp_set", "60") == "OK"
    assert fake_db.writes == [("boiler_temp_set", "60")]
    assert fake_db.get_text("boiler_temp_set") == "60"
    fake_db.fail["max_power"] = ValueError("bad")
    with pytest.raises(ValueError):
        fake_db.set_value("max_power", "1")
    fake_db.fail["min_power"] = IOError("offline")
    with pytest.raises(IOError):
        fake_db.set_value("min_power", "1")


def test_fake_db_exclude_and_snapshot():
    db = FakeDb.make_scotte_db(exclude=("oxygen",))
    assert "oxygen" not in db
    assert db.snapshot()["power"] == db.get_text("power")


def test_fake_factory_fixture(fake_factory):
    assert fake_factory.last is None
