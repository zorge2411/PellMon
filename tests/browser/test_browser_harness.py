"""Harness smoke tests: Playwright and Chromium work under the suite's socket guard."""
import pytest

PAGES = ["/", "/parameters/Overview", "/settings/", "/consumptionview/consumption",
         "/logview/logView", "/auth/login", "/homeassistant/"]


def test_playwright_starts_under_socket_guard(playwright_rt):
    assert playwright_rt is not None


def test_chromium_launches_and_renders_about_blank(page_at):
    page = page_at("about:blank", 1280)
    assert page.evaluate("1+1") == 2


@pytest.mark.parametrize("path", PAGES)
def test_stub_serves_key_pages(page_at, stub_url, path):
    page = page_at("about:blank", 390)
    response = page.goto(stub_url + path, wait_until="load")
    assert response.status == 200
    assert page.locator(".navbar").count() >= 1
