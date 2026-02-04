import random
import time
from typing import Optional, Dict, Any, Tuple

from playwright.sync_api import sync_playwright, Error, Browser, BrowserContext, Page
import playwright_stealth

from utils import rotate_ua, random_delay


def init_browser(
    headless: bool = True,
    proxy: Optional[Dict[str, Any]] = None,
    proxies: Optional[list[str]] = None,
) -> Tuple[Browser, BrowserContext, Page]:
    """Description.

    Args:
        headless (type): desc.
        proxy (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=headless)
        if proxies:
            proxy = {"server": random.choice(proxies)}
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=rotate_ua(),
            proxy=proxy,
        )
        playwright_stealth.stealth_sync(context)
        page = context.new_page()
        return browser, context, page
    except Error:
        time.sleep(1)
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=headless)
        if proxies:
            proxy = {"server": random.choice(proxies)}
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=rotate_ua(),
            proxy=proxy,
        )
        playwright_stealth.stealth_sync(context)
        page = context.new_page()
        return browser, context, page


def scroll_and_navigate(
    page: Page,
    url: str,
    depth: int,
    min_delay: int,
    max_delay: int,
) -> None:
    """Description.

    Args:
        page (type): desc.
        url (type): desc.
        depth (type): desc.
        min_delay (type): desc.
        max_delay (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    try:
        page.goto(url)
        for _ in range(depth):
            page.mouse.move(random.randint(0, 800), random.randint(0, 600))
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(min_delay, max_delay)
    except Error:
        time.sleep(1)
        page.goto(url)
        for _ in range(depth):
            page.mouse.move(random.randint(0, 800), random.randint(0, 600))
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(min_delay, max_delay)


def close_browser(browser: Browser, context: BrowserContext) -> None:
    """Description.

    Args:
        browser (type): desc.
        context (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    context.close()
    browser.close()
