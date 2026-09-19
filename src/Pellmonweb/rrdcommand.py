#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    Copyright (C) 2014  Anders Nylund

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

    Builds the rrdtool graph argument vector. stdlib only, so it is
    importable without dbus/gi/cherrypy.
"""
import re
from logging import getLogger

logger = getLogger('pellMon')

_HEX_COLOR = re.compile(r'\A[0-9A-Fa-f]{6}\Z')
_RRD_NAME = re.compile(r'\A[A-Za-z0-9_]{1,64}\Z')
_LINE_COLOR = re.compile(r'\A#?([0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?)\Z')


def valid_bgcolor(value):
    return isinstance(value, str) and bool(_HEX_COLOR.match(value))


def valid_name(value):
    return isinstance(value, str) and bool(_RRD_NAME.match(value))


def valid_color(value):
    """Return normalized '#rrggbb[aa]' or None."""
    if not isinstance(value, str):
        return None
    m = _LINE_COLOR.match(value)
    if not m:
        return None
    return '#' + m.group(1)


def _coerce_int(value, default, minimum=None, maximum=None):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _scale(line):
    scale = str(line['scale']).split(':')
    try:
        gain = float(scale[1])
        offset = float(scale[0])
    except (ValueError, IndexError):
        gain = 1
        offset = 0
    return gain, offset


def build_graph_command(db, graph_lines, lines, logtick=None, legends=None,
                        bgcolor=None, width=440, height=400, graphtime=None,
                        time_start='', time_end='', right_axis=None):
    cmd = ['rrdtool', 'graph', '-', '--disable-rrdtool-tag', '--border', '0']
    if legends == 'no':
        cmd.append('--no-legend')
    if bgcolor is not None:
        if valid_bgcolor(bgcolor):
            cmd += ['--color', 'BACK#' + bgcolor]
        else:
            logger.warning('rejected bgcolor argument: %r', bgcolor)
    cmd += ['--lower-limit', '0']
    if right_axis:
        try:
            gain, offset = str(right_axis).split(':')
            cmd += ['--right-axis', '%s:%s' % (float(gain), float(offset))]
        except (ValueError, TypeError):
            logger.warning('rejected right axis argument: %r', right_axis)
    cmd += ['--right-axis-format', '%1.0lf']
    width = _coerce_int(width, 440, 1, 5000)
    height = _coerce_int(height, 400, 1, 2000)
    graphtime = _coerce_int(graphtime, 0)
    time_start = _coerce_int(time_start, 0)
    time_end = _coerce_int(time_end, 0)
    cmd += ['--full-size-mode', '--width', str(width), '--height', str(height)]
    cmd += ['--end', '%s-%ss' % (graphtime, time_end)]
    cmd += ['--start', '%s-%ss' % (graphtime, time_start)]
    if logtick:
        if valid_name(logtick):
            cmd.append('DEF:tickmark=%s:%s:AVERAGE' % (db, logtick))
            cmd.append('TICK:tickmark#E7E7E7:1.0')
        else:
            logger.warning('rejected logtick: %r', logtick)
    for line in graph_lines:
        name = line.get('name')
        if not (lines == '__all__' or name in lines):
            continue
        color = valid_color(line.get('color'))
        if not (valid_name(name) and valid_name(line.get('ds_name')) and color):
            logger.warning('skipping graph line with invalid fields: %r', name)
            continue
        cmd.append('DEF:%s=%s:%s:AVERAGE' % (name, db, line['ds_name']))
        if 'scale' in line:
            gain, offset = _scale(line)
            cmd.append('CDEF:%s_s=%s,%d,+,%d,/' % (name, name, offset, gain))
            cmd.append('LINE1:%s_s%s:%s' % (name, color, name))
        else:
            cmd.append('LINE1:%s%s:%s' % (name, color, name))
    return [str(a) for a in cmd]
