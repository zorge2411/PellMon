"""Fixtures for headless-browser layout tests (gated by PELLMON_BROWSER_TESTS=1)."""
import os
import subprocess
import sys
import time
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


@pytest.fixture(scope="session")
def stub_url(playwright_rt):
    """Start tests/browser/stub_server.py in a subprocess and yield its base URL.

    The port is read from the child's stdout, so the test process opens no TCP socket."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, str(Path(__file__).with_name("stub_server.py"))],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    collected = []
    port = None
    deadline = time.time() + 30
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        collected.append(line)
        if line.startswith("READY port="):
            port = int(line.split("=", 1)[1])
            break
    if port is None:
        proc.kill()
        _unavailable("stub server did not start:\n%s" % "".join(collected))
    yield "http://127.0.0.1:%d" % port
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def page_at(browser, request):
    """Return open_page(path, width); path is relative to the stub server, or absolute."""
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
            url = request.getfixturevalue("stub_url") + path
        page.goto(url, wait_until="load")
        return page

    yield open_page
    for ctx in contexts:
        ctx.close()


def shot(page, name):
    SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS_DIR / ("%s.png" % name)), full_page=True)
