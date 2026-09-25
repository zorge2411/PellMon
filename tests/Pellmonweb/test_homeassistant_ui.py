"""Phase 6 Plan 04: Home Assistant / MQTT page structure (Mako render, Windows-safe)."""

import re
import sys
from pathlib import Path

from mako.lookup import TemplateLookup

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
HTML_DIR = ROOT / "src" / "Pellmonweb" / "html"
TEMPLATE = (HTML_DIR / "homeassistant.html").read_text(encoding="utf-8")
CSS = (ROOT / "src" / "Pellmonweb" / "media" / "css" / "pellmon.css").read_text(encoding="utf-8")

SENTINEL = "s3cret-XYZ"
INPUT_NAMES = ["enabled", "host", "port", "username", "password", "clear_password", "tls",
               "tls_verify", "prefix", "discovery_prefix", "device_id", "device_name", "node_id",
               "uid_prefix", "allow_commands", "refresh", "tls_verify_field"]


def _settings(**kw):
    s = dict(enabled=False, host="", port=1883, username="", tls=False, tls_verify=True,
             prefix="scotte", discovery_prefix="homeassistant", device_id="", device_name="",
             node_id="", uid_prefix="", allow_commands=False, refresh=60)
    s.update(kw)
    return s


def render(settings=None, **kw):
    ctx = dict(username="u", webroot="", active_page="homeassistant",
               settings=_settings(**(settings or {})), has_password=False,
               password_reentered=False, errors={}, msg="", msg_level="",
               status=dict(level="well", glyph="", word="Off", text="Home Assistant publishing is turned off.", title=""),
               test_msg="", test_level="", auth_configured=True, available=True, daemon_down=False)
    ctx.update(kw)
    lookup = TemplateLookup(directories=[str(HTML_DIR)])
    return lookup.get_template("homeassistant.html").render(**ctx)


def inputs(html):
    return re.findall(r"<input\b[^>]*>", html)


def input_by_name(html, name):
    for tag in inputs(html):
        if re.search(r'name="%s"' % re.escape(name), tag):
            return tag
    return None


# ---- structure ----

def test_inherit_title_h1_form_panels():
    assert '<%inherit file="layout.html"/>' in TEMPLATE
    assert "<h1>Home Assistant / MQTT</h1>" in TEMPLATE
    html = render()
    assert len(re.findall(r"<form\b", html)) == 1
    assert re.search(r'<form[^>]*method="post"[^>]*action="/homeassistant/save"', html)
    for heading in ("Connection", "Security", "Topics and discovery", "Device", "Behaviour"):
        assert re.search(r'class="panel-heading">\s*%s\s*<' % heading, html), heading
    assert len(re.findall(r'<section class="panel panel-default', html)) == 5


def test_scripts_declared():
    assert "scripts = ['js/homeassistant.js']" in TEMPLATE
    assert "/media/js/homeassistant.js" in render()


def test_input_names_present_and_labelled():
    html = render(has_password=True)
    for name in INPUT_NAMES:
        assert input_by_name(html, name), name
    names = [re.search(r'name="([^"]*)"', t).group(1) for t in inputs(html)]
    assert sorted(set(names)) == sorted(INPUT_NAMES)
    assert len(names) == len(set(names))
    for tag in inputs(html):
        if 'type="hidden"' in tag:
            continue
        ident = re.search(r'\bid="([^"]*)"', tag).group(1)
        assert re.search(r'<label[^>]*for="%s"' % re.escape(ident), html), ident


def test_keyboard_order():
    html = render(has_password=True)
    order = [re.search(r'name="([^"]*)"', t).group(1) for t in inputs(html)
             if 'type="hidden"' not in t]
    assert order == ["enabled", "host", "port", "username", "password", "clear_password", "tls",
                     "tls_verify", "prefix", "discovery_prefix", "device_id", "device_name",
                     "node_id", "uid_prefix", "allow_commands", "refresh"]


def test_password_input_rules():
    html = render(has_password=True)
    pw = input_by_name(html, "password")
    assert 'type="password"' in pw and 'autocomplete="new-password"' in pw
    assert "value=" not in pw
    assert 'placeholder="set"' in pw
    assert "A password is stored. Leave this field blank to keep it." in html
    assert "Remove the stored password" in html
    assert input_by_name(html, "clear_password")


def test_password_input_no_value_in_source():
    for line in TEMPLATE.splitlines():
        if 'type="password"' in line:
            assert "value=" not in line


