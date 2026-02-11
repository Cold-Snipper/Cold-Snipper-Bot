#!/usr/bin/env python3
"""
Real website listing scraper (no simulation).
- Uses silo scrapers (athome, immotop, rightmove, Luxembourg nextimmo/bingo/propertyweb/wortimmo)
  when URL is recognized; otherwise falls back to generic extract_listings.
- All data appended/merged to one canonical leads.csv (dedup by URL). No AI required.
"""
import argparse
import csv
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

COLD_BOT_ROOT = Path(__file__).resolve().parent
if str(COLD_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(COLD_BOT_ROOT))

from silos.browser_automation import scroll_and_navigate, close_browser
from silos.data_scraper import extract_listings
from silos.scraper import _infer_source_from_url, get_scraper_for_source
from utils import random_delay, extract_contacts

DEFAULT_SELECTOR = "a[href*='/listing'], a[href*='/property'], a[href*='/buy'], a[href*='/sell'], [data-testid*='listing'], [class*='listing'], [class*='card']"
DEFAULT_SCROLL_DEPTH = 30
DEFAULT_DELAY_MIN = 3
DEFAULT_DELAY_MAX = 12

LEADS_FIELDS = [
    "id", "url", "title", "description", "price", "location",
    "bedrooms", "bathrooms", "size", "listing_type",
    "source", "is_private", "agency_name", "image_url",
    "contact_email", "contact_phone", "scan_time", "status",
]


