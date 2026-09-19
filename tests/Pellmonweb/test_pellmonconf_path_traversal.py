"""Regression tests for arbitrary file read/write via Pellmonconf source()/save()."""
import json

import cherrypy
import pytest

from Pellmonweb.pellmonconf import Pellmonconf

PAYLOADS = ['/etc/passwd', 'C:\\Windows\\win.ini', '../../etc/passwd',
            'conf.d/../../../etc/passwd', None, '']


@pytest.fixture
def inst(tmp_path):
    conf = tmp_path / 'pellmon.conf'
    conf.write_text('[conf]\nconfig_dir=%s\n' % (tmp_path / 'conf.d'), encoding='utf-8')
    obj = Pellmonconf(config_file=str(conf), lookup=None)
    obj.dirs = {'pellmon.conf': str(tmp_path)}
    return obj


def test_source_allowed(inst):
    r = json.loads(inst.source('pellmon.conf'))
    assert 'data' in r and r['filename'] == 'pellmon.conf'


@pytest.mark.parametrize('name', PAYLOADS)
def test_source_rejected(inst, mocker, name):
    m = mocker.patch('codecs.open')
    r = json.loads(inst.source(name))
    assert 'error' in r and 'data' not in r
    m.assert_not_called()


@pytest.mark.parametrize('name', PAYLOADS)
def test_save_rejected(inst, cherrypy_request_ctx, mocker, name):
    cherrypy.request.method = 'POST'
    m = mocker.patch('codecs.open')
    r = json.loads(inst.save(name, 'x'))
    assert r['success'] is False
    m.assert_not_called()


def test_save_not_post(inst, cherrypy_request_ctx):
    cherrypy.request.method = 'GET'
    r = json.loads(inst.save('pellmon.conf', 'x'))
    assert r == {'success': False, 'error': {'msg': 'only POST'}}


def test_save_allowed(inst, cherrypy_request_ctx, tmp_path):
    cherrypy.request.method = 'POST'
    r = json.loads(inst.save('pellmon.conf', 'hello'))
    assert r == {'success': True}
    assert (tmp_path / 'pellmon.conf').read_text(encoding='utf-8') == 'hello'


def test_crafted_dirs_escape(inst, tmp_path):
    inst.dirs['../evil'] = str(tmp_path)
    with pytest.raises(ValueError):
        inst._resolve('../evil')
