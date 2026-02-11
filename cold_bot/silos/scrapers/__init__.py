"""
Same root (base), different module per site. Reject cookies first; fast flow.
"""
from .base import (
    LISTING_SCHEMA,
    Scraper,
    save_to_db,
)
from .athome import AtHomeScraper
from .immotop import ImmotopScraper
from .nextimmo import NextimmoScraper
from .bingo import BingoScraper
from .propertyweb import PropertyWebScraper
from .wortimmo import WortimmoScraper
from .rightmove import RightmoveScraper
from .facebook import FBMarketplaceScraper


def get_scraper_for_source(config, source_type: str) -> Scraper:
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
    if "athome" in u or "at-home" in u:
        return "athome"
    if "immotop" in u:
        return "immotop"
    if "rightmove" in u:
        return "rightmove"
    return "generic"


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
