"""D-08: saving a read-only config file yields a friendly message, not a raw OSError."""
import errno
import json

import cherrypy
import pytest

from Pellmonweb.pellmonconf import Pellmonconf


@pytest.fixture
def inst(tmp_path):
    conf = tmp_path / 'pellmon.conf'
    conf.write_text('[conf]\nconfig_dir=%s\n' % (tmp_path / 'conf.d'), encoding='utf-8')
    obj = Pellmonconf(config_file=str(conf), lookup=None)
    obj.dirs = {'pellmon.conf': str(tmp_path)}
    return obj


def _post():
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = {'Origin': 'http://localhost:8083', 'Host': 'localhost:8083'}


@pytest.mark.parametrize('code', [errno.EROFS, errno.EACCES, errno.EPERM])
def test_readonly_message(inst, cherrypy_request_ctx, mocker, code):
    _post()
    mocker.patch('codecs.open', side_effect=OSError(code, 'Read-only file system'))
    r = json.loads(inst.save('pellmon.conf', 'x'))
    assert r['success'] is False
    assert 'read-only' in r['error'].lower()
    assert 'pellmon.conf' in r['error']


def test_other_oserror_keeps_original_message(inst, cherrypy_request_ctx, mocker):
    _post()
    mocker.patch('codecs.open', side_effect=OSError(errno.ENOSPC, 'No space left on device'))
    r = json.loads(inst.save('pellmon.conf', 'x'))
    assert r['success'] is False
    assert 'No space left' in r['error']
    assert 'read-only' not in r['error'].lower()


def test_save_allowed_still_works(inst, cherrypy_request_ctx, tmp_path):
    _post()
    r = json.loads(inst.save('pellmon.conf', 'hello'))
    assert r == {'success': True}
    assert (tmp_path / 'pellmon.conf').read_text(encoding='utf-8') == 'hello'


def test_disallowed_filename_still_rejected(inst, cherrypy_request_ctx):
    _post()
    r = json.loads(inst.save('../../etc/passwd', 'x'))
    assert r['success'] is False
    assert 'read-only' not in str(r['error']).lower()
