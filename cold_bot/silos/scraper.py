"""
Multi-purpose website scraper module. Base class + site-specific subclasses.
Dry-run by default (print, no DB). Use --live to write to SQLite.

Research-backed flow (all scrapers): goto (wait until 'load') -> accept_consent ->
scroll (human-like delays) -> collect. Cookie consent: click Accept-style buttons
(OneTrust, Cookiebot, GDPR). Avoid networkidle (hangs on SPAs); use element waits.
Site scrapers can override accept_consent (e.g. AtHome), add set_language/navigate_to_section.
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

from .browser_automation import close_browser, init_browser, scroll_and_navigate, try_accept_consent
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
    "bedrooms": "",
    "bathrooms": "",
    "size": "",
    "listing_type": "",
    "image_url": "",
}

PRIVATE_KWS = ["private seller", "owner direct", "fsbo", "for sale by owner", "no agent"]
AGENT_KWS = ["agency", "broker", "real estate", "realtor", "listing agent"]


def _fill_beds_baths_size(soup: Any, out: Dict[str, Any]) -> None:
    """Fill bedrooms, bathrooms, size from card HTML when present."""
    text = soup.get_text(separator=" ", strip=True) if hasattr(soup, "get_text") else ""
    if not text:
        return
    bed_m = re.search(r"(\d+)\s*(?:bed|bedroom|chambre|chb)s?", text, re.IGNORECASE)
    if bed_m:
        out["bedrooms"] = bed_m.group(1)
    bath_m = re.search(r"(\d+)\s*(?:bath|bathroom|salle de bain)s?", text, re.IGNORECASE)
    if bath_m:
        out["bathrooms"] = bath_m.group(1)
    m2_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", text, re.IGNORECASE) or re.search(r"(\d+(?:[.,]\d+)?)\s*m2\b", text, re.IGNORECASE)
    if m2_m:
        out["size"] = m2_m.group(1).replace(",", ".") + " m²"
    else:
        sqft_m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:sq\.?\s*ft|sqft)", text, re.IGNORECASE)
        if sqft_m:
            out["size"] = sqft_m.group(1).replace(",", ".") + " sqft"


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
        self._page.goto(url, timeout=timeout_ms, wait_until="load")
        self._page.wait_for_load_state("load", timeout=timeout_ms)

    def accept_consent(self) -> None:
        """Try to dismiss cookie/consent banner. Override in subclasses for site-specific handling."""
        if self._page:
            try_accept_consent(self._page)

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
        """Navigate, accept consent, scroll, collect (research: consent then load then element waits)."""
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
            self.accept_consent()
            _random_delay(1, 2)
            self.scroll()
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
    # athome.lu: listing cards may be .listing-item or links to /id-XXX.html; try multiple
    default_selector = ".listing-item"
    _FALLBACK_SELECTORS = [
        "a[href*='/id-'][href$='.html']",
        "a[href*='/en/buy/'][href*='.html'], a[href*='/en/rent/'][href*='.html']",
        "[class*='card'] a[href*='.html']",
        "article a[href*='/buy/'], article a[href*='/rent/']",
    ]
    site_name = "athome"

    # Cookie/consent: try locator by text first, then CSS selectors
    _CONSENT_TEXTS = [
        "Accept all", "Accept", "I accept", "OK", "Allow all", "Agree",
        "Tout accepter", "Alles akzeptieren", "Accepter", "Accept all cookies",
    ]
    _CONSENT_SELECTORS = [
        "[data-testid='accept-cookies']",
        ".cookie-consent button",
        "[class*='cookie'] button",
        "[class*='consent'] button",
        "#onetrust-accept-btn-handler",
        "[id*='accept']",
    ]

    def accept_consent(self) -> None:
        """Click cookie/terms accept if present. Call after goto, before scroll."""
        if not self._page:
            return
        # Try by button text (most reliable for "Accept" style buttons)
        for text in self._CONSENT_TEXTS:
            try:
                loc = self._page.locator(f"button:has-text('{text}')").first
                loc.wait_for(state="visible", timeout=3000)
                loc.click()
                _random_delay(1, 2)
                LOG.info("athome: accepted consent (button text: %s)", text)
                return
            except Exception:
                continue
        # Fallback: CSS selectors
        for sel in self._CONSENT_SELECTORS:
            try:
                btn = self._page.wait_for_selector(sel, timeout=2000)
                if btn:
                    btn.click()
                    _random_delay(1, 2)
                    LOG.info("athome: accepted consent with %s", sel)
                    return
            except Exception:
                continue

    def set_language(self, lang: str = "en") -> None:
        """Set site language so we know what we're scraping. Call after accept_consent."""
        if not self._page:
            return
        # If already on correct lang path (e.g. /en/), skip
        current = self._page.url
        if f"/{lang}/" in current or current.rstrip("/").endswith(f"/{lang}"):
            LOG.info("athome: language already %s", lang)
            return
        # Try to click language link: English, Français, Deutsch
        lang_texts = {"en": "English", "fr": "Français", "de": "Deutsch"}
        text = lang_texts.get(lang.lower(), "English")
        for sel in [
            f"a:has-text('{text}')",
            f"[role='menuitem']:has-text('{text}')",
            f"button:has-text('{text}')",
            "a[href*='/en/']",
        ]:
            try:
                loc = self._page.locator(sel).first
                loc.wait_for(state="visible", timeout=2500)
                loc.click()
                _random_delay(1, 2)
                LOG.info("athome: set language to %s", lang)
                return
            except Exception:
                continue
        # Fallback: go directly to lang version of current path
        try:
            from urllib.parse import urlparse
            parsed = urlparse(current)
            path = parsed.path or "/"
            if not path.startswith(f"/{lang}/"):
                new_path = f"/{lang}/" + path.lstrip("/").split("/", 1)[-1] if "/" in path.lstrip("/") else f"/{lang}/"
                self._page.goto(parsed.scheme + "://" + parsed.netloc + new_path, timeout=15000)
                _random_delay(1, 2)
                LOG.info("athome: navigated to %s path", lang)
        except Exception as e:
            LOG.warning("athome: set_language failed: %s", e)

    def navigate_to_section(self, section: Optional[str]) -> None:
        """Navigate to Rent or Buy section via nav/dropdown. section is 'rent' or 'buy'. Call after set_language."""
        if not self._page or not section:
            return
        section = section.lower()
        current = self._page.url.lower()
        if f"/{section}" in current or f"?tr={section}" in current:
            LOG.info("athome: already on %s section", section)
            return
        # Click nav link: Rent or Buy (text or href)
        link_text = "Rent" if section == "rent" else "Buy"
        for sel in [
            f"a:has-text('{link_text}')",
            f"a[href*='/{section}']",
            f"a[href*='tr={section}']",
            f"[role='menuitem']:has-text('{link_text}')",
        ]:
            try:
                loc = self._page.locator(sel).first
                loc.wait_for(state="visible", timeout=3000)
                loc.click()
                _random_delay(2, 4)
                LOG.info("athome: navigated to %s section", section)
                return
            except Exception:
                continue
        LOG.warning("athome: could not navigate to section %s", section)

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        """Try default selector then fallbacks (athome.lu uses various card/link structures)."""
        for sel in [selector or self.selector] + [s for s in self._FALLBACK_SELECTORS if s != (selector or self.selector)]:
            try:
                elements = self._page.query_selector_all(sel)
                if elements and len(elements) > 0:
                    LOG.info("athome: collected %d elements with selector %s", len(elements), sel[:50])
                    return list(elements)
            except Exception:
                continue
        return []

    def scrape(
        self,
        url: str,
        dry_run: bool = True,
        db_path: Optional[str] = None,
        page: Optional[Page] = None,
    ) -> List[Dict[str, Any]]:
        """Navigate, accept terms, set language, go to rent/buy section, scroll, collect."""
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
            self.accept_consent()
            # Language: from URL (/en/, /fr/, /de/) or config, default en
            lang = self.config.get("athome_lang") or "en"
            if "/fr/" in url:
                lang = "fr"
            elif "/de/" in url:
                lang = "de"
            elif "/en/" in url:
                lang = "en"
            self.set_language(lang)
            # Section: from URL (/rent, /buy) or config, so we're on the right layer
            section = self.config.get("athome_section")
            if not section and "/rent" in url.lower():
                section = "rent"
            elif not section and "/buy" in url.lower():
                section = "buy"
            if not section:
                section = "buy"
            self.navigate_to_section(section)
            self.scroll()
            _random_delay(self.delay_min, self.delay_max)
            # Wait for listing links to appear (JS-rendered)
            try:
                self._page.wait_for_selector("a[href*='/id-'][href$='.html'], .listing-item", timeout=15_000)
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
                    print(L, flush=True)
            else:
                save_to_db(listings, db_path or self.config.get("database", "leads.db"))
            return listings
        finally:
            if own_browser and self._playwright:
                close_browser(self._playwright, self._browser, self._context)
                self._playwright = self._browser = self._context = self._page = None

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        link_url = a["href"] if a and a.get("href") else ""
        if link_url and ".html" in link_url and "athome" in link_url:
            out["url"] = link_url if link_url.startswith("http") else "https://www.athome.lu" + (link_url if link_url.startswith("/") else "/" + link_url)
        else:
            out["url"] = link_url or ""
        t = soup.select_one(".title, [class*='title']")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".price, [class*='price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one(".location, [class*='location'], [class*='address']")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        _fill_beds_baths_size(soup, out)
        # When element is just a link (e.g. "Apartment2 60€906,303"), parse link text
        if not out["title"] and not out["price"] and a:
            full_text = a.get_text(strip=True) or ""
            if full_text:
                out["title"] = full_text[:200]
            price_match = re.search(r"€[\d\s,.]+", full_text)
            if price_match:
                out["price"] = price_match.group(0).strip()
            _fill_beds_baths_size(soup, out)
        if out["url"] and not out["url"].startswith("http"):
            out["url"] = "https://www.athome.lu" + (out["url"] if out["url"].startswith("/") else "/" + out["url"])
        return out


