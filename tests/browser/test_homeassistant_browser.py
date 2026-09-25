"""Rendered checks for /homeassistant/ (06-UI-SPEC H-A1, H-A2, H-B1..H-B10, H-E1..H-E3).

Gated by PELLMON_BROWSER_TESTS=1 through the shared fixtures; run in WSL/CI:
PELLMON_BROWSER_TESTS=1 PYTHONPATH=src pytest tests/browser -v -rs --allow-unix-socket
"""
import json

import pytest

from conftest import shot
from test_mobile_overflow import OVERFLOW_JS

PATH = "/homeassistant/"
COL_TOP_JS = "e => e.closest('[class*=col-]').getBoundingClientRect().top"
ENABLE_BUTTONS_JS = "document.querySelectorAll('.mqtt-save, .mqtt-test').forEach(b => { b.disabled = false; })"

LONG_HOST = ("a" * 62 + ".") * 4 + "b"
LONG_PREFIX = "p" * 64
LONG_ID = "i" * 64

STATUS_OFF = {"level": "well", "glyph": "", "word": "Off.",
              "text": 'Home Assistant publishing is turned off. Turn on "Enable Home Assistant MQTT" and save to connect.',
              "title": ""}
STATUS_CONNECTED = {"level": "success", "glyph": "ok", "word": "Connected",
                    "text": "to broker.example.com:1883. Last publish: 10:00:00.", "title": ""}
STATUS_DISCONNECTED = {"level": "danger", "glyph": "remove", "word": "Disconnected",
                       "text": "from %s:1883: certificate could not be verified. PellMon keeps retrying automatically." % LONG_HOST,
                       "title": ""}
STATUS_BURNER_OFFLINE = {"level": "warning", "glyph": "warning-sign", "word": "Connected",
                         "text": "to broker.example.com:1883, but the burner is not connected. Home Assistant shows "
                                 "the entities as unavailable until it answers again.", "title": ""}


def assert_no_overflow(page, width, where):
    res = page.evaluate(OVERFLOW_JS, width)
    assert res["scrollW"] <= width, "A1: documentElement.scrollWidth %s > %s (%s); offenders: %s" % (
        res["scrollW"], width, where, res["offenders"])
    assert res["bodyScrollW"] <= width, "A1: body.scrollWidth %s > %s (%s); offenders: %s" % (
        res["bodyScrollW"], width, where, res["offenders"])
    assert not res["offenders"], "A2: elements stick out sideways (%s): %s" % (where, res["offenders"])
    assert res["viewport"], "A3: viewport meta missing (%s)" % where
    assert res["bodyOverflowX"] != "hidden" and res["htmlOverflowX"] != "hidden", "A3: overflow-x hidden (%s)" % where


def open_ha(page_at, width):
    page = page_at(PATH, width)
    page.wait_for_selector("#mqtt-status", state="attached", timeout=20000)
    return page


def fill_longest(page):
    page.fill("#host", LONG_HOST)
    page.fill("#prefix", LONG_PREFIX)
    page.fill("#device_id", LONG_ID)


def submit_invalid_port(page):
    """Save with port 70000 so the server re-renders the error state."""
    page.evaluate(ENABLE_BUTTONS_JS)
    page.evaluate("document.querySelector('form.mqtt-form').noValidate = true")
    page.fill("#port", "70000")
    with page.expect_navigation(wait_until="load"):
        page.click(".mqtt-save")
    page.wait_for_selector(".form-group.has-error", state="attached", timeout=20000)


