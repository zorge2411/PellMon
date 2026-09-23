"""System image setting: same-origin helper, whitelist, resolver and Settings controller."""
import logging
from pathlib import Path

import pytest

IMG_DIR = Path(__file__).resolve().parents[2] / 'src' / 'Pellmonweb' / 'media' / 'img'


def _post(cherrypy_request_ctx, **headers):
    import cherrypy
    cherrypy.request.method = 'POST'
    cherrypy.request.headers = dict(headers)


class TestCheckSameOrigin:
    def test_same_origin_origin_header(self, cherrypy_request_ctx):
        from Pellmonweb.security import check_same_origin
        _post(cherrypy_request_ctx, Origin='http://localhost:8083', Host='localhost:8083')
        assert check_same_origin() is True

    def test_referer_fallback(self, cherrypy_request_ctx):
        from Pellmonweb.security import check_same_origin
        _post(cherrypy_request_ctx, Referer='http://localhost:8083/page', Host='localhost:8083')
        assert check_same_origin() is True

    def test_missing_headers_fail_closed(self, cherrypy_request_ctx):
        from Pellmonweb.security import check_same_origin
        _post(cherrypy_request_ctx, Host='localhost:8083')
        assert check_same_origin() is False

    def test_cross_origin_rejected(self, cherrypy_request_ctx):
        from Pellmonweb.security import check_same_origin
        _post(cherrypy_request_ctx, Origin='http://evil.example', Host='localhost:8083')
        assert check_same_origin() is False

    def test_unparseable_origin_rejected(self, cherrypy_request_ctx):
        from Pellmonweb.security import check_same_origin
        _post(cherrypy_request_ctx, Origin='http://[bad', Host='localhost:8083')
        assert check_same_origin() is False


# ---- Task 2: whitelist and resolver ----

@pytest.fixture
def settings_mod():
    from Pellmonweb import settings
    settings.reset_warning_state()
    return settings


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno == logging.WARNING]


class TestWhitelist:
    def test_names_match_whitelist(self, settings_mod):
        assert set(settings_mod.IMAGE_NAMES) == set(settings_mod.SYSTEM_IMAGES)

    def test_every_entry_ships(self, settings_mod):
        for name in settings_mod.SYSTEM_IMAGES:
            assert (IMG_DIR / name).is_file(), name

    def test_is_allowed(self, settings_mod):
        assert settings_mod.is_allowed('system_nbe.svg')
        assert not settings_mod.is_allowed('../../etc/passwd')
        assert not settings_mod.is_allowed(None)
        assert not settings_mod.is_allowed(b'system.svg')

    def test_available_images_order_and_missing(self, settings_mod, tmp_path):
        for n in ('system_nbe.svg', 'system.svg'):
            (tmp_path / n).write_text('x')
        got = [i['file'] for i in settings_mod.available_images(str(tmp_path))]
        assert got == ['system.svg', 'system_nbe.svg']

    def test_available_images_missing_dir(self, settings_mod, tmp_path):
        assert settings_mod.available_images(str(tmp_path / 'nope')) == []


class TestEffectiveImage:
    def test_gui_choice_wins(self, settings_mod, tmp_path):
        (tmp_path / 'system_nbe.svg').write_text('x')
        r = settings_mod.effective_image(str(tmp_path), lambda: 'system_nbe.svg', 'cfg')
        assert r == str(tmp_path / 'system_nbe.svg')

    @pytest.mark.parametrize('val', ['', None, 'error'])
    def test_unset_is_silent(self, settings_mod, tmp_path, caplog, val):
        assert settings_mod.effective_image(str(tmp_path), lambda: val, 'cfg') == 'cfg'
        assert _warnings(caplog) == []

    def test_invalid_warns_once(self, settings_mod, tmp_path, caplog):
        with caplog.at_level(logging.WARNING, logger='pellMon'):
            for _ in range(11):
                assert settings_mod.effective_image(str(tmp_path), lambda: '../../etc/passwd', 'cfg') == 'cfg'
        assert len(_warnings(caplog)) == 1

    def test_missing_file_falls_back(self, settings_mod, tmp_path):
        assert settings_mod.effective_image(str(tmp_path), lambda: 'system_nbe.svg', 'cfg') == 'cfg'

    def test_getter_raises(self, settings_mod, tmp_path):
        def boom():
            raise RuntimeError('daemon down')
        assert settings_mod.effective_image(str(tmp_path), boom, 'cfg') == 'cfg'


# ---- Task 3: Settings controller ----

