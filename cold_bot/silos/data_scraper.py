from typing import Optional, List, Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import lxml
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


def extract_listings(page, selector: str, site: Optional[str] = None) -> List[Dict[str, object]]:
    """Description.

    Args:
        page (type): desc.
        selector (type): desc.
        site (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    listings = []
    seen = set()
    try:
        if site == "facebook":
            selector = selector
        elif site == "craigslist":
            selector = selector
        elif site == "zillow":
            selector = selector
        elements = page.query_selector_all(selector)
        if elements:
            for el in elements:
                text = el.inner_text()
                href = el.get_attribute("href")
                if not href:
                    link_el = el.query_selector("a")
                    if link_el:
                        href = link_el.get_attribute("href")
                if href and isinstance(href, str) and page.url:
                    href = urljoin(page.url, href)
                text_hash = hash(text)
                if text_hash in seen:
                    continue
                seen.add(text_hash)
                listings.append(
                    {
                        "text": text,
                        "hash": text_hash,
                        "url": href or getattr(page, "url", ""),
                    }
                )
        else:
            soup = BeautifulSoup(page.content(), "lxml")
            for el in soup.select(selector):
                text = el.get_text()
                href = el.get("href")
                if not href:
                    link_el = el.find("a")
                    if link_el:
                        href = link_el.get("href")
                if href and isinstance(href, str) and page.url:
                    href = urljoin(page.url, href)
                text_hash = hash(text)
                if text_hash in seen:
                    continue
                seen.add(text_hash)
                listings.append(
                    {
                        "text": text,
                        "hash": text_hash,
                        "url": href or getattr(page, "url", ""),
                    }
                )
        return listings
    except PlaywrightTimeoutError:
        return listings
