import argparse
import hashlib
import logging
import re
import signal
import sys
import time
from typing import Tuple

from silos.config_loader import ConfigLoader
from silos.browser_automation import init_browser, scroll_and_navigate, close_browser
from setup.phase1 import run_phase1
from setup.phase2 import run_phase2
from silos.data_scraper import extract_listings
from silos.llm_integration import (
    classify_eligible,
    extract_contact,
    generate_proposal,
    is_airbnb_viable,
)
from silos.email_sender import is_contacted, init_db, upsert_lead
from silos.contacting import send_all
from silos.analysis import agent_private_check, deduplicated, verify_qualifies, extract_agent_details
from silos.logging import init_leads_db, log_lead, log_agent_listing
from utils import random_delay, extract_contacts


def _parse_listing(text: str) -> Tuple[str, str, str]:
    title = text.splitlines()[0][:120] if text else "Listing"
    price_match = re.search(r"\$[\d,]+", text)
    price = price_match.group(0) if price_match else ""
    location_match = re.search(r"\b(?:near|in)\s+([A-Za-z\s]+)", text, re.IGNORECASE)
    location = location_match.group(1).strip() if location_match else ""
    return title, price, location


def _build_target_urls(config: dict) -> list[str]:
    urls: list[str] = []
    # Prefer phase2 output when source_type is set (config_loader already derived start_urls).
    if config.get("source_type"):
        urls.extend(config.get("start_urls") or [])
        return list(dict.fromkeys(urls))
    countries = config.get("countries") or []
    target_by_country = config.get("target_sites_by_country") or {}
    if countries and target_by_country:
        for country in countries:
            urls.extend(target_by_country.get(country, []))
    else:
        urls.extend(config.get("start_urls", []))
    fb_cfg = config.get("facebook", {})
    if fb_cfg.get("marketplace_enabled"):
        template = fb_cfg.get("marketplace_url_template", "")
        if template:
            for country in countries or []:
                slug = country.lower().replace(" ", "")
                urls.append(template.format(country=slug))
    groups_by_country = fb_cfg.get("groups_by_country", {})
    for country in countries or []:
        urls.extend(groups_by_country.get(country, []))
    return list(dict.fromkeys(urls))


