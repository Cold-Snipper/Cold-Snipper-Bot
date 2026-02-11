#!/usr/bin/env python3
"""
Facebook scan with anti-detection: FB-only rate limits, delays, stealth, optional non-headless.
Appends listing URLs to fb_queue.csv. Use when UI sends scan_mode=facebook.
"""
import csv
import os
import random
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

COLD_BOT_ROOT = Path(__file__).resolve().parent
if str(COLD_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(COLD_BOT_ROOT))


def load_config():
    config_path = COLD_BOT_ROOT / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


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
    except Exception as e:
        print(f"Warning: could not read queue from {queue_path}: {e}", file=sys.stderr)
    return rows, next_id, existing_urls


def write_queue(queue_path: Path, rows: list) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with open(queue_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["id", "url", "status", "saved_at"])
        w.writerows(rows)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="FB scan with anti-detection (rate limit, stealth, delays)")
    parser.add_argument("--queue-path", required=True, help="Path to fb_queue.csv")
    parser.add_argument("--url", action="append", default=[], dest="urls", help="Feed URL (repeat for multiple)")
    parser.add_argument("--headless", action="store_true", help="Override config and run headless")
    parser.add_argument("--storage-state", default="", help="Path to Playwright storage state for logged-in FB")
    parser.add_argument("--config", default=str(COLD_BOT_ROOT / "config.yaml"), help="Config YAML")
    args = parser.parse_args()

    queue_path = Path(args.queue_path).resolve()
    urls = [u.strip() for u in args.urls if u.strip()]
    if not urls:
        print("No URLs provided. Use --url <feed_url> (repeat for multiple).", file=sys.stderr)
        return 1

    config = load_config()
    if args.config != str(COLD_BOT_ROOT / "config.yaml") and Path(args.config).exists():
        try:
            import yaml
            with open(args.config, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            pass

    limits = config.get("limits") or {}
    fb_rpm = max(1, int(limits.get("fb_requests_per_minute", 10)))
    fb_delay_min = max(3, int(limits.get("fb_delay_min", 5)))
    fb_delay_max = max(fb_delay_min, int(limits.get("fb_delay_max", 15)))
    fb_max_urls = max(1, int(limits.get("fb_max_urls_per_run", 8)))
    fb_scroll_depth = max(5, int(limits.get("fb_max_scroll_depth", 20)))
    fb_cfg = config.get("facebook")
    fb_headless = bool(
        args.headless
        or (isinstance(fb_cfg, dict) and fb_cfg.get("headless", False))
    )

    config_fb = {
        **config,
        "limits": {
            **(config.get("limits") or {}),
            "delay_min": fb_delay_min,
            "delay_max": fb_delay_max,
            "scroll_depth": fb_scroll_depth,
        },
        "headless": fb_headless,
    }

    from silos.browser_automation import close_browser, _apply_stealth
    from silos.scraper import FBMarketplaceScraper
    from utils import rotate_ua

    from playwright.sync_api import sync_playwright

    urls = urls[:fb_max_urls]
    min_interval_sec = 60.0 / fb_rpm
    p = None
    try:
        p = sync_playwright().start()
        browser = p.chromium.launch(headless=fb_headless)
        viewport = {"width": random.randint(1200, 1400), "height": random.randint(700, 900)}
        opts = {"viewport": viewport, "user_agent": rotate_ua()}
        if args.storage_state and os.path.isfile(args.storage_state):
            opts["storage_state"] = args.storage_state
        context = browser.new_context(**opts)
        _apply_stealth(context)
        page = context.new_page()
        page.set_default_timeout(60_000)

        scraper = FBMarketplaceScraper(config_fb)
        scraper._playwright = p
        scraper._browser = browser
        scraper._context = context
        scraper._page = page

        all_urls = []
        for i, url in enumerate(urls):
            if i > 0:
                time.sleep(min_interval_sec)
            print(f"Opening {url}", flush=True)
            try:
                raw = scraper.scrape(url, dry_run=True, db_path=None, page=page)
                for r in raw:
                    u = (r.get("url") or "").strip()
                    if u and not u.startswith("javascript:"):
                        all_urls.append(u)
            except Exception as e:
                print(f"FB scrape failed for {url}: {e}", flush=True)
            if i < len(urls) - 1:
                time.sleep(random.uniform(fb_delay_min, fb_delay_max))

        close_browser(p, browser, context)
        p = None

        existing_rows, next_id, existing_urls = read_existing_queue(queue_path)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        added = 0
        for u in all_urls:
            if u in existing_urls:
                continue
            existing_urls.add(u)
            existing_rows.append([str(next_id), u, "queued", now])
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
        traceback.print_exc()
        return 1
    finally:
        if p is not None:
            try:
                p.stop()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
