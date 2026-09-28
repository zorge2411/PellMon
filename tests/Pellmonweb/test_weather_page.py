"""Weather (OpenWeatherMap) controller: auth/CSRF guards, write-only API key, status mapping."""
import json
import logging
import time

import pytest

SENTINEL = 's3cret-XYZ'
ORIGIN = dict(Origin='http://localhost:8081', Host='localhost:8081')

from Pellmonweb import weather as wx  # noqa: E402


class FakeTemplate:
    def __init__(self, sink):
        self.sink = sink

    def render(self, **kw):
        self.sink.append(kw)
        return kw


class FakeLookup:
    def __init__(self):
        self.calls = []

    def get_template(self, name):
        assert name == 'weather.html'
        return FakeTemplate(self.calls)


class FakeDbus:
    def __init__(self, fail=False, stored=None, status=None, set_result=None):
        self.fail = fail
        self.stored = stored if stored is not None else dict(has_apikey=False, available=True,
                                                              enabled=False, unit='celsius', location='')
        self.status = status if status is not None else dict(available=True, state='disabled')
        self.set_result = set_result if set_result is not None else dict(ok=True)
        self.set_calls = []

    def _check(self):
        if self.fail:
            raise RuntimeError('down')

    def owm_get_settings(self):
        self._check()
        return dict(self.stored)

    def owm_set_settings(self, d):
        self._check()
        self.set_calls.append(d)
        return self.set_result

    def owm_status(self):
        self._check()
        return self.status

    def any_call(self):
        return bool(self.set_calls)


def _make(creds=True, **kw):
    dbus = FakeDbus(**kw)
    c = wx.Weather(FakeLookup(), dbus, credentials={'u': 'p'} if creds else {})
    return c, dbus


def _post(**headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)


def _valid(**kw):
    form = dict(enabled='1', location='copenhagen,dk', unit='celsius', apikey='a1b2c3d4e5f6a7b8')
    form.update(kw)
    return form


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


def _redirect(c, **form):
    import cherrypy
    with pytest.raises(cherrypy.HTTPRedirect) as exc:
        c.save(**form)
    return exc.value


# ---- auth and CSRF ----

def test_auth_required_on_all_routes():
    for name in ('index', 'save'):
        assert 'auth.require' in getattr(wx.Weather, name)._cp_config


def test_get_rejected_without_dbus(cherrypy_request_ctx):
    import cherrypy
    cherrypy.request.method = 'GET'
    c, d = _make()
    ctx = c.save(**_valid())
    assert ctx['msg'] == wx.MSG_REJECTED
    assert not d.any_call()


def test_cross_origin_403(cherrypy_request_ctx, caplog):
    import cherrypy
    _post(Origin='http://evil.example', Host='localhost:8081')
    c, d = _make()
    with caplog.at_level(logging.WARNING, logger='pellMon'):
        ctx = c.save(**_valid(apikey=SENTINEL))
    assert cherrypy.response.status == 403
    assert not d.any_call()
    assert any('evil.example' in r.getMessage() for r in _warnings(caplog))
    assert SENTINEL not in caplog.text
    assert ctx['msg'] == wx.MSG_REJECTED


def test_headerless_post_rejected(cherrypy_request_ctx):
    _post(Host='localhost:8081')
    c, d = _make()
    c.save(**_valid())
    assert not d.any_call()


# ---- save ----