def main(config_path: str, dry_run: bool = True) -> None:
    """Run the Cold Bot scanning loop. Use --setup to run phase1+phase2 and exit."""
    logging.basicConfig(filename="bot.log", level=logging.INFO)
    config = ConfigLoader.load_config(config_path)
    config["dry_run"] = dry_run
    # Initialise primary leads DB and separate logging tables.
    init_db(config["database"])
    init_leads_db(config["database"])
    playwright_instance, browser, context, page = init_browser(config.get("headless", True))
    def _shutdown(*_args):  # noqa: B008
        close_browser(playwright_instance, browser, context)
        sys.exit(0)
    signal.signal(signal.SIGINT, _shutdown)
    try:
        while True:
            cycle_start = time.time()
            session_set = set()
            viable_count = 0
            for url in _build_target_urls(config):
                scroll_and_navigate(
                    page,
                    url,
                    config["limits"]["scroll_depth"],
                    config["limits"]["delay_min"],
                    config["limits"]["delay_max"],
                )
                start = time.time()
                listings = extract_listings(page, config["selectors"]["listing"])
                for lst in listings:
                    text = lst["text"]
                    if deduplicated(text, config["database"], session_set):
                        continue
                    listing_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    eligible = classify_eligible(
                        text,
                        config["criteria"],
                        config["ollama_model"],
                        config.get("llm_provider", "ollama"),
                    ).get("eligible", False)
                    if not eligible:
                        continue
                    detection = agent_private_check(text, config)
                    contact = extract_contact(
                        text,
                        config["ollama_model"],
                        config.get("llm_provider", "ollama"),
                    )
                    extracted = extract_contacts(text)
                    email = extracted.get("email", "")
                    phone = extracted.get("phone", "")
                    if contact:
                        llm_email = contact.get("email", "")
                        llm_phone = contact.get("phone", "")
                        if llm_email and llm_email in lst["text"]:
                            email = llm_email
                        if llm_phone and llm_phone in lst["text"]:
                            phone = llm_phone
                    contact_value = email or phone
                    title, price, location = _parse_listing(text)
                    listing_url = lst.get("url", "")
                    viability = is_airbnb_viable(
                        text,
                        config.get("airbnb_criteria", ""),
                        config["ollama_model"],
                        config.get("llm_provider", "ollama"),
                    )
                    viable = viability.get("viable", False)
                    if viable:
                        viable_count += 1
                    upsert_lead(
                        config["database"],
                        title,
                        price,
                        location,
                        contact_value,
                        listing_url,
                        text,
                        viable,
                        viability.get("reason", ""),
                        int(viability.get("rating", 0) or 0),
                        str(viability.get("qualification_factors", [])),
                        "New",
                    )

                    # Private seller vs agent path
                    min_conf = (config.get("private_seller_detection") or {}).get("min_confidence", 6)
                    is_private = (
                        detection.get("is_private")
                        and (detection.get("confidence", 0) or 0) >= min_conf
                        and verify_qualifies(text)
                    )
                    if is_private:
                        airbnb_ok = config.get("airbnb_enabled", True) and (
                            int(viability.get("rating", 0) or 0) >= config.get("airbnb_min_rating", 6)
                        )
                        if not airbnb_ok:
                            try:
                                log_lead(
                                    listing_hash,
                                    {"email": email, "phone": phone},
                                    listing_url,
                                    detection,
                                    "skipped",
                                    None,
                                    None,
                                    db_path=config["database"],
                                )
                            except Exception:
                                pass
                        elif email and not is_contacted(config["database"], email):
                            proposal = generate_proposal(
                                text,
                                email,
                                config["ollama_model"],
                                config["email"]["from"],
                                config.get("llm_provider", "ollama"),
                            )
                            proposal_body = (proposal.get("body") or proposal.get("message") or "").strip() or str(proposal)
                            proposal_subject = proposal.get("subject") or config.get("message_templates", {}).get("email", {}).get("subject", "")
                            if config.get("manual_approve"):
                                print(proposal)
                                input("Approve send? Press Enter to send.")

                            contacts_payload = {"email": email, "emails": [email], "phone": phone}
                            message_payload = {"subject": proposal_subject, "body": proposal_body}
                            send_results = send_all(contacts_payload, message_payload, listing_url or "website", config)
                            any_success = any(r.get("success") for r in send_results)
                            status = "queued" if config.get("dry_run", True) else ("sent" if any_success else "failed")
                            try:
                                log_lead(
                                    listing_hash,
                                    {"email": email, "phone": phone},
                                    listing_url,
                                    detection,
                                    status,
                                    message_payload,
                                    "email",
                                    db_path=config["database"],
                                )
                            except Exception:
                                pass
                    else:
                        agent_details = extract_agent_details(text, config)
                        agent_details["url"] = agent_details.get("url") or listing_url
                        agent_details["reason"] = detection.get("reason", "") or agent_details.get("reason", "")
                        try:
                            log_agent_listing(agent_details, db_path=config["database"])
                        except Exception:
                            pass
                elapsed = time.time() - start
                if listings:
                    logging.info("Average per listing: %s", elapsed / len(listings))
            print(f"{viable_count} viable listing(s) identified that can be Airbnb'd")
            cooldown_sec = config["limits"].get("cycle_cooldown_seconds", 300)
            elapsed = time.time() - cycle_start
            if elapsed < cooldown_sec:
                time.sleep(cooldown_sec - elapsed)
            else:
                random_delay(config["limits"]["cooldown_min"], config["limits"]["cooldown_max"])
    except Exception:
        logging.exception("Cold Bot loop error")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cold Bot: FSBO real estate outreach.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--setup", action="store_true", help="Run phase1+phase2 then exit")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Do not send emails (default)")
    parser.add_argument("--live", action="store_true", help="Enable real send (implies not dry-run)")
    args = parser.parse_args()
    if args.setup:
        source_type = run_phase1(args.config)
        run_phase2(source_type, args.config)
        print("Setup complete. Run without --setup to start the scanning loop.")
        sys.exit(0)
    dry_run = not args.live
    main(args.config, dry_run=dry_run)
