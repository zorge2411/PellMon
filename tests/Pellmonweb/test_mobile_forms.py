"""Phase 10 Plan 04: Parameters and Settings pages are phone-friendly (structural + Mako render)."""

import re
import sys
from pathlib import Path

from mako.lookup import TemplateLookup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
HTML_DIR = ROOT / "src" / "Pellmonweb" / "html"
PARAMS_HTML = (HTML_DIR / "parameters.html").read_text(encoding="utf-8")
PARAMS_JS = (ROOT / "src" / "Pellmonweb" / "media" / "js" / "parameters.js").read_text(encoding="utf-8")
SETTINGS_HTML = (HTML_DIR / "settings.html").read_text(encoding="utf-8")


def _render(name, **kw):
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    return lookup.get_template(name).render(**kw)


def _params_ctx():
    commands = [dict(name="cmd%d" % i, longname="command %d" % i) for i in range(2)]
    data = [dict(name="d%d" % i, longname="data %d" % i, unit="C", description="") for i in range(3)]
    params = [
        dict(name="p0", longname="param 0", unit="", description="desc"),
        dict(name="p1", longname="param 1", unit="", description="", get_enum_list=[(0, "Off"), (1, "On")]),
        dict(name="p2", longname="param 2", unit="", description="", min=1, max=9),
    ]
    tags = ["tag%d" % i for i in range(8)]
    return dict(username="u", webroot="", heading="Basic", tags=tags, commands=commands,
                data=data, params=params, level="Basic", from_page="parameters",
                websockets=False, values={}, active_page="parameters")


def test_parameters_sections_collapsible():
    """Control, Data and Settings are Bootstrap collapse sections with correct initial state."""
    assert PARAMS_HTML.count('data-toggle="collapse"') >= 3
    for sid in ("param-control", "param-data", "param-settings"):
        assert 'id="%s"' % sid in PARAMS_HTML
    assert "param-section-heading" in PARAMS_HTML
    assert re.search(r'class="[^"]*param-section-toggle[^"]*collapsed[^"]*"[^>]*href="#param-settings"[^>]*aria-expanded="false"', PARAMS_HTML)
    for sid in ("control", "data"):
        assert re.search(r'href="#param-%s" aria-expanded="true"' % sid, PARAMS_HTML)
        assert 'id="param-%s" class="collapse in param-section"' % sid in PARAMS_HTML
    assert 'id="param-settings" class="collapse param-section"' in PARAMS_HTML


def test_parameters_grid_has_xs_sibling():
    """Every col-md-* column also has a col-xs-* class; tag list is param-tags."""
    assert "col-xs-12" in PARAMS_HTML
    for cls in re.findall(r'class="([^"]*)"', PARAMS_HTML):
        if re.search(r'\bcol-md-', cls):
            assert re.search(r'\bcol-xs-', cls), cls
    assert "nav nav-pills nav-stacked param-tags" in PARAMS_HTML


def test_parameters_js_hooks_preserved():
    """Hooks used by parameters.js and the page-local style are untouched."""
    for token in ("editable", "details hidden", "select_enum", "save form-inline", "param value",
                  "command btn btn-primary", "-value", "-selectbox", "-form"):
        assert token in PARAMS_HTML, token
    assert re.search(r"\.details \.form-inline \.form-control\s*\{\s*width: 60%;", PARAMS_HTML)


def test_parameters_render():
    """Rendered page has three toggles with existing targets, labels and 8 pills."""
    html = _render("parameters.html", **_params_ctx())
    toggles = re.findall(r'<a class="[^"]*param-section-toggle[^"]*"[^>]*href="#([^"]+)"', html)
    assert len(toggles) == 3
    for t in toggles:
        assert 'id="%s"' % t in html
    for label in ("Control", "Data", "Settings"):
        assert re.search(r"param-section-toggle[^>]*>\s*%s " % label, html)
    ul = re.search(r'<ul class="[^"]*param-tags[^"]*">(.*?)</ul>', html, re.S).group(1)
    assert len(re.findall(r'<a href="/parameters/tag\d">', ul)) == 8


def test_parameters_js_aria_sync():
    """parameters.js syncs aria-expanded on collapse events without html sinks."""
    for token in ("show.bs.collapse", "hide.bs.collapse", "aria-expanded", ".param-section"):
        assert token in PARAMS_JS, token
    assert ".html(" not in PARAMS_JS


def test_settings_gallery_two_up():
    """Gallery tiles are two per row on phones."""
    assert "col-xs-6 col-sm-6 col-md-4" in SETTINGS_HTML
    assert "col-xs-12 col-sm-6 col-md-4" not in SETTINGS_HTML


def test_settings_save_button_class():
    """Save image button has the sysimg-save hook and stays disabled without auth."""
    from Pellmonweb.settings import SYSTEM_IMAGES, IMAGE_NAMES
    imgs = [dict(file=f, name=IMAGE_NAMES[f] if isinstance(IMAGE_NAMES, dict) else f) for f in SYSTEM_IMAGES]
    for auth in (True, False):
        html = _render("settings.html", username="u", webroot="", active_page="settings", images=imgs,
                       current=SYSTEM_IMAGES[1], msg="", msg_level="", auth_configured=auth)
        assert re.search(r'<button[^>]*class="btn btn-primary sysimg-save"', html)
        if not auth:
            assert re.search(r'<button[^>]*btn-primary[^>]*disabled', html)
