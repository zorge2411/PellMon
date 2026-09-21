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
