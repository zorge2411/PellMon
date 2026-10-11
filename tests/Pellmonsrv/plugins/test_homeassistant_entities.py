# -*- coding: utf-8 -*-
"""Entity table and discovery payload tests (D-01, D-02, D-05, D-07, D-18, D-19)."""

import json
import os

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


# The 21 entities of the original Phase 6 device. They stay first, unchanged (Phase 11 D-09).
PHASE6_IDS = (
    'power_percent', 'power_kw', 'boiler_temp', 'chute_temp', 'smoke_temp', 'oxygen', 'light',
    'feeder_time', 'mode', 'boiler_temp_set', 'boiler_temp_min', 'boiler_diff_down',
    'boiler_diff_up', 'chimney_draught', 'cleaning_interval', 'cleaning_time',
    'feeder_capacity', 'min_power', 'max_power', 'reset_alarm', 'reset_ignition')


def test_counts():
    assert tuple(e.object_id for e in ENTITIES[:len(PHASE6_IDS)]) == PHASE6_IDS
    comps = [e.component for e in ENTITIES]
    assert comps.count('sensor') + comps.count('number') + comps.count('button') == len(ENTITIES)
    assert comps[:9] == ['sensor'] * 9
    assert comps[9:19] == ['number'] * 10
    assert comps[19:21] == ['button'] * 2
    assert len(set(e.object_id for e in ENTITIES)) == len(ENTITIES)


def test_phase6_discovery_payloads_unchanged():
    golden = json.load(open(os.path.join(os.path.dirname(__file__), 'data', 'ha_golden_v6.json')))
    cfg = {'prefix': 'scotte', 'discovery_prefix': 'homeassistant', 'device_id': 'dev',
           'device_name': 'Dev', 'node_id': 'n', 'uid_prefix': 'u'}
    old = [e for e in ENTITIES if e.object_id in PHASE6_IDS]
    for commands in (True, False):
        got = dict((t, p) for t, p in discovery_messages(cfg, old, commands, {}, 'v1'))
        want = dict((t, p) for t, p in golden['commands_%s' % commands])
        assert got == want


@pytest.mark.parametrize('kind,value,ok', [
    ('numeric', '12', True), ('numeric', '-3.5', True), ('numeric', '0', True),
    ('numeric', '', False), ('numeric', '-', False), ('numeric', 'None', False),
    ('numeric', 'nan', False), ('numeric', 'inf', False), ('numeric', None, False),
    ('text', 'Running', True), ('text', '', False), ('text', 'None', False),
    ('timestamp', '2026-10-11T12:00:00+02:00', True), ('timestamp', '', False),
    ('none', 'x', False)])
def test_is_publishable(kind, value, ok):
    e = ent.Entity('n', 'sensor', 'o', 'i', None, None, None, None, None, kind)
    assert ent.is_publishable(e, value) is ok


def test_every_entity_has_a_valid_kind():
    for e in ENTITIES:
        assert e.kind in ('numeric', 'text', 'timestamp', 'none'), e.object_id
        if e.component == 'button':
            assert e.kind == 'none'
        if e.component == 'number':
            assert e.kind == 'numeric'
        if e.kind in ('text', 'timestamp'):
            assert e.unit is None and e.state_class is None, e.object_id


def test_no_burner_on_off_entities():
    assert [e for e in ENTITIES if e.object_id in ('burner_on', 'burner_off')] == []
    assert CLEANUP_BUTTONS == ('burner_on', 'burner_off')


def test_object_id_to_item_mapping():
    special = {'power_percent': 'power', 'power_kw': 'power_kW',
               'boiler_diff_down': 'boiler_temp_diff_down',
               'boiler_diff_up': 'boiler_temp_diff_up',
               'magazine_content_set': 'magazine_content'}
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
    assert sum(1 for e in ENTITIES if needs_commands(e)) == sum(
        1 for e in ENTITIES if e.component in ('number', 'button'))
    assert sum(1 for e in ENTITIES[:21] if needs_commands(e)) == 12


# plugin items (not Scotte datamap parameters) that have writable entities
NOT_IN_DATAMAP = ('silo_reset_level',)


def _windows(item):
    return dataBaseMap[item].values()


def test_datamap_cross_check():
    for e in ENTITIES:
        if e.component != 'number':
            continue
        if e.item in NOT_IN_DATAMAP:
            continue
        assert e.item in dataBaseMap
        for w in _windows(e.item):
            assert e.min >= float(w.min), e.object_id
            assert e.max <= float(w.max), e.object_id


def test_present_entities():
    keys = set(ALL_ITEMS)
    total = len(ENTITIES)
    assert len(present_entities(keys)) == total
    keys.discard('chimney_draught')
    assert len(present_entities(keys)) == total - 1
    keys.discard('boiler_temp_diff_up')
    assert len(present_entities(keys)) == total - 2


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
    assert n_empty == sum(1 for e in ENTITIES if e.component in ('number', 'button'))


def test_cleanup_buttons_always_empty():
    for commands in (True, False):
        d = dict(_msgs(commands))
        for oid in CLEANUP_BUTTONS:
            assert d['homeassistant/button/node_x/%s/config' % oid] == ''


