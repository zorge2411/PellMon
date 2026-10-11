# -*- coding: utf-8 -*-
"""tools/ha_dashboard.py: generates the Home Assistant dashboard from the entity table."""

import importlib.util
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location('ha_dashboard', os.path.join(ROOT, 'tools', 'ha_dashboard.py'))
hd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hd)

ALL_GROUPS = set(hd.OPTIONAL_GROUPS)
ALLOWED_CARDS = {'tile', 'grid', 'heading', 'conditional', 'gauge', 'history-graph', 'statistics-graph',
                 'markdown', 'custom:apexcharts-card'}
ALLOWED_FEATURES = {'bar-gauge', 'trend-graph', 'numeric-input'}


def full_mapping(prefix=''):
    return hd.default_ids(hd.select_entities(ALL_GROUPS), prefix)


def walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            for x in walk(v):
                yield x
    elif isinstance(node, list):
        for v in node:
            for x in walk(v):
                yield x


def card_types(dash):
    return set(n['type'] for n in walk(dash) if 'type' in n and isinstance(n['type'], str))


def friendly_lines(device='Scotte Pellet Burner'):
    return [(e.component + '.' + hd.slug(device + ' ' + e.name), device + ' ' + e.name) for e in hd.ENTITIES]


# ---- coverage ---------------------------------------------------------------

def test_every_entity_is_placed_when_all_groups_included():
    """Adding an entity to ENTITIES without giving it a place on the page fails here."""
    mapping = full_mapping()
    dash = hd.build(mapping)
    used = hd.collect_entities(dash)
    assert used == set(mapping.values())


def test_default_selection_leaves_out_optional_sensors():
    entities = hd.select_entities(set())
    ids = set(e.object_id for e in entities)
    for group in hd.OPTIONAL_GROUPS.values():
        assert not ids & set(group)
    dash = hd.build(hd.default_ids(entities))
    used = hd.collect_entities(dash)
    assert 'sensor.outside_temperature' not in used and 'sensor.water_flow' not in used
    assert 'sensor.boiler_return_temperature' in used


def test_referenced_entities_always_come_from_the_mapping():
    mapping = full_mapping('x_')
    assert hd.collect_entities(hd.build(mapping)) <= set(mapping.values())


# ---- absent entities ----------------------------------------------------------

def test_absent_entities_are_left_off_without_empty_cards():
    mapping = full_mapping()
    for oid in ('silo_level', 'silo_days_left', 'silo_empty_date', 'silo_reset_level',
                'consumption_today', 'consumption_7d', 'consumption_month'):
        del mapping[oid]
    dash = hd.build(mapping)
    used = hd.collect_entities(dash)
    assert not [u for u in used if 'silo' in u or 'consumption' in u]
    titles = [n.get('heading') for n in walk(dash) if n.get('type') == 'heading']
    assert 'Silo history and forecast' not in titles and 'Daily consumption' not in titles and 'Fuel' in titles
    for sec in [s for v in dash['views'] for s in v['sections']]:
        assert len(sec['cards']) > 1  # more than the heading


def test_no_commands_means_no_controls_view():
    mapping = dict((o, e) for o, e in full_mapping().items() if hd.BY_OBJECT_ID[o].component == 'sensor')
    dash = hd.build(mapping)
    assert [v['title'] for v in dash['views']] == ['Pellets']


def test_no_controls_flag():
    dash = hd.build(full_mapping(), controls=False)
    assert [v['title'] for v in dash['views']] == ['Pellets']


# ---- cards ---------------------------------------------------------------------

def test_only_known_card_and_feature_types():
    dash = hd.build(full_mapping())
    chart_kinds = {'line', 'area', 'column', 'mean', 'entity'}  # series / statistic types, not cards
    assert card_types(dash) <= ALLOWED_CARDS | ALLOWED_FEATURES | {'sections'} | chart_kinds
    for n in walk(dash):
        for f in n.get('features', []):
            assert f['type'] in ALLOWED_FEATURES


def test_apex_cards_optional():
    with_apex = hd.build(full_mapping(), apex=True)
    without = hd.build(full_mapping(), apex=False)
    assert 'custom:apexcharts-card' in card_types(with_apex)
    assert not [t for t in card_types(without) if t.startswith('custom:')]
    assert 'statistics-graph' in card_types(without)


def test_capacity_flows_into_gauge_and_chart():
    dash = hd.build(full_mapping(), capacity=300)
    bars = [f for n in walk(dash) for f in n.get('features', []) if f['type'] == 'bar-gauge']
    assert {'type': 'bar-gauge', 'min': 0, 'max': 300} in bars
    apex = [n for n in walk(dash) if n.get('type') == 'custom:apexcharts-card' and 'yaxis' in n and n['series'][0]['entity'] == 'sensor.silo_level'][0]
    assert apex['yaxis'][0]['max'] == 300


