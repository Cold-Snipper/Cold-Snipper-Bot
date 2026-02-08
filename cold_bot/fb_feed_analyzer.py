#!/usr/bin/env python3
"""
Real Facebook Marketplace/Groups feed analyzer.
Uses Playwright to open FB URLs, scroll the feed, extract listing links,
and append them to the Java UI fb_queue.csv (id,url,status,saved_at).
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Run from cold_bot so silos and utils are importable
COLD_BOT_ROOT = Path(__file__).resolve().parent
if str(COLD_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(COLD_BOT_ROOT))

from silos.browser_automation import scroll_and_navigate, close_browser
from silos.data_scraper import extract_listings
from utils import random_delay

# Default selector for FB Marketplace feed (same as config.yaml)
DEFAULT_SELECTOR = '[data-testid="marketplace_feed_card"]'
DEFAULT_SCROLL_DEPTH = 30
DEFAULT_DELAY_MIN = 3
DEFAULT_DELAY_MAX = 12


def load_config():
    """Load selector and limits from cold_bot config.yaml."""
    config_path = COLD_BOT_ROOT / "config.yaml"
    if not config_path.exists():
        return {
            "selector": DEFAULT_SELECTOR,
            "scroll_depth": DEFAULT_SCROLL_DEPTH,
            "delay_min": DEFAULT_DELAY_MIN,
            "delay_max": DEFAULT_DELAY_MAX,
        }
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        sel = (cfg.get("selectors") or {}).get("listing") or DEFAULT_SELECTOR
        limits = cfg.get("limits") or {}
        return {
            "selector": sel,
            "scroll_depth": int(limits.get("scroll_depth", DEFAULT_SCROLL_DEPTH)),
            "delay_min": int(limits.get("delay_min", DEFAULT_DELAY_MIN)),
            "delay_max": int(limits.get("delay_max", DEFAULT_DELAY_MAX)),
        }
    except Exception:
        return {
            "selector": DEFAULT_SELECTOR,
            "scroll_depth": DEFAULT_SCROLL_DEPTH,
            "delay_min": DEFAULT_DELAY_MIN,
            "delay_max": DEFAULT_DELAY_MAX,
        }


def read_existing_queue(queue_path: Path):
    """Return (rows list, next_id, existing_urls set)."""
    rows = []
    next_id = 1
    existing_urls = set()
    if not queue_path.exists():
        return rows, next_id, existing_urls
    try:
        with open(queue_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header and header[0] != "id":
                # No header or wrong format
                return rows, next_id, existing_urls
            for row in reader:
                if len(row) < 4:
                    continue
                try:
                    i = int(row[0])
                    next_id = max(next_id, i + 1)
                except ValueError:
                    continue
                url = row[1]
                existing_urls.add(url)
                rows.append(row)
    except Exception:
        pass
    return rows, next_id, existing_urls


def write_queue(queue_path: Path, rows: list) -> None:
    """Write full queue CSV with header id,url,status,saved_at."""
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["id", "url", "status", "saved_at"])
        w.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Facebook feed and append listings to queue CSV")
    parser.add_argument("--queue-path", required=True, help="Path to fb_queue.csv (e.g. java_ui/data/fb_queue.csv)")
    parser.add_argument("--url", action="append", default=[], dest="urls", help="Feed URL (repeat for multiple)")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--storage-state", default="", help="Path to Playwright storage state for logged-in FB")
    args = parser.parse_args()

    queue_path = Path(args.queue_path).resolve()
    urls = [u.strip() for u in args.urls if u.strip()]
    if not urls:
        print("No URLs provided. Use --url <feed_url> (repeat for multiple).", file=sys.stderr)
        return 1

    config = load_config()
    selector = config["selector"]
    scroll_depth = config["scroll_depth"]
    delay_min = config["delay_min"]
    delay_max = config["delay_max"]

    from playwright.sync_api import sync_playwright

    p = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=args.headless)
        opts = {"viewport": {"width": 1280, "height": 800}}
        try:
            from utils import rotate_ua
            opts["user_agent"] = rotate_ua()
        except Exception:
            pass
        if args.storage_state and os.path.isfile(args.storage_state):
            opts["storage_state"] = args.storage_state
        context = browser.new_context(**opts)
        page = context.new_page()

        all_listings = []
        for url in urls:
            print(f"Opening {url}", flush=True)
            scroll_and_navigate(page, url, scroll_depth, delay_min, delay_max)
            listings = extract_listings(page, selector, site="facebook")
            for lst in listings:
                u = (lst.get("url") or "").strip()
                if u and not u.startswith("javascript:"):
                    all_listings.append(u)
            random_delay(2, 5)

        close_browser(p, browser, context)
        p = None

        existing_rows, next_id, existing_urls = read_existing_queue(queue_path)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        added = 0
        for url in all_listings:
            if url in existing_urls:
                continue
            existing_urls.add(url)
            existing_rows.append([str(next_id), url, "queued", now])
            next_id += 1
            added += 1

        write_queue(queue_path, existing_rows)
        print(f"Done. Appended {added} new listings to {queue_path} (total {len(existing_rows)}).", flush=True)
        return 0

    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if p is not None:
            try:
                p.stop()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
