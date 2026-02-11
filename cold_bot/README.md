# Cold Bot (backend)

Automated, privacy-focused, local-AI cold outreach for real estate: find FSBO listings, extract contacts, send proposals. Data stays local.

## Quick start

```bash
# One-time: venv + deps (from cold_bot/)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && python -m playwright install chromium

# Health check
python main.py --config config.yaml --check

# Setup then run scan loop (dry-run)
python main.py --config config.yaml --setup
python main.py --config config.yaml
```

Use `--live` to enable real sends. Use the **repo root** `run-and-test-localhost.sh` to run the Java UI with this backend.

## Run modes

| Mode | Command |
|------|--------|
| Health check | `python main.py --config config.yaml --check` |
| Setup (phase1 + phase2) | `python main.py --config config.yaml --setup` |
| Scan loop (dry-run) | `python main.py --config config.yaml` |
| Scan loop (live) | `python main.py --config config.yaml --live` |

Run from `cold_bot/` or from repo root via `python main.py` (root script forwards here).

## Core Objectives (in order)
- Automatically discover motivated private sellers on public listing sites
- Extract contact info with minimal human intervention using local LLMs
- Generate polite, personalized outreach emails (no spam)
- Run mostly hands-free from a config file with strong rate limits
- Stay local and private (Ollama / local LLMs only)
- Minimize bans with stealth browsing and conservative outreach limits

## Usage
`python main.py --config config.yaml`

- **Health check:** `python main.py --config config.yaml --check` — verifies config, DB, and exits 0/1.
- **Setup (phase1 + phase2):** `python main.py --config config.yaml --setup` — then run without `--setup` to start the scan loop.

### Supported sources (auto-detected from URL)
- **atHome** (athome.lu)
- **Immotop**
- **Rightmove** (rightmove.co.uk)
- **Facebook Marketplace / Groups**

### Config options (in `config.yaml`)
- **limits.parallel_urls** (default `1`, max 3): scrape multiple scraper URLs in parallel, each with its own browser.
- **limits.requests_per_minute**: per-domain rate limit (default `30`).
- **target_sites_by_country**: add URLs per country; use `UK` and Rightmove URLs to scrape UK listings.

## Local Test UI
For a lightweight localhost UI to test scanning, database controls, and logs,
see `java_ui/README.md`.

## atHome.lu Test Scan
For a minimal test scan against atHome.lu that stores text-only listings
in a local SQLite DB (no photos):

`python athome_scan.py --start-url "https://www.athome.lu/en/apartment" --limit 10 --db listings.db`

## Real Scrapers & Outreach (Playwright — no simulation)
All four tools use a real browser (Playwright/Chromium), real HTTP navigation, and real DOM/form interaction. No mocks or stubs.

| Tool | What it does (real behavior) |
|------|------------------------------|
| **site_scraper.py** | Launches browser, navigates to each start URL (60s timeout, retry once), scrolls to trigger dynamic content, waits for listing selector if present, extracts cards via `data_scraper.extract_listings`, parses price/location/bedrooms/size/listing_type/contacts, appends new rows to `leads.csv`. |
| **fb_feed_analyzer.py** | Launches browser (optional `--storage-state` for logged-in FB), navigates to Marketplace/Group URL(s), waits for feed selector (15s), scrolls, extracts listing links, appends to `fb_queue.csv`. Skips URL on load failure and continues. |
| **site_forms.py** | Loads pending leads from `leads.csv`, opens each URL (networkidle then fallback domcontentloaded, 30s timeout, retry once), finds message/comment field (textarea/input by name, placeholder, aria-label), fills message, submits via form-scoped submit button or generic submit; updates status contacted/failed and saves CSV. |
| **fb_messenger.py** | Requires logged-in session (`storage_state` from config or `fb_storage_state.json`). Loads queued URLs from `fb_queue.csv`, navigates to each (30s timeout), clicks Message, finds contenteditable message box, fills text, clicks Send (aria-label/button) or presses Enter; updates status and saves CSV. |

The Java UI triggers these scripts; ensure `python3` has Playwright (`PATH=cold_bot/.venv/bin:$PATH` or install globally).

Recommended: use a venv and install Playwright so the UI’s `python3` can run them:

```bash
cd cold_bot && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium
```
