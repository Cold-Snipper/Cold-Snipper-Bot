# Real Estate Outreach Bot (Local Reference)

This document captures the refined, production-oriented proposal for a fully automatic real-estate outreach bot (set-and-forget style) and is intended as a local, persistent reference for implementation and future iteration.

## Purpose
- Continuously browse public real estate listings
- Identify FSBO/owner listings that match criteria
- Extract contact details (email/phone)
- Generate personalized outreach using a local LLM
- Send emails/messages with strong anti-spam and compliance safeguards

## Purpose (Expanded Summary)
Cold Bot is an automated, privacy-focused, local-AI-powered cold outreach tool whose main
goal is to help a real estate agent or agency find and contact private sellers (FSBO) on
public online marketplaces (Facebook Marketplace, Craigslist, local classifieds, etc.) and
send them personalized partnership / listing takeover proposals via email.

### Core Objectives — ranked by importance
1. Find motivated private sellers automatically
   - Scroll listing feeds → identify owner listings → classify with local Llama
2. Extract contact information with almost no human intervention
   - Pull email/phone from listing text or seller snippets
3. Generate and send polite, personalized outreach emails
   - Offer help selling faster/for more, with no upfront costs
4. Run mostly hands-free ("set and forget")
   - Use config (locations, price hints, search URLs) and keep scanning
5. Stay local and private
   - All LLM decisions run via local Ollama
6. Minimize bans / reports
   - Stealth browsing, random delays, rate limits, optional manual approval

### In plain English — the dream end-state
You run:
`python main.py --config miami-homes.yaml`

Then 20–60 minutes later, you start receiving replies from owners who posted:
"House for sale by owner – $420k – text me"

…without manually scrolling, copying emails, or writing the same message 40 times.

### Local UI & Database (Testing)
A lightweight localhost UI (Java) exists for testing scan actions, monitoring output,
and managing a local leads database (`data/leads.csv`) before automating outreach.

### atHome.lu Test Scanner (Text-only)
For safe, local testing against atHome.lu, a simple scanner can pull listing
URLs and text fields (title, price, location, description, contact info) and
store them in SQLite. It deliberately does **not** save photos.

### CRM + Browser Outreach (Current Build)
The current build includes:
- A CRM-style dashboard for leads/clients (pipeline stages, automation toggles).
- A browser-driven outreach layer (Playwright):
  - FB Messenger send for queued URLs.
  - Website contact form submission for website leads.

## Operating Principles
- Low volume, human-like cadence
- Respect site ToS and public data boundaries
- Avoid duplicate contact or re-sending
- Prioritize safety, compliance, and explainability

## Core Stack (2026 Context)
- **Browser Automation:** Playwright (Python)
- **Stealth / Anti-Detection:** playwright-stealth or stealth plugins + randomized behavior
- **Local LLM:** Ollama + Llama 3.1/3.2
- **Storage:** SQLite for dedupe and history
- **Email:** SMTP (Gmail/Outlook app password) or `yagmail`

## Key Design Choices
- Playwright for modern JS-heavy sites (Facebook Marketplace)
- Randomized delays, human-like scrolling, and UA rotation
- Local LLM for classification + drafting to reduce API costs
- Modular architecture and prompt files for easy iteration

## Suggested Project Structure
```
project/
├── main.py              # CLI entry + infinite loop orchestrator
├── config.yaml          # URLs, criteria, email creds, limits
├── browser.py           # Playwright setup, stealth, scroll/navigate
├── scraper.py           # Site-specific: extract listings → parse → eligibility
├── llm.py               # Ollama calls: classify + generate email
├── sender.py            # SMTP email sending + logging
├── storage.py           # SQLite: contacted leads, history
└── prompts/             # .txt files for Llama prompts
```

## Main Loop (High-Level)
- Load config + prompts
- Launch Playwright with stealth context
- Iterate URLs
- Scroll, collect listing cards
- Filter + classify
- Extract contact
- Generate proposal
- Send email
- Log and sleep

## Pseudocode Snapshot
```
def main():
    config = load_config()
    model = "llama3.1"  # or 3.2
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=rotate_ua(),
        )
        page = context.new_page()
        while True:
            for url in config["start_urls"]:
                page.goto(url, wait_until="networkidle")
                scroll_and_collect(page, config, model)
            sleep_random(1800, 3600)

def scroll_and_collect(page, config, model):
    seen = set()
    for _ in range(30):
        cards = page.query_selector_all(config["listing_selector"])
        for el in cards:
            text = el.inner_text().lower()
            fingerprint = hash(text)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            if is_eligible(text, config["criteria"], model):
                contact = extract_contact(text, model)
                if contact and not already_contacted(contact):
                    proposal = generate_proposal(text, contact, model)
                    send_email(contact, proposal)
                    log_contacted(contact, proposal)
        human_scroll(page)
```