def test_no_password_stored():
    html = render(has_password=False)
    pw = input_by_name(html, "password")
    assert 'placeholder="set"' not in pw
    assert "No password stored." in html
    assert input_by_name(html, "clear_password") is None
    assert "Remove the stored password" not in html


def test_password_reentered_help():
    html = render(has_password=False, password_reentered=True)
    assert "Re-enter the password. It is not kept when the form is redisplayed." in html


def test_sentinel_secret_never_rendered():
    html = render(has_password=True, settings=dict(password=SENTINEL),
                  status=dict(level="well", glyph="", word="Off", text="x", title=""))
    assert SENTINEL not in html


def test_allow_commands_default_and_warning():
    html = render()
    tag = input_by_name(html, "allow_commands")
    assert "checked" not in tag
    warn = re.search(r'<[^>]*id="mqtt-commands-warning"[^>]*>', html).group(0)
    assert "hidden" in warn
    on = render(settings=dict(allow_commands=True))
    assert "checked" in input_by_name(on, "allow_commands")
    warn_on = re.search(r'<[^>]*id="mqtt-commands-warning"[^>]*>', on).group(0)
    assert "hidden" not in warn_on
    assert ("Anyone who can reach your Home Assistant or MQTT broker can change burner settings "
            "while this is on. Use a broker password and TLS.") in on


def test_tls_off_disables_verify_and_marker():
    html = render(settings=dict(tls=False))
    assert " disabled" in input_by_name(html, "tls_verify")
    assert "Turn on TLS to change this." in html
    marker = input_by_name(html, "tls_verify_field")
    assert " disabled" in marker
    assert "checked" in input_by_name(html, "tls_verify")
    assert "hidden" in re.search(r'<[^>]*id="mqtt-verify-warning"[^>]*>', html).group(0)


def test_tls_on_enables_verify_and_marker():
    html = render(settings=dict(tls=True, tls_verify=True))
    assert " disabled" not in input_by_name(html, "tls_verify")
    marker = input_by_name(html, "tls_verify_field")
    assert " disabled" not in marker
    assert "Turn on TLS to change this." not in html
    assert len([t for t in inputs(html) if 'name="tls_verify_field"' in t]) == 1
    assert 'type="hidden"' in marker and 'id="tls_verify_field"' in marker and 'value="1"' in marker
    assert "hidden" in re.search(r'<[^>]*id="mqtt-verify-warning"[^>]*>', html).group(0)


def test_verify_warning_shown_when_tls_on_verify_off():
    html = render(settings=dict(tls=True, tls_verify=False))
    assert "checked" not in input_by_name(html, "tls_verify")
    assert "hidden" not in re.search(r'<[^>]*id="mqtt-verify-warning"[^>]*>', html).group(0)
    assert ("Certificate verification is off. The connection is encrypted, but PellMon does not "
            "check who the broker is.") in html


def test_buttons_and_auth():
    html = render()
    assert re.search(r'<button[^>]*class="btn btn-primary mqtt-save"[^>]*>\s*Save settings\s*</button>', html)
    test_btn = re.search(r'<button[^>]*class="btn btn-default mqtt-test"[^>]*>\s*Test connection\s*</button>', html)
    assert test_btn and re.search(r'formaction="/homeassistant/test"', test_btn.group(0))
    assert "Saving is disabled until web login credentials are configured." not in html
    off = render(auth_configured=False)
    assert "Saving is disabled until web login credentials are configured." in off
    for cls in ("mqtt-save", "mqtt-test"):
        assert re.search(r'<button[^>]*%s[^>]*disabled' % cls, off)
        assert not re.search(r'<button[^>]*%s[^>]*disabled' % cls, html)


def test_status_element_and_position():
    st = dict(level="success", glyph="ok", word="Connected", text="to broker:1883.", title="2026-09-25 10:00:00")
    html = render(status=st)
    tag = re.search(r'<div[^>]*id="mqtt-status"[^>]*>', html).group(0)
    assert 'role="status"' in tag and 'aria-live="polite"' in tag
    assert "alert-success" in tag
    assert 'title="2026-09-25 10:00:00"' in tag
    assert "glyphicon-ok" in html
    assert re.search(r"<strong>Connected</strong>", html)
    assert html.index('id="mqtt-status"') < html.index('class="panel-heading"')
    well = re.search(r'<div[^>]*id="mqtt-status"[^>]*>', render()).group(0)
    assert "well" in well and "alert-" not in well


