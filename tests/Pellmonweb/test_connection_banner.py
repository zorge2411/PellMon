"""Main-page connection banner: template render per state, and the rule that
the banner copy lives in exactly one file."""

import re
from pathlib import Path

import pytest
from mako.lookup import TemplateLookup
from mako.template import Template

ROOT = Path(__file__).resolve().parents[2]
HTML_DIR = ROOT / "src" / "Pellmonweb" / "html"
NO_CONN = "No connection to the burner"
DEMO = "Demo mode: values are simulated."


def render(state, reason=""):
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    tmpl = lookup.get_template("connectionbanner")
    return tmpl.render(connection_state=state, connection_reason=reason)


def element_classes(html, element_id):
    m = re.search(r'<[^>]*id="%s"[^>]*>' % re.escape(element_id), html)
    assert m, "element %s missing" % element_id
    c = re.search(r'class="([^"]*)"', m.group(0))
    return c.group(1).split() if c else []


def test_no_connection_state():
    html = render("no_connection", "serial port /dev/ttyUSB0 cannot be opened: No such file")
    assert 'data-state="no_connection"' in html
    assert NO_CONN in html
    assert "hidden" not in element_classes(html, "conn-no_connection")
    assert "hidden" in element_classes(html, "conn-demo")
    assert "hidden" in element_classes(html, "conn-connected")
    assert "/dev/ttyUSB0 cannot be opened" in html


def test_demo_state():
    html = render("demo", "no serialport configured")
    assert 'data-state="demo"' in html
    assert DEMO in html
    assert "hidden" not in element_classes(html, "conn-demo")
    assert "hidden" in element_classes(html, "conn-no_connection")


def test_connected_state_hides_everything():
    html = render("connected", "")
    assert 'data-state="connected"' in html
    for state in ("no_connection", "demo", "server_down"):
        assert "hidden" in element_classes(html, "conn-" + state)


def test_server_down_is_friendly():
    html = render("server_down", "")
    assert 'data-state="server_down"' in html
    assert "hidden" not in element_classes(html, "conn-server_down")
    assert "not running or not reachable" in html
    assert "Traceback" not in html


def test_reason_is_escaped():
    html = render("no_connection", '<script>alert(1)</script>')
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_index_page_includes_banner_and_greys_widgets():
    """index.html pulls the include in, above the widget rows."""
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    src = (HTML_DIR / "index.html").read_text(encoding="utf-8")
    assert 'file="connectionbanner"' in src
    assert src.index("connectionbanner") < src.index("%for row in widgets")
    assert "pellmon-disconnected" in src


def test_banner_text_only_in_the_include():
    for rel in ("src/Pellmonweb/media/js/index.js", "src/Pellmonweb/pellmonweb.py",
                "src/Pellmonweb/html/index.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert NO_CONN not in text, rel
        assert "values are simulated" not in text, rel
    assert NO_CONN in (HTML_DIR / "connectionbanner").read_text(encoding="utf-8")


def test_resolver_daemon_unreachable():
    web = pytest.importorskip("Pellmonweb.pellmonweb")

    class Down:
        def getItem(self, name):
            raise web.DbusNotConnected("server not running")

    assert web.resolve_connection_state(Down()) == ("server_down", "")


def test_resolver_missing_item_means_connected():
    web = pytest.importorskip("Pellmonweb.pellmonweb")

    class NoPlugin:
        def getItem(self, name):
            raise KeyError(name)

    assert web.resolve_connection_state(NoPlugin()) == ("connected", "")


def test_resolver_reads_state_and_reason():
    web = pytest.importorskip("Pellmonweb.pellmonweb")

    class Up:
        def getItem(self, name):
            return {"burner_connection": "no_connection",
                    "burner_connection_reason": "why"}[name]

    assert web.resolve_connection_state(Up()) == ("no_connection", "why")
