"""Rendered geometry and interaction checks (UI-SPEC B1-B7, C1-C3, D1-D2, E1-E3)."""
from conftest import shot, wait_dashboard

TAPPABLE = "a.lineselection, a.timeChoice, a.autorefresh, .graph-nav .btn"
SETTINGS_TOGGLE = "a.param-section-toggle[href='#param-settings']"


def rect(page, selector):
    box = page.locator(selector).first.bounding_box()
    assert box is not None, "%s is not rendered" % selector
    return box


def boxes(page, selector):
    out = []
    loc = page.locator(selector)
    for i in range(loc.count()):
        box = loc.nth(i).bounding_box()
        if box is not None:
            out.append(box)
    return out


def distinct_columns(lefts):
    cols = []
    for x in sorted(lefts):
        if not cols or x - cols[-1] > 1:
            cols.append(x)
    return cols


def open_settings(page):
    page.wait_for_selector("#param-settings", state="attached")
    page.locator(SETTINGS_TOGGLE).tap()
    page.wait_for_function("document.getElementById('param-settings').classList.contains('in')")
    page.wait_for_function("!document.getElementById('param-settings').classList.contains('collapsing')")


def test_main_390_order_and_sizes(page_at):
    page = page_at("/", 390)
    wait_dashboard(page)
    shot(page, "main-390-order")
    ids = ["#systemimage", "#events-wrap", "#graph", "#consumption7d", "#silolevel"]
    tops = [rect(page, i)["y"] for i in ids]
    assert all(a < b for a, b in zip(tops, tops[1:])), "B1: dashboard order must be %s, tops were %s" % (ids, tops)
    img = rect(page, "#systemimage")
    assert 340 <= img["width"] <= 360, "B2: system image width must be 340-360, got %s" % img["width"]
    assert img["height"] >= 230, "B2: system image height must be >= 230, got %s" % img["height"]
    graph_h = page.evaluate("document.getElementById('graph').offsetHeight")
    graph_w = page.evaluate("document.getElementById('graph').offsetWidth")
    assert abs(graph_h - 260) <= 1, "B4: phone graph height must be 260px, got %s" % graph_h
    assert graph_w <= 360, "B4: phone graph width must be <= 360, got %s" % graph_w
    heights = page.evaluate("Array.from(document.querySelectorAll('.pellmon-chart')).map(e => e.offsetHeight)")
    assert heights, "B7: no .pellmon-chart elements found"
    for h in heights:
        assert abs(h - 260) <= 1, "B7: phone chart height must be 260px, got %s" % h


def test_main_390_events_toggle(page_at):
    page = page_at("/", 390)
    wait_dashboard(page)
    wrap = "document.getElementById('events-wrap')"
    assert page.evaluate("%s.classList.contains('events-collapsed')" % wrap), "B3: events must start collapsed"
    assert page.evaluate("%s.offsetHeight" % wrap) <= 96, "B3: collapsed events must be <= 96px tall"
    toggle = page.locator(".events-toggle")
    assert toggle.is_visible(), "B3: events toggle must be visible on phones"
    assert rect(page, ".events-toggle")["height"] >= 44, "B3: events toggle must be >= 44px tall"
    assert toggle.inner_text().strip() == "Show all events", "B3: collapsed label wrong: %r" % toggle.inner_text()
    shot(page, "main-390-events-collapsed")

    toggle.tap()
    page.wait_for_function("!document.getElementById('events-wrap').classList.contains('events-collapsed')")
    assert toggle.inner_text().strip() == "Show fewer events", "B3: expanded label wrong: %r" % toggle.inner_text()
    assert toggle.get_attribute("aria-expanded") == "true", "B3: aria-expanded must be true after tap"
    assert page.locator("#lines").count() == 1, "B3: #lines must survive toggling"
    shot(page, "main-390-events-expanded")

    toggle.tap()
    page.wait_for_function("document.getElementById('events-wrap').classList.contains('events-collapsed')")
    assert toggle.inner_text().strip() == "Show all events", "B3: label must return to 'Show all events'"
    assert toggle.get_attribute("aria-expanded") == "false", "B3: aria-expanded must return to false"


