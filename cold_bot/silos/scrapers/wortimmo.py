"""Wortimmo.lu scraper. FR; listings at /fr/vente-...-id_XXX or /fr/location/...-id_XXX."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

from .base import LISTING_SCHEMA, LOG, Scraper, _fill_beds_baths_size

_BASE = "https://www.wortimmo.lu"


class WortimmoScraper(Scraper):
    default_selector = "a[href*='-id_'], a[href*='/vente-'], a[href*='/location/']"
    site_name = "wortimmo"
    _WAIT_FOR_LISTINGS_SELECTOR = "a[href*='-id_']"
    _FALLBACK_SELECTORS = [
        "[class*='card'] a[href*='-id_']",
        "[class*='listing'] a[href*='-id_']",
    ]

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        for sel in [selector or self.selector] + [s for s in self._FALLBACK_SELECTORS if s != (selector or self.selector)]:
            try:
                elements = self._page.query_selector_all(sel)
                if elements and len(elements) > 0:
                    LOG.info("wortimmo: collected %d elements with selector %s", len(elements), sel[:50])
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
        href = (a.get("href") if a else "") or elem_href
        if href and not href.startswith("http"):
            href = _BASE + (href if href.startswith("/") else "/" + href)
        out["url"] = href
        t = soup.select_one("h2, h3, .title, [class*='title']")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".price, [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one(".location, [class*='location'], [class*='address'], address")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        full_text = soup.get_text(separator=" ", strip=True) if hasattr(soup, "get_text") else ""
        if not full_text and hasattr(element, "inner_text"):
            try:
                full_text = element.inner_text() or ""
            except Exception:
                pass
        if full_text and not out["price"]:
            price_match = re.search(r"[\d\s,.]+\s*€", full_text) or re.search(r"€[\d\s,.]+", full_text)
            if price_match:
                out["price"] = price_match.group(0).strip()
        if not out["title"] and (a or full_text):
            out["title"] = (a.get_text(strip=True) if a else full_text)[:200]
        _fill_beds_baths_size(soup, out)
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        return out
