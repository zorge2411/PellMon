"""Fixtures for headless-browser layout tests (gated by PELLMON_BROWSER_TESTS=1)."""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
MEDIA = SRC / "Pellmonweb" / "media"
JQUERY_MIN = MEDIA / "jquery" / "jquery.min.js"
WIDTHS = {390: (390, 844), 768: (768, 1024), 1280: (1280, 900)}
SHOTS_DIR = Path(os.environ.get("PELLMON_SHOTS_DIR") or (ROOT / "tests" / "browser" / "_shots"))


def _unavailable(msg):
    """Fail when browser tests are mandatory (env var = 1), otherwise skip."""
    if os.environ.get("PELLMON_BROWSER_TESTS") == "1":
        pytest.fail(msg)
    pytest.skip(msg)


@pytest.fixture(scope="session")
def playwright_rt():
    if os.environ.get("PELLMON_BROWSER_TESTS") != "1":
        pytest.skip("set PELLMON_BROWSER_TESTS=1 to run headless-browser layout tests")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        _unavailable("playwright is not installed: %s" % e)
    pw = sync_playwright().start()
    yield pw
    pw.stop()


@pytest.fixture(scope="session")
def browser(playwright_rt):
    try:
        br = playwright_rt.chromium.launch(headless=True)
    except Exception as e:
        _unavailable("chromium not launchable: %s" % e)
    yield br
    br.close()


@pytest.fixture
def page_at(browser):
    """Return open_page(path, width); path is relative to the stub server or absolute."""
    contexts = []

    def open_page(path, width):
        w, h = WIDTHS[width]
        opts = {"viewport": {"width": w, "height": h}}
        if width == 390:
            opts.update(device_scale_factor=2, is_mobile=True, has_touch=True)
        elif width == 768:
            opts.update(has_touch=True)
        ctx = browser.new_context(**opts)
        contexts.append(ctx)
        ctx.route("**/ajax.googleapis.com/**",
                  lambda route: route.fulfill(path=str(JQUERY_MIN), content_type="application/javascript"))
        page = ctx.new_page()
        if path.startswith("http") or path == "about:blank":
            url = path
        else:
            url = request_stub_url() + path
        page.goto(url, wait_until="load")
        return page

    # stub_url is resolved lazily so that harness tests not using the stub never start it
    request_stub_url = lambda: _stub_url_holder["url"]
    yield open_page
    for ctx in contexts:
        ctx.close()


_stub_url_holder = {"url": None}


def shot(page, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS_DIR / ("%s.png" % name)), full_page=True)
