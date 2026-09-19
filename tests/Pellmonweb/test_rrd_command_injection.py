"""Regression tests for the shell=True command injection in /graph.

Imports only Pellmonweb.rrdcommand (stdlib-only); never pellmonweb (dbus/gi).
"""
import pathlib

import pytest

import importlib.util

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Load by file path: importing the Pellmonweb package runs __init__, which needs cherrypy.
_spec = importlib.util.spec_from_file_location(
    "rrdcommand_under_test", REPO_ROOT / "src" / "Pellmonweb" / "rrdcommand.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
build_graph_command = _mod.build_graph_command
valid_bgcolor = _mod.valid_bgcolor
valid_color = _mod.valid_color
valid_name = _mod.valid_name
META = [';', '|', '&', '$', '`', '>', '<', '\n', '\\', "'", '"', '(', ')', '{', '}', '*']
LINE = {'name': 'temp', 'color': '#00ff00', 'ds_name': 'ds_temp'}


def build(**kw):
    kw.setdefault('lines', '__all__')
    kw.setdefault('graph_lines', [dict(LINE)])
    return build_graph_command('/tmp/x.rrd', **kw)


def test_basic_shape():
    cmd = build()
    assert cmd[:2] == ['rrdtool', 'graph']
    assert 'DEF:temp=/tmp/x.rrd:ds_temp:AVERAGE' in cmd
    assert 'LINE1:temp#00ff00:temp' in cmd
    assert all(isinstance(a, str) for a in cmd)


def test_bgcolor_valid():
    cmd = build(bgcolor='ff0000')
    i = cmd.index('--color')
    assert cmd[i + 1] == 'BACK#ff0000'


@pytest.mark.parametrize('bad', ['0; rm -rf /', '$(id)', 'aa`id`bb',
                                 'ff0000 --imginfo /etc/passwd', 'ff0000\n', 'gggggg', ''])
def test_bgcolor_rejected(bad):
    cmd = build(bgcolor=bad)
    assert '--color' not in cmd
    assert not any('imginfo' in a for a in cmd)


def test_legends():
    assert '--no-legend' in build(legends='no')
    assert '--no-legend' not in build(legends='yes')


@pytest.mark.parametrize('name', ['temp; id', 'a b', 'a:b'])
def test_bad_line_name_skipped(name):
    cmd = build(graph_lines=[{'name': name, 'color': '#00ff00', 'ds_name': 'ok'}])
    assert not any(a.startswith(('DEF:', 'LINE1:')) for a in cmd)


@pytest.mark.parametrize('color,ok', [('#00ff00', True), ('00ff00', True), ('red; id', False),
                                      ('00ff00 XPORT:x', False), ('#gggggg', False)])
def test_line_color(color, ok):
    cmd = build(graph_lines=[{'name': 'a', 'color': color, 'ds_name': 'b'}])
    assert any(a.startswith('LINE1:') for a in cmd) == ok


@pytest.mark.parametrize('ds', ['a:b', 'a;b', 'a b'])
def test_bad_ds_skipped(ds):
    cmd = build(graph_lines=[{'name': 'a', 'color': '#00ff00', 'ds_name': ds}])
    assert not any(a.startswith('DEF:') for a in cmd)


def test_logtick():
    assert not any('tickmark' in a for a in build(logtick='badname;id'))
    assert any('tickmark' in a for a in build(logtick='valid_ds'))


def test_numeric_params_never_verbatim():
    cmd = build(width='1;id', height='$(id)', graphtime='x', time_start='y', time_end='z')
    assert not any('$' in a or ';' in a for a in cmd)
    assert cmd[cmd.index('--width') + 1] == '440'
    assert cmd[cmd.index('--height') + 1] == '400'


def test_right_axis_sanitized():
    cmd = build(right_axis='2:1')
    assert cmd[cmd.index('--right-axis') + 1] == '2.0:1.0'
    assert '--right-axis' not in build(right_axis='1:0; id')


def test_scale_line():
    cmd = build(graph_lines=[dict(LINE, scale='0:1;id')])
    assert any(a.startswith('CDEF:') for a in cmd)
    assert not any(';' in a for a in cmd)


@pytest.mark.parametrize('ch', META)
def test_metachar_sweep(ch):
    payload = 'a' + ch + 'b'
    cmd = build(bgcolor=payload, logtick=payload,
                graph_lines=[{'name': payload, 'color': payload, 'ds_name': payload},
                             {'name': 'ok', 'color': payload, 'ds_name': 'ok'},
                             {'name': 'ok2', 'color': '#00ff00', 'ds_name': payload}])
    assert not any(payload in a for a in cmd)


def test_validators():
    assert valid_bgcolor('abcdef') and not valid_bgcolor('abcde')
    assert valid_name('a_1') and not valid_name('a:b')
    assert valid_color('00ff00') == '#00ff00'


def test_no_shell_true_in_pellmonweb():
    src = (REPO_ROOT / 'src' / 'Pellmonweb' / 'pellmonweb.py').read_text(encoding='utf-8')
    assert 'shell=True' not in src
