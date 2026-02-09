"""
Multi-purpose website scraper module. Base class + site-specific subclasses.
Dry-run by default (print, no DB). Use --live to write to SQLite.
"""
from __future__ import annotations

import hashlib
import logging
import random
import sqlite3
import time
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
except Exception:
    PlaywrightTimeoutError = Exception

from .browser_automation import close_browser, init_browser, scroll_and_navigate
from .llm_integration import extract_contact as llm_extract_contact
from .llm_integration import _call_json_with_retry
from .pipeline import validate_url

import sys
from pathlib import Path
_COLD_BOT_ROOT = Path(__file__).resolve().parent.parent
if str(_COLD_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(_COLD_BOT_ROOT))
from utils import extract_contacts as regex_extract_contacts

LOG = logging.getLogger(__name__)

LISTING_SCHEMA = {
    "title": "",
    "price": "",
    "location": "",
    "description": "",
    "contact": {},
    "is_private": False,
    "agency_name": "",
    "url": "",
}

PRIVATE_KWS = ["private seller", "owner direct", "fsbo", "for sale by owner", "no agent"]
AGENT_KWS = ["agency", "broker", "real estate", "realtor", "listing agent"]


def _random_delay(min_sec: float, max_sec: float) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def _mouse_move_stub(page: Page) -> None:
    try:
        page.mouse.move(random.randint(100, 700), random.randint(100, 500))
    except Exception:
        pass


class Scraper:
    """Base scraper: init_browser, goto, scroll, collect_listings, extract_listing_data -> list[dict]."""

    default_selector = "[data-listing]"
    site_name = "generic"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config or {}
        self.limits = self.config.get("limits") or {}
        self.delay_min = self.limits.get("delay_min", 3)
        self.delay_max = self.limits.get("delay_max", 12)
        self.scroll_depth = self.limits.get("scroll_depth", 30)
        self.selectors = self.config.get("selectors") or {}
        self.selector = self.selectors.get("listing") or self.default_selector
        self.headless = self.config.get("headless", True)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Optional[Page] = None

    def init_browser(self) -> None:
        self._playwright, self._browser, self._context, self._page = init_browser(headless=self.headless)

    def goto(self, url: str, timeout_ms: int = 60_000) -> None:
        if not self._page:
            self.init_browser()
        self._page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        self._page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

    def scroll(self, depth: Optional[int] = None) -> None:
        depth = depth or self.scroll_depth
        for _ in range(depth):
            _mouse_move_stub(self._page)
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            _random_delay(self.delay_min, self.delay_max)

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        sel = selector or self.selector
        try:
            elements = self._page.query_selector_all(sel)
            return list(elements) if elements else []
        except PlaywrightTimeoutError:
            return []

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        """Override in subclasses. Return dict with title, price, location, description, contact, is_private, agency_name, url."""
        out = dict(LISTING_SCHEMA)
        out["url"] = getattr(element, "url", "") or (element.get_attribute("href") if hasattr(element, "get_attribute") else "")
        return out

    def _detect_private_agent(self, text: str) -> Dict[str, Any]:
        t = (text or "").lower()
        has_private = any(k in t for k in PRIVATE_KWS)
        has_agent = any(k in t for k in AGENT_KWS)
        if has_private and not has_agent:
            return {"is_private": True, "agency_name": ""}
        if has_agent and not has_private:
            return {"is_private": False, "agency_name": ""}
        if has_private and has_agent:
            try:
                model = self.config.get("ollama_model") or "llama3"
                provider = self.config.get("llm_provider") or "ollama"
                prompt = f'From this listing text, reply with JSON only: {{"is_private": true or false, "agency_name": "name or empty"}}\n\nText:\n{text[:1500]}'
                data = _call_json_with_retry(prompt, model, provider)
                return {"is_private": bool(data.get("is_private", False)), "agency_name": str(data.get("agency_name", ""))}
            except Exception:
                return {"is_private": False, "agency_name": ""}
        return {"is_private": False, "agency_name": ""}

    def _extract_contact(self, text: str) -> Dict[str, str]:
        try:
            model = self.config.get("ollama_model") or "llama3"
            provider = self.config.get("llm_provider") or "ollama"
            out = llm_extract_contact(text, model=model, provider=provider)
            return {"email": out.get("email") or "", "phone": out.get("phone") or ""}
        except Exception:
            return regex_extract_contacts(text or "")

    def scrape(
        self,
        url: str,
        dry_run: bool = True,
        db_path: Optional[str] = None,
        page: Optional[Page] = None,
    ) -> List[Dict[str, Any]]:
        """Navigate, scroll, collect, extract. If page given, use it and do not close browser."""
        if not validate_url(url):
            LOG.warning("invalid url skipped: %s", url[:80])
            return []
        own_browser = page is None
        try:
            if page is not None:
                self._page = page
            else:
                self.init_browser()
            scroll_and_navigate(
                self._page,
                url,
                self.scroll_depth,
                self.delay_min,
                self.delay_max,
            )
            _random_delay(self.delay_min, self.delay_max)
            elements = self.collect_listings()
            listings: List[Dict[str, Any]] = []
            for el in elements:
                data = self.extract_listing_data(el)
                text = (data.get("description") or "") + " " + (data.get("title") or "")
                pa = self._detect_private_agent(text)
                data["is_private"] = pa["is_private"]
                data["agency_name"] = pa["agency_name"]
                data["contact"] = self._extract_contact(text)
                data["url"] = data.get("url") or url
                if "source" not in data:
                    data["source"] = self.site_name
                listings.append(data)
            if dry_run:
                for L in listings:
                    LOG.info("extract: %s", L)
                    print(L)
            else:
                save_to_db(listings, db_path or self.config.get("database", "leads.db"))
            return listings
        finally:
            if own_browser and self._playwright:
                close_browser(self._playwright, self._browser, self._context)
                self._playwright = self._browser = self._context = self._page = None


