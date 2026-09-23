"""Settings page wiring (pellmonweb.py) and Mako render of settings.html."""

import ast
import re
import sys
from pathlib import Path

import pytest
from mako.lookup import TemplateLookup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
WEB_SRC = (ROOT / "src" / "Pellmonweb" / "pellmonweb.py").read_text()
HTML_DIR = ROOT / "src" / "Pellmonweb" / "html"
TREE = ast.parse(WEB_SRC)


def _class(name):
    return next(n for n in ast.walk(TREE) if isinstance(n, ast.ClassDef) and n.name == name)


def _method(cls, name):
    return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)


# ---- structural wiring ----

def test_systemimage_no_cache_and_effective_image():
    src = ast.get_source_segment(WEB_SRC, _method(_class("Root"), "systemimage")) \
        if any(c.name == "Root" for c in ast.walk(TREE) if isinstance(c, ast.ClassDef)) \
        else WEB_SRC
    assert "'Cache-Control'] = 'no-cache'" in src
    assert "'Pragma'] = 'no-cache'" in src
    assert "effective_image(system_image_dir, dbus.get_setting, system_image)" in src
    assert "return serve_file(system_image)" not in WEB_SRC


def test_caching_tool_not_enabled_for_systemimage():
    assert "tools.caching" not in WEB_SRC


def test_settings_mounted():
    init = _method(_class("PellMonWeb"), "__init__")
    assert "self.settings = Settings(" in ast.get_source_segment(WEB_SRC, init)


def test_dbus_handler_proxies():
    cls = _class("Dbus_handler")
    assert "GetSetting" in ast.get_source_segment(WEB_SRC, _method(cls, "get_setting"))
    assert "SetSetting" in ast.get_source_segment(WEB_SRC, _method(cls, "set_setting"))


def test_settings_handlers_still_require_auth():
    from Pellmonweb import settings as s
    src = Path(s.__file__).read_text()
    assert src.count("@require()") >= 2


def test_dbus_handler_functional():
    pytest.importorskip("cherrypy")
    pytest.importorskip("dbus")
    pytest.importorskip("gi")
    import importlib
    web = importlib.import_module("Pellmonweb.pellmonweb")
    h = web.Dbus_handler.__new__(web.Dbus_handler)
    import threading
    h.lock = threading.Lock()
    h.remote_object = None
    with pytest.raises(web.DbusNotConnected):
        h.get_setting("web.system_image")
    with pytest.raises(web.DbusNotConnected):
        h.set_setting("web.system_image", "x.svg")


# ---- template render ----

from Pellmonweb.settings import SYSTEM_IMAGES, IMAGE_NAMES  # noqa: E402


def images():
    return [dict(file=f, name=IMAGE_NAMES[f] if isinstance(IMAGE_NAMES, dict) else f)
            for f in SYSTEM_IMAGES]


def render(name="settings.html", **kw):
    ctx = dict(username="u", webroot="", active_page="settings", images=images(),
               current=SYSTEM_IMAGES[1], msg="", msg_level="", auth_configured=True)
    ctx.update(kw)
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    return lookup.get_template(name).render(**ctx)


def test_one_radio_per_image():
    html = render()
    radios = re.findall(r'<input type="radio"[^>]*value="([^"]*)"', html)
    assert radios == list(SYSTEM_IMAGES)
    for f in SYSTEM_IMAGES:
        assert re.search(r'<img[^>]*src="[^"]*%s"' % re.escape(f), html)


def test_current_marked_once():
    html = render()
    assert html.count(" checked") == 1
    assert html.count(">Current<") == 1
    assert re.search(r'value="%s" checked' % re.escape(SYSTEM_IMAGES[1]), html)


def test_form_posts_to_save():
    assert re.search(r'<form method="post" action="/settings/save"', render())


def test_message_escaped():
    html = render(msg="<script>alert(1)</script>", msg_level="danger")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_empty_state():
    html = render(images=[])
    assert "No system images available" in html
    assert "<form" not in html


def test_auth_not_configured():
    html = render(auth_configured=False)
    assert "Saving is disabled until web login credentials are configured." in html
    assert re.search(r'<button[^>]*btn-primary[^>]*disabled', html)


def test_navbar_active_and_backward_compat():
    html = render()
    assert re.search(r'<li class="active">\s*<a href="/settings/">Settings', html)
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    log = lookup.get_template("logview.html").render(username=None, webroot="")
    assert 'class="active"' not in log
    assert "/settings/" in log
