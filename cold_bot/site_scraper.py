#!/usr/bin/env python3
"""
Real website listing scraper for the Java UI.
Uses Playwright to open start URL(s), scroll the page, extract listing cards
with a configurable CSS selector, parses title/price/location/contact from card text,
and appends new leads to java_ui/data/leads.csv (same format as Java: id, url, title,
description, price, location, contact_email, contact_phone, scan_time, status).
"""
import argparse
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

COLD_BOT_ROOT = Path(__file__).resolve().parent
if str(COLD_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(COLD_BOT_ROOT))

from silos.browser_automation import scroll_and_navigate, close_browser
from silos.data_scraper import extract_listings
from utils import random_delay, extract_contacts

DEFAULT_SELECTOR = "a[href*='/listing'], a[href*='/property'], a[href*='/buy'], a[href*='/sell'], [data-testid*='listing'], [class*='listing'], [class*='card']"
DEFAULT_SCROLL_DEPTH = 30
DEFAULT_DELAY_MIN = 3
DEFAULT_DELAY_MAX = 12

LEADS_FIELDS = [
    "id", "url", "title", "description", "price", "location",
    "contact_email", "contact_phone", "scan_time", "status",
]


def parse_listing_text(text: str, url: str) -> dict:
    """Extract title, price, location, email, phone from card text."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    title = lines[0][:200] if lines else "Listing"
    description = (text or "")[:2000].replace("\n", " ")
    price = ""
    location = ""
    price_match = re.search(r"\$[\d,]+(?:\s*(?:USD|EUR|GBP))?", text or "")
    if price_match:
        price = price_match.group(0)
    eur_match = re.search(r"[\d.,]+\s*€", text or "")
    if eur_match and not price:
        price = eur_match.group(0)
    loc_match = re.search(r"(?:in|at|near|location:?)\s*([A-Za-z0-9\s,-]+?)(?:\n|$|[0-9]{5})", text or "", re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).strip()[:120]
    contacts = extract_contacts(text or "")
    return {
        "url": url,
        "title": title,
        "description": description,
        "price": price,
        "location": location,
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
    except Exception:
        pass
    return rows, next_id, existing_urls


def write_leads(leads_path: Path, rows: list[dict]) -> None:
    leads_path.parent.mkdir(parents=True, exist_ok=True)
    with open(leads_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LEADS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in LEADS_FIELDS})


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape website listing pages and append leads to CSV")
    parser.add_argument("--leads-path", required=True, help="Path to leads.csv (e.g. java_ui/data/leads.csv)")
    parser.add_argument("--url", action="append", default=[], dest="urls", help="Start URL (repeat for multiple)")
    parser.add_argument("--listing-selector", default=DEFAULT_SELECTOR, help="CSS selector for listing cards/links")
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

    selector = args.listing_selector or DEFAULT_SELECTOR
    scroll_depth = max(1, args.scroll_depth)
    delay_min = max(1, args.delay_min)
    delay_max = max(delay_min, args.delay_max)

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

        all_leads = []
        for url in urls:
            print(f"Opening {url}", flush=True)
            scroll_and_navigate(page, url, scroll_depth, delay_min, delay_max)
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
        p = None

        existing_rows, next_id, existing_urls = read_existing_leads(leads_path)
        added = 0
        for lead in all_leads:
            url = lead.get("url", "")
            if url in existing_urls:
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
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if p is not None:
            try:
                p.stop()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
