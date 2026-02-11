# Luxembourg sites – per-site analysis and scraper adaptation

**URLs in this doc and in `config.yaml` are researched by navigating each site and inspecting real links; they are not guessed.**

---

## Researched start URLs (from live navigation)

| Site | Researched URL | What it shows |
|------|----------------|---------------|
| atHome | `https://www.athome.lu/en/buy/`, `.../en/rent` | Buy / Rent listing grid |
| Immotop | `https://www.immotop.lu/vente-maisons-appartements/luxembourg-pays/?criterio=rilevanza` | ~11k results, links to `/annonces/ID` |
| Immotop EN | `https://www.immotop.lu/en/vente-maisons-appartements/luxembourg-pays/?criterio=rilevanza` | Same, EN UI |
| Nextimmo | `https://nextimmo.lu/en/search/page/1` | 7856+ listings, links to `/en/details/ID` |
| Bingo | `https://www.bingo.lu/fr/vente/`, `.../fr/search/offers?mapViewType=list` | FR buy; list view (JS-heavy, may show "Traitement en cours") |
| PropertyWeb | `https://propertyweb.lu/en/to-let/office`, `.../for-sale/office`, `.../for-sale/residential/apartment` | Office/residential listing lists |
| Wortimmo | `https://www.wortimmo.lu/fr/vente`, `.../fr/vente/appartement`, `.../fr/vente/maison` | FR sale; apartment/house lists, links `...-id_XXXXX` |

**Note:** Immotop has no `/en/buy/` path; the real listing results URL is `vente-maisons-appartements/luxembourg-pays/?criterio=rilevanza`. Nextimmo’s real search results are at `/en/search/page/1`, not `/en/`.

---

## 1. atHome.lu

- **Base URL:** `https://www.athome.lu`
- **Language:** EN/FR/DE via path (`/en/`, `/fr/`, `/de/`) or config `athome_lang`
- **Sections:** Buy (`/buy/`), Rent (`/rent/`) – config `athome_section` or inferred from URL
- **Listing URL pattern:** `https://www.athome.lu/.../id-XXXXX.html` (e.g. `/en/buy/apartment/id-12345.html`)
- **Search/list URL (researched):** `https://www.athome.lu/en/buy/`, `.../en/rent`
- **Card structure:** Not always `.listing-item`; often links with `a[href*='/id-'][href$='.html']`. Card text can be minimal.
- **Scraper adaptations:** Consent + language + section; fallback selectors; wait for listing links; URL normalisation; title/price from link text.

---

## 2. immotop.lu

- **Base URL:** `https://www.immotop.lu`
- **Language:** FR default; EN via `/en/` prefix on same path.
- **Listing URL pattern:** `/annonces/ID` e.g. `https://www.immotop.lu/annonces/1843479/`
- **Search/list URL (researched):** Homepage links to `vente-maisons-appartements/luxembourg-pays/?criterio=rilevanza` (FR) and `en/vente-maisons-appartements/luxembourg-pays/?criterio=rilevanza` (EN). **There is no `/en/buy/`** – that path does not show a listing grid.
- **Card structure:** Links `<a href="/annonces/...">` with title and price in text (e.g. "€ 629 000", "Appartement 2 chambres...").
- **Scraper adaptations:** Default selector `.property-item`; fallbacks `a[href*='/annonces/']`, etc.; URL normalisation; price regex `€[\d\s,.]+`; Immotop-specific consent.

---

## 3. nextimmo.lu

- **Base URL:** `https://nextimmo.lu` (no `www` in canonical URLs)
- **Language:** EN; path `/en/`
- **Listing URL pattern:** `/en/details/ID` e.g. `https://nextimmo.lu/en/details/86109474`
- **Search/list URL (researched):** Homepage links to `search/page/1`; EN results at `https://nextimmo.lu/en/search/page/1` (7856 properties). **Use `/en/search/page/1`, not `/en/`** for a full listing grid.
- **Card structure:** Links `a[href*='/en/details/']`; card text e.g. "4-bedroom House for sale in Grevels", "549 000 €".
- **Scraper adaptations:** Fallbacks `a[href*='/en/details/']`, `a[href*='/details/']`; base `https://nextimmo.lu`; price/title from card text.

---

## 4. bingo.lu

- **Base URL:** `https://www.bingo.lu`
- **Language:** FR default (nav: Acheter/Louer); EN via language switcher.
- **Listing URL pattern (researched):** Nav points to `/fr/vente/` (buy) and `/fr/location/` (rent). List view: `/fr/search/offers?mapViewType=list`. Page can show "Traitement en cours", "Pas de résultats" or "nombre maximal de résultats" (JS/map-heavy).
- **Scraper adaptations:** Fallbacks for `a[href*='/en/']`, `[class*='card'] a[href*='/en/']`; base `https://www.bingo.lu`. Use researched URLs in config; if results depend on map/filters, scraper may need longer wait or interaction.

---

## 5. propertyweb.lu

- **Base URL:** `https://www.propertyweb.lu` (homepage redirects to `propertyweb.lu/en`)
- **Language:** EN; path `/en/`
- **Listing URL pattern (researched):** `/en/to-let/office`, `/en/to-let/office/cosy/51972`, `/en/for-sale/office`, `/en/for-sale/residential/apartment`, `/en/investment/office`. Homepage "Search per city" and "Search by property type" link to these.
- **Cookie consent (researched):** "Accept All Cookies", "Reject All Cookies", "Cookie Settings".
- **Scraper adaptations:** Fallbacks for to-let/for-sale/investment; base `https://www.propertyweb.lu`; reject/accept consent.

---

## 6. wortimmo.lu

- **Base URL:** `https://www.wortimmo.lu`
- **Language:** FR default; paths `/fr/vente/...`, `/fr/location/...`
- **Listing URL pattern (researched):** Detail pages `/fr/vente-appartement-...-id_XXXXX`, `/fr/vente-maison-...-id_XXXXX`. Nav: "Appartements à vendre" → `/fr/vente/appartement`, "Maisons à vendre" → `/fr/vente/maison`, "Acheter" → `/fr/vente`.
- **Card structure:** Links with `-id_`; price "318 650 €", "1 148 000 €"; surface "35m2", "150m2"; "1 Chb", "4 Chb".
- **Scraper adaptations:** Selectors `a[href*='-id_']`, `/vente-`, `/location/`; base `https://www.wortimmo.lu`; price/beds/size from card text.

---

## Config (target_sites_by_country.LU)

Use the **researched** URLs above in `config.yaml`; they are already set there. Do not use guessed paths like `/en/buy/` for Immotop or `/en/` for Nextimmo.

---

## Shared helpers

- `_fill_beds_baths_size()`: extracts bedrooms, bathrooms, size (m²/sqft) from card text; FR "Chb" (chambres) can be matched by extending bedroom regex if needed.
- All LU scrapers: normalise listing URL to full `https://<domain>` when href is relative; prefer one canonical base (with or without `www`) per site.
