import random
import time
from typing import Any, Dict, Optional, Tuple

from playwright.sync_api import sync_playwright, Error, Browser, BrowserContext, Page

from utils import rotate_ua, random_delay

# Cookie consent: prefer "reject non-essential" / "necessary only" (mandatory cookies only), then fallback to accept to dismiss banner.
REJECT_OR_NECESSARY_TEXTS = [
    "Reject non-essential", "Only necessary", "Necessary only", "Essential only", "Strictly necessary",
    "Tout refuser", "Refuser", "Accepter uniquement les essentiels", "Seulement les essentiels",
    "Nur notwendige", "Alles ablehnen", "Allow essential only", "Reject all", "Refuse non-essential",
    "Accept necessary only", "Necessaire uniquement", "Nur erforderliche",
]
ACCEPT_TEXTS = [
    "Accept all", "Accept", "I accept", "OK", "Allow all", "Agree", "Accept all cookies",
    "Tout accepter", "Alles akzeptieren", "Accepter", "Accept & continue", "Allow",
]
REJECT_SELECTORS = [
    "[id*='reject']", "[class*='reject']", "[data-action='reject']", ".cc-reject", ".cc-deny",
    "[aria-label*='eject']", "button[class*='necessary']", "a[class*='necessary']",
]
ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "[data-testid='accept-cookies']",
    ".cookie-consent button",
    "[class*='cookie'] button",
    "[class*='consent'] button",
    "[id*='accept']",
    ".cc-btn.cc-allow",
    "[aria-label*='Accept']",
]
# Legacy names for any external use
CONSENT_BUTTON_TEXTS = ACCEPT_TEXTS
CONSENT_SELECTORS = ACCEPT_SELECTORS

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


def _click_consent_by_text(page: Page, texts: list, timeout_ms: int = 600) -> bool:
    """Click first visible button/link that contains one of the texts. Returns True if clicked."""
    for text in texts:
        try:
            loc = page.locator(f"button:has-text('{text}'), a:has-text('{text}'), [role='button']:has-text('{text}')").first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.click()
            time.sleep(0.3)
            return True
        except Exception:
            continue
    return False


def _click_consent_by_selectors(page: Page, selectors: list, timeout_ms: int = 500) -> bool:
    for sel in selectors:
        try:
            btn = page.wait_for_selector(sel, timeout=timeout_ms)
            if btn:
                btn.click()
                time.sleep(0.3)
                return True
        except Exception:
            continue
    return False


def _click_consent_nuclear(page: Page, timeout_ms: int = 400) -> bool:
    """Click any button/link with Accept/OK/Accepter/Allow. Last resort."""
    for word in ["Accept", "OK", "Accepter", "Allow", "Agree", "Tout accepter", "Accept all"]:
        try:
            loc = page.locator(f"button:has-text('{word}'), a:has-text('{word}'), [role='button']:has-text('{word}')").first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.click()
            time.sleep(0.3)
            return True
        except Exception:
            continue
    return False


def _try_consent_in_frame(frame, timeout_ms: int) -> bool:
    """Try consent inside a frame (cookie banners often in iframe). Returns True if clicked."""
    for text in REJECT_OR_NECESSARY_TEXTS + ACCEPT_TEXTS:
        try:
            loc = frame.locator(f"button:has-text('{text}'), a:has-text('{text}')").first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.click()
            time.sleep(0.3)
            return True
        except Exception:
            continue
    for sel in REJECT_SELECTORS + ACCEPT_SELECTORS:
        try:
            btn = frame.locator(sel).first
            btn.wait_for(state="visible", timeout=timeout_ms)
            btn.click()
            time.sleep(0.3)
            return True
        except Exception:
            continue
    return False


def try_accept_consent(page: Page, timeout_per_try_ms: int = 350) -> bool:
    """Dismiss cookie banner: prefer reject/necessary, else accept. Short timeouts so we don't hang. Tries iframes."""
    if not page:
        return False
    t = timeout_per_try_ms
    # 1) Main page: reject then accept (fast cycle)
    if _click_consent_by_text(page, REJECT_OR_NECESSARY_TEXTS, t):
        return True
    if _click_consent_by_selectors(page, REJECT_SELECTORS, t):
        return True
    if _click_consent_by_text(page, ACCEPT_TEXTS, t):
        return True
    if _click_consent_by_selectors(page, ACCEPT_SELECTORS, t):
        return True
    # 2) Cookie banners often in iframe
    try:
        for frame in page.frames:
            if frame != page.main_frame and _try_consent_in_frame(frame, t):
                return True
    except Exception:
        pass
    # 3) Nuclear: any button with accept/ok/accepter
    if _click_consent_nuclear(page, t):
        return True
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