def test_forecast_series_reads_the_days_left_entity():
    dash = hd.build(full_mapping())
    apex = [n for n in walk(dash) if n.get('type') == 'custom:apexcharts-card' and n['series'][0]['entity'] == 'sensor.silo_level'][0]
    forecast = [s for s in apex['series'] if s['name'] == 'Forecast'][0]
    assert "hass.states['sensor.silo_days_left']" in forecast['data_generator']
    assert forecast['stroke_dash'] and apex['now']['show'] is True
    # no days-left entity: the level chart is kept, the forecast goes
    mapping = full_mapping()
    del mapping['silo_days_left']
    apex = [n for n in walk(hd.build(mapping)) if n.get('type') == 'custom:apexcharts-card' and n['series'][0]['entity'] == 'sensor.silo_level'][0]
    assert [s['name'] for s in apex['series']] == ['Level']


def test_daily_consumption_uses_daily_maximum():
    dash = hd.build(full_mapping())
    card = [n for n in walk(dash) if n.get('type') == 'custom:apexcharts-card' and n['series'][0]['entity'] == 'sensor.consumption_today'][0]
    assert card['series'][0]['group_by'] == {'func': 'max', 'duration': '1d'}
    assert card['series'][0]['type'] == 'column'


def test_alarm_banner_only_when_alarm_is_not_ok():
    dash = hd.build(full_mapping())
    cond = [n for n in walk(dash) if n.get('type') == 'conditional'][0]
    assert cond['conditions'] == [{'condition': 'state', 'entity': 'sensor.alarm', 'state_not': 'ok'}]


def test_gauge_segments_match_the_mockup():
    dash = hd.build(full_mapping())
    gauge = [n for n in walk(dash) if n.get('type') == 'gauge'][0]
    assert gauge['needle'] is True and (gauge['min'], gauge['max']) == (0, 60)
    assert [s['from'] for s in gauge['segments']] == [0, 7, 21]


def test_controls_cover_every_number_and_buttons_confirm():
    dash = hd.build(full_mapping())
    ctl = [v for v in dash['views'] if v['title'] == 'Controls'][0]
    numbers = set(e.object_id for e in hd.ENTITIES if e.component == 'number')
    placed = set()
    for n in walk(ctl):
        if n.get('type') == 'tile' and any(f['type'] == 'numeric-input' for f in n.get('features', [])):
            placed.add(n['entity'])
    assert placed == set(full_mapping()[o] for o in numbers)
    presses = [n for n in walk(ctl) if n.get('type') == 'tile' and 'tap_action' in n]
    assert len(presses) == 2
    for n in presses:
        assert n['tap_action']['perform_action'] == 'button.press'
        assert n['tap_action']['confirmation']['text']
        assert n['tap_action']['target'] == {'entity_id': n['entity']}


def test_controls_view_limited_to_admin_users():
    dash = hd.build(full_mapping(), admin_users=['abc123', 'def456'])
    ctl = [v for v in dash['views'] if v['title'] == 'Controls'][0]
    assert ctl['visible'] == [{'user': 'abc123'}, {'user': 'def456'}]
    assert 'visible' not in hd.build(full_mapping())['views'][1]


def test_header_and_sections_view():
    view = hd.build(full_mapping(), title='Pellet burner')['views'][0]
    assert view['type'] == 'sections' and view['max_columns'] == 3
    assert view['header']['card']['content'] == '# Pellet burner'
    assert len(view['badges']) == 3


# ---- entity id resolution ---------------------------------------------------------

@pytest.mark.parametrize('device', ['Scotte Pellet Burner', 'Pellmon', ''])
def test_resolve_matches_every_entity_despite_overlapping_names(device):
    lines = friendly_lines(device) if device else [(e.component + '.' + hd.slug(e.name), e.name) for e in hd.ENTITIES]
    mapping, missing, ambiguous = hd.resolve(list(hd.ENTITIES), lines)
    assert not missing and not ambiguous
    assert len(set(mapping.values())) == len(hd.ENTITIES)  # no id used twice
    assert mapping['power_percent'].endswith('_power') or mapping['power_percent'] == 'sensor.power'
    # "Magazine Content" (sensor) and "Set Magazine Content" (number) never swap
    assert mapping['magazine_content'].startswith('sensor.')
    assert mapping['magazine_content_set'].startswith('number.')
    for oid, entity_id in mapping.items():
        assert entity_id.startswith(hd.BY_OBJECT_ID[oid].component + '.')