MSG_REJECTED = 'Could not save the image. Sign in again and retry.'
MSG_UNKNOWN = 'That image is not available. Pick one from the list and retry.'
MSG_DOWN = ('Cannot save right now because the PellMon server is not running. '
            'The main page keeps its current image. Start the server and retry.')
MSG_OK = 'System image saved. Reload the main page to see it.'


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
        assert name == 'settings.html'
        return FakeTemplate(self.calls)


class FakeDbus:
    def __init__(self, stored='', fail=False, ret=True):
        self.stored, self.fail, self.ret = stored, fail, ret
        self.set_calls = []

    def get_setting(self, key):
        if self.fail:
            raise RuntimeError('down')
        return self.stored

    def set_setting(self, key, value):
        self.set_calls.append((key, value))
        if self.fail:
            raise RuntimeError('down')
        return self.ret


def _make(tmp_path, **kw):
    from Pellmonweb.settings import Settings
    dbus = FakeDbus(**kw)
    return Settings(FakeLookup(), dbus, str(IMG_DIR), credentials={'u': 'p'}), dbus


class TestSettingsController:
    def test_auth_required(self):
        from Pellmonweb.settings import Settings
        assert 'auth.require' in Settings.index._cp_config
        assert 'auth.require' in Settings.save._cp_config

    def test_index_context(self, cherrypy_request_ctx, tmp_path):
        s, _ = _make(tmp_path, stored='system_nbe.svg')
        ctx = s.index()
        assert ctx['current'] == 'system_nbe.svg'
        assert ctx['active_page'] == 'settings'
        assert ctx['auth_configured'] is True
        assert ctx['msg'] == ''
        assert len(ctx['images']) == 6

    def test_index_invalid_stored_is_empty(self, cherrypy_request_ctx, tmp_path):
        s, _ = _make(tmp_path, stored='../x')
        assert s.index()['current'] == ''

    def test_index_daemon_down_still_renders(self, cherrypy_request_ctx, tmp_path):
        s, _ = _make(tmp_path, fail=True)
        ctx = s.index()
        assert ctx['current'] == ''
        assert ctx['msg'] == MSG_DOWN and ctx['msg_level'] == 'warning'

    def test_get_does_not_save(self, cherrypy_request_ctx, tmp_path):
        import cherrypy
        cherrypy.request.method = 'GET'
        s, d = _make(tmp_path)
        s.save(image='system_nbe.svg')
        assert d.set_calls == []

    def test_cross_origin_rejected(self, cherrypy_request_ctx, tmp_path, caplog):
        import cherrypy
        _post(cherrypy_request_ctx, Origin='http://evil.example', Host='localhost:8081')
        s, d = _make(tmp_path)
        with caplog.at_level(logging.WARNING, logger='pellMon'):
            ctx = s.save(image='system_nbe.svg')
        assert d.set_calls == []
        assert cherrypy.response.status == 403
        assert ctx['msg'] == MSG_REJECTED and ctx['msg_level'] == 'danger'
        assert any('evil.example' in r.getMessage() and 'localhost:8081' in r.getMessage()
                   for r in _warnings(caplog))

    def test_headerless_post_rejected(self, cherrypy_request_ctx, tmp_path):
        _post(cherrypy_request_ctx, Host='localhost:8081')
        s, d = _make(tmp_path)
        ctx = s.save(image='system_nbe.svg')
        assert d.set_calls == []
        assert ctx['msg'] == MSG_REJECTED

    def test_non_whitelisted_rejected(self, cherrypy_request_ctx, tmp_path):
        _post(cherrypy_request_ctx, Origin='http://localhost:8081', Host='localhost:8081')
        s, d = _make(tmp_path)
        ctx = s.save(image='../../etc/passwd')
        assert d.set_calls == []
        assert ctx['msg'] == MSG_UNKNOWN

    def test_success(self, cherrypy_request_ctx, tmp_path):
        _post(cherrypy_request_ctx, Origin='http://localhost:8081', Host='localhost:8081')
        s, d = _make(tmp_path)
        ctx = s.save(image='system_nbe.svg')
        assert d.set_calls == [('web.system_image', 'system_nbe.svg')]
        assert ctx['msg'] == MSG_OK and ctx['msg_level'] == 'success'
        assert ctx['current'] == 'system_nbe.svg'

    @pytest.mark.parametrize('kw', [{'fail': True}, {'ret': False}])
    def test_daemon_down_or_rejected(self, cherrypy_request_ctx, tmp_path, kw):
        _post(cherrypy_request_ctx, Origin='http://localhost:8081', Host='localhost:8081')
        s, d = _make(tmp_path, **kw)
        ctx = s.save(image='system_nbe.svg')
        assert ctx['msg'] == MSG_DOWN and ctx['msg_level'] == 'warning'