class ImmotopScraper(Scraper):
    """Luxembourg: immotop.lu. Listings at /annonces/ID; FR default."""
    default_selector = ".property-item"
    site_name = "immotop"
    _BASE = "https://www.immotop.lu"
    _FALLBACK_SELECTORS = [
        "a[href*='/annonces/']",
        "[class*='card'] a[href*='/annonces/']",
        "article a[href*='/annonces/']",
    ]

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
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        href = a["href"] if a and a.get("href") else ""
        if href and not href.startswith("http"):
            href = self._BASE + (href if href.startswith("/") else "/" + href)
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
        if not out["title"] or not out["price"]:
            full_text = a.get_text(strip=True) if a else soup.get_text(separator=" ", strip=True)
            if full_text and not out["title"]:
                out["title"] = full_text[:200]
            if full_text:
                price_match = re.search(r"€[\d\s,.]+", full_text)
                if price_match and not out["price"]:
                    out["price"] = price_match.group(0).strip()
        return out
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
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        _fill_beds_baths_size(soup, out)
        return out


class NextimmoScraper(Scraper):
    """Luxembourg: nextimmo.lu. Listings at /en/details/ID; EN."""
    default_selector = "[class*='listing'], [class*='card'], article a[href*='/details/']"
    site_name = "nextimmo"
    _BASE = "https://nextimmo.lu"
    _FALLBACK_SELECTORS = [
        "a[href*='/en/details/']",
        "a[href*='/details/']",
    ]

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        for sel in [selector or self.selector] + [s for s in self._FALLBACK_SELECTORS if s != (selector or self.selector)]:
            try:
                elements = self._page.query_selector_all(sel)
                if elements and len(elements) > 0:
                    LOG.info("nextimmo: collected %d elements with selector %s", len(elements), sel[:50])
                    return list(elements)
            except Exception:
                continue
        return []

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        href = a.get("href") if a else ""
        if href and not href.startswith("http"):
            href = self._BASE + (href if href.startswith("/") else "/" + href)
        out["url"] = href
        t = soup.select_one("h2, h3, .title, [class*='title'], [class*='Title']")
        out["title"] = t.get_text(strip=True) if t else ""
        p = soup.select_one(".price, [class*='price'], [class*='Price']")
        out["price"] = p.get_text(strip=True) if p else ""
        loc = soup.select_one(".location, [class*='location'], [class*='address'], address")
        out["location"] = loc.get_text(strip=True) if loc else ""
        desc = soup.select_one(".description, [class*='description']")
        out["description"] = desc.get_text(strip=True) if desc else ""
        full_text = soup.get_text(separator=" ", strip=True) if hasattr(soup, "get_text") else ""
        if full_text and not out["price"]:
            price_match = re.search(r"[\d\s,.]+\s*€", full_text) or re.search(r"€[\d\s,.]+", full_text)
            if price_match:
                out["price"] = price_match.group(0).strip()
        if full_text and not out["title"] and a:
            out["title"] = (a.get_text(strip=True) or full_text)[:200]
        _fill_beds_baths_size(soup, out)
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        return out


