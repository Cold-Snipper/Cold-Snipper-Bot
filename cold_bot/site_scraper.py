#!/usr/bin/env python3
"""
Real website listing scraper (no simulation).
- Uses silo scrapers (athome, immotop, rightmove, Luxembourg nextimmo/bingo/propertyweb/wortimmo)
  when URL is recognized; otherwise falls back to generic extract_listings.
- Output nomenclature aligned with listings.db: listing_ref, listing_url, transaction_type,
  sale_price, rent_price, surface_m2, agent_name, phone_number, agency_name, first_seen, last_updated.
"""
import argparse
import csv
import hashlib
import re
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

COLD_BOT_ROOT = Path(__file__).resolve().parent
if str(COLD_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(COLD_BOT_ROOT))

from silos.browser_automation import scroll_and_navigate, close_browser, init_browser, try_accept_consent
from silos.data_scraper import extract_listings
from silos.detail_enrichment import enrich_listing_detail
from silos.scraper import _infer_source_from_url, get_scraper_for_source
from utils import random_delay, extract_contacts

DEFAULT_SELECTOR = "a[href*='/listing'], a[href*='/property'], a[href*='/buy'], a[href*='/sell'], [data-testid*='listing'], [class*='listing'], [class*='card']"
DEFAULT_SCROLL_DEPTH = 30
DEFAULT_DELAY_MIN = 3
DEFAULT_DELAY_MAX = 12

# Nomenclature aligned with listings.db (listing_ref, listing_url, transaction_type, sale_price, rent_price, surface_m2, agent_name, phone_number, agency_name, first_seen, last_updated)
LEADS_FIELDS = [
    "id", "listing_ref", "listing_url", "transaction_type", "title", "location", "description",
    "sale_price", "rent_price", "surface_m2", "bedrooms", "bathrooms", "rooms",
    "phone_number", "agency_name", "agency_url", "agent_name",
    "image_urls", "first_seen", "last_updated",
    "source", "is_private", "contact_email", "status",
]


def _listing_ref(url: str) -> str:
    if not url:
        return ""
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def _parse_price_numeric(price_str: str) -> tuple:
    """Return (sale_price, rent_price) as floats or empty string. Guesses sale vs rent from € and context."""
    if not price_str or not isinstance(price_str, str):
        return ("", "")
    s = re.sub(r"[\s\xa0]", "", price_str)
    m = re.search(r"([\d.,]+)", s)
    if not m:
        return ("", "")
    try:
        num = float(m.group(1).replace(",", ".").replace(" ", ""))
    except ValueError:
        return ("", "")
    if "rent" in price_str.lower() or "€/month" in price_str.lower() or "/mo" in price_str.lower():
        return ("", num)
    return (num, "")


def _parse_surface_m2(size_str: str):
    """Return surface_m2 as float or empty string."""
    if not size_str or not isinstance(size_str, str):
        return ""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", size_str, re.IGNORECASE) or re.search(r"(\d+(?:[.,]\d+)?)\s*m2\b", size_str, re.IGNORECASE)
    if not m:
        return ""
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return ""


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
    sale, rent = _parse_price_numeric(price)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "listing_ref": _listing_ref(url),
        "listing_url": url,
        "transaction_type": "rent" if listing_type == "rent" else "sale",
        "title": title,
        "location": location,
        "description": description,
        "sale_price": sale,
        "rent_price": rent,
        "surface_m2": _parse_surface_m2(size),
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "rooms": "",
        "phone_number": contacts.get("phone", ""),
        "agency_name": "",
        "agency_url": "",
        "agent_name": "",
        "image_urls": "",
        "first_seen": ts,
        "last_updated": ts,
        "source": source,
        "is_private": "false",
        "contact_email": contacts.get("email", ""),
        "status": "new",
    }


def read_existing_leads(leads_path: Path) -> tuple[list[dict], int, set[str]]:
    """Return (rows as list of dicts, next_id, existing_urls). Dedup by listing_url."""
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
                u = row.get("listing_url") or row.get("url", "")
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