def save_to_db(listings: List[Dict[str, Any]], db_path: str) -> None:
    """Create tables if not exist; insert/upsert by url hash."""
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scraped_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE,
            url TEXT,
            title TEXT,
            price TEXT,
            location TEXT,
            description TEXT,
            contact_json TEXT,
            is_private INTEGER,
            agency_name TEXT,
            source TEXT,
            scraped_at INTEGER
        )
    """)
    now = int(time.time())
    for row in listings:
        url = row.get("url") or ""
        h = hashlib.sha256(url.encode()).hexdigest()[:32]
        import json
        contact_json = json.dumps(row.get("contact") or {})
        conn.execute(
            """INSERT OR REPLACE INTO scraped_listings
               (url_hash, url, title, price, location, description, contact_json, is_private, agency_name, source, scraped_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                h,
                url,
                row.get("title") or "",
                row.get("price") or "",
                row.get("location") or "",
                row.get("description") or "",
                contact_json,
                1 if row.get("is_private") else 0,
                row.get("agency_name") or "",
                row.get("source", "web"),
                now,
            ),
        )
    conn.commit()
    conn.close()
    LOG.info("saved %d listings to %s", len(listings), db_path)


class AtHomeScraper(Scraper):
    default_selector = ".listing-item"
    site_name = "athome"

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        t = soup.select_one(".title, [class*='title']")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".price, [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one(".location, [class*='location'], [class*='address']")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        a = soup.find("a", href=True)
        out["url"] = a["href"] if a and a.get("href") else ""
        return out


class ImmotopScraper(Scraper):
    default_selector = ".property-item"
    site_name = "immotop"

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        t = soup.select_one(".title, [class*='title'], .property-title")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".price, [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one(".location, [class*='location'], .address")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        a = soup.find("a", href=True)
        out["url"] = a["href"] if a and a.get("href") else ""
        return out


class RightmoveScraper(Scraper):
    """UK Rightmove listing cards."""
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
        # Title: h2, .propertyCard-title, [data-testid="propertyCardTitle"]
        t = soup.select_one("h2, .propertyCard-title, [data-testid='propertyCardTitle'], [class*='title']")
        out["title"] = t.get_text(strip=True) if t else ""
        # Price: .propertyCard-price, [data-testid="propertyCardPrice"]
        p = soup.select_one(".propertyCard-price, [data-testid='propertyCardPrice'], [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        # Address/location
        loc = soup.select_one("address, [data-testid='address'], .propertyCard-address, [class*='address']")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".propertyCard-description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        a = soup.find("a", href=True)
        href = a.get("href") if a else ""
        if href and not href.startswith("http"):
            href = "https://www.rightmove.co.uk" + href if href.startswith("/") else ""
        out["url"] = href
        return out


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
        """FB Marketplace: single feed URL. Groups handled in scrape_with_groups."""
        return super().scrape(url, dry_run=dry_run, db_path=db_path, page=page)

    def scrape_with_groups(
        self,
        marketplace_url: Optional[str] = None,
        group_urls: Optional[List[str]] = None,
        dry_run: bool = True,
        db_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """If config.facebook.groups enabled (group_urls), loop and scrape; then optionally marketplace in same session."""
        all_listings: List[Dict[str, Any]] = []
        db_path = db_path or self.config.get("database", "leads.db")
        try:
            if group_urls:
                for gurl in group_urls:
                    try:
                        self.goto(gurl)
                        _random_delay(self.delay_min, self.delay_max)
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
                        LOG.warning("group scrape %s: %s", gurl, e)
            if marketplace_url:
                self.goto(marketplace_url)
                _random_delay(self.delay_min, self.delay_max)
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


def get_scraper_for_source(config: Dict[str, Any], source_type: str) -> Scraper:
    if source_type == "athome" or "athome" in str(config.get("target_sites_by_country") or "").lower():
        return AtHomeScraper(config)
    if source_type == "immotop":
        return ImmotopScraper(config)
    if source_type == "rightmove":
        return RightmoveScraper(config)
    if source_type in ("facebook", "fb", "marketplace"):
        return FBMarketplaceScraper(config)
    return Scraper(config)


def _infer_source_from_url(url: str) -> str:
    u = (url or "").lower()
    if "athome" in u or "at-home" in u:
        return "athome"
    if "immotop" in u:
        return "immotop"
    if "rightmove" in u:
        return "rightmove"
    if "facebook.com/marketplace" in u or "fb.com/marketplace" in u:
        return "marketplace"
    if "facebook.com/groups" in u or "fb.com/groups" in u:
        return "facebook"
    return "generic"


if __name__ == "__main__":
    import argparse
    import yaml
    from pathlib import Path
    parser = argparse.ArgumentParser(description="Cold Bot scraper module (dry-run by default)")
    parser.add_argument("url", nargs="?", help="URL to scrape")
    parser.add_argument("--config", default=str(_COLD_BOT_ROOT / "config.yaml"), help="Config YAML")
    parser.add_argument("--live", action="store_true", help="Write to DB (default: dry-run, print only)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    url = args.url or (config.get("start_urls") or [""])[0]
    if not url:
        print("Provide URL or start_urls in config")
        sys.exit(1)
    source = _infer_source_from_url(url)
    scraper = get_scraper_for_source(config, source)
    dry_run = not args.live
    listings = scraper.scrape(url, dry_run=dry_run, db_path=config.get("database", "leads.db"))
    print(f"Total: {len(listings)} listings (dry_run={dry_run})")
