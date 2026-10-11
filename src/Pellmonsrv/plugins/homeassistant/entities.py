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

# Entity table and Home Assistant discovery payload builder.
# Pure module: stdlib only, no paho, no dbus.

import json
import math
from collections import namedtuple

# kind: 'numeric' (finite number), 'text' (any non-empty text), 'timestamp' (ISO 8601 text)
# or 'none' (buttons, no state)
Entity = namedtuple('Entity', 'name component object_id item unit device_class state_class min max kind')

DEG_C = u'°C'


def _s(name, object_id, item, unit=None, device_class=None, state_class=None, kind='numeric'):
    return Entity(name, 'sensor', object_id, item, unit, device_class, state_class, None, None, kind)


def _n(name, object_id, item, unit, lo, hi):
    return Entity(name, 'number', object_id, item, unit, None, None, lo, hi, 'numeric')


def _b(name, object_id, item):
    return Entity(name, 'button', object_id, item, None, None, None, None, None, 'none')


# object_id is the topic segment and unique-id suffix of the existing device;
# item is the PellMon database item (four of them differ, D-19 / C1).
ENTITIES = (
    _s('Power', 'power_percent', 'power', '%', 'power_factor', 'measurement'),
    _s('Power kW', 'power_kw', 'power_kW', 'kW', 'power', 'measurement'),
    _s('Boiler Temperature', 'boiler_temp', 'boiler_temp', DEG_C, 'temperature', 'measurement'),
    _s('Chute Temperature', 'chute_temp', 'chute_temp', DEG_C, 'temperature', 'measurement'),
    _s('Smoke Temperature', 'smoke_temp', 'smoke_temp', DEG_C, 'temperature', 'measurement'),
    _s('Oxygen Level', 'oxygen', 'oxygen', '%'),
    _s('Light (LDR)', 'light', 'light'),
    _s('Feeder Time', 'feeder_time', 'feeder_time', 's', 'duration', 'measurement'),
    _s('Burner Mode', 'mode', 'mode', kind='text'),
    _n('Boiler Temp Setpoint', 'boiler_temp_set', 'boiler_temp_set', DEG_C, 40, 85),
    _n('Boiler Temp Minimum', 'boiler_temp_min', 'boiler_temp_min', DEG_C, 10, 70),
    _n('Boiler Diff Down', 'boiler_diff_down', 'boiler_temp_diff_down', DEG_C, 0, 20),
    _n('Boiler Diff Up', 'boiler_diff_up', 'boiler_temp_diff_up', DEG_C, 0, 15),
    _n('Chimney Draught', 'chimney_draught', 'chimney_draught', None, 0, 10),
    _n('Cleaning Interval', 'cleaning_interval', 'cleaning_interval', 'min', 1, 120),
    _n('Cleaning Time', 'cleaning_time', 'cleaning_time', 's', 0, 60),
    _n('Feeder Capacity', 'feeder_capacity', 'feeder_capacity', 'g/h', 400, 8000),
    _n('Min Power', 'min_power', 'min_power', '%', 10, 100),
    _n('Max Power', 'max_power', 'max_power', '%', 10, 100),
    _b('Reset Alarm', 'reset_alarm', 'reset_alarm'),
    _b('Reset Ignition', 'reset_ignition', 'reset_ignition'),
)

# Phase 11 additions. Appended after the original 21 so their order, object ids and
# unique ids never change. Device and state classes follow Home Assistant's
# sensor/const.py: duration accepts d/s, weight accepts kg/g, volume_flow_rate wants
# 'L/s', timestamp takes neither unit nor state class.
ENTITIES += (
    # silolevel plugin
    _s('Silo Days Left', 'silo_days_left', 'silo_days_left', 'd', 'duration', 'measurement'),
    _s('Silo Level', 'silo_level', 'silo_level', 'kg', 'weight', 'measurement'),
    _s('Silo Empty Date', 'silo_empty_date', 'silo_empty_date', None, 'timestamp', None, kind='timestamp'),
    # consumption plugin
    _s('Consumption Today', 'consumption_today', 'consumption_today', 'kg', 'weight', 'measurement'),
    _s('Consumption 7 Days', 'consumption_7d', 'consumption_7d', 'kg', 'weight', 'measurement'),
    _s('Consumption This Month', 'consumption_month', 'consumption_month', 'kg', 'weight', 'measurement'),
    # Scotte burner (chip version dependent, only published when the item exists)
    _s('Magazine Content', 'magazine_content', 'magazine_content', 'kg', 'weight', 'measurement'),
    _s('Boiler Return Temperature', 'boiler_return_temp', 'boiler_return_temp', DEG_C, 'temperature', 'measurement'),
    _s('Hot Water Temperature', 'hotwater_temp', 'hotwater_temp', DEG_C, 'temperature', 'measurement'),
    _s('Outside Temperature', 'outside_temp', 'outside_temp', DEG_C, 'temperature', 'measurement'),
    _s('Indoor Temperature', 'indoor_temp', 'indoor_temp', DEG_C, 'temperature', 'measurement'),
    _s('Water Flow', 'flow', 'flow', 'L/s', 'volume_flow_rate', 'measurement'),
    _s('Desired Oxygen Level', 'oxygen_desired', 'oxygen_desired', '%', None, 'measurement'),
    _s('Ignition Count', 'ignition_count', 'ignition_count', None, None, 'total_increasing'),
    _s('Ignition Time', 'ignition_time', 'ignition_time', 's', 'duration', 'total_increasing'),
    _s('Motor Time', 'motor_time', 'motor_time', 's', 'duration', 'total_increasing'),
    _s('Electricity Time', 'el_time', 'el_time', 's', 'duration', 'total_increasing'),
    _s('Alarm', 'alarm', 'alarm', kind='text'),
    # pelletcalc plugin, counter mode
    _s('Feeder Revolutions', 'feeder_rev', 'feeder_rev', None, None, 'total_increasing'),
    _s('Feeder Speed', 'feeder_rpm', 'feeder_rpm', 'rpm', None, 'measurement'),
    _s('Feeder Revolutions per 6 min', 'feeder_rp6m', 'feeder_rp6m', 'rev/6min', None, 'measurement'),
    _s('Feeder Pellets per Revolution', 'feeder_rev_capacity', 'feeder_rev_capacity', 'g', 'weight', 'measurement'),
    # writable (only with commands on, like the original numbers)
    _n('Hot Water Temp Setpoint', 'hotwater_temp_set', 'hotwater_temp_set', DEG_C, 0, 80),
    _n('Hot Water Diff', 'hotwater_temp_diff', 'hotwater_temp_diff', DEG_C, 0, 20),
    _n('Set Magazine Content', 'magazine_content_set', 'magazine_content', 'kg', 0, 9999),
    _n('Silo Fill Level', 'silo_reset_level', 'silo_reset_level', 'kg', 0, 50000),
)

