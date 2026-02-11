# Luxembourg sites – per-site analysis and scraper adaptation

This document summarizes each LU target site: URL patterns, DOM selectors, language, and how the scraper is adapted.

---

## 1. atHome.lu

- **Base URL:** `https://www.athome.lu`
- **Language:** EN/FR/DE via path (`/en/`, `/fr/`, `/de/`) or config `athome_lang`
- **Sections:** Buy (`/buy/`), Rent (`/rent/`) – config `athome_section` or inferred from URL
- **Listing URL pattern:** `https://www.athome.lu/.../id-XXXXX.html` (e.g. `/en/buy/apartment/id-12345.html`)
- **Search/list URL:** e.g. `https://www.athome.lu/en/buy/`
- **Card structure:** Not always `.listing-item`; often links with `a[href*='/id-'][href$='.html']`. Card text can be minimal (e.g. "Apartment2 60€906,303").
- **Scraper adaptations:**
  - Consent + language + section (Rent/Buy) handling in `scrape()`
  - Fallback selectors: `a[href*='/id-'][href$='.html']`, `a[href*='/en/buy/'][href*='.html']`, `a[href*='/en/rent/'][href*='.html']`, `[class*='card'] a[href*='.html']`, `article a[href*='/buy/']`, `article a[href*='/rent/']`
  - `collect_listings()` tries default then each fallback
  - `extract_listing_data()`: URL from `<a href>`, normalised to full `https://www.athome.lu/...`; title/price parsed from link text when no `.title`/`.price` (e.g. € price regex)
  - Wait for `a[href*='/id-'][href$='.html'], .listing-item` after scroll before collect

---

## 2. immotop.lu

- **Base URL:** `https://www.immotop.lu`
- **Language:** FR default; paths like `/vente-maisons-appartements/`, `/location/`; EN possible via `/en/`
- **Listing URL pattern:** `/annonces/ID` e.g. `https://www.immotop.lu/annonces/1868045/`
- **Search/list URL:** e.g. `https://www.immotop.lu/vente-maisons-appartements/luxembourg-pays/` or `/en/buy/`
- **Card structure:** Cards are often `<a href="/annonces/...">` with title and price in text (e.g. "Maison jumelée / mitoyenne 174 m², Ettelbruck Localité, Ettelbruck" and "€ 795 000").
- **Scraper adaptations:**
  - Default selector: `.property-item`; fallbacks: `a[href*='/annonces/']`, `[class*='card'] a[href*='/annonces/']`, `article a[href*='/annonces/']`
  - `collect_listings()` tries default then fallbacks
  - URL normalisation: ensure `https://www.immotop.lu` + path (relative links like `/annonces/123/`)
  - `extract_listing_data()`: title/location from link text or `.title`/`.location`; price via regex `€[\d\s,.]+` when no `.price`

---

## 3. nextimmo.lu

- **Base URL:** `https://nextimmo.lu` (no `www` in canonical URLs)
- **Language:** EN; path `/en/`
- **Listing URL pattern:** `/en/details/ID` e.g. `https://nextimmo.lu/en/details/86109474`
- **Search/list URL:** e.g. `https://nextimmo.lu/en/search/page/1` or `/en/`
- **Card structure:** Links like `a[href*='/en/details/']`; card text e.g. "4-bedroom House for sale in Grevels", "549 000 €", "4295 m²" (or similar).
- **Scraper adaptations:**
  - Default selector: `[class*='listing'], [class*='card'], article a[href*='/details/']`; fallbacks: `a[href*='/en/details/']`, `a[href*='/details/']`
  - `collect_listings()` tries default then fallbacks
  - URL normalisation: `https://nextimmo.lu` (prefer no www) for relative `/en/details/...`
  - `extract_listing_data()`: price regex for "549 000 €"; title from h2/h3 or link text; bedrooms from "X-bedroom" in text

---

## 4. bingo.lu