## Prompts (Templates)
### 1) Eligibility Classification
```
You are a real estate lead qualifier. Given this listing text: """{text}"""
Criteria: {criteria}
Output JSON only:
{"eligible": true/false, "reason": "...", "property_summary": "..."}
```

### 2) Contact Extraction
```
Extract any email or phone from this text: """{text}"""
Return JSON: {"email": "...", "phone": "..."} or null if none.
```

### 3) Proposal Generation
```
Write a short, polite email (150-220 words) proposing a real estate agency partnership.
From: Local licensed agent [Your Name/Agency]
To: Owner of {property_summary}
Key points: Compliment listing, offer help selling faster/higher price, no upfront fees.
Tone: friendly, professional. Include call-to-action.
Subject line first, then body.
```

## Configuration (Suggested `config.yaml` Keys)
- `start_urls`: list of search URLs
- `listing_selector`: CSS selector for listing cards
- `criteria`: eligibility rule text for LLM
- `max_actions_per_hour`: throttle limit
- `min_delay_seconds` / `max_delay_seconds`: random delays
- `email`: SMTP settings and sender identity
- `log_db_path`: SQLite file path

## Anti-Detection Checklist
- Randomized waits (5–45s)
- Mouse movement + scroll variability
- User-Agent rotation
- Headless vs. headed testing
- Proxy rotation optional (later)

## Safety / Compliance
- Public data only
- Respect ToS and privacy
- Avoid mass outreach
- Provide opt-out messaging if needed

## Incremental Build Steps
1. Prototype Craigslist (simpler HTML)
2. Add FB Marketplace scroll + selector tuning
3. Add Ollama classify + contact extraction
4. Add proposal generation
5. Add SQLite dedupe
6. Add SMTP send + logging

## Next Refinements
- Better prompt calibration and temperature tuning
- Add structured logging and observability
- Add account/proxy rotation hooks
- Add “dry-run mode” for testing

## Predevelopment Package (Cursor-Oriented Notes)
### Research Highlights
- Playwright v2.x+ stealth via `playwright-stealth` (patches webdriver, UA).
- Ollama Python v0.6.1 supports `format="json"` and structured outputs.
- Ethical FB Marketplace scraping: public data only, 3–12s delays, 8–12 req/min.
- `yagmail` supports OAuth2 (`oauth2_file="creds.json"`) or app passwords.

### Config Stub (Baseline)
```
start_urls:
  - "https://www.facebook.com/marketplace/[city]/propertyforsale?query=owner"
criteria: "FSBO, owner selling, no agent, home for sale"
ollama:
  model: "qwen3"
email:
  from: "youragency@gmail.com"
  app_password: "your_app_pw"
  smtp_host: "smtp.gmail.com"
limits:
  max_contacts_per_hour: 5
  scroll_depth: 30
  delay_min: 3
  delay_max: 12
selectors:
  listing: '[data-testid="marketplace_feed_card"]'
database: "leads.db"
```

### Prompt Targets
1. Add proxy rotation, keep login manual-only.
2. Qwen3 prompts with strict JSON parsing retries.
3. Main loop: 3–12s delay, max 5/hour, SQLite logging.
4. `yagmail` with retries and OAuth2 fallback.

## Development Plan (Modular Silos)
### Integration Strategy
- Central `main.py` orchestrates all silos
- Data flow: Config → Browser → Scraper → LLM → Sender → Storage
- Testing pyramid: unit → integration → end-to-end
- Dependencies shared via `requirements.txt`
- Build sequence: silos 1–5, then integrate in silo 6

### Silo 1: Configuration Loader
- YAML load + schema validation
- Exports `load_config(path) -> dict`
- PyYAML dependency

### Silo 2: Browser Automation
- Playwright init + stealth + scroll
- Inputs: URL, depth, delay range

### Silo 3: Data Extraction/Scraping
- Extract listing text and hashes from selectors
- Optional BeautifulSoup fallback

### Silo 4: LLM Integration
- Ollama classify + contact extraction + proposal
- Strict JSON output with retry

### Silo 5: Email Sender & Logging
- `yagmail` send + SQLite dedupe/log

### Silo 6: Main Orchestrator
- Loop: navigate → scrape → classify → send/log → cooldown
