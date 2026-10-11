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

# Generates a Home Assistant dashboard (Sections view, YAML for the raw configuration
# editor) for the entities PellMon publishes over MQTT. The entity table in
# Pellmonsrv/plugins/homeassistant/entities.py is the single source of truth, so the page
# follows the integration. Stdlib only.
#
#   python tools/ha_dashboard.py --ids ids.txt --silo-capacity 220 -o dashboard.yaml
#
# ids.txt is the output of this template (Developer tools > Template in Home Assistant):
#   {% for e in integration_entities('mqtt') %}{{ e }} | {{ state_attr(e, 'friendly_name') }}
#   {% endfor %}
# Entities missing from that list are left off the page, so the dashboard never shows
# "entity not available" tiles.

import argparse
import json
import math
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from Pellmonsrv.plugins.homeassistant.entities import ENTITIES  # noqa: E402

BY_OBJECT_ID = dict((e.object_id, e) for e in ENTITIES)

# Optional sensors that are left off unless asked for (--include), because they are
# often not wired and would show dead tiles.
OPTIONAL_GROUPS = {
    'outside': ('outside_temp',),
    'indoor': ('indoor_temp',),
    'flow': ('flow',),
    'feeder': ('feeder_rev', 'feeder_rpm', 'feeder_rp6m', 'feeder_rev_capacity'),
}

# Short names for the tiles (the entity names are longer because they sit in a device).
NAMES = {
    'power_percent': 'Power', 'power_kw': 'Power kW', 'boiler_temp': 'Boiler',
    'chute_temp': 'Chute', 'smoke_temp': 'Smoke', 'oxygen': 'Oxygen',
    'oxygen_desired': 'Oxygen target', 'light': 'Light sensor', 'feeder_time': 'Feeder time',
    'mode': 'Mode', 'alarm': 'Alarm', 'boiler_return_temp': 'Boiler return',
    'hotwater_temp': 'Hot water', 'outside_temp': 'Outside', 'indoor_temp': 'Indoor',
    'flow': 'Water flow', 'silo_days_left': 'Silo days left', 'silo_level': 'Silo level',
    'silo_empty_date': 'Empty around', 'magazine_content': 'Magazine',
    'consumption_today': 'Today', 'consumption_7d': '7 days', 'consumption_month': 'This month',
    'ignition_count': 'Ignitions', 'ignition_time': 'Ignition time', 'motor_time': 'Motor time',
    'el_time': 'Electricity time', 'feeder_rev': 'Feeder revolutions',
    'feeder_rpm': 'Feeder speed', 'feeder_rp6m': 'Revolutions per 6 min',
    'feeder_rev_capacity': 'Pellets per revolution',
    'boiler_temp_set': 'Boiler setpoint', 'boiler_temp_min': 'Boiler minimum',
    'boiler_diff_down': 'Boiler diff down', 'boiler_diff_up': 'Boiler diff up',
    'chimney_draught': 'Chimney draught', 'cleaning_interval': 'Cleaning interval',
    'cleaning_time': 'Cleaning time', 'feeder_capacity': 'Feeder capacity',
    'min_power': 'Min power', 'max_power': 'Max power', 'hotwater_temp_set': 'Hot water setpoint',
    'hotwater_temp_diff': 'Hot water diff', 'magazine_content_set': 'Set magazine content',
    'silo_reset_level': 'Silo fill level', 'reset_alarm': 'Reset alarm',
    'reset_ignition': 'Reset ignition',
}

EMBER = '#c4571a'
RED = '#db4437'
ORANGE = '#ffa600'
GREEN = '#43a047'


def slug(text):
    """Home Assistant style object id from a name"""
    s = re.sub(r'[^a-z0-9]+', '_', text.lower())
    return s.strip('_')


# ---- entity id resolution ---------------------------------------------------

_LINE_RE = re.compile(
    r'\b((?:sensor|number|button)\.[a-z0-9_]+)\s*\|\s*(.*?)(?=\s+(?:sensor|number|button)\.[a-z0-9_]+\s*\||\s*$)',
    re.S)
