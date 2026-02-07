import random
import time
from typing import Any, Dict, Optional, Tuple

from playwright.sync_api import sync_playwright, Error, Browser, BrowserContext, Page

from utils import rotate_ua, random_delay

# Optional: apply stealth if available (API may vary by version)
try:
    import playwright_stealth
    _stealth_fn = getattr(playwright_stealth, "stealth_sync", None)
except Exception:
    _stealth_fn = None


def _apply_stealth(context: BrowserContext) -> None:
    if _stealth_fn is not None:
        _stealth_fn(context)


def init_browser(
    headless: bool = True,
    proxy: Optional[Dict[str, Any]] = None,
    proxies: Optional[list[str]] = None,
) -> Tuple[Any, Browser, BrowserContext, Page]:
    """Launch Playwright and return (playwright_instance, browser, context, page)."""
    p = None
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
        _apply_stealth(context)
        page = context.new_page()
        return (p, browser, context, page)
    except Error:
        if p is not None:
            try:
                p.stop()
            except Exception:
                pass
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
        _apply_stealth(context)
        page = context.new_page()
        return (p, browser, context, page)


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


def close_browser(
    playwright_instance: Any,
    browser: Browser,
    context: BrowserContext,
) -> None:
    """Close context, browser, and stop Playwright."""
    try:
        context.close()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass
    try:
        playwright_instance.stop()
    except Exception:
        pass
