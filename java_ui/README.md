# Localhost Java UI

Java-based localhost UI for Cold Bot: scan controls, logs, and local leads (CSV-backed). The UI runs Python scripts in `../cold_bot/` for website scan, FB analyze, and messaging.

## Quick start (from repo root)

Best option: run from the repo root so the script injects the Cold Bot venv into `PATH` for spawned Python:

```bash
# From repo root (not from java_ui/)
./run-and-test-localhost.sh
```

Then open **http://localhost:1111**. Scans will use `cold_bot/.venv` automatically.

## Build and run (from java_ui/)

```bash
cd java_ui
./build.sh
java -cp out Main
```

Then open **http://localhost:1111**. For scans to work, `python3` must have Playwright and deps: either activate `../cold_bot/.venv` first or run with `PATH="../cold_bot/.venv/bin:$PATH" java -cp out Main`.

Override port via env or arg:

```bash
PORT=9090 java -cp out Main
# or: java -cp out Main 9090
```

**Scraper with backend (optional):** So the scraper runs as soon as the backend is up:

- **One run on start:** Set `SCRAPER_RUN_ON_START=true`. One website scrape runs 10 seconds after server start (uses `data/interval_urls.txt`).
- **Interval:** Set `SCRAPER_INTERVAL_MINUTES` (e.g. 5 or 10) and add one URL per line in `data/interval_urls.txt`. First run is 10 seconds after start, then every N minutes.

```bash
SCRAPER_RUN_ON_START=true java -cp out Main
SCRAPER_INTERVAL_MINUTES=10 java -cp out Main
```

## Notes

- UI is served from `static/`.
- Local DB (CSV) is stored at `data/leads.csv` and `data/fb_queue.csv`. The frontend reads via `/api/leads` and `/api/fbqueue`; each refresh calls `/api/reload` so the table always shows the latest CSV data. When a scan is running, status is polled every 1.5s and leads/FB queue are refreshed so new data appears as soon as the scan finishes.
- **Scan mode:** Start Scan uses `scan_mode` from the active panel (Website Bot vs Facebook). Website mode runs `site_scraper.py` (Luxembourg and other silo scrapers); Facebook mode runs `fb_scan.py` (anti-detection limits).
- API endpoints:
  - `POST /api/action?name=start_scan` (body: `scan_mode=website|facebook`, `start_urls=...` or FB params)
  - `GET /api/reload` — reload leads and FB queue from CSV
  - `POST /api/action?name=test_single_page`
  - `POST /api/action?name=mark_contacted` (form body `ids=1,2,3`)
  - `POST /api/action?name=export_csv`
  - `POST /api/action?name=backup_db`
  - `POST /api/action?name=clear_database`
  - `POST /api/action?name=clear_logs`
  - `GET /api/status`
  - `GET /api/logs?since=0`
  - `GET /api/leads?limit=200&q=miami`
