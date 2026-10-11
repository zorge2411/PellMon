# -*- coding: utf-8 -*-
"""silolevel plugin: estimate branches, unknown-on-error and silo_empty_date (Phase 11 D-01..D-03)."""

import json
import logging
from datetime import datetime, timedelta

import pytest

from Pellmonsrv.plugins import silolevel as silo

NOW = 1700007200

XPORT = """{
  about: 'RRDtool graph JSON output',
  meta: {
    start: 1700000000,
    step: 3600,
    end: 1700007200,
    legend: [
      'level'
    ]
  },
  data: [
    [ 100 ],
    [ 95 ],
    [ 90 ]
  ]
}
"""


class FakePopen(object):
    def __init__(self, argv, **kw):
        self.argv = argv

    def communicate(self):
        if 'last' in self.argv:
            return (('%d\n' % NOW).encode(), None)
        return (XPORT.encode(), None)


def bars(label, values):
    return json.dumps({'bardata': [{'label': label, 'data': [[i, v] for i, v in enumerate(values)]}]})


class FakeDb(object):
    def __init__(self, week=None, eight=None, year=None, fail=False):
        self.values = {
            'consumptionData7d': bars('last 7', week or [0] * 8),
            'consumptionData8w': bars('last 8', eight or [0] * 8),
            'consumptionData1y': bars('last 12', year or [0] * 12),
        }
        self.fail = fail

    def get_value(self, name):
        if self.fail:
            raise ValueError('rrd gone')
        return self.values[name]


class Conf(object):
    db = '/nonexistent.rrd'
    poll_interval = 30
    item_to_ds_name = {'feeder_time': 'ds0', 'feeder_capacity': 'ds1'}


def make_plugin(monkeypatch, db):
    p = silo.silolevelplugin()
    p.glob = {'conf': Conf()}
    p.db = db
    p.updateTime = 0
    p.siloData = None
    p.silo_days_left = None
    p.last_prediction_error = None
    p.silo_level = 0
    p.feeder_time = 'ds0'
    p.feeder_capacity = 'ds1'
    settings = {'silo_reset_level': '100', 'silo_reset_time': '01/01/14 12:00'}
    monkeypatch.setattr(p, 'load_setting', lambda item: settings[item])
    monkeypatch.setattr(silo.subprocess, 'Popen', FakePopen)
    return p


def test_last_week_estimate(monkeypatch):
    p = make_plugin(monkeypatch, FakeDb(week=[0, 10, 10, 10, 10, 10, 10, 0]))
    data = json.loads(p.getItem('siloLevelData'))
    assert data['silo_level'] == 90
    assert 8 <= int(data['silo_days_left']) <= 10
    assert p.getItem('silo_level') == '90'
    assert p.getItem('silo_days_left') == data['silo_days_left']
    assert data['graphdata'][-1]['label'] == 'future'


def test_no_consumption_data_gives_365(monkeypatch):
    p = make_plugin(monkeypatch, FakeDb())
    p.getItem('siloLevelData')
    assert p.getItem('silo_days_left') == '365'


def test_last_month_estimate(monkeypatch):
    p = make_plugin(monkeypatch, FakeDb(eight=[0, 0, 0, 5, 30, 30, 30, 30]))
    p.getItem('siloLevelData')
    assert int(p.getItem('silo_days_left')) > 0


def test_last_year_estimate_is_not_an_error(monkeypatch):
    p = make_plugin(monkeypatch, FakeDb(year=[50] + [0] * 11))
    p.getItem('siloLevelData')
    assert p.silo_days_left is not None
    assert int(p.getItem('silo_days_left')) >= 0


def test_prediction_error_is_unknown_not_zero(monkeypatch, caplog):
    p = make_plugin(monkeypatch, FakeDb(fail=True))
    with caplog.at_level(logging.WARNING, logger='pellMon'):
        data = json.loads(p.getItem('siloLevelData'))
        p.updateTime = 0
        p.getItem('siloLevelData')
    assert data['silo_days_left'] is None
    assert p.silo_days_left is None
    assert p.getItem('silo_days_left') == ''
    assert p.getItem('silo_empty_date') == ''
    # the same error is logged once, not on every poll
    assert len([r for r in caplog.records if 'prediction error' in r.getMessage()]) == 1


def test_error_clears_after_recovery(monkeypatch):
    db = FakeDb(fail=True)
    p = make_plugin(monkeypatch, db)
    p.getItem('siloLevelData')
    db.fail = False
    p.updateTime = 0
    p.getItem('siloLevelData')
    assert p.silo_days_left == '365'
    assert p.last_prediction_error is None


def test_empty_date_is_now_plus_days(monkeypatch):
    p = make_plugin(monkeypatch, FakeDb())
    p.getItem('siloLevelData')
    value = p.getItem('silo_empty_date')
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None
    delta = parsed - datetime.now().astimezone()
    assert abs(delta - timedelta(days=365)) < timedelta(minutes=5)


def test_empty_date_item_registered():
    names = [i['name'] for i in silo.itemList]
    assert 'silo_empty_date' in names
    assert 'silo_empty_date' in silo.itemTags and 'silo_empty_date' in silo.itemDescriptions
    assert [i for i in silo.itemList if i['name'] == 'silo_empty_date'][0]['type'] == 'R'