def _write_listings_db(db_path: str, rows: list[dict]) -> None:
    """Write rows to SQLite using listings.db nomenclature (listing_ref PK, listing_url, sale_price, rent_price, surface_m2, agent_name, phone_number, etc.)."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            listing_ref TEXT PRIMARY KEY,
            agency_ref TEXT, transaction_type TEXT, listing_url TEXT,
            title TEXT, location TEXT, description TEXT,
            sale_price REAL, rent_price REAL, monthly_charges REAL,
            deposit REAL, commission TEXT, availability TEXT,
            surface_m2 REAL, floor INTEGER, rooms INTEGER,
            bedrooms INTEGER, year_of_construction INTEGER,
            fitted_kitchen INTEGER, open_kitchen INTEGER,
            shower_rooms INTEGER, bathrooms INTEGER,
            separate_toilets INTEGER, furnished INTEGER,
            balcony INTEGER, balcony_m2 REAL, terrace_m2 REAL,
            garden INTEGER, parking_spaces INTEGER,
            energy_class TEXT, thermal_insulation_class TEXT,
            gas_heating INTEGER, electric_heating INTEGER,
            heat_pump INTEGER, district_heating INTEGER,
            pellet_heating INTEGER, oil_heating INTEGER,
            solar_heating INTEGER,
            basement INTEGER, laundry_room INTEGER,
            elevator INTEGER, storage INTEGER, pets_allowed INTEGER,
            phone_number TEXT, phone_source TEXT,
            agency_name TEXT, agency_url TEXT,
            agent_name TEXT, agency_logo_url TEXT,
            image_urls TEXT, images_dir TEXT,
            first_seen TEXT, last_updated TEXT,
            title_history TEXT
        )
    """)
    for row in rows:
        ref = row.get("listing_ref") or _listing_ref(row.get("listing_url") or "")
        if not ref:
            continue
        try:
            sale = row.get("sale_price")
            sale = float(sale) if sale is not None and str(sale).strip() and str(sale).strip() != "" else None
        except (TypeError, ValueError):
            sale = None
        try:
            rent = row.get("rent_price")
            rent = float(rent) if rent is not None and str(rent).strip() and str(rent).strip() != "" else None
        except (TypeError, ValueError):
            rent = None
        try:
            surface = row.get("surface_m2")
            if surface == "":
                surface = None
            elif surface is not None:
                surface = float(surface)
        except (TypeError, ValueError):
            surface = None
        try:
            bed = row.get("bedrooms")
            bed = int(bed) if bed and str(bed).strip().isdigit() else None
        except (TypeError, ValueError):
            bed = None
        try:
            bath = row.get("bathrooms")
            bath = int(bath) if bath and str(bath).strip().isdigit() else None
        except (TypeError, ValueError):
            bath = None
        conn.execute(
            """INSERT OR REPLACE INTO listings (
                listing_ref, transaction_type, listing_url, title, location, description,
                sale_price, rent_price, surface_m2, bedrooms, bathrooms,
                phone_number, agency_name, agency_url, agent_name, image_urls,
                first_seen, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ref,
                row.get("transaction_type") or "",
                row.get("listing_url") or "",
                row.get("title") or "",
                row.get("location") or "",
                row.get("description") or "",
                sale,
                rent,
                surface,
                bed,
                bath,
                row.get("phone_number") or "",
                row.get("agency_name") or "",
                row.get("agency_url") or "",
                row.get("agent_name") or "",
                row.get("image_urls") or "",
                row.get("first_seen") or "",
                row.get("last_updated") or "",
            ),
        )
    conn.commit()
    conn.close()
    print(f"Wrote {len(rows)} rows to {db_path} (listings table).", flush=True)


def _scraper_listing_to_lead(r: dict) -> dict:
    """Convert silo scraper listing dict to one row (listings.db nomenclature)."""
    contact = r.get("contact") or {}
    url = (r.get("url") or "").strip()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    price_str = (r.get("price") or "").strip()
    sale_price, rent_price = _parse_price_numeric(price_str)
    size_str = (r.get("size") or "").strip()
    surface_m2 = _parse_surface_m2(size_str)
    transaction = (r.get("listing_type") or "").strip().lower()
    if transaction in ("rent", "rental"):
        transaction_type = "rent"
    else:
        transaction_type = "sale"
    return {
        "listing_ref": _listing_ref(url),
        "listing_url": url,
        "transaction_type": transaction_type,
        "title": (r.get("title") or "").strip(),
        "location": (r.get("location") or "").strip(),
        "description": (r.get("description") or "").strip(),
        "sale_price": sale_price if sale_price != "" else "",
        "rent_price": rent_price if rent_price != "" else "",
        "surface_m2": surface_m2,
        "bedrooms": (r.get("bedrooms") or "").strip(),
        "bathrooms": (r.get("bathrooms") or "").strip(),
        "rooms": "",
        "phone_number": (contact.get("phone") or r.get("contact_phone") or "").strip(),
        "agency_name": (r.get("agency_name") or "").strip(),
        "agency_url": (r.get("agency_url") or "").strip(),
        "agent_name": (r.get("contact_name") or "").strip(),
        "image_urls": (r.get("image_url") or "").strip(),
        "first_seen": ts,
        "last_updated": ts,
        "source": (r.get("source") or "").strip(),
        "is_private": "true" if r.get("is_private") else "false",
        "contact_email": (contact.get("email") or r.get("contact_email") or "").strip(),
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
    parser.add_argument("--no-enrich", action="store_true", dest="no_enrich", help="Skip visiting each listing (faster but no email/phone extraction)")
    parser.add_argument("--enrich-max", type=int, default=80, help="Max listings to enrich for email/phone (default 80)")
    parser.add_argument("--private-only", action="store_true", help="Keep only non-agent (private seller) listings in output")
    parser.add_argument("--db", default="", help="Optional: also write to this SQLite DB (listings table, same nomenclature as listings.db)")
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
                print(f"Scraping {url} with {scraper.site_name} scraper...", flush=True)
                raw = scraper.scrape(url, dry_run=True, db_path=None, page=None)
                n = 0
                for r in raw:
                    lead = _scraper_listing_to_lead(r)
                    listing_url = lead.get("listing_url") or ""
                    if not listing_url or listing_url.startswith("javascript:"):
                        continue
                    # AtHome: only keep rows with real listing URL (/id-XXX.html)
                    if lead.get("source") == "athome" and "/id-" not in listing_url:
                        continue
                    # PropertyWeb: skip category/nav links (e.g. /en/to-let/warehouse)
                    if lead.get("source") == "propertyweb":
                        from urllib.parse import urlparse
                        path = (urlparse(listing_url).path or "").strip("/")
                        if path.count("/") < 3:  # need en/category/subcategory/slug
                            continue
                    all_leads.append(lead)
                    n += 1
                print(f"  {scraper.site_name}: found {n} listings from this page", flush=True)
            except Exception as e:
                print(f"Silo scrape failed for {url}: {e}", flush=True)
                traceback.print_exc()

        # Enrich leads: visit each listing detail page to get contact name, email, phone, agency/private
        run_enrich = not getattr(args, "no_enrich", False)
        if run_enrich and all_leads:
            enrich_max = max(1, getattr(args, "enrich_max", 50))
            to_enrich = all_leads[:enrich_max]
            print(f"Enriching {len(to_enrich)} listings (contact, agency/private)...", flush=True)
            p, browser, context, page = None, None, None, None
            try:
                p, browser, context, page = init_browser(headless=args.headless)
                page.set_default_timeout(20_000)
                for i, lead in enumerate(to_enrich):
                    try:
                        url = lead.get("listing_url") or ""
                        if not url or url.startswith("javascript:"):
                            continue
                        src = lead.get("source") or "generic"
                        e = enrich_listing_detail(
                            page, url, src,
                            timeout_ms=15_000,
                            accept_consent_fn=lambda pg: try_accept_consent(pg, timeout_per_try_ms=400),
                        )
                        if e.get("contact_name"):
                            lead["agent_name"] = e["contact_name"]
                        if e.get("contact_email"):
                            lead["contact_email"] = e["contact_email"]
                        if e.get("contact_phone"):
                            lead["phone_number"] = e["contact_phone"]
                        if e.get("description"):
                            lead["description"] = lead.get("description") or e["description"]
                        if e.get("location"):
                            lead["location"] = lead.get("location") or e["location"]
                        if e.get("is_private") is not None:
                            lead["is_private"] = "true" if e["is_private"] else "false"
                        if e.get("agency_name"):
                            lead["agency_name"] = e["agency_name"]
                        if (i + 1) % 10 == 0:
                            print(f"  Enriched {i + 1}/{len(to_enrich)}", flush=True)
                    except Exception as ex:
                        print(f"  Enrich failed for {url[:60]!r}: {ex}", flush=True)
                    random_delay(1, 2)
            finally:
                if p is not None:
                    close_browser(p, browser, context)
            print(f"  Enrichment done.", flush=True)

        # Focus on non-agents: keep only private seller listings
        if getattr(args, "private_only", False) and all_leads:
            before = len(all_leads)
            all_leads = [l for l in all_leads if (l.get("is_private") or "").lower() == "true"]
            print(f"  Private-only: kept {len(all_leads)} of {before} (non-agent listings).", flush=True)

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
            listing_url = lead.get("listing_url") or ""
            if not listing_url or listing_url in existing_urls:
                continue
            existing_urls.add(listing_url)
            row = {k: lead.get(k, "") for k in LEADS_FIELDS}
            row["id"] = str(next_id)
            next_id += 1
            existing_rows.append(row)
            added += 1
            title = (row.get("title") or "")[:60]
            sale = row.get("sale_price")
            rent = row.get("rent_price")
            price_disp = f"{sale}€" if sale else (f"{rent}€/mo" if rent else "")
            loc = (row.get("location") or "")[:40]
            print(f"SAVED id={row['id']} | {title!r} | {price_disp} | {loc} | {listing_url[:70]}", flush=True)
        write_leads(leads_path, existing_rows)
        if getattr(args, "db", "").strip():
            _write_listings_db(args.db.strip(), existing_rows)
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
