import os
from unittest.mock import patch, MagicMock

from silos import browser_automation


def test_init_browser():
    with patch("silos.browser_automation.sync_playwright") as mock_playwright:
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.start.return_value = mock_p
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        browser_automation.init_browser()

        assert mock_browser.new_context.called


def test_scroll():
    if not os.getenv("RUN_FUNCTIONAL"):
        return
    browser, context, page = browser_automation.init_browser(headless=False)
    browser_automation.scroll_and_navigate(page, "https://www.google.com", 5, 1, 2)
    page.screenshot(path="test_scroll.png")
    browser_automation.close_browser(browser, context)


def test_proxy():
    browser, context, page = browser_automation.init_browser(
        headless=True, proxy={"server": "http://localhost:8080"}
    )
    browser_automation.close_browser(browser, context)


def test_delays():
    with patch("utils.time.sleep") as mock_sleep:
        browser, context, page = browser_automation.init_browser(headless=True)
        browser_automation.scroll_and_navigate(page, "https://www.google.com", 1, 1, 2)
        assert mock_sleep.called
        browser_automation.close_browser(browser, context)


def test_errors():
    with patch("silos.browser_automation.sync_playwright") as mock_playwright:
        mock_p = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_playwright.return_value.start.side_effect = [
            browser_automation.Error("fail"),
            mock_p,
        ]
        mock_p.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        browser_automation.init_browser()