def test_main_390_graph_tap_targets(page_at):
    page = page_at("/", 390)
    wait_dashboard(page)
    shot(page, "main-390-graph-targets")
    found = boxes(page, TAPPABLE)
    assert found, "B5: no graph controls found"
    for box in found:
        assert box["height"] >= 44, "B5: graph control height must be >= 44, got %s" % box
        assert box["width"] >= 44, "B5: graph control width must be >= 44, got %s" % box
        assert box["x"] + box["width"] <= 390.5, "B5: graph control sticks out past 390px: %s" % box


def test_main_390_navbar(page_at):
    page = page_at("/", 390)
    wait_dashboard(page)
    toggle = page.locator(".navbar-toggle")
    assert toggle.is_visible(), "B6: navbar hamburger must be visible on phones"
    box = rect(page, ".navbar-toggle")
    assert box["width"] >= 44 and box["height"] >= 44, "B6: hamburger must be >= 44x44, got %s" % box
    assert toggle.get_attribute("aria-label") == "Toggle navigation", "B6: hamburger aria-label wrong"
    shot(page, "main-390-navbar-closed")
    toggle.tap()
    page.wait_for_function("document.querySelector('.navbar-collapse').classList.contains('in')")
    page.wait_for_function("!document.querySelector('.navbar-collapse').classList.contains('collapsing')")
    assert toggle.get_attribute("aria-expanded") == "true", "B6: aria-expanded must be true after tap"
    shot(page, "main-390-navbar-open")
    links = boxes(page, ".navbar-nav > li > a")
    assert links, "B6: no navbar links found"
    for b in links:
        assert b["height"] >= 44, "B6: navbar link height must be >= 44, got %s" % b
        assert b["x"] + b["width"] <= 390.5, "B6: navbar link sticks out past 390px: %s" % b


def test_parameters_390_pills(page_at):
    page = page_at("/parameters/Overview", 390)
    page.wait_for_selector("ul.param-tags > li")
    shot(page, "parameters-390-pills")
    ul_w = rect(page, "ul.param-tags")["width"]
    lis = boxes(page, "ul.param-tags > li")
    assert len(lis) >= 3, "C1: need at least 3 pills, got %s" % len(lis)
    for b in lis:
        assert abs(b["width"] - (ul_w * 0.5 - 8)) <= 2, "C1: pill width must be 50%% of the list minus 8px (%s), got %s" % (
            ul_w * 0.5 - 8, b["width"])
    assert abs(lis[0]["y"] - lis[1]["y"]) <= 1, "C1: pills 0 and 1 must share a row"
    assert lis[2]["y"] > lis[0]["y"] + 1, "C1: pill 2 must be on a lower row"
    hgap = lis[1]["x"] - (lis[0]["x"] + lis[0]["width"])
    assert hgap >= 7.5, "C1: horizontal gap between pills must be >= 8, got %s" % hgap
    vgap = lis[2]["y"] - (lis[0]["y"] + lis[0]["height"])
    assert vgap >= 7.5, "C1: vertical gap between pill rows must be >= 8, got %s" % vgap
    for b in boxes(page, "ul.param-tags > li > a"):
        assert b["height"] >= 44, "C1: pill link height must be >= 44, got %s" % b


def test_parameters_390_sections(page_at):
    page = page_at("/parameters/Overview", 390)
    page.wait_for_selector("#param-settings", state="attached")
    assert page.locator("#param-control").is_visible(), "C2: Control must start open"
    assert page.locator("#param-data").is_visible(), "C2: Data must start open"
    assert page.evaluate("document.getElementById('param-settings').offsetHeight") == 0, "C2: Settings must start collapsed"
    for b in boxes(page, "a.param-section-toggle"):
        assert b["height"] >= 44, "C2: section toggle height must be >= 44, got %s" % b
    shot(page, "parameters-390-sections-closed")
    open_settings(page)
    assert page.locator("#param-settings").is_visible(), "C2: Settings must be visible after tap"
    assert page.locator(SETTINGS_TOGGLE).get_attribute("aria-expanded") == "true", \
        "C2: Settings toggle aria-expanded must be true after tap"
    shot(page, "parameters-390-sections-open")


