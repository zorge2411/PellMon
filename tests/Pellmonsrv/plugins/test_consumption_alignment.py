# -*- coding: utf-8 -*-
"""Consumption bar chart alignment (quick task 261011-idv).

getItem computes the start time of each bar chart. Python 2 integer division rounded it
to the hour / local midnight / week / month grid; under Python 3 plain `/` made it a no-op
(start == now). Expected values below are the Python 2 (floor division) results."""

import time
from datetime import datetime

import pytest

from Pellmonsrv.plugins import consumption as cons

# tz, local wall clock, then expected `start` for 24h, 7d, 8w, 1y
CASES = [
    ('UTC', (2026, 3, 15, 14, 30, 25), (1773583200, 1773532800, 1773532800, 1772448804)),
    ('Europe/Helsinki', (2026, 3, 15, 14, 30, 25), (1773576000, 1773525600, 1773525600, 1772441604)),
    ('America/New_York', (2026, 3, 15, 14, 30, 25), (1773597600, 1773547200, 1773547200, 1772463204)),
    # clocks go back in Helsinki that day
    ('Europe/Helsinki', (2026, 10, 25, 12, 0, 0), (1792922400, 1792879200, 1792879200, 1790849826)),
    # just after a month boundary
    ('Europe/Helsinki', (2026, 11, 1, 0, 5, 0), (1793484000, 1793484000, 1792965600, 1790936226)),
]
ITEMS = ('consumptionData24h', 'consumptionData7d', 'consumptionData8w', 'consumptionData1y')


def make_plugin(monkeypatch, now):
    p = cons.Consumption_plugin()
    p.updatetime24h = p.updatetime7d = p.updatetime8w = p.updatetime1y = 0
    p.scalar_cache = {}
    starts = []

    def barchartdata(start=0, period=3600, bars=1):
        starts.append(start)
        return '{}'
    monkeypatch.setattr(p, 'barchartdata', barchartdata)
    monkeypatch.setattr(p, '_now', lambda: now)
    p.starts = starts
    return p


@pytest.mark.parametrize('tz,wall,expected', CASES)
def test_start_is_aligned(tz, wall, expected, monkeypatch):
    monkeypatch.setenv('TZ', tz)
    time.tzset()
    try:
        now = int(datetime(*wall).timestamp())
        for item, want in zip(ITEMS, expected):
            p = make_plugin(monkeypatch, now)
            p.getItem(item)
            assert p.starts == [want], (item, tz, wall)
            assert isinstance(p.starts[0], int)
    finally:
        monkeypatch.delenv('TZ')
        time.tzset()


@pytest.mark.parametrize('tz', ['UTC', 'Europe/Helsinki', 'America/New_York'])
def test_start_never_after_now_and_within_one_period(tz, monkeypatch):
    monkeypatch.setenv('TZ', tz)
    time.tzset()
    try:
        # a plain (non DST-change) day; the offset trick is exact there for whole-hour zones
        base = int(datetime(2026, 5, 20, 8, 0, 0).timestamp())
        for k in range(0, 8 * 3600, 1800):
            now = base + k
            p = make_plugin(monkeypatch, now)
            p.getItem('consumptionData24h')
            assert now - 3600 < p.starts[0] <= now
            assert p.starts[0] % 3600 == 0
    finally:
        monkeypatch.delenv('TZ')
        time.tzset()
