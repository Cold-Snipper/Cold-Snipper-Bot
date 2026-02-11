"""
Shared base and helpers for all site scrapers. Fast defaults: reject cookies first, short waits, few scrolls.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
except Exception:
    PlaywrightTimeoutError = Exception

from ..browser_automation import close_browser, init_browser, try_accept_consent
from ..llm_integration import extract_contact as llm_extract_contact
from ..llm_integration import _call_json_with_retry
from ..pipeline import validate_url

import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from utils import extract_contacts as regex_extract_contacts

LOG = logging.getLogger(__name__)

LISTING_SCHEMA = {
    "title": "", "price": "", "location": "", "description": "",
    "contact": {}, "is_private": False, "agency_name": "", "url": "",
    "bedrooms": "", "bathrooms": "", "size": "", "listing_type": "", "image_url": "",
}

PRIVATE_KWS = ["private seller", "owner direct", "fsbo", "for sale by owner", "no agent"]
AGENT_KWS = ["agency", "broker", "real estate", "realtor", "listing agent"]


def _fill_beds_baths_size(soup: Any, out: Dict[str, Any]) -> None:
    text = soup.get_text(separator=" ", strip=True) if hasattr(soup, "get_text") else ""
    if not text:
        return
    m = re.search(r"(\d+)\s*(?:bed|bedroom|chambre|chb)s?", text, re.IGNORECASE)
    if m:
        out["bedrooms"] = m.group(1)
    m = re.search(r"(\d+)\s*(?:bath|bathroom|salle de bain)s?", text, re.IGNORECASE)
    if m:
        out["bathrooms"] = m.group(1)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", text, re.IGNORECASE) or re.search(r"(\d+(?:[.,]\d+)?)\s*m2\b", text, re.IGNORECASE)
    if m:
        out["size"] = m.group(1).replace(",", ".") + " m²"
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:sq\.?\s*ft|sqft)", text, re.IGNORECASE)
        if m:
            out["size"] = m.group(1).replace(",", ".") + " sqft"


def _random_delay(min_sec: float, max_sec: float) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def _mouse_move_stub(page: Page) -> None:
    try:
        page.mouse.move(random.randint(100, 700), random.randint(100, 500))
    except Exception:
        pass


def save_to_db(listings: List[Dict[str, Any]], db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scraped_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, url_hash TEXT UNIQUE, url TEXT,
            title TEXT, price TEXT, location TEXT, description TEXT, contact_json TEXT,
            is_private INTEGER, agency_name TEXT, source TEXT, scraped_at INTEGER)
    """)
    now = int(time.time())
    for row in listings:
        url = row.get("url") or ""
        h = hashlib.sha256(url.encode()).hexdigest()[:32]
        conn.execute(
            """INSERT OR REPLACE INTO scraped_listings
               (url_hash, url, title, price, location, description, contact_json, is_private, agency_name, source, scraped_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (h, url, row.get("title") or "", row.get("price") or "", row.get("location") or "",
             row.get("description") or "", json.dumps(row.get("contact") or {}),
             1 if row.get("is_private") else 0, row.get("agency_name") or "", row.get("source", "web"), now),
        )
    conn.commit()
    conn.close()
    LOG.info("saved %d listings to %s", len(listings), db_path)


class Scraper:
    """Base scraper: goto -> reject/accept consent -> scroll (fast) -> collect -> extract."""

    default_selector = "[data-listing]"
    site_name = "generic"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config or {}
        self.limits = self.config.get("limits") or {}
        self.delay_min = float(self.limits.get("delay_min", 0.4))
        self.delay_max = float(self.limits.get("delay_max", 0.9))
        self.scroll_depth = int(self.limits.get("scroll_depth", 3))
        self.selectors = self.config.get("selectors") or {}
        self.selector = self.selectors.get("listing") or self.default_selector
        self.headless = self.config.get("headless", True)
        self._playwright = None
        self._browser = None
        self._context = None
        self._page: Optional[Page] = None

    def init_browser(self) -> None:
        self._playwright, self._browser, self._context, self._page = init_browser(headless=self.headless)

    def goto(self, url: str, timeout_ms: int = 45_000) -> None:
        if not self._page:
            self.init_browser()
        self._page.goto(url, timeout=timeout_ms, wait_until="load")
        self._page.wait_for_load_state("load", timeout=timeout_ms)

    def accept_consent(self) -> None:
        """Reject cookies first, then accept. Override in subclasses."""
        if self._page:
            try_accept_consent(self._page, timeout_per_try_ms=350)

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
                prompt = f'From this listing text, reply JSON only: {{"is_private": true or false, "agency_name": "name or empty"}}\n\nText:\n{text[:1500]}'
                data = _call_json_with_retry(prompt, model, provider)
                return {"is_private": bool(data.get("is_private", False)), "agency_name": str(data.get("agency_name", ""))}
            except Exception:
                pass
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
        if not validate_url(url):
            LOG.warning("invalid url skipped: %s", url[:80])
            return []
        own_browser = page is None
        try:
            if page is not None:
                self._page = page
            else:
                self.init_browser()
            self.goto(url)
            _random_delay(0.5, 0.8)
            self.accept_consent()
            _random_delay(0.3, 0.5)
            self.scroll()
            _random_delay(0.2, 0.4)
            wait_sel = getattr(self, "_WAIT_FOR_LISTINGS_SELECTOR", None)
            if wait_sel:
                try:
                    self._page.wait_for_selector(wait_sel, timeout=3_000)
                except Exception:
                    pass
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