def parse_listing_text(text: str, url: str, source: str = "generic") -> dict:
    """Extract title, price, location, bedrooms, bathrooms, size, listing_type, email, phone from card text."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title = lines[0][:200] if lines else "Listing"
    description = (text or "")[:2000].replace("\n", " ")
    price = ""
    location = ""
    bedrooms = ""
    bathrooms = ""
    size = ""
    listing_type = ""
    price_match = re.search(r"\$[\d,]+(?:\s*(?:USD|EUR|GBP))?", text or "")
    if price_match:
        price = price_match.group(0)
    eur_match = re.search(r"[\d.,]+\s*€", text or "")
    if eur_match and not price:
        price = eur_match.group(0)
    loc_match = re.search(r"(?:in|at|near|location:?)\s*([A-Za-z0-9\s,-]+?)(?:\n|$|[0-9]{5})", text or "", re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()[:120]
    bed_match = re.search(r"(\d+)\s*(?:bed|bedroom|chambre)s?", text or "", re.IGNORECASE)
    if bed_match:
        bedrooms = bed_match.group(1)
    bath_match = re.search(r"(\d+)\s*(?:bath|bathroom|salle de bain)s?", text or "", re.IGNORECASE)
    if bath_match:
        bathrooms = bath_match.group(1)
    size_m2 = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", text or "", re.IGNORECASE)
    size_sqft = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:sq\.?\s*ft|sqft)", text or "", re.IGNORECASE)
    if size_m2:
        size = size_m2.group(1).replace(",", ".") + " m²"
    elif size_sqft:
        size = size_sqft.group(1).replace(",", ".") + " sqft"
    if "/rent/" in url or "/rental" in url or re.search(r"\brent\b", (text or ""), re.IGNORECASE):
        listing_type = "rent"
    elif "/buy/" in url or "/sale" in url or "/sell" in url or re.search(r"\b(?:for sale|buy|sale)\b", (text or ""), re.IGNORECASE):
        listing_type = "buy"
    contacts = extract_contacts(text or "")
    return {
        "url": url,
        "title": title,
        "description": description,
        "price": price,
        "location": location,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "size": size,
        "listing_type": listing_type,
        "source": source,
        "is_private": "",
        "agency_name": "",
        "image_url": "",
        "contact_email": contacts.get("email", ""),
        "contact_phone": contacts.get("phone", ""),
    }


def read_existing_leads(leads_path: Path) -> tuple[list[dict], int, set[str]]:
    """Return (rows as list of dicts, next_id, existing_urls)."""
    rows = []
    next_id = 1
    existing_urls = set()
    if not leads_path.exists():
        return rows, next_id, existing_urls
    try:
        with open(leads_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    i = int(row.get("id", 0))
                    next_id = max(next_id, i + 1)
                except (ValueError, TypeError):
                    pass
                u = row.get("url", "")
                if u:
                    existing_urls.add(u)
                rows.append({k: row.get(k, "") for k in LEADS_FIELDS})
    except Exception as e:
        print(f"Warning: could not read existing leads from {leads_path}: {e}", file=sys.stderr)
    return rows, next_id, existing_urls


def write_leads(leads_path: Path, rows: list[dict]) -> None:
    leads_path.parent.mkdir(parents=True, exist_ok=True)
    with open(leads_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEADS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in LEADS_FIELDS})


def _scraper_listing_to_lead(r: dict) -> dict:
    """Convert silo scraper listing dict to one row for LEADS_FIELDS."""
    contact = r.get("contact") or {}
    is_private = r.get("is_private")
    return {
        "url": (r.get("url") or "").strip(),
        "title": (r.get("title") or "").strip(),
        "description": (r.get("description") or "").strip(),
        "price": (r.get("price") or "").strip(),
        "location": (r.get("location") or "").strip(),
        "bedrooms": (r.get("bedrooms") or "").strip(),
        "bathrooms": (r.get("bathrooms") or "").strip(),
        "size": (r.get("size") or "").strip(),
        "listing_type": (r.get("listing_type") or "").strip(),
        "source": (r.get("source") or "").strip(),
        "is_private": "true" if is_private else "false",
        "agency_name": (r.get("agency_name") or "").strip(),
        "image_url": (r.get("image_url") or "").strip(),
        "contact_email": (contact.get("email") or "").strip(),
        "contact_phone": (contact.get("phone") or "").strip(),
        "scan_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "new",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape website listing pages and append leads to CSV")
    parser.add_argument("--leads-path", required=True, help="Path to leads.csv (e.g. java_ui/data/leads.csv)")
    parser.add_argument("--url", action="append", default=[], dest="urls", help="Start URL (repeat for multiple)")
    parser.add_argument("--config", default=str(COLD_BOT_ROOT / "config.yaml"), help="Config YAML for silo scrapers")
    parser.add_argument("--listing-selector", default=DEFAULT_SELECTOR, help="CSS selector for generic/fallback")
    parser.add_argument("--scroll-depth", type=int, default=DEFAULT_SCROLL_DEPTH)
    parser.add_argument("--delay-min", type=int, default=DEFAULT_DELAY_MIN)
    parser.add_argument("--delay-max", type=int, default=DEFAULT_DELAY_MAX)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    leads_path = Path(args.leads_path).resolve()
    urls = [u.strip() for u in args.urls if u.strip()]
    if not urls:
        print("No URLs provided. Use --url <start_url> (repeat for multiple).", file=sys.stderr)
        return 1

    config = {}
    if Path(args.config).exists():
        try:
            import yaml
            with open(args.config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass
    limits = config.get("limits") or {}
    scroll_depth = max(1, int(limits.get("scroll_depth", DEFAULT_SCROLL_DEPTH)))
    delay_min = max(1, int(limits.get("delay_min", DEFAULT_DELAY_MIN)))
    delay_max = max(delay_min, int(limits.get("delay_max", DEFAULT_DELAY_MAX)))
    config["headless"] = args.headless
    selector = args.listing_selector or DEFAULT_SELECTOR

    try:
        all_leads = []
        silo_urls = []
        generic_urls = []
        for u in urls:
            if _infer_source_from_url(u) != "generic":
                silo_urls.append(u)
            else:
                generic_urls.append(u)

        # Use silo scrapers for recognized sites (each opens its own browser)
        for url in silo_urls:
            try:
                source = _infer_source_from_url(url)
                scraper = get_scraper_for_source(config, source)
                print(f"Scraping {url} with {scraper.site_name} scraper", flush=True)
                raw = scraper.scrape(url, dry_run=True, db_path=None, page=None)
                for r in raw:
                    lead = _scraper_listing_to_lead(r)
                    if lead.get("url") and not lead["url"].startswith("javascript:"):
                        all_leads.append(lead)
            except Exception as e:
                print(f"Silo scrape failed for {url}: {e}", flush=True)
                traceback.print_exc()

        # Generic fallback: one browser for all generic URLs
        if generic_urls:
            from playwright.sync_api import sync_playwright
            p = None
            try:
                p = sync_playwright().start()
                browser = p.chromium.launch(headless=args.headless)
                opts = {"viewport": {"width": 1280, "height": 800}}
                try:
                    from utils import rotate_ua
                    opts["user_agent"] = rotate_ua()
                except Exception:
                    pass
                context = browser.new_context(**opts)
                page = context.new_page()
                page.set_default_timeout(60_000)
                for url in generic_urls:
                    print(f"Opening (generic) {url}", flush=True)
                    for attempt in range(2):
                        try:
                            scroll_and_navigate(page, url, scroll_depth, delay_min, delay_max, timeout_ms=60_000)
                            break
                        except Exception as e:
                            if attempt == 1:
                                print(f"Failed to load {url}: {e}", flush=True)
                                continue
                            random_delay(3, 6)
                    else:
                        continue
                    try:
                        page.wait_for_selector(selector.split(",")[0].strip(), timeout=10_000)
                    except Exception:
                        pass
                    listings = extract_listings(page, selector, site=None)
                    for lst in listings:
                        href = (lst.get("url") or "").strip()
                        if not href or href.startswith("javascript:"):
                            continue
                        text = (lst.get("text") or "").strip()
                        parsed = parse_listing_text(text, href)
                        parsed["scan_time"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        parsed["status"] = "new"
                        all_leads.append(parsed)
                    random_delay(2, 5)
                close_browser(p, browser, context)
            except Exception as e:
                print(f"Generic scrape error: {e}", flush=True)
                traceback.print_exc()
            finally:
                if p is not None:
                    try:
                        p.stop()
                    except Exception:
                        pass

        existing_rows, next_id, existing_urls = read_existing_leads(leads_path)
        added = 0
        for lead in all_leads:
            url = lead.get("url", "")
            if not url or url in existing_urls:
                continue
            existing_urls.add(url)
            row = {k: lead.get(k, "") for k in LEADS_FIELDS}
            row["id"] = str(next_id)
            next_id += 1
            existing_rows.append(row)
            added += 1
        write_leads(leads_path, existing_rows)
        print(f"Done. Appended {added} new leads to {leads_path} (total {len(existing_rows)}).", flush=True)
        return 0
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
