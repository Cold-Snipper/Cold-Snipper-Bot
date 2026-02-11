# Contact reveal by country / site

Many listing sites **hide** phone/email behind a click: "Voir les coordonnées", "Afficher le téléphone", "Show phone", etc. The crawler must **click that element** before scraping contact info. This doc records per-site specificities and the process to add new countries.

---

## 1. Luxembourg (current)

| Site | Specificity | Implemented |
|------|-------------|-------------|
| **atHome** | Click **"Voir les coordonnées"** (or "Voir les coordonnées de l'annonceur") → contact card pops out with agency name, **Tél. +352...**, sometimes email. Red "Contacter" may open form. | ✅ `REVEAL_BY_SOURCE["athome"]` |
| **Immotop** | Click **"Afficher le téléphone"** (blue link with phone icon below agency name) → phone number appears. "ENVOYER UN MESSAGE" / "DEMANDER UNE VISITE" are separate actions. | ✅ `REVEAL_BY_SOURCE["immotop"]` |
| **Nextimmo** | Contact may be direct or behind "Contact" / "Show contact". No confirmed "reveal phone" pattern yet. | ✅ Generic + `REVEAL_BY_SOURCE["nextimmo"]` (to be refined) |
| **Bingo** | JS-heavy; contact may be in sidebar or behind "Contact" / "Contacter". | ✅ Generic + `REVEAL_BY_SOURCE["bingo"]` (to be refined) |
| **PropertyWeb** | CBRE-style; listing detail often has "Contact" for that property. | ✅ Generic + `REVEAL_BY_SOURCE["propertyweb"]` (to be refined) |
| **Wortimmo** | Per search: "Contacter" / "Email" buttons to contact seller or agency; "Voir détails" for agencies. | ✅ Generic + `REVEAL_BY_SOURCE["wortimmo"]` (to be refined) |

**Code:** `cold_bot/silos/detail_enrichment.py`  
- `REVEAL_BY_SOURCE`: per-source list of link/button texts to try.  
- `_click_reveal(text)`: finds and clicks `a:has-text(...)`, `button:has-text(...)`, etc., then waits.  
- After any click we wait, then scrape `tel:` links, "Tél. +352...", and overlay/modal content.

---

## 2. How to discover a new site’s “reveal” (any country)

When you add a **new country or site**, do this so the crawler can extract phone/email:

1. **Open a listing detail page** (one property, not the search list) in a browser.
2. **Find where phone/email would be:**  
   - Often in a sidebar or box: "Contact the agent", "Agency", "Seller".
3. **Check if it’s hidden:**  
   - If you see a link like "Show phone", "Voir le numéro", "Display contact", "Afficher le téléphone", "View contact details", etc., that’s the **reveal**.
4. **Note the exact wording and language:**  
   - e.g. "Afficher le téléphone" (FR), "Show phone number" (EN), "Telefon anzeigen" (DE).
5. **Add to the code:**  
   - In `detail_enrichment.py`:  
     - Add a key to `REVEAL_BY_SOURCE` if the site has its own source id (e.g. `"rightmove"`, `"leboncoin"`).  
     - Or extend `REVEAL_COORDONNEES` / `REVEAL_CONTACT_BUTTONS` with the new text(s).  
   - Use the **exact** button/link text (or a short unique substring) so the locator `a:has-text('...')` / `button:has-text('...')` matches.
6. **Optional:**  
   - If the reveal opens a **modal/overlay**, ensure `CONTACT_OVERLAY_SELECTORS` includes a class/role that appears on that overlay (e.g. `[class*='modal']`, `[role='dialog']`) so we scrape the revealed block.
7. **Test:**  
   - Run the scraper with `--enrich` and `--enrich-max 1` for one URL of that site and check that `phone_number` or `contact_email` is filled in the CSV.

---

## 3. Plan for non-Luxembourg nations

When it’s time to support **another country**, follow this checklist:

| Step | Action |
|------|--------|
| 1 | Add the country’s main listing sites to `config.yaml` under `target_sites_by_country.<CC>` (e.g. `UK`, `FR`, `DE`). |
| 2 | Ensure each site has a **scraper** (or generic) and a **source** id (e.g. `rightmove`, `leboncoin`, `immobilienscout24`). |
| 3 | For each site, **visit 1–2 listing detail pages** and apply the discovery process (§2): find the “reveal” link/button text and language. |
| 4 | In `detail_enrichment.py`: add or extend `REVEAL_BY_SOURCE` for that source with the **exact** reveal text(s) in the site’s language (and EN if the site is bilingual). |
| 5 | If the country uses a **different phone format** (e.g. UK 07xxx, DE 0xx / +49), add or adjust phone regex in `enrich_listing_detail` (e.g. `phone_pats`) so we don’t miss numbers. |
| 6 | Run a small test (`--enrich --enrich-max 3`) and confirm contact fields are populated. |
| 7 | Update this doc with a new section **"N. Country name (CC)"** and a table like §1 for that country’s sites. |

**Example for a future country (e.g. France):**

```markdown
## N. France (FR)

| Site | Specificity | Implemented |
|------|-------------|-------------|
| leboncoin | Click "Afficher le numéro" / "Voir le numéro" → phone appears. | ✅ REVEAL_BY_SOURCE["leboncoin"] |
| seloger.com | "Contacter l'annonceur" opens form; phone sometimes in "Voir les coordonnées". | ✅ to be refined |
```

And in code:

```python
REVEAL_BY_SOURCE["leboncoin"] = ["Afficher le numéro", "Voir le numéro", "Contacter"]
```

---

## 4. Summary

- **Luxembourg:** atHome and Immotop specificities are implemented; other LU sites use generic + per-source lists to be refined when someone checks a live listing.
- **Other nations:** When you add a country, (1) add sites to config and scrapers, (2) visit listing pages and note the reveal button/link text, (3) add that text to `REVEAL_BY_SOURCE` or `REVEAL_COORDONNEES`, (4) test with `--enrich`, (5) document in this file.