def status_route(page, holder):
    page.route("**/homeassistant/status*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(holder["view"])))


# ---------------------------------------------------------------- H-A1 / H-A2

@pytest.mark.parametrize("width", [390, 768])
def test_a1_no_overflow_with_longest_values_and_error_state(page_at, width):
    page = open_ha(page_at, width)
    assert_no_overflow(page, width, "default at %d" % width)
    fill_longest(page)
    assert_no_overflow(page, width, "longest values at %d" % width)
    submit_invalid_port(page)
    shot(page, "homeassistant-error-%d" % width)
    assert_no_overflow(page, width, "error state at %d" % width)


@pytest.mark.parametrize("width", [390, 768])
@pytest.mark.parametrize("name,view,word", [
    ("off", STATUS_OFF, "Off."),
    ("connected", STATUS_CONNECTED, "Connected"),
    ("disconnected", STATUS_DISCONNECTED, "Disconnected"),
    ("burner-offline", STATUS_BURNER_OFFLINE, "burner is not connected"),
])
def test_a2_no_overflow_in_each_status_state(page_at, width, name, view, word):
    page = open_ha(page_at, width)
    status_route(page, {"view": view})
    page.wait_for_function(
        "w => document.getElementById('mqtt-status').textContent.indexOf(w) !== -1", arg=word, timeout=9000)
    shot(page, "homeassistant-status-%s-%d" % (name, width))
    assert_no_overflow(page, width, "status %s at %d" % (name, width))


# ---------------------------------------------------------------- 390px

def test_b1_status_line_above_first_panel_and_fold(page_at):
    page = open_ha(page_at, 390)
    status = page.locator("#mqtt-status").bounding_box()
    panel = page.locator(".mqtt-form .panel").first.bounding_box()
    assert status["y"] < 844, "H-B1: status line below the fold (top %s)" % status["y"]
    assert status["y"] < panel["y"], "H-B1: status line must be above the first panel"


def test_b2_tap_targets_and_form_control_sizes(page_at):
    page = open_ha(page_at, 390)
    controls = page.locator(".mqtt-form .form-control")
    assert controls.count() >= 9
    for i in range(controls.count()):
        box = controls.nth(i).bounding_box()
        assert box["height"] >= 44, "H-B2: form-control %d height %s" % (i, box["height"])
        assert box["width"] >= 300, "H-B2: form-control %d width %s" % (i, box["width"])
        assert controls.nth(i).evaluate("e => getComputedStyle(e).fontSize") == "16px"
    labels = page.locator(".mqtt-form .checkbox label")
    for i in range(labels.count()):
        assert labels.nth(i).bounding_box()["height"] >= 44, "H-B2: checkbox label %d shorter than 44px" % i
    save = page.locator(".mqtt-save").bounding_box()
    test = page.locator(".mqtt-test").bounding_box()
    for name, box in (("save", save), ("test", test)):
        assert box["height"] >= 44 and box["width"] >= 340, "H-B2: %s button %s" % (name, box)
    assert save["y"] < test["y"], "H-B2: Save must be above Test"
    assert test["y"] - (save["y"] + save["height"]) >= 8, "H-B2: buttons closer than 8px"


def test_b3_single_column_fields(page_at):
    page = open_ha(page_at, 390)
    lefts = page.locator(".mqtt-form .form-control").evaluate_all(
        "els => els.map(e => e.getBoundingClientRect().left)")
    assert max(lefts) - min(lefts) <= 1, "H-B3: fields are not single column: %s" % lefts


def test_b4_navbar_menu_link(page_at):
    page = open_ha(page_at, 390)
    page.click(".navbar-toggle")
    link = page.locator(".navbar a", has_text="Home Assistant").first
    link.wait_for(state="visible", timeout=5000)
    box = link.bounding_box()
    assert box["height"] >= 44, "H-B4: menu link height %s" % box["height"]
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390, "H-B4: menu link outside viewport: %s" % box


def test_b5_password_never_in_page(page_at):
    page = open_ha(page_at, 390)
    pw = page.locator("input[type=password]")
    assert pw.input_value() == ""
    assert pw.get_attribute("placeholder") == "set"
    assert pw.get_attribute("value") is None
    html = page.evaluate("document.body.innerHTML")
    assert "s3cret-XYZ" not in html


def test_b6_tls_interaction(page_at):
    page = open_ha(page_at, 390)
    marker = "document.getElementById('tls_verify_field').disabled"
    assert page.locator("#tls_verify").is_disabled(), "H-B6: Verify must be disabled while TLS is off"
    assert page.evaluate(marker) is True, "H-B6: hidden marker must be disabled together with Verify"
    assert page.input_value("#port") == "1883"
    page.check("#tls")
    assert page.locator("#tls_verify").is_enabled()
    assert page.evaluate(marker) is False, "H-B6: hidden marker must be enabled after ticking TLS"
    assert page.input_value("#port") == "8883"
    assert not page.locator("#mqtt-verify-warning").is_visible()
    page.uncheck("#tls_verify")
    warning = page.locator("#mqtt-verify-warning")
    assert warning.is_visible()
    assert "Certificate verification is off" in warning.inner_text()
    page.uncheck("#tls")
    assert page.locator("#tls_verify").is_disabled()
    assert page.evaluate(marker) is True, "H-B6: hidden marker must be disabled again after unticking TLS"
    assert page.input_value("#port") == "1883"
    assert not page.locator("#mqtt-verify-warning").is_visible()


def test_b7_allow_commands_warning(page_at):
    page = open_ha(page_at, 390)
    warning = page.locator("#mqtt-commands-warning")
    assert not page.locator("#allow_commands").is_checked()
    assert not warning.is_visible()
    page.check("#allow_commands")
    assert warning.is_visible()
    box = warning.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 390, "H-B7: warning outside the viewport: %s" % box
    page.uncheck("#allow_commands")
    assert not warning.is_visible()


def test_b8_test_connection_states(page_at):
    page = open_ha(page_at, 390)
    page.evaluate(ENABLE_BUTTONS_JS)
    urls = []
    page.on("request", lambda r: urls.append(r.url))
    held = []
    page.route("**/homeassistant/test", lambda route: held.append(route))
    button = page.locator(".mqtt-test")
    result = page.locator("#mqtt-test-result")

    def run(body, expected):
        del held[:]
        button.click()
        for _ in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        assert held, "H-B8: the test request was never sent"
        assert button.inner_text().strip() == "Testing..."
        assert button.is_disabled()
        assert button.get_attribute("aria-busy") == "true"
        assert "Testing the connection..." in result.inner_text()
        held[0].fulfill(status=200, content_type="application/json", body=json.dumps(body))
        page.wait_for_function(
            "t => document.getElementById('mqtt-test-result').textContent.indexOf(t) !== -1", arg=expected, timeout=5000)
        assert button.inner_text().strip() == "Test connection"
        assert button.is_enabled()
        assert button.get_attribute("aria-busy") is None

    run({"state": "ok", "level": "success", "errors": {},
         "message": "Connection successful. The broker accepted the host, port, credentials and TLS settings. Nothing was saved."},
        "Connection successful.")
    assert "text-success" in result.get_attribute("class")
    run({"state": "error", "level": "danger", "errors": {},
         "message": "Test failed: connection refused. Nothing was saved."}, "Test failed:")
    assert "connection refused" in result.inner_text()
    assert "text-danger" in result.get_attribute("class")
    assert not [u for u in urls if "/save" in u], "H-B8: the test path must never call /save"


def test_b9_save_invalid_port_shows_errors(page_at):
    page = open_ha(page_at, 390)
    submit_invalid_port(page)
    assert page.locator(".form-group.has-error #port").count() == 1, "H-B9: port group lacks has-error"
    assert page.locator("#port").get_attribute("aria-invalid") == "true"
    summary = page.locator(".mqtt-page > .alert[role=alert]")
    assert summary.count() == 1
    page.wait_for_function("() => document.activeElement && document.activeElement.getAttribute('role') === 'alert'",
                           timeout=5000)


def test_b10_status_refreshes_without_navigation(page_at):
    page = open_ha(page_at, 390)
    holder = {"view": STATUS_CONNECTED}
    status_route(page, holder)
    page.evaluate("window.__mqttMarker = 1")
    holder["view"] = STATUS_DISCONNECTED
    page.wait_for_function(
        "() => document.getElementById('mqtt-status').className.indexOf('alert-danger') !== -1", timeout=6500)
    text = page.locator("#mqtt-status").inner_text()
    assert "Disconnected" in text
    assert page.evaluate("window.__mqttMarker") == 1, "H-B10: the page reloaded instead of updating in place"


# ---------------------------------------------------------------- 768px

@pytest.mark.parametrize("left,right", [("host", "port"), ("username", "password"),
                                        ("prefix", "discovery_prefix"), ("device_id", "device_name")])
def test_e1_paired_rows(page_at, left, right):
    page = open_ha(page_at, 768)
    a = page.locator("#" + left)
    b = page.locator("#" + right)
    assert abs(a.evaluate(COL_TOP_JS) - b.evaluate(COL_TOP_JS)) <= 1, "H-E1: %s and %s not on one row" % (left, right)
    if left == "host":
        assert a.bounding_box()["width"] > b.bounding_box()["width"], "H-E1: host must be wider than port"


def test_e2_save_and_test_on_one_row(page_at):
    page = open_ha(page_at, 768)
    save = page.locator(".mqtt-save").bounding_box()
    test = page.locator(".mqtt-test").bounding_box()
    assert abs(save["y"] - test["y"]) <= 1, "H-E2: buttons not on one row"
    assert test["x"] - (save["x"] + save["width"]) >= 8, "H-E2: gap between buttons under 8px"
    assert save["width"] < 300 and test["width"] < 300, "H-E2: buttons must be auto width"


def test_e3_navbar_stays_on_one_row(page_at):
    page = open_ha(page_at, 768)
    tops = page.locator(".navbar-nav > li").evaluate_all("els => els.map(e => e.getBoundingClientRect().top)")
    assert len(tops) >= 2
    assert max(tops) - min(tops) <= 1, "H-E3: navbar wraps at 768px: %s" % tops
    assert page.locator(".navbar-nav > li", has_text="Home Assistant").count() == 1
    assert page.locator(".navbar").first.bounding_box()["height"] <= 60
    pad = page.locator(".navbar-nav > li > a").first.evaluate("e => getComputedStyle(e).paddingLeft")
    assert pad == "8px", "H-E3: navbar link padding-left is %s" % pad
