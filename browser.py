import os
import random
from typing import Dict, Any, Optional, List, Tuple

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
import playwright_stealth


USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
    "Mobile/15E148 Safari/604.1",
]


def _choose_proxy(proxies: List[str]) -> Optional[Dict[str, str]]:
    usable = [p for p in proxies if p and p.strip()]
    if not usable:
        return None
    return {"server": random.choice(usable)}


def init_browser(
    config: Dict[str, Any],
    headless: bool = True,
) -> Tuple[sync_playwright, Browser, BrowserContext, Page]:
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=headless)

    proxy = _choose_proxy(config.get("proxies", []))
    storage_state = config.get("facebook", {}).get("storage_state", "")
    storage_state_arg = storage_state if storage_state and os.path.exists(storage_state) else None
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=random.choice(USER_AGENTS),
        proxy=proxy,
        storage_state=storage_state_arg,
    )

    # Stealth patches on context/page to reduce automation signals
    playwright_stealth.stealth_sync(context)

    page = context.new_page()
    return p, browser, context, page


def ensure_fb_session(
    page: Page,
    config: Dict[str, Any],
    require_public_only: bool = True,
) -> None:
    """
    If FB blocks access or requires login, allow a manual login step.
    This keeps compliance with public-only use and avoids automating credentials.
    """
    login_url = config.get("facebook", {}).get("login_url")
    storage_state = config.get("facebook", {}).get("storage_state")

    if not login_url or not storage_state:
        return

    if require_public_only:
        # If we can access listings without login, skip this entirely.
        return

    page.goto(login_url)
    page.wait_for_timeout(2000)
    print(
        "Manual login required. Complete login in the opened browser, "
        "then press Enter in this terminal to continue."
    )
    input()
    page.context.storage_state(path=storage_state)


def scroll_page(page: Page, depth: int, delay_min: int, delay_max: int) -> None:
    for _ in range(depth):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(random.randint(delay_min * 1000, delay_max * 1000))
