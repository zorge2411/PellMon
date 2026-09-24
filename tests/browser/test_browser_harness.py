"""Harness smoke tests: Playwright and Chromium work under the suite's socket guard."""


def test_playwright_starts_under_socket_guard(playwright_rt):
    assert playwright_rt is not None


def test_chromium_launches_and_renders_about_blank(page_at):
    page = page_at("about:blank", 1280)
    assert page.evaluate("1+1") == 2
