import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List

import yaml
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def load_config_storage_state(config_path: Path) -> Path | None:
    if not config_path.exists():
        return None
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    storage = (
        data.get("facebook", {}).get("storage_state")
        if isinstance(data, dict)
        else None
    )
    if not storage:
        return None
    storage_path = (config_path.parent / storage).resolve()
    return storage_path if storage_path.exists() else None


def load_queue(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def save_queue(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = ["id", "url", "status", "saved_at"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def find_message_box(page):
    selectors = [
        "div[role='textbox'][contenteditable='true']",
        "div[contenteditable='true'][aria-label*='Message']",
        "div[contenteditable='true'][aria-label*='message']",
        "textarea",
    ]
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=2000):
                return locator
        except PlaywrightTimeoutError:
            continue
    return None


def click_message_button(page) -> bool:
    candidates = [
        "text=Message",
        "text=Send message",
        "text=Send Message",
        "button:has-text('Message')",
        "[aria-label*='Message']",
    ]
    for selector in candidates:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=2000):
                locator.click()
                return True
        except PlaywrightTimeoutError:
            continue
    return False


def send_message(page, message: str) -> bool:
    if not click_message_button(page):
        return False
    box = find_message_box(page)
    if box is None:
        return False
    box.click()
    box.fill(message)
    box.press("Enter")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue-path", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--config", default=None)
    parser.add_argument("--delay", type=float, default=2.5)
    args = parser.parse_args()

    queue_path = Path(args.queue_path).resolve()
    rows = load_queue(queue_path)
    pending = [row for row in rows if row.get("status", "") == "queued"]
    if not pending:
        print("No queued URLs found.")
        return 0

    root = Path(__file__).resolve().parents[1]
    config_path = Path(args.config).resolve() if args.config else root / "config.yaml"
    storage_state = load_config_storage_state(config_path) if config_path else None
    if storage_state is None:
        fallback = root / "fb_storage_state.json"
        storage_state = fallback if fallback.exists() else None

    if storage_state is None:
        print("No storage state found. Login required.", file=sys.stderr)
        return 1

    to_send = pending[: max(1, args.limit)]
    print(f"Sending {len(to_send)} messages via Playwright...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context(storage_state=str(storage_state))
        page = context.new_page()
        for row in to_send:
            url = row.get("url", "")
            if not url:
                continue
            try:
                page.goto(url, wait_until="domcontentloaded")
                ok = send_message(page, args.message)
                row["status"] = "contacted" if ok else "failed"
            except Exception:
                row["status"] = "failed"
            time.sleep(args.delay)
        context.close()
        browser.close()

    save_queue(queue_path, rows)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
