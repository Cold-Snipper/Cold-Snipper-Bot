# Cold Bot – What’s Missing (Code Analysis)

Summary of gaps between the current codebase and the intended workflow. Fix these for a complete, production-style run.

---

## 1. Setup not wired into main

- **Phase 1 & 2** exist in `setup/phase1.py` and `setup/phase2.py` but are **never called** from `main.py`.
- There is no `--setup` (or similar) flow that runs phase1 then phase2 before the scan loop.
- **Impact**: User must run setup manually; config may lack `source_type` and the phase2 structure.

**Suggested fix**: In `main.py`, if `config.get("source_type")` is missing, call `run_phase1(config_path)` then `run_phase2(source_type, config_path)`, reload config, then continue. Or add `argparse --setup` that runs both and exits.

---

## 2. Main ignores phase1/phase2 URL output

- `_build_target_urls(config)` only uses:
  - `start_urls`, `countries`, `target_sites_by_country`
  - `facebook.marketplace_enabled`, `marketplace_url_template`, `facebook.groups_by_country`
- It **does not** use:
  - `config["source_type"]`
  - `config["websites"][i]["generated_urls"]`
  - `config["facebook"]["marketplace"]["generated_urls"]` or `config["facebook"]["groups"]["group_urls"]`
- **Impact**: URLs produced by phase2 are never used; scanning still relies on the old config shape.

**Suggested fix**: In `_build_target_urls`, if `config.get("source_type")` is set, build URL list from `websites[].generated_urls` and `facebook.marketplace.generated_urls` / `facebook.groups.group_urls`. Fall back to current logic when `source_type` is absent.

---

## 3. Config validation doesn’t support phase2-only config

- `ConfigLoader.validate_config()` **requires** `start_urls`.
- A config written only by phase1+phase2 has `source_type`, `websites`, `facebook` and may have **no** `start_urls`.
- **Impact**: Loading a phase2-only config raises `ValueError("Missing required key: start_urls")`.

**Suggested fix**: In validation, require either `start_urls` or the presence of `source_type` plus at least one of `websites` or `facebook` with non-empty URL lists. When `source_type` is present, derive or allow empty `start_urls`.

---

## 4. No persistent deduplication

- `listing_hash` is computed per listing but **never checked** against the DB or any persistent store before processing.
- **Impact**: The same listing can be processed (and e.g. emailed) again on the next run or next cycle.

**Suggested fix**: Before the per-listing logic, check if `listing_hash` exists in `lead_logs` (or a dedicated `seen_hashes` table). Skip the listing if already processed. Optionally keep an in-memory set for the current run to avoid duplicate work inside one cycle.

---

## 5. contacting.send_all never used

- `silos/contacting.send_all()` implements email + stubs for WhatsApp, form, FB Marketplace, FB Group.
- **main.py** only uses `silos.email_sender.send_email()` directly.
- **Impact**: Multi-channel logic and dry-run behaviour in `send_all` are unused; no single place to add form/FB/WhatsApp later.

**Suggested fix**: In main, for private leads with contacts, build `contacts` dict and `message` dict, then call `contacting.send_all(contacts, message, source, config)` (with `config.dry_run` respected inside `send_all`). Remove the direct `send_email` + `log_contact` block and let `send_all` return results; then log via `log_lead` using those results.

---

## 6. Logging DB path not configurable

- `silos/logging.py` uses **hardcoded** `DB_PATH = "leads.db"`.
- `main.py` and `email_sender` use `config["database"]` (e.g. `path/to/leads.db`).
- **Impact**: Lead/agent logs can end up in a different file than the rest of the app (e.g. `leads.db` in cwd vs configured path).

**Suggested fix**: Pass `config["database"]` (or a dedicated `logging_db` key) into `init_leads_db(db_path)` and `log_lead(..., db_path=...)` / `log_agent_listing(..., db_path=...)`, or read from config inside the logging module. Use one DB path for the whole app unless you explicitly want separate DBs.

---

## 7. No Airbnb viability gate

