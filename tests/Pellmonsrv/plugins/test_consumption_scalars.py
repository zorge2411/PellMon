# -*- coding: utf-8 -*-
"""consumption plugin scalar items (Phase 11 D-06)."""

import os
import time
from datetime import datetime

import pytest

from Pellmonsrv.plugins import consumption as cons


@pytest.fixture(params=['UTC', 'Europe/Helsinki', 'America/New_York'])
def tz(request, monkeypatch):
    monkeypatch.setenv('TZ', request.param)
    time.tzset()
    yield request.param
    monkeypatch.delenv('TZ')
    time.tzset()


def local_ts(*args):
    return datetime(*args).timestamp()


def make_plugin(monkeypatch, now, totals):
    p = cons.Consumption_plugin()
    p.scalar_cache = {}
    p.calls = []
    clock = {'now': now}
    monkeypatch.setattr(p, '_now', lambda: clock['now'])

    def rrd_total(start, end, cache=True):
        p.calls.append((start, end, cache))
        v = totals.pop(0) if isinstance(totals, list) else totals
        return v
    monkeypatch.setattr(p, 'rrd_total', rrd_total)
    p.clock = clock
    return p


def test_items_registered():
    names = [i['name'] for i in cons.itemList]
    for n in cons.SCALAR_ITEMS:
        assert n in names
    assert all(i['unit'] == 'kg' and i['type'] == 'R' for i in cons.itemList if i['name'] in cons.SCALAR_ITEMS)


def test_windows(tz, monkeypatch):
    now = local_ts(2026, 3, 15, 14, 30, 0)
    p = make_plugin(monkeypatch, now, '(12.34)')
    assert p.getItem('consumption_today') == '12.3'
    assert p.getItem('consumption_7d') == '12.3'
    assert p.getItem('consumption_month') == '12.3'
    starts = [c[0] for c in p.calls]
    assert starts == [int(local_ts(2026, 3, 15)), int(now) - 7 * 86400, int(local_ts(2026, 3, 1))]
    assert all(c[1] == int(now) and c[2] is False for c in p.calls)


def test_month_boundary(tz, monkeypatch):
    now = local_ts(2026, 11, 1, 0, 5, 0)
    p = make_plugin(monkeypatch, now, '(1.0)')
    p.getItem('consumption_month')
    assert p.calls[0][0] == int(local_ts(2026, 11, 1))
    now = local_ts(2026, 10, 31, 23, 59, 0)
    p = make_plugin(monkeypatch, now, '(1.0)')
    p.getItem('consumption_month')
    assert p.calls[0][0] == int(local_ts(2026, 10, 1))


def test_dst_change_day_starts_at_local_midnight(monkeypatch):
    monkeypatch.setenv('TZ', 'Europe/Helsinki')
    time.tzset()
    try:
        now = local_ts(2026, 10, 25, 12, 0, 0)  # clocks go back this day
        p = make_plugin(monkeypatch, now, '(1.0)')
        p.getItem('consumption_today')
        assert p.calls[0][0] == int(local_ts(2026, 10, 25))
    finally:
        monkeypatch.delenv('TZ')
        time.tzset()


def test_cached_for_five_minutes(monkeypatch):
    p = make_plugin(monkeypatch, 1_800_000_000, ['(5.0)', '(6.0)'])
    assert p.getItem('consumption_7d') == '5.0'
    p.clock['now'] += 299
    assert p.getItem('consumption_7d') == '5.0'
    assert len(p.calls) == 1
    p.clock['now'] += 2
    assert p.getItem('consumption_7d') == '6.0'
    assert len(p.calls) == 2


@pytest.mark.parametrize('answer', [None, '(nan)', '(garbage)', ''])
def test_unknown_not_zero(monkeypatch, answer):
    p = make_plugin(monkeypatch, 1_800_000_000, answer)
    assert p.getItem('consumption_today') == ''


def test_existing_items_unaffected(monkeypatch):
    p = make_plugin(monkeypatch, 1_800_000_000, '(1.0)')
    assert p.getItem('nonsense') == 'Error'