def test_error_rendering():
    html = render(errors=dict(port="Port must be a number from 1 to 65535."),
                  msg="Could not save. Fix the highlighted fields and try again.", msg_level="danger")
    assert re.search(r'class="form-group[^"]*has-error', html)
    port = input_by_name(html, "port")
    assert 'aria-invalid="true"' in port
    assert 'id="port-error"' in html and "Port must be a number from 1 to 65535." in html
    assert re.search(r'aria-describedby="[^"]*port-error', port)
    alert = re.search(r'<div[^>]*class="alert alert-danger"[^>]*>', html).group(0)
    assert 'role="alert"' in alert and 'tabindex="-1"' in alert


def test_success_message_role_status():
    html = render(msg="Settings saved.", msg_level="success")
    assert re.search(r'<div[^>]*alert-success[^>]*role="status"[^>]*>\s*Settings saved\.', html)


def test_test_result_area():
    html = render(test_msg="Connection successful.", test_level="success")
    assert re.search(r'<p[^>]*id="mqtt-test-result"[^>]*role="status"[^>]*aria-live="polite"', html)
    assert "text-success" in html and "Connection successful." in html


def test_grid_and_inline_style_rules():
    for cls in re.findall(r'class="([^"]*)"', TEMPLATE):
        if re.search(r"\bcol-(sm|md)-", cls):
            assert re.search(r"\bcol-xs-", cls), cls
    for m in re.finditer(r'style="([^"]*)"', TEMPLATE):
        style = m.group(1)
        assert "height" not in style
        for num in re.findall(r"width\s*:\s*(\d+)px", style):
            assert int(num) < 361


def test_escaping():
    html = render(settings=dict(host="<script>x</script>", prefix='"><b>'))
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert '"><b>' not in html


def test_prefix_help_code():
    html = render(settings=dict(prefix="mypre"))
    assert '<code class="mqtt-prefix-code">mypre</code>/&lt;item&gt;/state' in html


def test_d19_fields_copy():
    html = render()
    assert "Discovery node ID" in html and "Unique ID prefix" in html
    assert ("Only needed to take over an existing device: the node ID used in its discovery topics. "
            "Leave empty to use the device identifier.") in html
    assert ("Only needed to take over an existing device: the part of each entity&#39;s unique ID "
            "before the item name. Leave empty to use the device identifier.") in html \
        or ("the part of each entity's unique ID before the item name. Leave empty to use the "
            "device identifier.") in html


def test_navbar_entry():
    html = render()
    assert re.search(r'<li class="active">\s*<a href="/homeassistant/">Home Assistant</a>', html)
    assert re.search(r'<a href="/settings/">Settings</a>', html)
    assert html.index("/settings/") < html.index("/homeassistant/")
    other = TemplateLookup(directories=[str(HTML_DIR)]).get_template("logview.html").render(
        username=None, webroot="")
    assert "/homeassistant/" in other
    assert not re.search(r'<li class="active">\s*<a href="/homeassistant/">', other)


# ---- CSS (UI-SPEC acceptance 10) ----

P6 = "/* Phase 6: Home Assistant / MQTT */"
P10 = "/* Phase 10: mobile / responsive */"


def p6_block():
    return CSS[CSS.index(P6):CSS.index(P10)]


def test_css_order():
    assert CSS.index(P6) < CSS.index(P10)


def test_css_phase6_block_values():
    b = p6_block()
    for needle in (".mqtt-", "max-width: 767px", "min-height: 44px", "padding-left: 8px"):
        assert needle in b, needle
    assert re.search(r"\.mqtt-form code\s*\{[^}]*font-size: 14px", b)
    assert re.search(r"\.mqtt-page \.panel-body\s*\{[^}]*padding: 16px", b)
    assert re.search(r"\.mqtt-page \.alert\s*\{[^}]*padding: 16px", b)
    assert re.search(r"\.mqtt-indent\s*\{[^}]*margin-left: 24px", b)
    assert "#337ab7" not in b
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", b)
    assert not re.search(r"padding[^;}]*\b(10|15)px", b)
    assert "overflow-x" not in b
    assert ".sysimg-tile" in CSS and "Phase 10" in CSS


def test_css_phase6_media_queries_allowed():
    allowed = ("(max-width: 767px)", "(min-width: 768px) and (max-width: 991px)", "(min-width: 768px)")
    for q in re.findall(r"@media\s*([^{]*)\{", p6_block()):
        assert q.strip() in allowed, q
