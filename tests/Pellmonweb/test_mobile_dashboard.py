"""Structural and Mako-render checks for the Phase 10 mobile dashboard markup."""
import re
from pathlib import Path

from mako.lookup import TemplateLookup

ROOT = Path(__file__).resolve().parents[2]
HTML_DIR = ROOT / "src" / "Pellmonweb" / "html"
JS_DIR = ROOT / "src" / "Pellmonweb" / "media" / "js"
PLUGINS = ROOT / "src" / "Pellmonsrv" / "plugins"

CHART_SOURCES = [
    (PLUGINS / "consumption" / "__init__.py", 'id="consumption"'),
    (PLUGINS / "silolevel" / "__init__.py", 'id="silolevel"'),
    (PLUGINS / "consumption" / "templates" / "consumption24h", 'id="consumption24h"'),
    (PLUGINS / "consumption" / "templates" / "consumption7d", 'id="consumption7d"'),
    (PLUGINS / "consumption" / "templates" / "consumption8w", 'id="consumption8w"'),
    (PLUGINS / "consumption" / "templates" / "consumption1y", 'id="consumption1y"'),
]


def read(path):
    return Path(path).read_text(encoding="utf-8")


def test_viewport_meta_exact_and_zoom_allowed():
    """Viewport meta is the plain responsive one and never blocks zoom."""
    text = read(HTML_DIR / "layout.html")
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in text
    assert "user-scalable" not in text
    assert "maximum-scale" not in text


def test_dashboard_columns_use_integer_division_and_xs12():
    """D-07: integer column width and full-width phone columns."""
    text = read(HTML_DIR / "index.html")
    assert "12 // len(row)" in text
    assert "col-xs-12 col-md-${width}" in text
    assert "12 / len(row)" not in text
    assert 'class="col-md-${width}"' not in text


def test_dashboard_render_emits_integer_md_classes():
    """D-07 regression: rendered index.html never emits col-md-6.0."""
    lines = [dict(name="a", color="#f00", label="A"), dict(name="b", color="#0f0", label="B")]
    ctx = dict(username=None, webroot="", connection_state="connected", connection_reason="",
               rand=0.5, websockets=False, graphlines=lines, selectedlines=["a"],
               timeSeconds=[3600, 86400], timeNames=["1h", "24h"], timeChoice=3600,
               timeName="1h", autorefresh=False,
               widgets=[["systemimage", "events"], ["graph"]])
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    html = lookup.get_template("index.html").render(**ctx)
    assert 'class="col-xs-12 col-md-6"' in html
    assert 'class="col-xs-12 col-md-12"' in html
    assert "col-md-6.0" not in html
    assert "col-md-12.0" not in html


def test_navbar_toggle_accessible():
    """Hamburger has an accessible name and aria-expanded follows collapse state."""
    text = read(HTML_DIR / "layout.html")
    m = re.search(r'<button[^>]*class="navbar-toggle"[^>]*>', text)
    assert m
    assert 'aria-label="Toggle navigation"' in m.group(0)
    assert 'aria-expanded="false"' in m.group(0)
    assert '<span class="sr-only">Toggle navigation</span>' in text
    boot = text.index("bootstrap.min.js")
    assert "shown.bs.collapse" in text[boot:]
    assert "hidden.bs.collapse" in text[boot:]


def test_graph_template_css_sized():
    """Graph has no inline height and keeps every hook index.js binds to."""
    text = read(HTML_DIR / "graph")
    assert 'class="pellmon-graph"' in text
    assert 'style="height:' not in text
    assert "</div   >" not in text
    for token in ["graph-lines", "graph-times pull-left", "graph-nav pull-right",
                  "lineselection", "timeChoice", "autorefresh", "data-linename",
                  "data-selected", "data-time-choice", "data-title-text",
                  "btn btn-info left", "btn btn-info right"]:
        assert token in text, token


def test_events_template_collapsible():
    """Events widget is collapsible on phones with a toggle outside #lines."""
    text = read(HTML_DIR / "events")
    for token in ['id="events-wrap"', "events-collapsed", 'id="lines"', "data-url=",
                  "events-toggle", "visible-xs", 'aria-expanded="false"',
                  "Show all events", "Show fewer events"]:
        assert token in text, token
    assert "visible-xs-block" not in text
    assert "<script" not in text
    wrap = text.index('id="events-wrap"')
    lines = text.index('id="lines"')
    button = text.index("events-toggle")
    assert wrap < lines < button


def test_index_js_events_toggle_uses_text():
    """Toggle handler writes labels with .text() and never .html()."""
    text = read(JS_DIR / "index.js")
    assert "$(document).on('click', '.events-toggle'" in text
    start = text.index("'.events-toggle'")
    end = text.index("\n});", start)
    block = text[start:end]
    assert ".text(" in block
    assert "aria-expanded" in block
    assert ".html(" not in block


def test_no_inline_400px_in_six_chart_sources():
    """RESEARCH C4: chart containers take height from CSS, keep their ids."""
    for path, ident in CHART_SOURCES:
        text = read(path)
        assert "height:400px" not in text.replace(" ", ""), path
        assert "pellmon-chart" in text, path
        assert ident in text, path


def test_consumption_page_stacks():
    """Consumption page columns stack below md."""
    text = read(HTML_DIR / "consumption.html")
    assert text.count("col-xs-12 col-md-6") == 4
    assert 'class="col-md-6"' not in text


def test_no_large_fixed_sizes_in_templates():
    """No inline style declares a large fixed pixel width or height."""
    files = [p for p in HTML_DIR.iterdir() if p.is_file()] + [p for p, _ in CHART_SOURCES]
    for path in files:
        for style in re.findall(r'style\s*=\s*"([^"]*)"', read(path)):
            for prop, val in re.findall(r'(width|height)\s*:\s*(\d+)px', style):
                limit = 361 if prop == "width" else 260
                assert int(val) < limit, (path, style)
