# Test localhost (Java UI + real scrapers)

## 1. Reset and run

```bash
cd "/Users/karlodefinis/COLD BOT"
./run-and-test-localhost.sh
```

Then open **http://localhost:1111** in your browser.

Optional: run on another port:

```bash
./run-and-test-localhost.sh 9090
# Open http://localhost:9090
```

---

## 2. Optional: Python venv (for real scrapers)

If **Start Scan**, **Analyze Feed**, or **Send via Website Forms** fail with `No module named 'playwright'`:

```bash
cd cold_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

Then start the UI from a shell where that venv is active:

```bash
source cold_bot/.venv/bin/activate
./run-and-test-localhost.sh
```

---

## 3. Quick tests in the UI

- **Website**
  - **Start URLs**: e.g. `https://example.com`
  - **Listing selector**: `a` (for a quick test)
  - Click **Start Scan** → browser opens, one lead is added. Refresh the Leads table.
  - **Send via Website Forms**: add a message and limit, click → visits URLs and tries to submit a form (example.com has no form, so status will be “failed”).

- **Facebook**
  - **Analyze Feed**: set city (e.g. miami) or paste a group URL, click → browser opens and scrapes the feed. Refresh the FB queue table.
  - **Save URLs** = mock URLs only. **Send Messages (Browser)** uses the real `fb_messenger.py` script.

---

## 4. Test via curl (no browser)

With the UI running on port 1111:

```bash
# Start a website scan (runs in background)
curl -s -X POST "http://localhost:1111/api/action?name=start_scan" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "start_urls=https://example.com&listing_selector=a&site_headless=true"

# Response: {"ok":true,"message":"Website scan started (browser will open; refresh leads when done)"}
```

```bash
# Get leads (after scan finishes, ~10–15 s)
curl -s "http://localhost:1111/api/leads?limit=50"
```

```bash
# Get logs
curl -s "http://localhost:1111/api/logs?since=0"
```