# Discovery configs that are always cleared (D-07: Burner ON/OFF is not published)
CLEANUP_BUTTONS = ('burner_on', 'burner_off')


def needs_commands(entity):
    return entity.component in ('number', 'button')


def present_entities(keys):
    """Entities whose PellMon item exists (version dependent items, D-05)"""
    return [e for e in ENTITIES if e.item in keys]


def entity_by_object_id(object_id):
    for e in ENTITIES:
        if e.object_id == object_id:
            return e
    return None


def is_publishable(entity, value):
    """True when value is a sane state for the entity (numeric sensors never get '-', '' or nan)"""
    if value is None:
        return False
    if entity.kind == 'numeric':
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
    if entity.kind in ('text', 'timestamp'):
        return str(value).strip() not in ('', 'None')
    return False


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(x):
    if x is not None and x == int(x):
        return int(x)
    return x


def effective_range(entity, item):
    """Entity range intersected with the item's own min/max (never wider, D-02)"""
    lo, hi = entity.min, entity.max
    if item is not None:
        ilo = _num(getattr(item, 'min', None))
        ihi = _num(getattr(item, 'max', None))
        if ilo is not None and ilo > lo:
            lo = ilo
        if ihi is not None and ihi < hi:
            hi = ihi
    return _clean(lo), _clean(hi)


def state_topic(cfg, entity):
    return '%s/%s/state' % (cfg['prefix'], entity.object_id)


def command_topic(cfg, entity):
    return '%s/%s/set' % (cfg['prefix'], entity.object_id)


def availability_topic(cfg):
    return '%s/status' % cfg['prefix']


def birth_topic(cfg):
    return '%s/status' % cfg['discovery_prefix']


def config_topic(cfg, component, object_id):
    return '%s/%s/%s/%s/config' % (cfg['discovery_prefix'], component, cfg['node_id'], object_id)


def _payload(cfg, entity, items, sw_version):
    p = {
        'name': entity.name,
        'unique_id': '%s_%s' % (cfg['uid_prefix'], entity.object_id),
        'device': {
            'identifiers': [cfg['device_id']],
            'name': cfg['device_name'],
            'manufacturer': 'Bio Comfort',
            'model': 'Scotte',
            'sw_version': sw_version,
        },
        'availability_topic': availability_topic(cfg),
        'payload_available': 'online',
        'payload_not_available': 'offline',
    }
    if entity.component in ('sensor', 'number'):
        p['state_topic'] = state_topic(cfg, entity)
    if entity.component in ('number', 'button'):
        p['command_topic'] = command_topic(cfg, entity)
    if entity.component == 'button':
        p['payload_press'] = 'PRESS'
    if entity.component == 'number':
        lo, hi = effective_range(entity, (items or {}).get(entity.item))
        p['min'] = lo
        p['max'] = hi
        p['step'] = 1
        p['mode'] = 'box'
    if entity.unit:
        p['unit_of_measurement'] = entity.unit
    if entity.device_class:
        p['device_class'] = entity.device_class
    if entity.state_class:
        p['state_class'] = entity.state_class
    return json.dumps(p)


def _removed_when_commands_off(entity):
    # D-18: with commands off, numbers and buttons are removed from Home
    # Assistant by publishing an empty retained config. One-line policy switch.
    return needs_commands(entity)


def discovery_messages(cfg, present, commands_enabled, items, sw_version):
    """Ordered list of (topic, payload) for all discovery configs.
    An empty payload removes the entity from Home Assistant."""
    out = []
    for comp in ('sensor', 'number', 'button'):
        for e in present:
            if e.component != comp:
                continue
            topic = config_topic(cfg, e.component, e.object_id)
            if not commands_enabled and _removed_when_commands_off(e):
                out.append((topic, ''))
            else:
                out.append((topic, _payload(cfg, e, items, sw_version)))
    for object_id in CLEANUP_BUTTONS:
        out.append((config_topic(cfg, 'button', object_id), ''))
    return out