- **Base URL:** `https://www.bingo.lu`
- **Language:** EN; path `/en/`
- **Listing URL pattern:** Not fully confirmed; `/en/buy/` can show "No results" or "Processing, please wait…" (heavy JS / map-based search).
- **Scraper adaptations:**
  - Default selector: `[class*='listing'], [class*='property'], [class*='card'], article a[href*='/property']`
  - Fallbacks: `a[href*='/en/'][href*='.html']`, `[class*='card'] a[href*='/en/']`, `article a[href*='/en/']` to catch listing links when results load
  - `collect_listings()` tries default then fallbacks
  - URL normalisation: `https://www.bingo.lu` for relative hrefs
  - If site remains JS-heavy or requires map interaction, consider longer wait or optional search params in config

---

## 5. propertyweb.lu

- **Base URL:** `https://www.propertyweb.lu`
- **Language:** EN; path `/en/`
- **Listing URL pattern:** `/en/to-let/...`, `/en/for-sale/...`, `/en/investment/...` (e.g. `/en/to-let/office/cosy/51972`)
- **Search/list URL:** `https://www.propertyweb.lu/en/`
- **Cookie consent:** "Accept All Cookies" – use generic consent click or button text match
- **Card structure:** Listing links in format `/en/to-let/...`, `/en/for-sale/...`, `/en/investment/...`
- **Scraper adaptations:**
  - Default selector: `[class*='listing'], [class*='property'], [class*='card']`; fallbacks: `a[href*='/en/to-let/'][href*='/']`, `a[href*='/en/for-sale/'][href*='/']`, `a[href*='/en/investment/'][href*='/']`
  - `collect_listings()` tries default then fallbacks
  - URL normalisation: `https://www.propertyweb.lu` for relative paths
  - `accept_consent()`: ensure "Accept All Cookies" / "Accept" is clicked (base `try_accept_consent` may already catch it)

---

## 6. wortimmo.lu

- **Base URL:** `https://www.wortimmo.lu`
- **Language:** FR default; paths `/fr/vente-...`, `/fr/location/...`
- **Listing URL pattern:** `/fr/vente-appartement-...-id_XXXXX` or `/fr/vente-maison-...-id_XXXXX`, `/fr/location/...-id_XXXXX` (e.g. `...-id_483620`)
- **Search/list URL:** e.g. `https://www.wortimmo.lu/fr/` or category listing pages
- **Card structure:** Links with `href` containing `-id_` or `/vente-`/`/location/`; card text: price "475 000 €", "1 699 157 €", location, surface "52m2", "3 Chb" (chambres).
- **Scraper adaptations:**
  - Default selector: `a[href*='-id_'], a[href*='/vente-'], a[href*='/location/']`; fallbacks: `[class*='card'] a[href*='-id_']`, `[class*='listing'] a[href*='-id_']`
  - `collect_listings()` tries default then fallbacks
  - URL normalisation: `https://www.wortimmo.lu` for relative paths
  - `extract_listing_data()`: price regex "475 000 €"; bedrooms from "X Chb"; size from "52m2" / "X m²"; title/location from card text or dedicated elements

---

## Config (target_sites_by_country.LU)

- atHome: `https://www.athome.lu/en/buy/`, `https://www.athome.lu/en/rent`
- Immotop: `https://www.immotop.lu/en/buy/` (or FR `/vente-maisons-appartements/luxembourg-pays/`)
- Nextimmo: `https://www.nextimmo.lu/en/`
- Bingo: `https://www.bingo.lu/en/`
- PropertyWeb: `https://www.propertyweb.lu/en/`
- Wortimmo: add e.g. `https://www.wortimmo.lu/fr/` for FR listings

---

## Shared helpers

- `_fill_beds_baths_size()`: extracts bedrooms, bathrooms, size (m²/sqft) from card text; FR "Chb" (chambres) can be matched by extending bedroom regex if needed.
- All LU scrapers: normalise listing URL to full `https://<domain>` when href is relative; prefer one canonical base (with or without `www`) per site.
