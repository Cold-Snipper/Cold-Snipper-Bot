import argparse
import logging
import time
from typing import List

from silos.athome_scraper import fetch_html, extract_listing_links, parse_listing
from storage import init_listings_db, upsert_listing


def scan_athome(start_url: str, db_path: str, limit: int, delay: float) -> int:
    logging.info("Fetching search page: %s", start_url)
    html = fetch_html(start_url)
    links = extract_listing_links(html, "https://www.athome.lu")
    if limit > 0:
        links = links[:limit]
    logging.info("Found %d listing links", len(links))
    stored = 0
    for link in links:
        logging.info("Fetching listing: %s", link)
        try:
            listing_html = fetch_html(link)
        except Exception as exc:
            logging.warning("Failed to fetch listing %s: %s", link, exc)
            continue
        listing = parse_listing(listing_html, link)
        if upsert_listing(db_path, listing):
            stored += 1
            logging.info("Stored listing: %s", listing.get("title"))
        time.sleep(delay)
    return stored


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-url", default="https://www.athome.lu/en/apartment")
    parser.add_argument("--db", default="listings.db")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--delay", type=float, default=2.5)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    init_listings_db(args.db)
    stored = scan_athome(args.start_url, args.db, args.limit, args.delay)
    logging.info("Done. Stored %d new listings in %s", stored, args.db)


if __name__ == "__main__":
    main()
