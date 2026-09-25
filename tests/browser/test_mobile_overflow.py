"""Rendered no-sideways-scroll checks (UI-SPEC A1-A3) and the 1280px desktop smoke (D-07)."""
import pytest

from conftest import shot, wait_ready

PAGES = ["/", "/parameters/Overview", "/settings/", "/consumptionview/consumption",
         "/logview/logView", "/auth/login", "/homeassistant/"]

OVERFLOW_JS = """
(W) => {
  const de = document.documentElement, b = document.body;
  const out = {scrollW: de.scrollWidth, bodyScrollW: b.scrollWidth, clientW: de.clientWidth,
               bodyOverflowX: getComputedStyle(b).overflowX, htmlOverflowX: getComputedStyle(de).overflowX,
               viewport: !!document.querySelector('meta[name=viewport]'), offenders: []};
  const clipped = (el) => { for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === 'hidden' || ox === 'auto' || ox === 'scroll') {
        const r = p.getBoundingClientRect(); if (r.right <= W + 1) return true; } } return false; };
  for (const el of document.body.querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > W + 1 && !clipped(el))
      out.offenders.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + String(el.className).split(' ').join('.') + ' right=' + Math.round(r.right));
  }
  return out;
}"""


def slug(path):
    return path.strip("/").replace("/", "-") or "main"


@pytest.mark.parametrize("width", [390, 768])
@pytest.mark.parametrize("path", PAGES, ids=slug)
def test_no_horizontal_overflow(page_at, path, width):
    page = page_at(path, width)
    wait_ready(page, path)
    shot(page, "overflow-%s-%d" % (slug(path), width))
    res = page.evaluate(OVERFLOW_JS, width)
    where = "%s at %dpx" % (path, width)
    assert res["scrollW"] <= width, "A1: documentElement.scrollWidth %s > %s on %s; offenders: %s" % (
        res["scrollW"], width, where, res["offenders"])
    assert res["bodyScrollW"] <= width, "A1: body.scrollWidth %s > %s on %s; offenders: %s" % (
        res["bodyScrollW"], width, where, res["offenders"])
    assert not res["offenders"], "A2: elements stick out sideways on %s: %s" % (where, res["offenders"])
    assert res["viewport"], "A3: viewport meta tag missing on %s" % where
    assert res["bodyOverflowX"] != "hidden", "A3: overflow-x hidden on body masks overflow (%s)" % where
    assert res["htmlOverflowX"] != "hidden", "A3: overflow-x hidden on html masks overflow (%s)" % where


COL_RECT_JS = "e => { const r = e.closest('[class*=col-]').getBoundingClientRect(); return {top: r.top, left: r.left}; }"


def test_desktop_smoke_1280(page_at, stub_url):
    page = page_at("/", 1280)
    wait_ready(page, "/")
    shot(page, "desktop-main-1280")
    graph_h = page.evaluate("document.getElementById('graph').offsetHeight")
    assert abs(graph_h - 400) <= 1, "D-07: desktop graph height must be 400px, got %s" % graph_h
    img = page.locator("#systemimage").evaluate(COL_RECT_JS)
    events = page.locator("#events-wrap").evaluate(COL_RECT_JS)
    assert abs(img["top"] - events["top"]) <= 1, "D-07: systemimage and events columns must share a top, got %s vs %s" % (
        img["top"], events["top"])
    assert abs(img["left"] - events["left"]) > 1, "D-07: systemimage and events columns must be side by side"
    assert not page.locator(".events-toggle").is_visible(), "D-07: events toggle must be hidden on desktop"

    page.goto(stub_url + "/parameters/Overview", wait_until="load")
    page.wait_for_selector("#param-data", state="attached")
    shot(page, "desktop-parameters-1280")
    assert page.locator("#param-data").is_visible(), "D-07: #param-data must be visible on desktop"
    assert page.locator("#param-settings").is_visible(), "D-07: #param-settings must be visible on desktop"
    data = page.locator("#param-data").bounding_box()
    sett = page.locator("#param-settings").bounding_box()
    assert abs(data["y"] - sett["y"]) <= 1, "D-07: Data and Settings must share a top on desktop"
    assert abs(data["x"] - sett["x"]) > 1, "D-07: Data and Settings must be side by side on desktop"