def test_parameters_390_controls(page_at):
    page = page_at("/parameters/Overview", 390)
    open_settings(page)
    checked = 0
    for idx in (0, 1):
        page.locator("#param-settings dt").nth(idx).tap()
        page.wait_for_selector("#param-settings .details:not(.hidden)")
        shot(page, "parameters-390-controls-%d" % idx)
        for b in boxes(page, "#param-settings .details:not(.hidden) .form-control"):
            assert b["height"] >= 44, "C3: form control height must be >= 44, got %s" % b
            assert b["width"] >= 300, "C3: form control width must be >= 300, got %s" % b
            checked += 1
        for b in boxes(page, "#param-settings .details:not(.hidden) input[type=submit]"):
            assert b["height"] >= 44, "C3: submit button height must be >= 44, got %s" % b
            checked += 1
    assert checked >= 3, "C3: expected to check a select, a text input and a submit button, checked %s" % checked


def test_settings_390_gallery(page_at):
    page = page_at("/settings/", 390)
    page.wait_for_selector(".sysimg-tile")
    shot(page, "settings-390-gallery")
    tiles = boxes(page, ".sysimg-tile")
    assert len(tiles) >= 2, "D1: need at least 2 tiles"
    cols = distinct_columns([t["x"] for t in tiles])
    assert len(cols) == 2, "D1: gallery must have exactly two columns at 390px, got lefts %s" % cols
    for t in tiles:
        assert 150 <= t["width"] <= 190, "D1: tile width must be 150-190, got %s" % t["width"]
    assert rect(page, ".sysimg-save")["height"] >= 44, "D2: Save image must be >= 44px tall"


def test_main_768(page_at):
    page = page_at("/", 768)
    wait_dashboard(page)
    shot(page, "main-768")
    fits = page.evaluate("(() => { const e = document.getElementById('events-wrap'); return [e.offsetHeight, e.scrollHeight]; })()")
    assert fits[0] == fits[1], "E1: events must be fully shown at 768px (offsetHeight %s, scrollHeight %s)" % tuple(fits)
    assert not page.locator(".events-toggle").is_visible(), "E1: events toggle must be hidden at 768px"
    graph_h = page.evaluate("document.getElementById('graph').offsetHeight")
    assert abs(graph_h - 320) <= 1, "E1: tablet graph height must be 320px, got %s" % graph_h
    lefts = page.evaluate("Array.from(document.querySelectorAll('#pellmon-widgets .row > [class*=col-]')).map(e => e.getBoundingClientRect().left)")
    assert lefts and max(lefts) - min(lefts) <= 1, "E1: widgets must be single column at 768px, lefts %s" % lefts


def test_parameters_768(page_at):
    page = page_at("/parameters/Overview", 768)
    page.wait_for_selector("#param-settings", state="attached")
    shot(page, "parameters-768")
    for sec in ("#param-control", "#param-data", "#param-settings"):
        assert page.locator(sec).is_visible(), "E2: %s must be visible at 768px without tapping" % sec
    chevrons = page.locator(".param-section-toggle .glyphicon")
    for i in range(chevrons.count()):
        assert not chevrons.nth(i).is_visible(), "E2: chevron %d must be hidden at 768px" % i


def test_settings_768(page_at):
    page = page_at("/settings/", 768)
    page.wait_for_selector(".sysimg-tile")
    shot(page, "settings-768")
    cols = distinct_columns([t["x"] for t in boxes(page, ".sysimg-tile")])
    assert len(cols) == 2, "E3: gallery must have exactly two columns at 768px, got lefts %s" % cols