class BingoScraper(Scraper):
    """Luxembourg: bingo.lu. EN; JS-heavy, may show 'No results' or loading."""
    default_selector = "[class*='listing'], [class*='property'], [class*='card'], article a[href*='/property']"
    site_name = "bingo"
    _BASE = "https://www.bingo.lu"
    _FALLBACK_SELECTORS = [
        "a[href*='/en/'][href*='.html']",
        "[class*='card'] a[href*='/en/']",
        "article a[href*='/en/']",
    ]

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        for sel in [selector or self.selector] + [s for s in self._FALLBACK_SELECTORS if s != (selector or self.selector)]:
            try:
                elements = self._page.query_selector_all(sel)
                if elements and len(elements) > 0:
                    LOG.info("bingo: collected %d elements with selector %s", len(elements), sel[:50])
                    return list(elements)
            except Exception:
                continue
        return []

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        href = a.get("href") if a else ""
        if href and not href.startswith("http"):
            href = self._BASE + (href if href.startswith("/") else "/" + href)
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
        if full_text and not out["price"]:
            price_match = re.search(r"€[\d\s,.]+", full_text) or re.search(r"[\d\s,.]+\s*€", full_text)
            if price_match:
                out["price"] = price_match.group(0).strip()
        if (not out["title"] and a) or (not out["title"] and full_text):
            out["title"] = (a.get_text(strip=True) if a else full_text)[:200]
        _fill_beds_baths_size(soup, out)
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        return out