def test_absent_entities_not_emitted():
    present = [e for e in ENTITIES if e.object_id != 'chimney_draught']
    d = dict(_msgs(False, present))
    assert 'homeassistant/number/node_x/chimney_draught/config' not in d
    assert len(d) == len(present) + 2  # present entities + 2 cleanup topics


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


# ---- Phase 11 additions -------------------------------------------------

PHASE11_SENSOR_IDS = (
    'silo_days_left', 'silo_level', 'silo_empty_date',
    'consumption_today', 'consumption_7d', 'consumption_month',
    'magazine_content', 'boiler_return_temp', 'hotwater_temp', 'outside_temp', 'indoor_temp',
    'flow', 'oxygen_desired', 'ignition_count', 'ignition_time', 'motor_time', 'el_time', 'alarm',
    'feeder_rev', 'feeder_rpm', 'feeder_rp6m', 'feeder_rev_capacity')
PHASE11_NUMBER_IDS = ('hotwater_temp_set', 'hotwater_temp_diff', 'magazine_content_set', 'silo_reset_level')

# Home Assistant sensor/const.py (core dev): units accepted per device class, and which
# state classes a device class may carry (timestamp none).
HA_UNITS = {
    'duration': ('d', 'h', 'min', 's', 'ms'),
    'weight': ('kg', 'g'),
    'temperature': (DEG, u'\u00b0F', 'K'),
    'volume_flow_rate': ('L/s', 'L/min', 'L/h'),
}


def test_phase11_entities_present_and_appended():
    ids = tuple(e.object_id for e in ENTITIES)
    assert ids[:len(PHASE6_IDS)] == PHASE6_IDS
    for oid in PHASE11_SENSOR_IDS + PHASE11_NUMBER_IDS:
        assert oid in ids
    assert len(ids) == len(PHASE6_IDS) + len(PHASE11_SENSOR_IDS) + len(PHASE11_NUMBER_IDS)


def test_phase11_units_match_home_assistant_device_classes():
    for e in ENTITIES:
        if e.device_class in HA_UNITS:
            assert e.unit in HA_UNITS[e.device_class], (e.object_id, e.unit)
        if e.device_class == 'timestamp':
            assert e.unit is None and e.state_class is None and e.kind == 'timestamp'
        if e.state_class == 'total_increasing':
            assert e.kind == 'numeric' and e.component == 'sensor'


def test_phase11_classes():
    for oid in ('ignition_count', 'ignition_time', 'motor_time', 'el_time', 'feeder_rev'):
        assert entity_by_object_id(oid).state_class == 'total_increasing'
    for oid in ('consumption_today', 'consumption_7d', 'consumption_month', 'silo_level', 'silo_days_left'):
        assert entity_by_object_id(oid).state_class == 'measurement'
    a = entity_by_object_id('alarm')
    assert (a.kind, a.unit, a.device_class, a.state_class) == ('text', None, None, None)


def test_phase11_numbers_ranges_and_commands():
    for oid, lo, hi in (('hotwater_temp_set', 0, 80), ('hotwater_temp_diff', 0, 20),
                        ('magazine_content_set', 0, 9999), ('silo_reset_level', 0, 50000)):
        e = entity_by_object_id(oid)
        assert e.component == 'number' and (e.min, e.max) == (lo, hi)
        assert needs_commands(e)
    # sensor and number for the same item are separate entities with separate ids
    assert entity_by_object_id('magazine_content').component == 'sensor'
    assert entity_by_object_id('magazine_content_set').item == 'magazine_content'
    # no blower / oxygen / regulator writes (Phase 11 D-08)
    forbidden = ('blower', 'oxygen_low', 'oxygen_high', 'oxygen_mid', 'regulator', 'oxygen_gain')
    for e in ENTITIES:
        if e.component == 'number':
            assert not any(e.item.startswith(f) for f in forbidden), e.object_id


def test_phase11_payloads():
    d = dict(_msgs(True))
    p = json.loads(d['homeassistant/sensor/node_x/silo_empty_date/config'])
    assert p['device_class'] == 'timestamp' and 'unit_of_measurement' not in p and 'state_class' not in p
    p = json.loads(d['homeassistant/sensor/node_x/flow/config'])
    assert p['unit_of_measurement'] == 'L/s' and p['device_class'] == 'volume_flow_rate'
    p = json.loads(d['homeassistant/number/node_x/silo_reset_level/config'])
    assert (p['min'], p['max'], p['unit_of_measurement']) == (0, 50000, 'kg')
    assert p['command_topic'] == 'scotte/silo_reset_level/set' if CFG.get('prefix') == 'scotte' else True
    assert 'homeassistant/sensor/node_x/alarm/config' in d


def test_phase11_chip_version_gating():
    # a burner without the 6.03+ items and without any plugin items keeps the original 21
    old = set(e.item for e in ENTITIES[:len(PHASE6_IDS)])
    assert len(present_entities(old)) == len(PHASE6_IDS)
    v603 = set(old) | {'boiler_return_temp', 'hotwater_temp', 'outside_temp', 'indoor_temp', 'flow',
                       'magazine_content', 'hotwater_temp_set', 'hotwater_temp_diff'}
    ids = [e.object_id for e in present_entities(v603)]
    assert 'magazine_content_set' in ids and 'silo_level' not in ids and 'consumption_today' not in ids