_ROW_RE = re.compile(r'^\s*((?:sensor|number|button)\.[a-z0-9_]+)\s*\|\s*(.+?)\s*(?:\|\s*([^|]*?))?\s*$')


def parse_rows(text):
    """[(entity_id, friendly_name, state_or_None)] from the template output.
    Works for one entity per line (anything else, such as the Template tool's trailing
    "listens to" text, is ignored) and for everything on one line."""
    rows = []
    if '\n' in text.strip():
        for line in text.splitlines():
            m = _ROW_RE.match(line)
            if m:
                rows.append((m.group(1), m.group(2).strip(), m.group(3)))
        return rows
    for m in _LINE_RE.finditer(text):
        name, state = m.group(2).strip(), None
        if ' | ' in name:
            name, state = [x.strip() for x in name.rsplit(' | ', 1)]
        rows.append((m.group(1), name, state))
    return rows


def parse_ids(text):
    """('lines', [(entity_id, friendly_name)]) from the template output, or
    ('map', {object_id: entity_id}) from a JSON object."""
    stripped = text.strip()
    if stripped.startswith('{'):
        try:
            data = json.loads(stripped)
        except ValueError:  # the pasted template itself starts with "{%"
            data = None
        if isinstance(data, dict):
            return 'map', dict((k, v) for k, v in data.items())
    return 'lines', [(eid, name) for eid, name, _state in parse_rows(text)]


def resolve(entities, lines):  # noqa: E302
    """Match entities to (entity_id, friendly_name) lines.
    Returns (mapping object_id -> entity_id, missing object_ids, ambiguous {object_id: [ids]})."""
    mapping = {}
    claimed = set()
    for e in entities:
        want = e.name.lower()
        for entity_id, friendly in lines:
            if entity_id in claimed or not entity_id.startswith(e.component + '.'):
                continue
            if friendly.lower() == want:
                mapping[e.object_id] = entity_id
                claimed.add(entity_id)
                break
    ambiguous = {}
    # longest names first: "Desired Oxygen Level" claims its line before "Oxygen Level" looks
    for e in sorted(entities, key=lambda x: -len(x.name)):
        if e.object_id in mapping:
            continue
        want = ' ' + e.name.lower()
        found = [entity_id for entity_id, friendly in lines
                 if entity_id not in claimed and entity_id.startswith(e.component + '.')
                 and (' ' + friendly.lower()).endswith(want)]
        if len(found) == 1:
            mapping[e.object_id] = found[0]
            claimed.add(found[0])
        elif len(found) > 1:
            ambiguous[e.object_id] = found
    missing = [e.object_id for e in entities if e.object_id not in mapping and e.object_id not in ambiguous]
    return mapping, missing, ambiguous


def default_ids(entities, prefix=''):
    """entity ids Home Assistant would create from the entity names"""
    return dict((e.object_id, '%s.%s%s' % (e.component, prefix, slug(e.name))) for e in entities)


# ---- card helpers -----------------------------------------------------------

