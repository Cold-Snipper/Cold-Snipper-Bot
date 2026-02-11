"""Immotop.lu scraper. Reject cookies first, then accept. Fast timeouts."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from ..browser_automation import try_accept_consent
from .base import (
    LISTING_SCHEMA,
    LOG,
    Scraper,
    _fill_beds_baths_size,
    _random_delay,
)

_BASE = "https://www.immotop.lu"


class ImmotopScraper(Scraper):
    default_selector = ".property-item"
    site_name = "immotop"
    _WAIT_FOR_LISTINGS_SELECTOR = "a[href*='/annonces/']"
    _FALLBACK_SELECTORS = [
        "a[href*='/annonces/']",
        "[class*='card'] a[href*='/annonces/']",
        "article a[href*='/annonces/']",
    ]
    _REJECT_TEXTS = ["Tout refuser", "Refuser", "Seulement les essentiels", "Accepter uniquement les essentiels", "Only necessary", "Necessary only"]
    _ACCEPT_TEXTS = ["Tout accepter", "Accepter", "Accept all", "Accept", "OK"]
    _CONSENT_SELECTORS = ["[class*='cookie'] button", "[class*='consent'] button", "[id*='accept']", "[id*='reject']"]

    def accept_consent(self) -> None:
        if not self._page:
            return
        t = 350
        _random_delay(0.3, 0.5)
        for text in self._REJECT_TEXTS:
            try:
                loc = self._page.locator(f"button:has-text('{text}'), a:has-text('{text}'), [role='button']:has-text('{text}')").first
                loc.wait_for(state="visible", timeout=t)
                loc.click()
                _random_delay(0.2, 0.35)
                LOG.info("immotop: consent (reject): %s", text)
                return
            except Exception:
                continue
        for text in self._ACCEPT_TEXTS:
            try:
                loc = self._page.locator(f"button:has-text('{text}'), a:has-text('{text}'), [role='button']:has-text('{text}')").first
                loc.wait_for(state="visible", timeout=t)
                loc.click()
                _random_delay(0.2, 0.35)
                LOG.info("immotop: consent (accept): %s", text)
                return
            except Exception:
                continue
        for sel in self._CONSENT_SELECTORS:
            try:
                btn = self._page.wait_for_selector(sel, timeout=t)
                if btn:
                    btn.click()
                    _random_delay(0.2, 0.35)
                    LOG.info("immotop: consent: %s", sel)
                    return
            except Exception:
                continue
        try_accept_consent(self._page, timeout_per_try_ms=t)

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        for sel in [selector or self.selector] + [s for s in self._FALLBACK_SELECTORS if s != (selector or self.selector)]:
            try:
                elements = self._page.query_selector_all(sel)
                if elements and len(elements) > 0:
                    LOG.info("immotop: collected %d elements with selector %s", len(elements), sel[:50])
                    return list(elements)
            except Exception:
                continue
        return []

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        elem_href = ""
        if hasattr(element, "get_attribute"):
            try:
                elem_href = element.get_attribute("href") or ""
            except Exception:
                pass
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        href = (a["href"] if a and a.get("href") else "") or elem_href
        if href and not href.startswith("http"):
            href = _BASE + (href if href.startswith("/") else "/" + href)
        out["url"] = href
        t = soup.select_one(".title, [class*='title'], .property-title")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".price, [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one(".location, [class*='location'], .address")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        _fill_beds_baths_size(soup, out)
        full_text = (a.get_text(strip=True) if a else "") or (soup.get_text(separator=" ", strip=True) if hasattr(soup, "get_text") else "")
        if not full_text and hasattr(element, "inner_text"):
            try:
                full_text = element.inner_text() or ""
            except Exception:
                pass
        if not out["title"] and full_text:
            out["title"] = full_text[:200]
        if full_text:
            price_match = re.search(r"€[\d\s,.]+", full_text)
            if price_match and not out["price"]:
                out["price"] = price_match.group(0).strip()
        return out
