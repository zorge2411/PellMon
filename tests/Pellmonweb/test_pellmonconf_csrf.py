"""Same-origin enforcement for Pellmonconf.save(), and web bind-host resolution."""
import ast
import configparser
import json
import os
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / 'src' / 'Pellmonweb'


@pytest.fixture
def inst(tmp_path):
    from Pellmonweb.pellmonconf import Pellmonconf
    conf = tmp_path / 'pellmon.conf'
    conf.write_text('[conf]\nconfig_dir=%s\n' % (tmp_path / 'conf.d'), encoding='utf-8')
    obj = Pellmonconf(config_file=str(conf), lookup=None)
    obj.dirs = {'pellmon.conf': str(tmp_path)}
    return obj


def _post(cherrypy_request_ctx, **headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)


def test_cross_origin_rejected(inst, cherrypy_request_ctx, mocker):
    _post(cherrypy_request_ctx, Origin='http://evil.example', Host='localhost:8083')
    m = mocker.patch('codecs.open')
    r = json.loads(inst.save('pellmon.conf', 'x'))
    assert r['success'] is False
    m.assert_not_called()


def test_missing_origin_and_referer_rejected(inst, cherrypy_request_ctx, mocker):
    _post(cherrypy_request_ctx, Host='localhost:8083')
    m = mocker.patch('codecs.open')
    assert json.loads(inst.save('pellmon.conf', 'x'))['success'] is False
    m.assert_not_called()


def test_same_origin_accepted(inst, cherrypy_request_ctx, tmp_path):
    _post(cherrypy_request_ctx, Origin='http://localhost:8083', Host='localhost:8083')
    assert json.loads(inst.save('pellmon.conf', 'ok')) == {'success': True}
    assert (tmp_path / 'pellmon.conf').read_text(encoding='utf-8') == 'ok'


def test_referer_fallback_accepted(inst, cherrypy_request_ctx):
    _post(cherrypy_request_ctx, Referer='http://localhost:8083/page', Host='localhost:8083')
    assert json.loads(inst.save('pellmon.conf', 'ok')) == {'success': True}


def test_no_debug_environment():
    for name in ('pellmonweb.py', 'pellmonconf.py'):
        assert 'server.environment' not in (SRC / name).read_text(encoding='utf-8')


# The resolver is extracted from the module source so it can be tested without
# importing pellmonweb.py (which needs cherrypy, dbus and gi).
@pytest.fixture
def resolver():
    tree = ast.parse((SRC / 'pellmonweb.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_resolve_socket_host')
    ns = {'os': os}
    exec(compile(ast.Module([fn], []), 'pellmonweb.py', 'exec'), ns)
    return ns['_resolve_socket_host']


def _parser(text=''):
    p = configparser.ConfigParser()
    p.read_string(text)
    return p


def test_default_host_is_localhost(resolver, monkeypatch):
    monkeypatch.delenv('PELLMON_WEB_HOST', raising=False)
    assert resolver(_parser()) == '127.0.0.1'


def test_env_host(resolver, monkeypatch):
    monkeypatch.setenv('PELLMON_WEB_HOST', '0.0.0.0')
    assert resolver(_parser()) == '0.0.0.0'


def test_config_host_wins_over_env(resolver, monkeypatch):
    monkeypatch.setenv('PELLMON_WEB_HOST', '0.0.0.0')
    assert resolver(_parser('[conf]\nhost = 192.168.1.5\n')) == '192.168.1.5'