def test_valid_save_payload_and_redirect(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    r = _redirect(c, **_valid())
    p = d.set_calls[0]
    assert p == {'enabled': True, 'location': 'copenhagen,dk', 'unit': 'celsius', 'apikey': 'a1b2c3d4e5f6a7b8'}
    assert r.status == 303
    assert r.urls[0].endswith('/weather/?saved=1')


def test_saved_off_when_disabled(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    form = _valid()
    del form['enabled']
    r = _redirect(c, **form)
    assert r.urls[0].endswith('?saved=off')


def test_blank_apikey_sends_no_key_stored_key_kept(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(stored=dict(has_apikey=True, available=True, enabled=True, unit='celsius', location='copenhagen,dk'))
    _redirect(c, **_valid(apikey=''))
    p = d.set_calls[0]
    assert 'apikey' not in p and 'clear_apikey' not in p


def test_clear_apikey_checked_sends_clear_flag(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(stored=dict(has_apikey=True, available=True, enabled=True, unit='celsius', location='copenhagen,dk'))
    _redirect(c, **_valid(apikey='', clear_apikey='1', enabled=''))
    p = d.set_calls[0]
    assert p.get('clear_apikey') is True and 'apikey' not in p


def test_set_result_not_active_gives_not_active_message(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(set_result=dict(ok=False, available=False, errors={}))
    ctx = c.save(**_valid())
    assert ctx['msg'] == wx.MSG_NOT_ACTIVE


def test_daemon_down_on_save(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(fail=True)
    ctx = c.save(**_valid())
    assert ctx['msg'] == wx.MSG_DAEMON_DOWN and ctx['msg_level'] == 'danger'


def test_daemon_errors_rendered(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(set_result=dict(ok=False, errors={'apikey': 'API key must be 16 to 64 letters or digits.'}))
    ctx = c.save(**_valid())
    assert ctx['errors'] == {'apikey': 'API key must be 16 to 64 letters or digits.'}
    assert ctx['msg'] == wx.MSG_INVALID


def test_auth_disabled_refuses_valid(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(creds=False)
    ctx = c.save(**_valid())
    assert ctx['msg'] == wx.MSG_AUTH_DISABLED and not d.any_call()


def test_invalid_local_validation_no_dbus_call(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.save(**_valid(unit='kelvin2'))
    assert not d.any_call()
    assert 'unit' in ctx['errors']
    assert ctx['msg'] == wx.MSG_INVALID


def test_apikey_never_echoed_and_reentered_flag(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.save(**_valid(unit='kelvin2', apikey=SENTINEL))
    assert 'apikey' not in ctx['settings']
    assert ctx['apikey_reentered'] is True
    assert SENTINEL not in json.dumps(ctx, default=str)


def test_sentinel_never_logged(cherrypy_request_ctx, caplog):
    _post(**ORIGIN)
    c, d = _make()
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        r = _redirect(c, **_valid(apikey='s3cretsecretkey1'))  # 16 chars, valid format
        ctx = c.save(**_valid(unit='kelvin2', apikey=SENTINEL))  # invalid format, renders instead
        c.index()
    assert SENTINEL not in caplog.text
    assert 's3cretsecretkey1' not in caplog.text


def test_index_saved_messages(cherrypy_request_ctx):
    c, _ = _make()
    ctx = c.index(saved='1')
    assert ctx['msg'] == wx.MSG_SAVED and ctx['msg_level'] == 'success'
    ctx = c.index(saved='off')
    assert ctx['msg'] == wx.MSG_SAVED_OFF and ctx['msg_level'] == 'success'


def test_index_context(cherrypy_request_ctx):
    c, _ = _make(stored=dict(has_apikey=True, available=True, enabled=True, unit='celsius',
                             location='aarhus,dk'))
    ctx = c.index()
    assert ctx['active_page'] == 'weather' and ctx['has_apikey'] is True
    assert ctx['settings']['location'] == 'aarhus,dk' and ctx['auth_configured'] is True
    assert ctx['available'] is True and ctx['daemon_down'] is False


def test_index_daemon_down(cherrypy_request_ctx):
    c, _ = _make(fail=True)
    ctx = c.index()
    assert ctx['daemon_down'] is True and ctx['msg'] == wx.MSG_DAEMON_DOWN


# ---- status_view ----

def test_status_daemon_down():
    v = wx.status_view({}, None, daemon_down=True)
    assert v['text'] == wx.STATUS_DAEMON_DOWN


def test_status_not_active():
    v = wx.status_view({}, dict(available=False))
    assert v['text'] == wx.STATUS_NOT_ACTIVE


def test_status_off():
    v = wx.status_view({}, dict(available=True, state='disabled'))
    assert (v['word'] + ' ' + v['text']).strip() == wx.STATUS_OFF


def test_status_no_key():
    v = wx.status_view({}, dict(available=True, state='no_key'))
    assert (v['word'] + ' ' + v['text']).strip() == wx.STATUS_NO_KEY


def test_status_waiting_with_location():
    v = wx.status_view({}, dict(available=True, state='waiting', location='aarhus,dk'))
    assert (v['word'] + ' ' + v['text']).strip() == wx.STATUS_WAITING % 'aarhus,dk'


def test_status_ok_with_stamp():
    ts = time.mktime((2026, 9, 25, 13, 4, 5, 0, 0, -1))
    v = wx.status_view({}, dict(available=True, state='ok', location='aarhus,dk', last_fetch=ts))
    assert (v['word'] + ' ' + v['text']).strip() == wx.STATUS_OK % ('aarhus,dk', '13:04:05')
    assert v['title'] == '2026-09-25 13:04:05'


def test_status_error_known_and_unknown_reason():
    v = wx.status_view({}, dict(available=True, state='error', reason='invalid API key'))
    assert (v['word'] + ' ' + v['text']).strip() == wx.STATUS_ERROR % 'invalid API key'
    v = wx.status_view({}, dict(available=True, state='error', reason='Traceback secret'))
    assert 'unknown error (see the server log)' in v['text']
    assert 'secret' not in v['text']


def test_copy_strings_present_in_source():
    from pathlib import Path
    src = Path(wx.__file__).read_text(encoding='utf-8')
    for s in ('Settings saved. The weather is updated within a few seconds.',
              'Settings saved. OpenWeatherMap is off.',
              'Could not save. Fix the highlighted fields and try again.',
              'Could not save the settings. Sign in again and retry.',
              'Saving is disabled until web login credentials are configured.',
              'unknown error (see the server log)'):
        assert s in src, s
    assert src.count('@require()') >= 2 and 'check_same_origin()' in src


# ---- Task 3: Dbus_handler proxies, mount, real-template render ----

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = (ROOT / 'src' / 'Pellmonweb' / 'pellmonweb.py').read_text(encoding='utf-8')
INIT_SRC = (ROOT / 'src' / 'Pellmonweb' / '__init__.py').read_text(encoding='utf-8')
TREE = ast.parse(WEB_SRC)
PROXIES = {'owm_get_settings': 'GetOwmSettings', 'owm_set_settings': 'SetOwmSettings',
           'owm_status': 'GetOwmStatus'}


def _class(name):
    return next(n for n in ast.walk(TREE) if isinstance(n, ast.ClassDef) and n.name == name)


def _method(cls, name):
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


@pytest.mark.parametrize('name,call', sorted(PROXIES.items()))
def test_dbus_handler_proxy_shape(name, call):
    src = ast.get_source_segment(WEB_SRC, _method(_class('Dbus_handler'), name))
    assert 'with self.lock' in src
    assert 'remote_object.%s(' % call in src
    assert "dbus_interface ='org.pellmon.int'" in src
    assert 'DbusNotConnected("server not running")' in src
    assert 'log' not in src


def test_weather_mounted_and_imported():
    init = ast.get_source_segment(WEB_SRC, _method(_class('PellMonWeb'), '__init__'))
    assert 'self.weather = Weather(lookup, dbus, credentials)' in init
    assert 'from Pellmonweb import *' in WEB_SRC
    assert 'from .weather import Weather' in INIT_SRC


def test_dbus_handler_proxies_raise_when_disconnected():
    pytest.importorskip('cherrypy')
    pytest.importorskip('dbus')
    pytest.importorskip('gi')
    import importlib
    import threading
    web = importlib.import_module('Pellmonweb.pellmonweb')
    h = web.Dbus_handler.__new__(web.Dbus_handler)
    h.lock = threading.Lock()
    h.remote_object = None
    for name in PROXIES:
        args = ({},) if name == 'owm_set_settings' else ()
        with pytest.raises(web.DbusNotConnected):
            getattr(h, name)(*args)


def test_real_template_render_hides_apikey_and_has_password_input(cherrypy_request_ctx):
    from mako.lookup import TemplateLookup
    html_dir = ROOT / 'src' / 'Pellmonweb' / 'html'
    dbus = FakeDbus(stored=dict(has_apikey=True, available=True, enabled=True, unit='celsius',
                                location='aarhus,dk'))
    c = wx.Weather(TemplateLookup(directories=[str(html_dir)]), dbus, credentials={'u': 'p'})
    out = c.index()
    assert 'Weather' in out
    assert '<input type="password" name="apikey"' in out or 'name="apikey"' in out
    assert 'placeholder="set"' in out
    assert SENTINEL not in out
    _post(**ORIGIN)
    bad = c.save(**_valid(unit='kelvin2', apikey=SENTINEL))
    assert SENTINEL not in bad and 'has-error' in bad


def test_layout_nav_has_weather_link():
    from mako.lookup import TemplateLookup
    html_dir = ROOT / 'src' / 'Pellmonweb' / 'html'
    lookup = TemplateLookup(directories=[str(html_dir)])
    out = lookup.get_template('logview.html').render(username=None, webroot='')
    assert out.count('/weather/') >= 1
