"""Phase 6 Plan 06: Home Assistant controller (D-10 protection, D-12 write-only password, D-13 status/test)."""
import json
import logging
import time

import pytest

SENTINEL = 's3cret-XYZ'
ORIGIN = dict(Origin='http://localhost:8081', Host='localhost:8081')

from Pellmonweb import homeassistant as ha  # noqa: E402


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
        assert name == 'homeassistant.html'
        return FakeTemplate(self.calls)


class FakeDbus:
    def __init__(self, fail=False, stored=None, status=None, set_result=None, start=True, results=None):
        self.fail = fail
        self.stored = stored if stored is not None else dict(has_password=False, available=True)
        self.status = status if status is not None else dict(state='disabled')
        self.set_result = set_result if set_result is not None else dict(ok=True)
        self.start = start
        self.results = list(results or [])
        self.set_calls = []
        self.start_calls = []
        self.result_calls = 0

    def _check(self):
        if self.fail:
            raise RuntimeError('down')

    def mqtt_get_settings(self):
        self._check()
        return dict(self.stored)

    def mqtt_set_settings(self, d):
        self._check()
        self.set_calls.append(d)
        return self.set_result

    def mqtt_status(self):
        self._check()
        return self.status

    def mqtt_test_start(self, d):
        self._check()
        self.start_calls.append(d)
        return self.start

    def mqtt_test_result(self):
        self._check()
        self.result_calls += 1
        if self.results:
            return self.results.pop(0) if len(self.results) > 1 else self.results[0]
        return dict(state='running', message='')

    def any_call(self):
        return bool(self.set_calls or self.start_calls or self.result_calls)


def _make(creds=True, **kw):
    dbus = FakeDbus(**kw)
    c = ha.HomeAssistant(FakeLookup(), dbus, credentials={'u': 'p'} if creds else {})
    clock = [0.0]
    c._clock = lambda: clock[0]

    def sleep(sec):
        clock[0] += sec
    c._sleep = sleep
    return c, dbus


def _post(**headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)


def _valid(**kw):
    form = dict(enabled='1', host='mqtt.local', port='1883', username='u', prefix='scotte',
                discovery_prefix='homeassistant', device_id='burner', device_name='Burner',
                node_id='', uid_prefix='', refresh='60')
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
    for name in ('index', 'save', 'test', 'status'):
        assert 'auth.require' in getattr(ha.HomeAssistant, name)._cp_config


@pytest.mark.parametrize('route', ['save', 'test'])
def test_get_rejected_without_dbus(cherrypy_request_ctx, route):
    import cherrypy
    cherrypy.request.method = 'GET'
    c, d = _make()
    ctx = getattr(c, route)(**_valid())
    assert ctx['msg'] == ha.MSG_REJECTED
    assert not d.any_call()


@pytest.mark.parametrize('route', ['save', 'test'])
def test_cross_origin_403(cherrypy_request_ctx, caplog, route):
    import cherrypy
    _post(Origin='http://evil.example', Host='localhost:8081')
    c, d = _make()
    with caplog.at_level(logging.WARNING, logger='pellMon'):
        ctx = getattr(c, route)(**_valid(password=SENTINEL))
    assert cherrypy.response.status == 403
    assert not d.any_call()
    assert any('evil.example' in r.getMessage() for r in _warnings(caplog))
    assert SENTINEL not in caplog.text
    assert (ctx['msg'] == ha.MSG_REJECTED) if route == 'save' else (ctx['test_msg'] == ha.TEST_REJECTED)


@pytest.mark.parametrize('route', ['save', 'test'])
def test_headerless_post_rejected(cherrypy_request_ctx, route):
    _post(Host='localhost:8081')
    c, d = _make()
    getattr(c, route)(**_valid())
    assert not d.any_call()


# ---- tls_verify blocker fix ----

def _payload_after_save(cherrypy_request_ctx, **form):
    _post(**ORIGIN)
    c, d = _make()
    _redirect(c, **_valid(**form))
    return d.set_calls[0]


def test_tls_off_no_marker_keeps_stored_verify(cherrypy_request_ctx):
    p = _payload_after_save(cherrypy_request_ctx)
    assert p['tls_verify_field'] is False and p['tls_verify'] is True and p['tls'] is False


