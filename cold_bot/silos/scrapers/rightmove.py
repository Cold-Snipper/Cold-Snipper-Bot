"""Rightmove UK scraper."""
from __future__ import annotations

from typing import Any, Dict

from bs4 import BeautifulSoup

from .base import LISTING_SCHEMA, Scraper, _fill_beds_baths_size


class RightmoveScraper(Scraper):
    default_selector = "[data-testid='propertyCard'], .l-searchResult, article[class*='PropertyCard']"
    site_name = "rightmove"

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        t = soup.select_one("h2, .propertyCard-title, [data-testid='propertyCardTitle'], [class*='title']")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".propertyCard-price, [data-testid='propertyCardPrice'], [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one("address, [data-testid='address'], .propertyCard-address, [class*='address']")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".propertyCard-description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        a = soup.find("a", href=True)
        href = a.get("href") if a else ""
        if href and not href.startswith("http"):
            href = "https://www.rightmove.co.uk" + href if href.startswith("/") else ""
        out["url"] = href
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        _fill_beds_baths_size(soup, out)
        return out