class Ids(object):
    """Maps object ids to entity ids; unknown ones are None so cards can be skipped."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.used = set()

    def get(self, object_id):
        entity_id = self.mapping.get(object_id)
        if entity_id:
            self.used.add(object_id)
        return entity_id

    def has(self, object_id):
        return object_id in self.mapping


def tile(ids, object_id, features=None, name=None, vertical=False, **extra):
    entity_id = ids.get(object_id)
    if not entity_id:
        return None
    card = {'type': 'tile', 'entity': entity_id, 'name': name or NAMES.get(object_id, BY_OBJECT_ID[object_id].name)}
    if vertical:
        card['vertical'] = True
    if features:
        card['features'] = features
    card.update(extra)
    return card


def bar_gauge(lo, hi):
    return {'type': 'bar-gauge', 'min': lo, 'max': hi}


def trend(hours=24):
    return {'type': 'trend-graph', 'hours_to_show': hours, 'detail': True}


def numeric():
    return {'type': 'numeric-input', 'style': 'slider'}


def grid(cards, columns=2):
    cards = [c for c in cards if c]
    if not cards:
        return None
    return {'type': 'grid', 'columns': columns, 'square': False, 'cards': cards}


def heading(title, icon, badge_ids=None, ids=None):
    card = {'type': 'heading', 'heading': title, 'heading_style': 'title', 'icon': icon}
    badges = []
    for oid in badge_ids or ():
        entity_id = ids.get(oid) if ids else None
        if entity_id:
            badges.append({'type': 'entity', 'entity': entity_id, 'show_state': True, 'show_icon': True})
    if badges:
        card['badges'] = badges
    return card


def section(cards, column_span=None):
    cards = [c for c in cards if c]
    if len(cards) <= 1:  # only a heading: nothing to show
        return None
    out = {'type': 'grid'}
    if column_span:
        out['column_span'] = column_span
    out['cards'] = cards
    return out


def press(ids, object_id, text):
    """A tile that presses a button entity after a confirmation"""
    entity_id = ids.get(object_id)
    if not entity_id:
        return None
    action = {'action': 'perform-action', 'perform_action': 'button.press',
              'target': {'entity_id': entity_id}, 'confirmation': {'text': text}}
    return {'type': 'tile', 'entity': entity_id, 'name': NAMES[object_id], 'icon': 'mdi:restart',
            'tap_action': action, 'icon_tap_action': action}


# ---- the dashboard ----------------------------------------------------------

def silo_forecast_card(ids, capacity, apex):
    level = ids.get('silo_level')
    if not level:
        return None
    days = ids.get('silo_days_left')
    if not apex:
        return {'type': 'statistics-graph', 'title': 'Silo level', 'entities': [level],
                'days_to_show': 30, 'period': 'day', 'stat_types': ['mean'], 'chart_type': 'line',
                'min_y_axis': 0, 'max_y_axis': capacity}
    series = [{'entity': level, 'name': 'Level', 'type': 'area', 'color': EMBER, 'stroke_width': 2,
               'extend_to': 'now', 'statistics': {'type': 'mean', 'period': 'hour'}}]
    if days:
        series.append({
            'entity': level, 'name': 'Forecast', 'type': 'line', 'color': EMBER, 'stroke_width': 2,
            'stroke_dash': 5, 'show': {'in_header': False, 'legend_value': False},
            'data_generator': (
                "const days = parseFloat(hass.states['%s'].state);\n"
                "const level = parseFloat(entity.state);\n"
                "if (isNaN(days) || isNaN(level)) { return []; }\n"
                "const now = Date.now();\n"
                "return [[now, level], [now + days * 86400000, 0]];") % days})
    return {'type': 'custom:apexcharts-card', 'section_mode': True,
            'grid_options': {'columns': 'full', 'rows': 6},
            'graph_span': '90d', 'span': {'start': 'day', 'offset': '-21d'},
            'header': {'show': True, 'title': 'Silo level and forecast', 'show_states': True,
                       'colorize_states': True},
            'now': {'show': True, 'label': 'Now'},
            'yaxis': [{'min': 0, 'max': capacity, 'decimals': 0}],
            'series': series}


def consumption_card(ids, apex):
    entity_id = ids.get('consumption_today')
    if not entity_id:
        return None
    if not apex:
        return {'type': 'statistics-graph', 'title': 'Pellets per day', 'entities': [entity_id],
                'days_to_show': 14, 'period': 'day', 'stat_types': ['max'], 'chart_type': 'bar'}
    # consumption_today resets at midnight, so the daily maximum is the daily total
    return {'type': 'custom:apexcharts-card', 'section_mode': True,
            'grid_options': {'columns': 'full', 'rows': 5},
            'graph_span': '14d', 'span': {'end': 'day'},
            'header': {'show': True, 'title': 'Pellets per day', 'show_states': False},
            'yaxis': [{'min': 0, 'decimals': 0}],
            'series': [{'entity': entity_id, 'name': 'Pellets per day', 'type': 'column',
                        'color': EMBER, 'unit': 'kg', 'group_by': {'func': 'max', 'duration': '1d'},
                        'show': {'legend_value': False}}]}


def build(mapping, capacity=220, apex=True, controls=True, admin_users=None, title='PellMon'):
    """The dashboard as plain data (dict) for the entities in mapping."""
    ids = Ids(mapping)
    capacity = int(capacity)

    # -- burner now
    alarm = ids.get('alarm')
    alarm_banner = None
    if alarm:
        alarm_banner = {
            'type': 'conditional',
            'conditions': [{'condition': 'state', 'entity': alarm, 'state_not': 'ok'}],
            'card': tile(ids, 'alarm', color='red', icon='mdi:alert')}
    burner = section([
        heading('Burner now', 'mdi:fire', ['power_percent'], ids),
        alarm_banner,
        grid([tile(ids, 'mode', icon='mdi:fire'), tile(ids, 'alarm', icon='mdi:shield-check')]),
        grid([tile(ids, 'power_percent', [bar_gauge(0, 100)]), tile(ids, 'power_kw')]),
        grid([tile(ids, 'boiler_temp', [trend()]), tile(ids, 'smoke_temp', [trend()]),
              tile(ids, 'chute_temp'), tile(ids, 'oxygen'), tile(ids, 'oxygen_desired'),
              tile(ids, 'light')]),
    ])

    # -- fuel
    days = ids.get('silo_days_left')
    gauge = None
    if days:
        gauge = {'type': 'gauge', 'entity': days, 'name': 'Silo days left', 'min': 0, 'max': 60,
                 'needle': True,
                 'segments': [{'from': 0, 'color': RED}, {'from': 7, 'color': ORANGE},
                              {'from': 21, 'color': GREEN}]}
    fuel = section([
        heading('Fuel', 'mdi:grain', ['silo_level'], ids),
        gauge,
        tile(ids, 'silo_empty_date', icon='mdi:calendar-end'),
        tile(ids, 'silo_level', [bar_gauge(0, capacity)], icon='mdi:grain'),
        grid([tile(ids, 'consumption_today', vertical=True), tile(ids, 'consumption_7d', vertical=True),
              tile(ids, 'consumption_month', vertical=True)], columns=3),
        tile(ids, 'magazine_content', icon='mdi:silo'),
    ])

    # -- heating and water
    temps = [oid for oid in ('boiler_temp', 'boiler_return_temp', 'hotwater_temp', 'outside_temp', 'indoor_temp')
             if ids.has(oid)]
    history = None
    if temps:
        history = {'type': 'history-graph', 'title': 'Temperatures', 'hours_to_show': 24,
                   'entities': [{'entity': ids.get(oid), 'name': NAMES[oid]} for oid in temps]}
    heating = section([
        heading('Heating & water', 'mdi:water-thermometer', ['boiler_return_temp'], ids),
        grid([tile(ids, 'boiler_return_temp'), tile(ids, 'hotwater_temp'),
              tile(ids, 'outside_temp'), tile(ids, 'indoor_temp'), tile(ids, 'flow')]),
        history,
    ])

    # -- charts
    silo_chart = silo_forecast_card(ids, capacity, apex)
    cons_chart = consumption_card(ids, apex)
    silo_section = section([heading('Silo history and forecast', 'mdi:chart-areaspline'), silo_chart], column_span=2)
    cons_section = section([heading('Daily consumption', 'mdi:chart-bar'), cons_chart])

    # -- service
    runtime = [ids.get(oid) for oid in ('motor_time', 'ignition_time') if ids.has(oid)]
    runtime_chart = None
    if runtime:
        runtime_chart = {'type': 'statistics-graph', 'title': 'Runtime per day', 'entities': runtime,
                         'days_to_show': 14, 'period': 'day', 'stat_types': ['change'],
                         'chart_type': 'bar'}
    service = section([
        heading('Service', 'mdi:wrench'),
        grid([tile(ids, 'ignition_count'), tile(ids, 'ignition_time'), tile(ids, 'motor_time'),
              tile(ids, 'el_time'), tile(ids, 'feeder_time')]),
        grid([tile(ids, 'feeder_rev'), tile(ids, 'feeder_rpm'), tile(ids, 'feeder_rp6m'),
              tile(ids, 'feeder_rev_capacity')]),
        runtime_chart,
    ])

    main_sections = [s for s in (burner, fuel, heating, silo_section, cons_section, service) if s]
    views = [{
        'title': 'Pellets', 'path': 'pellmon', 'icon': 'mdi:fire', 'type': 'sections', 'max_columns': 3,
        'header': {'layout': 'responsive', 'badges_position': 'bottom',
                   'card': {'type': 'markdown', 'text_only': True, 'content': '# %s' % title}},
        'badges': [b for b in (
            {'type': 'entity', 'entity': ids.get('mode'), 'show_name': False} if ids.has('mode') else None,
            {'type': 'entity', 'entity': ids.get('boiler_temp'), 'show_name': False} if ids.has('boiler_temp') else None,
            {'type': 'entity', 'entity': ids.get('silo_days_left'), 'show_name': False} if ids.has('silo_days_left') else None,
        ) if b],
        'sections': main_sections,
    }]

    # -- controls: a second view, optionally limited to some users
    if controls:
        def num(oid):
            return tile(ids, oid, [numeric()]) if BY_OBJECT_ID[oid].component == 'number' else None
        burner_ctl = section([
            heading('Burner settings', 'mdi:tune'),
            grid([num(o) for o in ('boiler_temp_set', 'boiler_temp_min', 'boiler_diff_down', 'boiler_diff_up',
                                   'min_power', 'max_power', 'chimney_draught', 'feeder_capacity',
                                   'cleaning_interval', 'cleaning_time')]),
        ])
        water_ctl = section([
            heading('Hot water', 'mdi:water-boiler'),
            grid([num('hotwater_temp_set'), num('hotwater_temp_diff')]),
        ])
        fuel_ctl = section([
            heading('Fuel', 'mdi:grain'),
            tile(ids, 'silo_reset_level', [numeric()], icon='mdi:silo'),
            tile(ids, 'magazine_content_set', [numeric()], icon='mdi:grain'),
        ])
        reset_ctl = section([
            heading('Resets', 'mdi:restart'),
            grid([press(ids, 'reset_alarm', 'Reset the burner alarm?'),
                  press(ids, 'reset_ignition', 'Clear the ignition counter and time?')]),
        ])
        ctl_sections = [s for s in (burner_ctl, water_ctl, fuel_ctl, reset_ctl) if s]
        if ctl_sections:
            view = {'title': 'Controls', 'path': 'pellmon-controls', 'icon': 'mdi:tune', 'type': 'sections',
                    'max_columns': 3, 'sections': ctl_sections}
            if admin_users:
                view['visible'] = [{'user': u} for u in admin_users]
            views.append(view)

    return {'title': title, 'views': views}


def collect_entities(node, out=None):
    """All entity ids referenced anywhere in the dashboard data (for validation)"""
    if out is None:
        out = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == 'entity' and isinstance(value, str):
                out.add(value)
            elif key == 'entity_id' and isinstance(value, str):
                out.add(value)
            elif key == 'entities' and isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        out.add(item)
                    else:
                        collect_entities(item, out)
            elif key == 'data_generator' and isinstance(value, str):
                out.update(re.findall(r"hass\.states\['([a-z_]+\.[a-z0-9_]+)'\]", value))
            else:
                collect_entities(value, out)
    elif isinstance(node, list):
        for item in node:
            collect_entities(item, out)
    return out


# ---- YAML emitter (stdlib only, deterministic) ---------------------------------

_PLAIN_RE = re.compile(r'^[A-Za-z][A-Za-z0-9 _./():&,+-]*$')
_RESERVED = ('true', 'false', 'yes', 'no', 'on', 'off', 'null', '~', 'y', 'n')


def _scalar(value):
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    plain = (_PLAIN_RE.match(text) and text.lower() not in _RESERVED and ': ' not in text
             and ' #' not in text and not text.endswith(':') and not text.endswith(' '))
    if plain:
        try:
            float(text)  # 'nan', 'inf', 'infinity' would load as numbers
            plain = False
        except ValueError:
            pass
    return text if plain else json.dumps(text, ensure_ascii=False)


def dump(node, indent=0):
    pad = '  ' * indent
    lines = []
    if isinstance(node, dict):
        if not node:
            return pad + '{}\n'
        for key, value in node.items():
            if isinstance(value, str) and '\n' in value:
                lines.append('%s%s: |-' % (pad, key))
                for part in value.rstrip('\n').split('\n'):
                    lines.append('%s  %s' % (pad, part) if part else '')
            elif isinstance(value, (dict, list)) and value:
                lines.append('%s%s:' % (pad, key))
                lines.append(dump(value, indent + 1).rstrip('\n'))
            elif isinstance(value, dict):
                lines.append('%s%s: {}' % (pad, key))
            elif isinstance(value, list):
                lines.append('%s%s: []' % (pad, key))
            else:
                lines.append('%s%s: %s' % (pad, key, _scalar(value)))
    elif isinstance(node, list):
        if not node:
            return pad + '[]\n'
        for item in node:
            if isinstance(item, (dict, list)) and item:
                body = dump(item, indent + 1).rstrip('\n').split('\n')
                body[0] = pad + '- ' + body[0].lstrip()
                lines.extend(body)
            else:
                lines.append('%s- %s' % (pad, _scalar(item) if not isinstance(item, (dict, list)) else
                                          ('{}' if isinstance(item, dict) else '[]')))
    else:
        return pad + _scalar(node) + '\n'
    return '\n'.join(lines) + '\n'


def header_comment(argv):
    skip = False
    kept = []
    for a in argv:
        if skip:
            skip = False
        elif a in ('-o', '--output'):
            skip = True
        elif not a.startswith('--output='):
            kept.append(os.path.basename(a) if kept and kept[-1] == '--ids' else a)
    argv_text = ' '.join(kept)
    return ('# PellMon dashboard for Home Assistant (Sections view).\n'
            '# Generated by tools/ha_dashboard.py %s\n'
            '# Paste into: Dashboards > (your dashboard) > pencil > three dots > Raw configuration editor.\n'
            '# Re-generate after the entity list changes instead of editing by hand.\n' % argv_text)


# ---- command line ---------------------------------------------------------------

EXCLUDE_ALIASES = {'magazine': ('magazine_content', 'magazine_content_set')}
UNAVAILABLE = ('unknown', 'unavailable', None, '')


def expand_exclude(text):
    """object ids (or aliases such as 'magazine') to leave off the page; ValueError if unknown"""
    out = set()
    for item in [x.strip() for x in text.split(',') if x.strip()]:
        if item in EXCLUDE_ALIASES:
            out.update(EXCLUDE_ALIASES[item])
        elif item in BY_OBJECT_ID:
            out.add(item)
        else:
            raise ValueError(item)
    return out


def check_report(rows):
    """Compare the entity list from Home Assistant with the entity table.
    Returns (text, ok): ok is False when a non-optional entity is missing."""
    lines = [(eid, name) for eid, name, _s in rows]
    states = dict((eid, st) for eid, _n, st in rows)
    mapping, missing, ambiguous = resolve(list(ENTITIES), lines)
    optional = set(o for group in OPTIONAL_GROUPS.values() for o in group)
    out = ['%d of %d expected entities found' % (len(mapping), len(ENTITIES))]
    hard = [o for o in missing if o not in optional]
    soft = [o for o in missing if o in optional]
    if hard:
        out.append('MISSING: ' + ', '.join(hard))
    if soft:
        out.append('absent, optional: ' + ', '.join(soft))
    for oid, found in sorted(ambiguous.items()):
        out.append('AMBIGUOUS %s: %s' % (oid, ', '.join(found)))
    quiet = [mapping[o] for o in mapping if states.get(mapping[o]) in UNAVAILABLE
             and BY_OBJECT_ID[o].component != 'button']
    if quiet:
        out.append('no state yet (unknown/unavailable): ' + ', '.join(sorted(quiet)))
    extra = [eid for eid, _n in lines if eid not in set(mapping.values())
             and not any(eid in v for v in ambiguous.values())]
    if extra:
        out.append('not from PellMon (leftover or other MQTT entities): ' + ', '.join(extra))
    return '\n'.join(out) + '\n', not hard and not ambiguous


def select_entities(include):
    """Entities that take part: everything except optional groups not asked for"""
    skipped = set()
    for group, object_ids in OPTIONAL_GROUPS.items():
        if group not in include:
            skipped.update(object_ids)
    return [e for e in ENTITIES if e.object_id not in skipped]


def parse_args(argv):
    p = argparse.ArgumentParser(description='Generate a Home Assistant dashboard for PellMon.')
    p.add_argument('--ids', help='file with "entity_id | friendly name" lines (or a JSON object {object_id: entity_id})')
    p.add_argument('--prefix', default='', help='prefix for assumed entity ids when no --ids file is given, e.g. scotte_pellet_burner_')
    p.add_argument('--map', action='append', default=[], metavar='OBJECT_ID=ENTITY_ID', help='override one entity id (repeatable)')
    p.add_argument('--include', default='', help='optional sensors to include: %s' % ','.join(sorted(OPTIONAL_GROUPS)))
    p.add_argument('--exclude', default='', help='entities to leave off the page, by object id (e.g. smoke_temp,oxygen) or alias: %s' % ','.join(sorted(EXCLUDE_ALIASES)))
    p.add_argument('--check', action='store_true', help='only compare --ids with the entity table and print a report (exit 1 if a required entity is missing)')
    p.add_argument('--silo-capacity', type=int, default=220, help='silo size in kg: maximum of the silo gauge and chart (default 220)')
    p.add_argument('--no-apexcharts', action='store_true', help='use core cards only (no HACS cards)')
    p.add_argument('--no-controls', action='store_true', help='leave out the Controls view')
    p.add_argument('--admin-user', action='append', default=[], metavar='USER_ID', help='limit the Controls view to this Home Assistant user id (repeatable)')
    p.add_argument('--title', default='PellMon')
    p.add_argument('-o', '--output', help='write to a file instead of stdout')
    return p.parse_args(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    args = parse_args(argv)
    include = set(x.strip() for x in args.include.split(',') if x.strip())
    unknown = include - set(OPTIONAL_GROUPS)
    if unknown:
        sys.stderr.write('unknown --include value(s): %s\n' % ', '.join(sorted(unknown)))
        return 2
    try:
        exclude = expand_exclude(args.exclude)
    except ValueError as e:
        sys.stderr.write('unknown --exclude value: %s\n' % e)
        return 2
    if args.check:
        if not args.ids:
            sys.stderr.write('--check needs --ids\n')
            return 2
        with open(args.ids, encoding='utf-8') as f:
            report, ok = check_report(parse_rows(f.read()))
        sys.stdout.write(report)
        return 0 if ok else 1
    entities = [e for e in select_entities(include) if e.object_id not in exclude]
    notes = []
    if args.ids:
        with open(args.ids, encoding='utf-8') as f:
            kind, data = parse_ids(f.read())
        if kind == 'map':
            mapping = dict((oid, eid) for oid, eid in data.items() if oid in BY_OBJECT_ID)
        else:
            mapping, missing, ambiguous = resolve(entities, data)
            if missing:
                notes.append('not found in the id list, left off the page: %s' % ', '.join(missing))
            for oid, found in sorted(ambiguous.items()):
                notes.append('ambiguous %s (%s): use --map %s=ENTITY_ID' % (oid, ', '.join(found), oid))
    else:
        mapping = default_ids(entities, args.prefix)
        notes.append('no --ids file: entity ids are assumed from the entity names, check them')
    for item in args.map:
        oid, _, eid = item.partition('=')
        if oid not in BY_OBJECT_ID or not eid:
            sys.stderr.write('bad --map %r\n' % item)
            return 2
        mapping[oid] = eid
    dashboard = build(mapping, args.silo_capacity, not args.no_apexcharts, not args.no_controls,
                      args.admin_user, args.title)
    text = header_comment(argv) + dump(dashboard)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    for note in notes:
        sys.stderr.write('note: %s\n' % note)
    return 0


if __name__ == '__main__':
    sys.exit(main())
