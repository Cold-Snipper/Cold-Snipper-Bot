import random
import time
from typing import Any, Dict, Optional, Tuple

from playwright.sync_api import sync_playwright, Error, Browser, BrowserContext, Page

from utils import rotate_ua, random_delay

# Research-backed: common cookie consent button texts and selectors (OneTrust, Cookiebot, GDPR banners)
CONSENT_BUTTON_TEXTS = [
    "Accept all", "Accept", "I accept", "OK", "Allow all", "Agree", "Accept all cookies",
    "Tout accepter", "Alles akzeptieren", "Accepter", "Accept & continue", "Allow",
]
CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "[data-testid='accept-cookies']",
    ".cookie-consent button",
    "[class*='cookie'] button",
    "[class*='consent'] button",
    "[id*='accept']",
    ".cc-btn.cc-allow",
    "[aria-label*='Accept']",
]

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


def try_accept_consent(page: Page, timeout_per_try_ms: int = 3000) -> bool:
    """Try to dismiss cookie/consent banner (research: click accept is standard). Returns True if clicked."""
    if not page:
        return False
    for text in CONSENT_BUTTON_TEXTS:
        try:
            loc = page.locator(f"button:has-text('{text}'), a:has-text('{text}')").first
            loc.wait_for(state="visible", timeout=timeout_per_try_ms)
            loc.click()
            random_delay(1, 2)
            return True
        except Exception:
            continue
    for sel in CONSENT_SELECTORS:
        try:
            btn = page.wait_for_selector(sel, timeout=2000)
            if btn:
                btn.click()
                random_delay(1, 2)
                return True
        except Exception:
            continue
    return False


def scroll_and_navigate(
    page: Page,
    url: str,
    depth: int,
    min_delay: int,
    max_delay: int,
    timeout_ms: int = 60_000,
) -> None:
    """Navigate to URL, wait for load (research: 'load' then element waits; avoid networkidle), try consent, then scroll."""
    goto_opts = {"timeout": timeout_ms, "wait_until": "load"}
    try:
        page.goto(url, **goto_opts)
        page.wait_for_load_state("load", timeout=timeout_ms)
        try_accept_consent(page)
        random_delay(1, 2)
        for _ in range(depth):
            page.mouse.move(random.randint(0, 800), random.randint(0, 600))
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(min_delay, max_delay)
    except Error:
        time.sleep(1)
        page.goto(url, **goto_opts)
        try_accept_consent(page)
        random_delay(1, 2)
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