class PropertyWebScraper(Scraper):
    """Luxembourg: propertyweb.lu (commercial/residential). EN; cookie consent 'Accept All Cookies'."""
    default_selector = "[class*='listing'], [class*='property'], [class*='card'], article a[href*='/property']"
    site_name = "propertyweb"
    _BASE = "https://www.propertyweb.lu"
    _FALLBACK_SELECTORS = [
        "a[href*='/en/to-let/'][href*='/']",
        "a[href*='/en/for-sale/'][href*='/']",
        "a[href*='/en/investment/'][href*='/']",
    ]

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
        for sel in [selector or self.selector] + [s for s in self._FALLBACK_SELECTORS if s != (selector or self.selector)]:
            try:
                elements = self._page.query_selector_all(sel)
                if elements and len(elements) > 0:
                    LOG.info("propertyweb: collected %d elements with selector %s", len(elements), sel[:50])
                    return list(elements)
            except Exception:
                continue
        return []

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        href = a.get("href") if a else ""
        if href and not href.startswith("http"):
            href = self._BASE + (href if href.startswith("/") else "/" + href)
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
        if full_text and not out["price"]:
            price_match = re.search(r"€[\d\s,.]+", full_text) or re.search(r"[\d\s,.]+\s*€", full_text)
            if price_match:
                out["price"] = price_match.group(0).strip()
        if not out["title"] and (a or full_text):
            out["title"] = (a.get_text(strip=True) if a else full_text)[:200]
        _fill_beds_baths_size(soup, out)
        img = soup.find("img", src=True)
        if img and img.get("src"):
            out["image_url"] = img["src"]
        return out


class WortimmoScraper(Scraper):
    """Luxembourg: wortimmo.lu. Listings at /fr/vente-...-id_XXX or /fr/location/...-id_XXX; FR."""
    default_selector = "a[href*='-id_'], a[href*='/vente-'], a[href*='/location/']"
    site_name = "wortimmo"
    _BASE = "https://www.wortimmo.lu"
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
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        a = soup.find("a", href=True)
        href = a.get("href") if a else ""
        if href and not href.startswith("http"):
            href = self._BASE + (href if href.startswith("/") else "/" + href)
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
                        self.accept_consent()
                        _random_delay(1, 2)
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
                self.accept_consent()
                _random_delay(1, 2)
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
    if source_type == "athome":
        return AtHomeScraper(config)
    if source_type == "immotop":
        return ImmotopScraper(config)
    if source_type == "rightmove":
        return RightmoveScraper(config)
    if source_type == "nextimmo":
        return NextimmoScraper(config)
    if source_type == "bingo":
        return BingoScraper(config)
    if source_type == "propertyweb":
        return PropertyWebScraper(config)
    if source_type == "wortimmo":
        return WortimmoScraper(config)
    if source_type in ("facebook", "fb", "marketplace"):
        return FBMarketplaceScraper(config)
    return Scraper(config)


def _infer_source_from_url(url: str) -> str:
    u = (url or "").lower()
    if "facebook.com/marketplace" in u or "fb.com/marketplace" in u:
        return "marketplace"
    if "facebook.com/groups" in u or "fb.com/groups" in u:
        return "facebook"
    # Luxembourg-specific domains (check before generic)
    if "nextimmo.lu" in u:
        return "nextimmo"
    if "bingo.lu" in u:
        return "bingo"
    if "propertyweb.lu" in u:
        return "propertyweb"
    if "wortimmo.lu" in u:
        return "wortimmo"
    if "athome.lu" in u or "at-home.lu" in u:
        return "athome"
    if "immotop.lu" in u:
        return "immotop"
    # Generic domain matches
    if "athome" in u or "at-home" in u:
        return "athome"
    if "immotop" in u:
        return "immotop"
    if "rightmove" in u:
        return "rightmove"
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
