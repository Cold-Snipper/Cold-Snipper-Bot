"""Facebook Marketplace (and groups) scraper."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..browser_automation import close_browser, try_accept_consent
from .base import LISTING_SCHEMA, Scraper, _random_delay, save_to_db

try:
    from playwright.sync_api import Page
except Exception:
    Page = None


class FBMarketplaceScraper(Scraper):
    default_selector = '[data-testid="marketplace_feed_card"]'
    site_name = "facebook_marketplace"

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        text = element.inner_text() if hasattr(element, "inner_text") else ""
        out["description"] = text
        lines = [s.strip() for s in text.split("\n") if s.strip()]
        out["title"] = lines[0] if lines else ""
        for line in lines[1:]:
            if "€" in line or "$" in line or "£" in line:
                out["price"] = line
                break
            if any(c.isdigit() for c in line) and len(line) < 50:
                if not out["location"]:
                    out["location"] = line
        a = element.query_selector("a") if hasattr(element, "query_selector") else None
        if a:
            out["url"] = a.get_attribute("href") or ""
        return out

    def scrape(
        self,
        url: str,
        dry_run: bool = True,
        db_path: Optional[str] = None,
        page: Optional[Page] = None,
    ) -> List[Dict[str, Any]]:
        return super().scrape(url, dry_run=dry_run, db_path=db_path, page=page)

    def scrape_with_groups(
        self,
        marketplace_url: Optional[str] = None,
        group_urls: Optional[List[str]] = None,
        dry_run: bool = True,
        db_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        all_listings: List[Dict[str, Any]] = []
        db_path = db_path or self.config.get("database", "leads.db")
        try:
            if group_urls:
                for gurl in group_urls:
                    try:
                        self.goto(gurl)
                        self.accept_consent()
                        _random_delay(0.3, 0.6)
                        self.scroll()
                        elements = self.collect_listings()
                        for el in elements:
                            data = self.extract_listing_data(el)
                            text = (data.get("description") or "") + " " + (data.get("title") or "")
                            pa = self._detect_private_agent(text)
                            data["is_private"] = pa["is_private"]
                            data["agency_name"] = pa["agency_name"]
                            data["contact"] = self._extract_contact(text)
                            data["url"] = data.get("url") or gurl
                            data["source"] = "facebook_group"
                            all_listings.append(data)
                            if dry_run:
                                print(data)
                    except Exception as e:
                        from .base import LOG
                        LOG.warning("group scrape %s: %s", gurl, e)
            if marketplace_url:
                self.goto(marketplace_url)
                self.accept_consent()
                _random_delay(0.3, 0.6)
                self.scroll()
                elements = self.collect_listings()
                for el in elements:
                    data = self.extract_listing_data(el)
                    text = (data.get("description") or "") + " " + (data.get("title") or "")
                    pa = self._detect_private_agent(text)
                    data["is_private"] = pa["is_private"]
                    data["agency_name"] = pa["agency_name"]
                    data["contact"] = self._extract_contact(text)
                    data["source"] = self.site_name
                    all_listings.append(data)
                    if dry_run:
                        print(data)
            if not dry_run and all_listings:
                save_to_db(all_listings, db_path)
        finally:
            if self._playwright:
                close_browser(self._playwright, self._browser, self._context)
                self._playwright = self._browser = self._context = self._page = None
        return all_listings
