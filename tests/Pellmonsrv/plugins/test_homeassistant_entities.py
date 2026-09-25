# -*- coding: utf-8 -*-
"""Entity table and discovery payload tests (D-01, D-02, D-05, D-07, D-18, D-19)."""

import json

import pytest

from Pellmonsrv.plugins.homeassistant import entities as ent
from Pellmonsrv.plugins.homeassistant.entities import (
    ENTITIES, CLEANUP_BUTTONS, present_entities, effective_range,
    discovery_messages, state_topic, command_topic, availability_topic,
    birth_topic, entity_by_object_id, needs_commands)
from Scotteprotocol.datamap import dataBaseMap

DEG = u'°C'

CFG = {
    'prefix': 'scotte', 'discovery_prefix': 'homeassistant',
    'device_id': 'test_device_1', 'device_name': 'Test Burner',
    'node_id': 'node_x', 'uid_prefix': 'uid_x',
}

ALL_ITEMS = set(e.item for e in ENTITIES)


class FakeItem(object):
    def __init__(self, min=None, max=None):
        if min is not None:
            self.min = min
        if max is not None:
            self.max = max


def test_counts():
    assert len(ENTITIES) == 21
    comps = [e.component for e in ENTITIES]
    assert comps.count('sensor') == 9
    assert comps.count('number') == 10
    assert comps.count('button') == 2


def test_no_burner_on_off_entities():
    assert [e for e in ENTITIES if e.object_id in ('burner_on', 'burner_off')] == []
    assert CLEANUP_BUTTONS == ('burner_on', 'burner_off')


def test_object_id_to_item_mapping():
    special = {'power_percent': 'power', 'power_kw': 'power_kW',
               'boiler_diff_down': 'boiler_temp_diff_down',
               'boiler_diff_up': 'boiler_temp_diff_up'}
    for e in ENTITIES:
        assert e.item == special.get(e.object_id, e.object_id)
    for k, v in special.items():
        assert entity_by_object_id(k).item == v


def test_table_values():
    p = entity_by_object_id('power_percent')
    assert (p.name, p.unit, p.device_class, p.state_class) == ('Power', '%', 'power_factor', 'measurement')
    k = entity_by_object_id('power_kw')
    assert (k.name, k.unit, k.device_class, k.state_class) == ('Power kW', 'kW', 'power', 'measurement')
    for oid in ('boiler_temp', 'chute_temp', 'smoke_temp'):
        e = entity_by_object_id(oid)
        assert (e.unit, e.device_class, e.state_class) == (DEG, 'temperature', 'measurement')
    f = entity_by_object_id('feeder_time')
    assert (f.unit, f.device_class, f.state_class) == ('s', 'duration', 'measurement')
    o = entity_by_object_id('oxygen')
    assert (o.unit, o.device_class, o.state_class) == ('%', None, None)
    for oid in ('light', 'mode'):
        e = entity_by_object_id(oid)
        assert (e.unit, e.device_class, e.state_class) == (None, None, None)
    expect = {
        'boiler_temp_set': (DEG, 40, 85), 'boiler_temp_min': (DEG, 10, 70),
        'boiler_diff_down': (DEG, 0, 20), 'boiler_diff_up': (DEG, 0, 15),
        'chimney_draught': (None, 0, 10), 'cleaning_interval': ('min', 1, 120),
        'cleaning_time': ('s', 0, 60), 'feeder_capacity': ('g/h', 400, 8000),
        'min_power': ('%', 10, 100), 'max_power': ('%', 10, 100),
    }
    for oid, (unit, lo, hi) in expect.items():
        e = entity_by_object_id(oid)
        assert e.component == 'number'
        assert (e.unit, e.min, e.max) == (unit, lo, hi)
    assert entity_by_object_id('reset_alarm').component == 'button'
    assert entity_by_object_id('reset_ignition').component == 'button'


def test_needs_commands():
    assert sum(1 for e in ENTITIES if needs_commands(e)) == 12


def _windows(item):
    return dataBaseMap[item].values()


def test_datamap_cross_check():
    for e in ENTITIES:
        if e.component != 'number':
            continue
        assert e.item in dataBaseMap
        for w in _windows(e.item):
            assert e.min >= float(w.min), e.object_id
            assert e.max <= float(w.max), e.object_id


def test_present_entities():
    keys = set(ALL_ITEMS)
    assert len(present_entities(keys)) == 21
    keys.discard('chimney_draught')
    assert len(present_entities(keys)) == 20
    keys.discard('boiler_temp_diff_up')
    assert len(present_entities(keys)) == 19


