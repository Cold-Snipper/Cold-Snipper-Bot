"""
Multi-purpose website scraper. Same root (base), different module per site.
Re-export from silos.scrapers so existing imports keep working.

Usage: from silos.scraper import get_scraper_for_source, Scraper, save_to_db, LISTING_SCHEMA
"""
from __future__ import annotations

from .scrapers import (
    LISTING_SCHEMA,
    AtHomeScraper,
    BingoScraper,
    FBMarketplaceScraper,
    ImmotopScraper,
    NextimmoScraper,
    PropertyWebScraper,
    RightmoveScraper,
    Scraper,
    WortimmoScraper,
    get_scraper_for_source,
    save_to_db,
    _infer_source_from_url,
)

__all__ = [
    "Scraper",
    "AtHomeScraper",
    "ImmotopScraper",
    "NextimmoScraper",
    "BingoScraper",
    "PropertyWebScraper",
    "WortimmoScraper",
    "RightmoveScraper",
    "FBMarketplaceScraper",
    "get_scraper_for_source",
    "_infer_source_from_url",
    "LISTING_SCHEMA",
    "save_to_db",
]

if __name__ == "__main__":
    import argparse
    import logging
    import sys
    import yaml
    from pathlib import Path
    _COLD_BOT_ROOT = Path(__file__).resolve().parent.parent
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