- `is_airbnb_viable()` is called and the result is stored in `upsert_lead`, but there is **no check** that viability is above a threshold before contacting.
- **Impact**: Low-viability leads can still get outreach; design said “if &lt; threshold, skip”.

**Suggested fix**: Add e.g. `airbnb_min_rating` or `airbnb_min_viable` in config. For private leads, only run contact + send when `viability.get("viable")` and e.g. `int(viability.get("rating", 0)) >= config.get("airbnb_min_rating", 0)` (or equivalent). Otherwise log and skip sending.

---

## 8. No private-seller confidence threshold

- `agent_private_check()` returns `confidence` (0–10), but **main** does not compare it to a config minimum.
- **Impact**: Low-confidence “private” classifications can still trigger outreach.

**Suggested fix**: Add e.g. `private_seller_detection.min_confidence` in config. Only treat as private and run contact/send when `detection.get("confidence", 0) >= config.get("private_seller_detection", {}).get("min_confidence", 6)` (or similar). Otherwise treat as “unclear” and e.g. log only, or skip.

---

## 9. Agent details are stub-only

- For agents, `agent_details["agency_name"]` is set to the literal **"Extracted from text"**.
- **Impact**: Agents list and XLS have no real agency name or structured data.

**Suggested fix**: Add a small LLM call or regex/pattern step (e.g. in `analysis.py` or a dedicated helper) to extract agency name, phone, etc. from listing text when `is_private` is false. Fill `agent_details` from that instead of fixed strings.

---

## 10. Email subject from LLM not used when sending

- `generate_proposal()` returns `subject` and `body`; main now passes `proposal_body` to `send_email`.
- **email_sender.send_email()** uses a **hardcoded** subject: `"Real Estate Partnership Proposal"`.
- **Impact**: Custom subject from the LLM is only stored in logs, not sent.

**Suggested fix**: Add a `subject` parameter to `send_email(..., subject=None)` and use it when present; otherwise keep the current default. In main, pass `proposal_subject` into `send_email`.

---

## 11. Playwright instance never stopped

- `browser_automation.init_browser()` calls `sync_playwright().start()` but does not store or return the Playwright instance.
- `close_browser()` only calls `context.close()` and `browser.close()`.
- **Impact**: The Playwright driver process may not exit cleanly; possible hang or leftover process.

**Suggested fix**: Return the Playwright instance (e.g. `return p, browser, context, page`) and in `close_browser` (or a new `stop_playwright(p)`) call `p.stop()` after closing browser/context. Main then stores and passes `p` and calls stop on shutdown.

---

## 12. Optional: cycle cooldown and rate limit visibility

- Cooldown is implemented as `random_delay(cooldown_min, cooldown_max)` after the URL loop.
- There is no explicit “cycle start time” or “wait until cycle_cooldown_seconds since cycle start” as in the design.
- **Impact**: Behaviour is “random delay between cycles”; strict cycle_cooldown_seconds is not enforced. Usually acceptable; document or tighten if you need exact timing.

**Suggested fix** (optional): Record cycle start time; at the start of the next cycle, sleep for `max(0, cycle_cooldown_seconds - elapsed)` before building URLs. Optionally expose “last cycle duration” or “next cycle in” in logs/UI.

---

## Quick checklist

| # | Item | Severity |
|---|------|----------|
| 1 | Wire setup (phase1/phase2) into main or --setup | High |
| 2 | Use phase2 URLs in _build_target_urls | High |
| 3 | Config validation for phase2-shaped config | Medium |
| 4 | Persistent dedup (listing_hash in DB) | High |
| 5 | Use contacting.send_all in main | Medium |
| 6 | Configurable DB path for logging silo | Medium |
| 7 | Airbnb viability gate before send | Medium |
| 8 | Confidence threshold for private | Low |
| 9 | Real agent extraction (LLM/regex) | Low |
| 10 | Pass LLM subject into send_email | Low |
| 11 | Stop Playwright instance on exit | Low |
| 12 | Strict cycle cooldown (optional) | Low |

Implementing 1, 2, 4, and 6 will align the run with the intended workflow and avoid duplicate sends and config/DB mismatch. The rest improve correctness, safety, and observability.