def test_effective_range():
    e = entity_by_object_id('boiler_temp_set')
    assert effective_range(e, FakeItem('40', '85')) == (40, 85)
    assert effective_range(e, FakeItem('50', '80')) == (50, 80)
    assert effective_range(e, FakeItem('x', None)) == (40, 85)
    assert effective_range(e, FakeItem()) == (40, 85)
    assert effective_range(e, None) == (40, 85)
    # an item range wider than the entity never widens it
    assert effective_range(e, FakeItem('0', '200')) == (40, 85)


def test_topic_helpers():
    e = entity_by_object_id('power_percent')
    assert state_topic(CFG, e) == 'scotte/power_percent/state'
    assert command_topic(CFG, entity_by_object_id('boiler_temp_set')) == 'scotte/boiler_temp_set/set'
    assert availability_topic(CFG) == 'scotte/status'
    assert birth_topic(CFG) == 'homeassistant/status'


def _msgs(commands, present=None):
    if present is None:
        present = list(ENTITIES)
    return discovery_messages(CFG, present, commands, {}, '1.2.3')


def test_sensor_payload():
    msgs = dict(_msgs(True))
    t = 'homeassistant/sensor/node_x/power_percent/config'
    p = json.loads(msgs[t])
    assert p['name'] == 'Power'
    assert p['unique_id'] == 'uid_x_power_percent'
    assert p['device'] == {'identifiers': ['test_device_1'], 'name': 'Test Burner',
                           'manufacturer': 'Bio Comfort', 'model': 'Scotte',
                           'sw_version': '1.2.3'}
    assert p['availability_topic'] == 'scotte/status'
    assert p['payload_available'] == 'online'
    assert p['payload_not_available'] == 'offline'
    assert p['state_topic'] == 'scotte/power_percent/state'
    assert p['unit_of_measurement'] == '%'
    assert p['device_class'] == 'power_factor'
    assert p['state_class'] == 'measurement'
    assert 'command_topic' not in p
    t2 = 'homeassistant/sensor/node_x/light/config'
    assert 'unit_of_measurement' not in json.loads(msgs[t2])


def test_number_and_button_payload():
    msgs = dict(_msgs(True))
    p = json.loads(msgs['homeassistant/number/node_x/boiler_temp_set/config'])
    assert p['command_topic'] == 'scotte/boiler_temp_set/set'
    assert p['state_topic'] == 'scotte/boiler_temp_set/state'
    assert (p['min'], p['max'], p['step'], p['mode']) == (40, 85, 1, 'box')
    assert p['unit_of_measurement'] == DEG
    b = json.loads(msgs['homeassistant/button/node_x/reset_alarm/config'])
    assert b['command_topic'] == 'scotte/reset_alarm/set'
    assert b['payload_press'] == 'PRESS'
    assert 'state_topic' not in b


def test_number_range_uses_item_range():
    items = {'boiler_temp_set': FakeItem('45', '80')}
    msgs = dict(discovery_messages(CFG, list(ENTITIES), True, items, 'v'))
    p = json.loads(msgs['homeassistant/number/node_x/boiler_temp_set/config'])
    assert (p['min'], p['max']) == (45, 80)


def test_commands_off_removes_numbers_and_buttons():
    msgs = _msgs(False)
    d = dict(msgs)
    n_empty = 0
    for e in ENTITIES:
        t = 'homeassistant/%s/node_x/%s/config' % (e.component, e.object_id)
        if needs_commands(e):
            assert d[t] == ''
            n_empty += 1
        else:
            assert json.loads(d[t])['name'] == e.name
    assert n_empty == 12


def test_cleanup_buttons_always_empty():
    for commands in (True, False):
        d = dict(_msgs(commands))
        for oid in CLEANUP_BUTTONS:
            assert d['homeassistant/button/node_x/%s/config' % oid] == ''


def test_absent_entities_not_emitted():
    present = [e for e in ENTITIES if e.object_id != 'chimney_draught']
    d = dict(_msgs(False, present))
    assert 'homeassistant/number/node_x/chimney_draught/config' not in d
    assert len(d) == 20 + 2  # 20 present entities + 2 cleanup topics


def test_payloads_are_json_and_unit_roundtrips():
    for t, p in _msgs(True):
        if p:
            json.loads(p)
    p = json.loads(dict(_msgs(True))['homeassistant/sensor/node_x/boiler_temp/config'])
    assert p['unit_of_measurement'] == DEG


def test_no_paho_or_hardcoded_ids():
    import inspect
    src = inspect.getsource(ent)
    assert 'import paho' not in src
