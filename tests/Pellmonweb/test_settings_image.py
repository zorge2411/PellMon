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