def test_tls_on_without_marker_keeps_stored_verify(cherrypy_request_ctx):
    p = _payload_after_save(cherrypy_request_ctx, tls='on')
    assert p['tls'] is True and p['tls_verify_field'] is False and p['tls_verify'] is True


def test_tls_on_marker_unticked_verify_is_explicit_off(cherrypy_request_ctx):
    p = _payload_after_save(cherrypy_request_ctx, tls='on', tls_verify_field='1')
    assert p['tls_verify_field'] is True and p['tls_verify'] is False


def test_tls_on_marker_ticked_verify(cherrypy_request_ctx):
    p = _payload_after_save(cherrypy_request_ctx, tls='on', tls_verify_field='1', tls_verify='on')
    assert p['tls_verify_field'] is True and p['tls_verify'] is True


def test_marker_without_tls_is_not_explicit(cherrypy_request_ctx):
    p = _payload_after_save(cherrypy_request_ctx, tls_verify_field='1')
    assert p['tls_verify_field'] is False and p['tls_verify'] is True


def test_test_candidate_uses_same_tls_rules(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(results=[dict(state='ok', message='')])
    c.test(**_valid(tls='on'))
    c.test(**_valid(tls='on', tls_verify_field='1'))
    a, b = d.start_calls
    assert a['tls_verify_field'] is False and a['tls_verify'] is True
    assert b['tls_verify_field'] is True and b['tls_verify'] is False


# ---- save ----

def test_valid_save_payload_and_redirect(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    r = _redirect(c, **_valid(port='8883', refresh='120', allow_commands='on'))
    p = d.set_calls[0]
    assert p['enabled'] is True and p['tls'] is False and p['allow_commands'] is True
    assert p['port'] == 8883 and p['refresh'] == 120
    assert isinstance(p['tls_verify'], bool) and isinstance(p['tls_verify_field'], bool)
    assert 'password' not in p and 'clear_password' not in p
    assert r.status == 303
    assert r.urls[0].endswith('/homeassistant/?saved=commands')


def test_saved_variants(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    assert _redirect(c, **_valid()).urls[0].endswith('?saved=1')
    form = _valid()
    del form['enabled']
    assert _redirect(c, **form).urls[0].endswith('?saved=off')
    c2, d2 = _make(stored=dict(allow_commands=True, has_password=False))
    assert _redirect(c2, **_valid(allow_commands='on')).urls[0].endswith('?saved=1')


def test_password_only_when_typed_and_clear_flag(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(stored=dict(has_password=True))
    _redirect(c, **_valid(password=''))
    _redirect(c, **_valid(password=SENTINEL))
    _redirect(c, **_valid(clear_password='1'))
    blank, typed, cleared = d.set_calls
    assert 'password' not in blank and 'clear_password' not in blank
    assert typed['password'] == SENTINEL
    assert cleared.get('clear_password') is True and 'password' not in cleared


@pytest.mark.parametrize('saved,text,level', [
    ('1', ha.MSG_SAVED, 'success'), ('commands', ha.MSG_SAVED_COMMANDS, 'success'),
    ('off', ha.MSG_SAVED_OFF, 'success')])
def test_index_saved_messages(cherrypy_request_ctx, saved, text, level):
    c, _ = _make()
    ctx = c.index(saved=saved)
    assert ctx['msg'] == text and ctx['msg_level'] == level


def test_index_unknown_saved_not_echoed(cherrypy_request_ctx):
    c, _ = _make()
    ctx = c.index(saved='<script>x</script>')
    assert ctx['msg'] == ''
    assert 'script' not in json.dumps(ctx)


def test_index_context(cherrypy_request_ctx):
    c, _ = _make(stored=dict(has_password=True, host='h', available=True))
    ctx = c.index()
    assert ctx['active_page'] == 'homeassistant' and ctx['has_password'] is True
    assert ctx['settings']['host'] == 'h' and ctx['auth_configured'] is True
    assert ctx['available'] is True and ctx['daemon_down'] is False
    assert ctx['status']['word'] == 'Off.'


def test_index_daemon_down(cherrypy_request_ctx):
    c, _ = _make(fail=True)
    ctx = c.index()
    assert ctx['daemon_down'] is True and ctx['msg'] == ha.MSG_DAEMON_DOWN
    assert ctx['status']['text'] == ha.STATUS_DAEMON_DOWN


def test_index_plugin_not_active(cherrypy_request_ctx):
    c, _ = _make(stored=dict(available=False), status=dict(available=False))
    ctx = c.index()
    assert ctx['available'] is False
    assert ctx['status']['text'] == ha.STATUS_NOT_ACTIVE


def test_invalid_port_no_dbus_password_never_echoed(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.save(**_valid(port='70000', password=SENTINEL))
    assert not d.any_call()
    assert ctx['errors']['port'] == 'Port must be a number from 1 to 65535.'
    assert ctx['msg'] == ha.MSG_INVALID and ctx['msg_level'] == 'danger'
    assert ctx['password_reentered'] is True
    assert 'password' not in ctx['settings'] and ctx['settings']['port'] == '70000'
    assert SENTINEL not in json.dumps(ctx, default=str)


def test_too_long_password_is_error(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.save(**_valid(password='x' * 300))
    assert 'password' in ctx['errors'] and not d.any_call()


def test_daemon_errors_rendered(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(set_result=dict(ok=False, errors={'host': 'Daemon says no.'}))
    ctx = c.save(**_valid())
    assert ctx['errors'] == {'host': 'Daemon says no.'} and ctx['msg'] == ha.MSG_INVALID


@pytest.mark.parametrize('kw', [dict(fail=True)])
def test_daemon_down_on_save(cherrypy_request_ctx, kw):
    _post(**ORIGIN)
    c, d = _make(**kw)
    ctx = c.save(**_valid())
    assert ctx['msg'] == ha.MSG_DAEMON_DOWN and ctx['msg_level'] == 'danger'


def test_auth_disabled_refuses_valid_but_shows_invalid(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(creds=False)
    ctx = c.save(**_valid())
    assert ctx['msg'] == ha.MSG_AUTH_DISABLED and not d.any_call()
    ctx = c.save(**_valid(port='0'))
    assert 'port' in ctx['errors'] and not d.any_call()
    ctx = c.test(**_valid())
    assert ctx['test_msg'] == ha.TEST_AUTH_DISABLED and not d.any_call()


def test_sentinel_never_logged_or_rendered(cherrypy_request_ctx, caplog):
    _post(**ORIGIN)
    c, d = _make(results=[dict(state='ok', message='')])
    with caplog.at_level(logging.DEBUG, logger='pellMon'):
        _redirect(c, **_valid(password=SENTINEL))
        ctx = c.test(**_valid(password=SENTINEL))
        bad = c.save(**_valid(password=SENTINEL, port='x'))
        c.index()
        c.status()
    assert SENTINEL not in caplog.text
    assert SENTINEL not in json.dumps(ctx, default=str)
    assert SENTINEL not in json.dumps(bad, default=str)


# ---- status ----

CONNECT = 'Connected'


def test_status_json(cherrypy_request_ctx):
    import cherrypy
    c, _ = _make(stored=dict(has_password=True, host='h', port=1883),
                 status=dict(state='connecting', host='h', port=1883))
    body = json.loads(c.status())
    assert cherrypy.response.headers['Content-Type'] == 'application/json'
    assert 'password' not in body and 'has_password' not in body
    assert body['text'] == 'to h:1883...'


def test_status_daemon_down(cherrypy_request_ctx):
    c, _ = _make(fail=True)
    assert json.loads(c.status())['text'] == ha.STATUS_DAEMON_DOWN


def _copy(view):
    return (view['word'] + ' ' + view['text']).strip()


def test_status_off():
    v = ha.status_view({}, dict(state='disabled'))
    assert v['level'] == 'well' and v['word'] == 'Off.'
    assert _copy(v) == 'Off. Home Assistant publishing is turned off. Turn on "Enable Home Assistant MQTT" and save to connect.'


def test_status_connecting():
    v = ha.status_view({}, dict(state='connecting', host='b.local', port=1883))
    assert v['level'] == 'well' and _copy(v) == 'Connecting to b.local:1883...'


def test_status_connected_with_publish():
    ts = time.mktime((2026, 9, 25, 13, 4, 5, 0, 0, -1))
    v = ha.status_view({}, dict(state='connected', host='b', port=1883, last_publish=ts, availability='online'))
    assert v['level'] == 'success' and v['glyph'] == 'ok'
    assert _copy(v) == 'Connected to b:1883. Last publish: 13:04:05.'
    assert v['title'] == '2026-09-25 13:04:05'


def test_status_connected_no_publish():
    v = ha.status_view({}, dict(state='connected', host='b', port=1883, last_publish=None))
    assert v['level'] == 'success' and _copy(v) == 'Connected to b:1883. No values published yet.'


def test_status_burner_offline():
    v = ha.status_view({}, dict(state='connected', host='b', port=1883, availability='offline', last_publish=5))
    assert v['level'] == 'warning'
    assert _copy(v) == ('Connected to b:1883, but the burner is not connected. Home Assistant shows the '
                        'entities as unavailable until it answers again.')


def test_status_disconnected_and_reason_mapping():
    v = ha.status_view({}, dict(state='disconnected', host='b', port=1, reason='connection refused'))
    assert v['level'] == 'danger' and v['glyph'] == 'remove'
    assert _copy(v) == 'Disconnected from b:1: connection refused. PellMon keeps retrying automatically.'
    v = ha.status_view({}, dict(state='disconnected', host='b', port=1, reason='Traceback secret'))
    assert 'unknown error (see the server log)' in v['text'] and 'secret' not in v['text']


def test_status_not_active_and_down():
    v = ha.status_view({}, dict(available=False))
    assert v['level'] == 'warning' and v['word'] == '' and v['text'] == (
        'The Home Assistant MQTT plugin is not active on the server. '
        'Check the PellMon installation and restart the server.')
    v = ha.status_view({}, None, daemon_down=True)
    assert v['word'] == '' and v['text'] == (
        'Cannot read the status because the PellMon server is not running. Start the server to see the status.')


# ---- test connection ----

def test_test_invalid(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    ctx = c.test(**_valid(host=''))
    assert ctx['test_msg'] == 'Test failed: fix the highlighted fields first.'
    assert 'host' in ctx['errors'] and not d.any_call()


def test_test_ok_polls_and_never_saves(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(results=[dict(state='running', message=''), dict(state='ok', message='')])
    ctx = c.test(**_valid(password=SENTINEL))
    assert ctx['test_msg'] == ('Connection successful. The broker accepted the host, port, credentials '
                               'and TLS settings. Nothing was saved.')
    assert ctx['test_level'] == 'success'
    assert len(d.start_calls) == 1 and d.start_calls[0]['password'] == SENTINEL
    assert d.result_calls == 2 and d.set_calls == []
    assert 'password' not in ctx['settings'] and ctx['password_reentered'] is True


def test_test_no_password_key_when_blank(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(results=[dict(state='ok', message='')])
    c.test(**_valid(clear_password='1'))
    assert 'password' not in d.start_calls[0] and 'clear_password' not in d.start_calls[0]


def test_test_error_reason(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(results=[dict(state='error', message='connection refused')])
    ctx = c.test(**_valid())
    assert ctx['test_msg'] == 'Test failed: connection refused. Nothing was saved.'
    assert ctx['test_level'] == 'danger'


def test_test_timeout_after_cap(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make()
    assert ha.TEST_POLL_CAP == 10
    ctx = c.test(**_valid())
    assert ctx['test_msg'] == 'Test failed: timed out. Nothing was saved.'
    assert d.result_calls == 21


def test_test_start_false(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(start=False)
    ctx = c.test(**_valid())
    assert ctx['test_msg'] == 'Test failed: unknown error (see the server log). Nothing was saved.'


def test_test_daemon_down(cherrypy_request_ctx):
    _post(**ORIGIN)
    c, d = _make(fail=True)
    ctx = c.test(**_valid())
    assert ctx['test_msg'] == ('Cannot test right now because the PellMon server is not running. '
                               'Your changes were not saved. Start the server and retry.')


def test_test_json_states(cherrypy_request_ctx):
    import cherrypy
    _post(**ORIGIN)
    c, d = _make(results=[dict(state='ok', message='')])
    body = json.loads(c.test(format='json', **_valid()))
    assert cherrypy.response.headers['Content-Type'] == 'application/json'
    assert body['state'] == 'ok' and body['level'] == 'success' and body['errors'] == {}
    assert d.set_calls == []
    body = json.loads(c.test(format='json', **_valid(port='0')))
    assert body['state'] == 'invalid' and body['level'] != 'success' and 'port' in body['errors']
    c2, _ = _make(fail=True)
    assert json.loads(c2.test(format='json', **_valid()))['state'] == 'daemon_down'
    c3, _ = _make(creds=False)
    assert json.loads(c3.test(format='json', **_valid()))['state'] == 'auth_disabled'
    c4, _ = _make(results=[dict(state='error', message='timed out')])
    assert json.loads(c4.test(format='json', **_valid()))['state'] == 'error'
    _post(Origin='http://evil.example', Host='localhost:8081')
    assert json.loads(c.test(format='json', **_valid()))['state'] == 'rejected'


def test_copy_strings_present_in_source():
    from pathlib import Path
    src = Path(ha.__file__).read_text(encoding='utf-8')
    for s in ('Settings saved. Reconnecting to the broker...',
              'Settings saved. Home Assistant can now change burner settings.',
              'Settings saved. Home Assistant publishing is off.',
              'Could not save. Fix the highlighted fields and try again.',
              'Could not save the settings. Sign in again and retry.',
              'Saving is disabled until web login credentials are configured.',
              'Testing is disabled until web login credentials are configured.',
              'Testing the connection...', 'Test failed: %s. Nothing was saved.',
              'Test failed: fix the highlighted fields first.',
              'Could not test the settings. Sign in again and retry.',
              'Connection successful. The broker accepted the host, port, credentials and TLS settings. Nothing was saved.',
              'unknown error (see the server log)'):
        assert s in src, s
    assert src.count('@require()') >= 4 and src.count('check_same_origin()') >= 2


# ---- Task 2: Dbus_handler proxies, mount, real-template render ----

import ast  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WEB_SRC = (ROOT / 'src' / 'Pellmonweb' / 'pellmonweb.py').read_text(encoding='utf-8')
INIT_SRC = (ROOT / 'src' / 'Pellmonweb' / '__init__.py').read_text(encoding='utf-8')
TREE = ast.parse(WEB_SRC)
PROXIES = {'mqtt_get_settings': 'GetMqttSettings', 'mqtt_set_settings': 'SetMqttSettings',
           'mqtt_status': 'GetMqttStatus', 'mqtt_test_start': 'StartMqttTest',
           'mqtt_test_result': 'GetMqttTestResult'}


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


def test_homeassistant_mounted_and_imported():
    init = ast.get_source_segment(WEB_SRC, _method(_class('PellMonWeb'), '__init__'))
    assert 'self.homeassistant = HomeAssistant(lookup, dbus, credentials)' in init
    # pellmonweb.py gets its controllers through "from Pellmonweb import *"
    assert 'from Pellmonweb import *' in WEB_SRC
    assert 'from .homeassistant import HomeAssistant' in INIT_SRC


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
        args = ({},) if name in ('mqtt_set_settings', 'mqtt_test_start') else ()
        with pytest.raises(web.DbusNotConnected):
            getattr(h, name)(*args)


def test_real_template_render_hides_password(cherrypy_request_ctx):
    from mako.lookup import TemplateLookup
    html_dir = ROOT / 'src' / 'Pellmonweb' / 'html'
    dbus = FakeDbus(stored=dict(has_password=True, available=True, host='mqtt.local'))
    c = ha.HomeAssistant(TemplateLookup(directories=[str(html_dir)]), dbus, credentials={'u': 'p'})
    out = c.index()
    assert 'Home Assistant / MQTT' in out
    assert 'placeholder="set"' in out
    assert SENTINEL not in out
    _post(**ORIGIN)
    bad = c.save(**_valid(port='70000', password=SENTINEL))
    assert SENTINEL not in bad and 'has-error' in bad