def test_resolve_reports_missing_and_ambiguous():
    lines = friendly_lines()
    lines = [l for l in lines if 'Silo Level' not in l[1]]
    mapping, missing, ambiguous = hd.resolve(list(hd.ENTITIES), lines)
    assert 'silo_level' in missing and 'silo_level' not in mapping
    # two candidates that both only match by suffix
    lines = [('sensor.a_flow', 'A Water Flow'), ('sensor.b_flow', 'B Water Flow')]
    mapping, missing, ambiguous = hd.resolve([hd.BY_OBJECT_ID['flow']], lines)
    assert ambiguous == {'flow': ['sensor.a_flow', 'sensor.b_flow']}


def test_parse_ids_formats():
    multi = 'sensor.power | Power\nnumber.min_power | Min Power\n'
    single = 'sensor.power | Power number.min_power | Min Power'
    assert hd.parse_ids(multi) == hd.parse_ids(single) == ('lines', [('sensor.power', 'Power'), ('number.min_power', 'Min Power')])
    kind, data = hd.parse_ids(json.dumps({'power_percent': 'sensor.p'}))
    assert kind == 'map' and data == {'power_percent': 'sensor.p'}


# ---- YAML emitter ------------------------------------------------------------------

def test_scalars_are_quoted_when_needed():
    assert hd._scalar('sensor.power') == 'sensor.power'
    assert hd._scalar('mdi:fire') == 'mdi:fire'
    assert hd._scalar('#c4571a') == '"#c4571a"'
    assert hd._scalar('on') == '"on"' and hd._scalar('ok') == 'ok'
    assert hd._scalar('24h') == '"24h"' and hd._scalar('nan') == '"nan"'
    assert hd._scalar(True) == 'true' and hd._scalar(60) == '60' and hd._scalar(None) == 'null'


def test_yaml_round_trip():
    yaml = pytest.importorskip('yaml')
    for kwargs in ({}, {'apex': False}, {'admin_users': ['u1']}, {'capacity': 500, 'controls': False}):
        dash = hd.build(full_mapping(), **kwargs)
        assert yaml.safe_load(hd.dump(dash)) == dash


def test_yaml_multiline_data_generator_round_trips():
    yaml = pytest.importorskip('yaml')
    data = {'a': [{'b': 'x\ny', 'c': 1}], 'd': {}, 'e': []}
    assert yaml.safe_load(hd.dump(data)) == data


# ---- command line --------------------------------------------------------------------

def test_cli_with_ids_file(tmp_path, capsys):
    yaml = pytest.importorskip('yaml')
    ids = tmp_path / 'ids.txt'
    ids.write_text('\n'.join('%s | %s' % l for l in friendly_lines() if 'Silo' not in l[1]))
    out = tmp_path / 'dash.yaml'
    assert hd.main(['--ids', str(ids), '-o', str(out), '--include', 'flow']) == 0
    dash = yaml.safe_load(out.read_text())
    used = hd.collect_entities(dash)
    assert not [u for u in used if 'silo' in u]
    assert any(u.endswith('water_flow') for u in used)
    assert 'left off the page' in capsys.readouterr().err
    assert out.read_text().startswith('# PellMon dashboard')


def test_cli_map_override_and_errors(tmp_path):
    out = tmp_path / 'd.yaml'
    assert hd.main(['--map', 'power_percent=sensor.my_power', '-o', str(out)]) == 0
    assert 'sensor.my_power' in out.read_text()
    assert hd.main(['--map', 'nonsense=sensor.x', '-o', str(out)]) == 2
    assert hd.main(['--include', 'bogus', '-o', str(out)]) == 2


def test_committed_example_matches_the_generator(tmp_path):
    out = tmp_path / 'example.yaml'
    assert hd.main(['--silo-capacity', '220', '-o', str(out)]) == 0
    with open(os.path.join(ROOT, 'config', 'ha-dashboard.example.yaml'), encoding='utf-8') as f:
        assert f.read() == out.read_text(), 'regenerate: python tools/ha_dashboard.py --silo-capacity 220 -o config/ha-dashboard.example.yaml'


def test_heading_badges_use_only_documented_keys():
    """Heading badges take show_icon/show_state; show_name belongs to view badges only."""
    dash = hd.build(full_mapping())
    for n in walk(dash):
        if n.get('type') == 'heading':
            for b in n.get('badges', []):
                assert set(b) <= {'type', 'entity', 'name', 'icon', 'color', 'show_icon', 'show_state',
                                  'state_content'}


def test_silo_chart_section_is_two_columns_wide():
    """column_span is a section key in the Home Assistant frontend (data/lovelace/config/section.ts)."""
    secs = hd.build(full_mapping())['views'][0]['sections']
    silo = [x for x in secs if any(c.get('heading') == 'Silo history and forecast' for c in x['cards'])][0]
    assert silo['column_span'] == 2
