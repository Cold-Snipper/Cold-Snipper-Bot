import hashlib
import random
import time
from typing import Dict, Any

import yaml

from browser import init_browser, scroll_page, ensure_fb_session
from llm import is_eligible, extract_contact, generate_proposal
from sender import send_email
from storage import init_db, already_contacted, log_contacted, count_contacts_since


def _load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _within_limits(conn, limits) -> bool:
    one_hour_ago = int(time.time()) - 3600
    recent_count = count_contacts_since(conn, one_hour_ago)
    return recent_count < int(limits["max_contacts_per_hour"])


def main() -> None:
    config = _load_config()
    limits = config["limits"]
    selectors = config["selectors"]
    criteria = config["criteria"]
    model = config["ollama"]["model"]
    email_cfg = config["email"]

    conn = init_db(config["database"])
    p, browser, context, page = init_browser(config, headless=True)
    allow_manual_login = bool(config.get("facebook", {}).get("allow_manual_login", False))
    if allow_manual_login:
        ensure_fb_session(page, config, require_public_only=False)

    try:
        while True:
            for url in config["start_urls"]:
                if not _within_limits(conn, limits):
                    time.sleep(60)
                    continue

                page.goto(url, wait_until="networkidle")
                scroll_page(
                    page,
                    depth=int(limits["scroll_depth"]),
                    delay_min=int(limits["delay_min"]),
                    delay_max=int(limits["delay_max"]),
                )

                cards = page.query_selector_all(selectors["listing"])
                for card in cards:
                    if not _within_limits(conn, limits):
                        break

                    try:
                        text = card.inner_text().strip()
                    except Exception:
                        continue

                    if not text:
                        continue

                    listing_hash = _hash_text(text.lower())
                    if is_eligible(text, criteria, model=model):
                        contact = extract_contact(text, model=model)
                        email = contact.get("email")
                        if not email:
                            continue
                        if already_contacted(conn, email):
                            continue

                        proposal = generate_proposal(text, model=model)
                        send_email(
                            to_email=email,
                            subject=proposal["subject"],
                            body=proposal["body"],
                            from_email=email_cfg["from"],
                            app_password=email_cfg["app_password"],
                            oauth2_file=email_cfg.get("oauth2_file") or None,
                        )
                        log_contacted(conn, email, listing_hash, int(time.time()))

                    time.sleep(random.randint(int(limits["delay_min"]), int(limits["delay_max"])))

                time.sleep(random.randint(int(limits["delay_min"]), int(limits["delay_max"])))

            time.sleep(int(limits["cycle_cooldown_seconds"]))
    finally:
        context.close()
        browser.close()
        p.stop()


if __name__ == "__main__":
    main()
