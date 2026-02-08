# Cold Bot – Current Behavior (Local Build)

This document describes how the Cold Bot works **right now** in this workspace.

## What It Does Today

### 1) Localhost UI (Java)
The system runs a Java-based localhost UI at `http://localhost:8080`.  
It is a **testing console** that lets you:
- Configure scan parameters for **Website Scrape** or **FB Marketplace**.
- Run simulated scans and queue URLs.
- Trigger **browser-driven outreach** (forms + Messenger).
- Manage a CRM-style pipeline: clients, communications, stages, and automation.

### 2) Website Scrape (Real)
The Website Scrape mode uses **real** Playwright scraping via `cold_bot/site_scraper.py`.  
When you click **Start Scan** or **Test Single Page**, a browser opens, loads the start URL(s), scrolls and extracts listing links; new leads are appended to:
- `java_ui/data/leads.csv`

No simulation. Data feed follows the stage plan (config → browser_automation → data_scraper → leads).

### 3) FB Marketplace Flow (Real)
The FB flow is **real only** (stage plan):
1. **Analyze Feed**: runs `cold_bot/fb_feed_analyzer.py` (Playwright), loads Marketplace or Group URL(s), and appends listing links to:
   - `java_ui/data/fb_queue.csv`
2. **Save URLs** (mock) has been removed; only Analyze Feed adds FB URLs.

You can mark items contacted or clear the queue.  
**Send Messages (Browser)** runs `cold_bot/fb_messenger.py` (Playwright) to message queued URLs when a logged-in FB storage state exists.

### 4) Website Form Outreach (Real Browser Automation)
The UI can trigger browser automation to submit **website contact forms**
for leads listed in `java_ui/data/leads.csv`.  
This uses Playwright to detect a message field + submit button and then
marks leads as `contacted` or `failed`.

### 5) CRM (Client Communications Tab)
A CRM-style workspace exists in the **Client Communciations** tab:
- Summary dashboard (total leads, viable leads, conversion, automation)
- Filters and tabs (All / Website / FB)
- CRM grid with automation toggles
- Client detail panel (unique panel per lead)
- Communication log tied to the selected client

Client data is stored locally in:
- `java_ui/data/clients.csv`  
Communications are stored in:
- `java_ui/data/communications.csv`

## Data Model (Current)

### Clients (CSV)
Stored in `java_ui/data/clients.csv` with fields:
- `id`, `name`, `email`, `phone`
- `status`, `stage`, `source`
- `source_type`, `outreach_channel`
- `automation_enabled`, `viability_score`
- `last_contacted_at`, `last_interaction`, `notes`

### Communications (CSV)
Stored in `java_ui/data/communications.csv` with fields:
- `id`, `contact_name`, `contact_email`, `contact_phone`
- `channel`, `last_message`, `status`
- `last_contacted_at`, `notes`, `client_id`

### FB Queue (CSV)
Stored in `java_ui/data/fb_queue.csv` with fields:
- `id`, `url`, `status`, `saved_at`

### Scripts (Browser Automation)
- `cold_bot/fb_messenger.py` (send FB Messenger messages via Playwright)
- `cold_bot/site_forms.py` (submit website contact forms via Playwright)

## What Is Real vs. Mock

**Real (no simulation):**
- Local UI and API routing
- Local CSV persistence
- Website scan (site_scraper.py → leads.csv)
- FB feed analysis (fb_feed_analyzer.py → fb_queue.csv)
- Browser-driven outreach (site_forms.py, fb_messenger.py)
- CRM workflow and client panel behaviors
- Data feed: real-time stream from scans only

**Removed:** All mock/simulation (Lead.mock, FbQueueItem.mock, saveFbUrls mock, simulateAction, simulateScan). Data feeds are hooked to the stage plan (config → browser_automation → data_scraper / feed analyzer).

## How To Run

```bash
cd "/Users/karlodefinis/COLD BOT/java_ui"
/opt/homebrew/opt/openjdk/bin/javac -d out src/Main.java
/opt/homebrew/opt/openjdk/bin/java -cp out Main
```

Open `http://localhost:8080`.

## Next Upgrade Paths (Planned)
- Wire Website Scrape UI to real Playwright scraping + local SQLite.
- Wire FB flow to Playwright with logged-in session and URL capture.
- Add LLM-based qualification & contact extraction.
- Add richer per-site form adapters and safety controls.
