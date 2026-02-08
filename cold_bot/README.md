# Cold Bot

Cold Bot is an automated, privacy-focused, local-AI-powered cold outreach tool for real estate.
Its primary purpose is to find private sellers (FSBO) on public marketplaces, extract contact
details, and send respectful, personalized partnership proposals — all while keeping data local.

## Core Objectives (in order)
- Automatically discover motivated private sellers on public listing sites
- Extract contact info with minimal human intervention using local LLMs
- Generate polite, personalized outreach emails (no spam)
- Run mostly hands-free from a config file with strong rate limits
- Stay local and private (Ollama / local LLMs only)
- Minimize bans with stealth browsing and conservative outreach limits

## Usage
`python main.py --config config.yaml`

## Local Test UI
For a lightweight localhost UI to test scanning, database controls, and logs,
see `java_ui/README.md`.

## atHome.lu Test Scan
For a minimal test scan against atHome.lu that stores text-only listings
in a local SQLite DB (no photos):

`python athome_scan.py --start-url "https://www.athome.lu/en/apartment" --limit 10 --db listings.db`

## Real Scrapers & Outreach (Playwright)
The Java UI triggers these Python scripts (run from repo root with `cold_bot` as CWD for the UI, or set `PATH=cold_bot/.venv/bin:$PATH` so `python3` has Playwright):

- **Website scan**: `site_scraper.py` — opens start URL(s), scrolls, extracts listing links/cards, appends to `java_ui/data/leads.csv`.
- **FB feed analyze**: `fb_feed_analyzer.py` — opens Marketplace/Group URL(s), extracts listing links, appends to `java_ui/data/fb_queue.csv`.
- **FB Messenger**: `fb_messenger.py` — sends messages to queued FB listing URLs.
- **Website Forms**: `site_forms.py` — visits lead URLs and submits the message in the first contact form found.

Recommended: use a venv and install Playwright so the UI’s `python3` can run them:

```bash
cd cold_bot && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python -m playwright install chromium
```
