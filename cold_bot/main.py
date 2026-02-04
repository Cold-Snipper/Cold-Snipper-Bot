import argparse
import logging
import re
import signal
import time
from typing import Tuple

from silos.config_loader import ConfigLoader
from silos.browser_automation import init_browser, scroll_and_navigate, close_browser
from silos.data_scraper import extract_listings
from silos.llm_integration import (
    classify_eligible,
    extract_contact,
    generate_proposal,
    is_airbnb_viable,
)
from silos.email_sender import (
    is_contacted,
    log_contact,
    send_email,
    init_db,
    upsert_lead,
)
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


def main(config_path: str) -> None:
    """Description.

    Args:
        config_path (type): desc.

    Returns:
        type: desc.

    Raises:
        exc: when.
    """
    logging.basicConfig(filename="bot.log", level=logging.INFO)
    config = ConfigLoader.load_config(config_path)
    init_db(config["database"])
    browser, context, page = init_browser(config.get("headless", True))
    signal.signal(signal.SIGINT, lambda *_: close_browser(browser, context))
    try:
        while True:
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
                    eligible = classify_eligible(
                        lst["text"],
                        config["criteria"],
                        config["ollama_model"],
                        config.get("llm_provider", "ollama"),
                    ).get("eligible", False)
                    if not eligible:
                        continue
                    contact = extract_contact(
                        lst["text"],
                        config["ollama_model"],
                        config.get("llm_provider", "ollama"),
                    )
                    extracted = extract_contacts(lst["text"])
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
                    title, price, location = _parse_listing(lst["text"])
                    listing_url = lst.get("url", "")
                    viability = is_airbnb_viable(
                        lst["text"],
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
                        lst["text"],
                        viable,
                        viability.get("reason", ""),
                        int(viability.get("rating", 0) or 0),
                        str(viability.get("qualification_factors", [])),
                        "New",
                    )
                    if email and not is_contacted(config["database"], email):
                        proposal = generate_proposal(
                            lst["text"],
                            email,
                            config["ollama_model"],
                            config["email"]["from"],
                            config.get("llm_provider", "ollama"),
                        )
                        if config.get("manual_approve"):
                            print(proposal)
                            input("Approve send? Press Enter to send.")
                        if send_email(
                            email,
                            proposal,
                            config["email"]["from"],
                            config["email"]["app_password"],
                            config["email"]["smtp_host"],
                            config["database"],
                            config["limits"]["max_contacts_per_hour"],
                        ):
                            log_contact(config["database"], email, "success")
                elapsed = time.time() - start
                if listings:
                    logging.info("Average per listing: %s", elapsed / len(listings))
            print(f"{viable_count} viable listing(s) identified that can be Airbnb'd")
            random_delay(config["limits"]["cooldown_min"], config["limits"]["cooldown_max"])
    except Exception:
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    main(args.config)
