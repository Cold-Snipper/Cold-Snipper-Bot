# Scraper Structure and Test Report

## Modality Structure

### 1. Website Scraper (scan_mode=website)

```
UI (Website Bot panel) → POST /api/action name=start_scan, scan_mode=website, start_urls=...
  → Main.java: runRealSiteScan(params, false)
    → Builds URLs from params.start_urls
    → Invokes: python3 cold_bot/site_scraper.py --leads-path java_ui/data/leads.csv --url <url1> --url <url2> ...
    → Waits for process, on success: LEADS.clear(); loadLeads(); scanState=idle

site_scraper.py flow:
  → For each URL: _infer_source_from_url(url)
    → If source != "generic": get_scraper_for_source(config, source) → scraper.scrape(url, dry_run=True)
      → Uses silo: AtHomeScraper, ImmotopScraper, RightmoveScraper, NextimmoScraper, BingoScraper, PropertyWebScraper, WortimmoScraper
      → Each opens own Playwright/Chromium browser, navigates, scrolls, collects elements, extracts listing data
    → If source == "generic": scroll_and_navigate + extract_listings (generic selector)
  → Convert all results to LEADS_FIELDS rows (url, title, description, price, location, contact_email, contact_phone, ...)
  → read_existing_leads(leads_path) → merge with dedup by URL → write_leads(leads_path)
```

**CSV schema (leads.csv):** id, url, title, description, price, location, bedrooms, size, listing_type, contact_email, contact_phone, scan_time, status

**Luxembourg sites:** athome.lu, immotop.lu, nextimmo.lu, bingo.lu, propertyweb.lu, wortimmo.lu → each has dedicated scraper class with site-specific selectors.

---

### 2. Facebook Scraper (scan_mode=facebook)

```
UI (Facebook panel) → POST /api/action name=start_scan, scan_mode=facebook, fb_search_url=... or fb_group_urls=...
  → Main.java: runRealFbScan(params)
    → Builds URLs from fb_source_type (marketplace vs groups), fb_search_url, fb_group_urls
    → Invokes: python3 cold_bot/fb_scan.py --queue-path java_ui/data/fb_queue.csv --url <url1> ...
    → Waits for process, on success: FB_QUEUE.clear(); loadFbQueue(); scanState=idle

fb_scan.py flow:
  → Load config: limits.fb_* (fb_requests_per_minute=10, fb_delay_min=5, fb_delay_max=15, fb_max_urls_per_run=8, fb_max_scroll_depth=20)
  → Create Playwright context: random viewport (1200-1400 x 700-900), rotate_ua(), _apply_stealth()
  → FBMarketplaceScraper(config_fb).scrape(url, dry_run=True, page=page) for each URL (rate-limited)
  → Extract listing URLs from results
  → read_existing_queue(queue_path) → merge with dedup by URL → write_queue(queue_path)
```

**CSV schema (fb_queue.csv):** id, url, status, saved_at

**Anti-detection:** Stealth, longer delays (5–15s), 8–10 req/min cap, optional non-headless, max URLs per run, max scroll depth.

---

### 3. Interval Automation

```
Java main() → if SCRAPER_INTERVAL_MINUTES > 0:
  → ScheduledExecutorService.scheduleAtFixedRate every N minutes:
    → if scanState != "running":
      → readIntervalUrls() from data/interval_urls.txt (one URL per line)
      → Build params: start_urls=urls, scan_mode=website
      → runRealSiteScan(params, false)  [same as manual website scan]
```

**Config:** Env `SCRAPER_INTERVAL_MINUTES` (e.g. 5 or 10). File `data/interval_urls.txt` for URLs.

---

### 4. CSV and Frontend Preview

**Canonical CSVs:**
- `java_ui/data/leads.csv` — website scrapes
- `java_ui/data/fb_queue.csv` — Facebook scrapes

**Persistence:** site_scraper and fb_scan both append/merge with dedup by URL. Data persists across runs.

**API:**
- `GET /api/reload` — clears in-memory LEADS and FB_QUEUE, reloads from CSV (so preview is in sync)
- `GET /api/leads?limit=200&q=...` — returns leads (filtered)
- `GET /api/fbqueue?limit=200` — returns FB queue

**Frontend:** refreshLeads() and refreshFbQueue() call /api/reload first, then fetch /api/leads and /api/fbqueue. Polling every 5s (leads) and 6s (FB queue).

---

## Test Results

| Test | Result |
|------|--------|
| Source inference (athome.lu, nextimmo.lu, facebook) | OK |
| Scraper registry (get_scraper_for_source) | OK |
| site_scraper --help | OK |
| fb_scan --help | OK |
| CSV read/write and merge logic (read_existing_leads, write_leads) | OK |
| Java build | OK |
| Java server start | OK |
| GET /api/status | OK |
| GET /api/reload | OK |
| GET /api/leads | OK (returns leads from CSV) |
| GET /api/fbqueue | OK |
| Reload clears before re-load | Fixed (LEADS.clear(), FB_QUEUE.clear() before load) |

**Full browser scrape:** Not run (would require network and real sites; site_scraper with example.com timed out waiting for Playwright).

---

## How to Run Manual Tests

1. **Website scan:** Add URLs to Start URLs in UI (e.g. https://www.athome.lu/en/buy/), click Start Scan. Check java_ui/data/leads.csv for new rows.

2. **Facebook scan:** Set fb_search_url or fb_group_urls in UI, click Start Scan. Check java_ui/data/fb_queue.csv.

3. **Interval:** Add URLs to data/interval_urls.txt, run `SCRAPER_INTERVAL_MINUTES=10 java -cp out Main`. Logs will show "Scraper interval run" every 10 min.

4. **CSV preview:** After a scan or manual edit of leads.csv, click Refresh or wait 5s for poll. /api/reload ensures server reads latest from disk.
