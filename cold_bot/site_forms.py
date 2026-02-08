"""
Real website contact form submitter (no simulation).
- Playwright: real browser, real page load (networkidle or domcontentloaded), real form fill/submit.
- Loads leads from CSV, visits each pending lead URL, finds message/comment field (multiple
  selectors including placeholder/aria-label), fills message, submits via form-scoped button or Enter.
- Retries each URL once (networkidle then domcontentloaded). Updates status to contacted/failed, saves CSV.
"""
import argparse
import csv
import sys
import time
from pathlib import Path
from typing import Dict, List

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


FORM_SELECTORS = [
    "form",
]

MESSAGE_SELECTORS = [
    "textarea",
    "textarea[name*='message' i]",
    "textarea[name*='comment' i]",
    "textarea[placeholder*='message' i]",
    "textarea[placeholder*='comment' i]",
    "textarea[data-placeholder*='message' i]",
    "textarea[aria-label*='message' i]",
    "textarea[aria-label*='comment' i]",
    "input[name*='message' i]",
    "input[name*='comment' i]",
    "input[placeholder*='message' i]",
    "input[aria-label*='message' i]",
]

SUBMIT_SELECTORS = [
    "button[type='submit']",
    "button:has-text('Send')",
    "button:has-text('Submit')",
    "button:has-text('Contact')",
    "input[type='submit']",
]


def load_leads(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def save_leads(path: Path, rows: List[Dict[str, str]]) -> None:
    fieldnames = [
        "id",
        "url",
        "title",
        "description",
        "price",
        "location",
        "bedrooms",
        "size",
        "listing_type",
        "contact_email",
        "contact_phone",
        "scan_time",
        "status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def find_message_input(page):
    for selector in MESSAGE_SELECTORS:
        locator = page.locator(selector).first
        try:
            if locator.is_visible(timeout=2000):
                return locator
        except PlaywrightTimeoutError:
            continue
    return None


def click_submit(page, within_form=None) -> bool:
    scope = within_form if within_form is not None else page
    for selector in SUBMIT_SELECTORS:
        locator = scope.locator(selector).first
        try:
            if locator.is_visible(timeout=2000):
                locator.click()
                return True
        except PlaywrightTimeoutError:
            continue
    return False


def attempt_form_submit(page, message: str) -> bool:
    message_input = find_message_input(page)
    if message_input is None:
        return False
    message_input.click()
    message_input.fill(message)
    try:
        form = message_input.locator("xpath=ancestor::form")
        if form.count() > 0:
            return click_submit(page, within_form=form.first) or click_submit(page)
    except Exception:
        pass
    return click_submit(page)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leads-path", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--delay", type=float, default=2.5)
    args = parser.parse_args()

    leads_path = Path(args.leads_path).resolve()
    rows = load_leads(leads_path)
    pending = [row for row in rows if row.get("status", "") in ("", "new", "queued")]
    if not pending:
        print("No pending leads found.")
        return 0

    to_send = pending[: max(1, args.limit)]
    print(f"Submitting forms for {len(to_send)} leads...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(30_000)
        for row in to_send:
            url = row.get("url", "")
            if not url:
                continue
            ok = False
            for attempt in range(2):
                try:
                    page.goto(url, wait_until="networkidle", timeout=30_000)
                    time.sleep(1.0)
                    ok = attempt_form_submit(page, args.message)
                    if ok:
                        break
                except Exception as e:
                    if attempt == 0:
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                            time.sleep(1.0)
                            ok = attempt_form_submit(page, args.message)
                        except Exception:
                            pass
                    if not ok:
                        row["status"] = "failed"
                        print(f"failed: {url[:80]}{'...' if len(url) > 80 else ''} ({e})", flush=True)
                        break
            if ok:
                row["status"] = "contacted"
                print(f"contacted: {url[:80]}{'...' if len(url) > 80 else ''}", flush=True)
            else:
                row["status"] = "failed"
                print(f"failed: {url[:80]}{'...' if len(url) > 80 else ''} (no form found)", flush=True)
            time.sleep(args.delay)
        context.close()
        browser.close()

    save_leads(leads_path, rows)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
