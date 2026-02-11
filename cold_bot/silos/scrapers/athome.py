"""atHome.lu scraper: consent (reject first), language, section, then collect. Fast timeouts."""
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
    save_to_db,
)

try:
    from playwright.sync_api import Page
except Exception:
    Page = None


class AtHomeScraper(Scraper):
    default_selector = ".listing-item"
    _FALLBACK_SELECTORS = [
        "a[href*='/id-'][href$='.html']",
        "a[href*='/en/buy/'][href*='.html'], a[href*='/en/rent/'][href*='.html']",
        "[class*='card'] a[href*='.html']",
        "article a[href*='/buy/'], article a[href*='/rent/']",
    ]
    site_name = "athome"

    _CONSENT_TEXTS = [
        "Tout refuser", "Refuser", "Only necessary", "Necessary only",
        "Tout accepter", "Alles akzeptieren", "Accepter", "Accept all", "Accept", "OK",
    ]
    _CONSENT_SELECTORS = [
        "[id*='reject']", "[class*='reject']",
        "[data-testid='accept-cookies']", ".cookie-consent button", "[class*='cookie'] button", "[class*='consent'] button", "#onetrust-accept-btn-handler", "[id*='accept']",
    ]

    def accept_consent(self) -> None:
        if not self._page:
            return
        t = 350
        if try_accept_consent(self._page, timeout_per_try_ms=t):
            LOG.info("athome: consent dismissed (reject/accept)")
            return
        for text in self._CONSENT_TEXTS:
            try:
                loc = self._page.locator(f"button:has-text('{text}'), a:has-text('{text}'), [role='button']:has-text('{text}')").first
                loc.wait_for(state="visible", timeout=t)
                loc.click()
                _random_delay(0.2, 0.35)
                LOG.info("athome: consent: %s", text)
                return
            except Exception:
                continue
        for sel in self._CONSENT_SELECTORS:
            try:
                btn = self._page.wait_for_selector(sel, timeout=t)
                if btn:
                    btn.click()
                    _random_delay(0.2, 0.35)
                    LOG.info("athome: consent: %s", sel)
                    return
            except Exception:
                continue

    def set_language(self, lang: str = "en") -> None:
        if not self._page:
            return
        current = self._page.url
        if f"/{lang}/" in current or current.rstrip("/").endswith(f"/{lang}"):
            LOG.info("athome: language already %s", lang)
            return
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
                loc.wait_for(state="visible", timeout=800)
                loc.click()
                _random_delay(0.2, 0.4)
                LOG.info("athome: language %s", lang)
                return
            except Exception:
                continue
        try:
            from urllib.parse import urlparse
            parsed = urlparse(current)
            path = parsed.path or "/"
            if not path.startswith(f"/{lang}/"):
                new_path = f"/{lang}/" + path.lstrip("/").split("/", 1)[-1] if "/" in path.lstrip("/") else f"/{lang}/"
                self._page.goto(parsed.scheme + "://" + parsed.netloc + new_path, timeout=15_000)
                _random_delay(0.3, 0.5)
                LOG.info("athome: navigated to %s path", lang)
        except Exception as e:
            LOG.warning("athome: set_language failed: %s", e)

    def navigate_to_section(self, section: Optional[str]) -> None:
        if not self._page or not section:
            return
        section = section.lower()
        current = self._page.url.lower()
        if f"/{section}" in current or f"?tr={section}" in current:
            LOG.info("athome: already on %s section", section)
            return
        link_text = "Rent" if section == "rent" else "Buy"
        for sel in [
            f"a:has-text('{link_text}')",
            f"a[href*='/{section}']",
            f"a[href*='tr={section}']",
            f"[role='menuitem']:has-text('{link_text}')",
        ]:
            try:
                loc = self._page.locator(sel).first
                loc.wait_for(state="visible", timeout=800)
                loc.click()
                _random_delay(0.3, 0.5)
                LOG.info("athome: section %s", section)
                return
            except Exception:
                continue
        LOG.warning("athome: could not navigate to section %s", section)

    def collect_listings(self, selector: Optional[str] = None) -> List[Any]:
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
        from ..pipeline import validate_url
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
            lang = self.config.get("athome_lang") or "en"
            if "/fr/" in url:
                lang = "fr"
            elif "/de/" in url:
                lang = "de"
            elif "/en/" in url:
                lang = "en"
            self.set_language(lang)
            section = self.config.get("athome_section")
            if not section and "/rent" in url.lower():
                section = "rent"
            elif not section and "/buy" in url.lower():
                section = "buy"
            if not section:
                section = "buy"
            self.navigate_to_section(section)
            self.scroll()
            _random_delay(0.2, 0.4)
            try:
                self._page.wait_for_selector("a[href*='/id-'][href$='.html'], .listing-item", timeout=3_000)
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
                from ..browser_automation import close_browser
                close_browser(self._playwright, self._browser, self._context)
                self._playwright = self._browser = self._context = self._page = None

    def extract_listing_data(self, element: Any) -> Dict[str, Any]:
        out = dict(LISTING_SCHEMA)
        out["source"] = self.site_name
        # When the collected element IS the listing link, get href from it
        elem_href = ""
        if hasattr(element, "get_attribute"):
            try:
                elem_href = (element.get_attribute("href") or "").strip()
            except Exception:
                pass
        if hasattr(element, "inner_html"):
            html = element.inner_html()
        else:
            html = str(element) if hasattr(element, "__str__") else ""
        soup = BeautifulSoup(html, "lxml")
        # Prefer the listing link (/id-XXX.html); first <a> may be nav (Buy, etc.)
        link_url = ""
        for a in soup.find_all("a", href=True):
            h = (a.get("href") or "").strip()
            if "/id-" in h and ".html" in h:
                link_url = h
                break
        if not link_url and elem_href and "/id-" in elem_href and ".html" in elem_href:
            link_url = elem_href
        if not link_url:
            a = soup.find("a", href=True)
            link_url = a["href"] if a and a.get("href") else ""
        else:
            a = next((x for x in soup.find_all("a", href=True) if "/id-" in (x.get("href") or "") and ".html" in (x.get("href") or "")), soup.find("a", href=True))
        if link_url and ".html" in link_url and ("athome" in link_url or link_url.startswith("/")):
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
        if not out["title"] and not out["price"]:
            a_fallback = soup.find("a", href=True)
            if a_fallback:
                full_text = a_fallback.get_text(strip=True) or ""
                if full_text:
                    out["title"] = full_text[:200]
                price_match = re.search(r"€[\d\s,.]+", full_text)
                if price_match:
                    out["price"] = price_match.group(0).strip()
                _fill_beds_baths_size(soup, out)
        if out["url"] and not out["url"].startswith("http"):
            out["url"] = "https://www.athome.lu" + (out["url"] if out["url"].startswith("/") else "/" + out["url"])
        return out
