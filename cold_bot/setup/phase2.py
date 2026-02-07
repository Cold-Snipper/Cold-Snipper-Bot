import sys
from pathlib import Path
from typing import Dict, List

import yaml


def _load_config(path: Path) -> Dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}


def _prompt_int(prompt: str, default: int | None = None) -> int:
    raw = input(f"{prompt} " + (f"[{default}] " if default is not None else "")).strip()
    if not raw and default is not None:
        return default
    return int(raw)


def _configure_websites() -> List[Dict]:
    """
    Minimal console-driven configuration for website sources.

    This is intentionally simple and acts as a stub that can be
    expanded later (site-specific URL builders, more filters, etc.).
    """
    print("Configure website sources.")
    print("Available sites: 1. atHome.lu, 2. Immotop.lu")
    raw = input("Sites (comma-separated numbers, e.g. 1,2): ").strip()
    choices = [c.strip() for c in raw.split(",") if c.strip()]

    websites: List[Dict] = []
    for choice in choices:
        if choice == "1":
            name = "atHome.lu"
            base_url = "https://www.athome.lu/en"
        elif choice == "2":
            name = "Immotop.lu"
            base_url = "https://www.immotop.lu/en"
        else:
            print(f"Unknown site option: {choice}, skipping.")
            continue

        print(f"\nConfiguring filters for {name}")
        price_min = _prompt_int("Minimum price (EUR)?", default=200000)
        price_max = _prompt_int("Maximum price (EUR)?", default=800000)
        rooms_min = _prompt_int("Minimum bedrooms?", default=2)
        location = input("Location/city (e.g. Luxembourg): ").strip() or "Luxembourg"

        filters = {
            "price_min": price_min,
            "price_max": price_max,
            "rooms_min": rooms_min,
            "location": location,
        }

        # Stub: a real implementation would build site-specific query URLs.
        generated_urls = [base_url]

        websites.append(
            {
                "name": name,
                "filters": filters,
                "generated_urls": generated_urls,
                "selector": '[data-testid="listing"]',
            }
        )

    return websites


def _configure_facebook() -> Dict:
    """
    Minimal console-driven configuration for Facebook sources.
    """
    print("\nConfigure Facebook sources.")
    fb_cfg: Dict = {"marketplace": {}, "groups": {}}

    use_marketplace = input("Use Facebook Marketplace? (y/N): ").strip().lower() == "y"
    if use_marketplace:
        city = input("Marketplace city/region slug (e.g. luxembourg): ").strip() or "luxembourg"
        query = input("Search query (e.g. owner, fsbo): ").strip() or "owner"
        base_url = f"https://www.facebook.com/marketplace/{city}/propertyforsale?query={query}"
        fb_cfg["marketplace"] = {
            "enabled": True,
            "filters": {"city": city, "query": query},
            "generated_urls": [base_url],
        }
    else:
        fb_cfg["marketplace"] = {"enabled": False, "filters": {}, "generated_urls": []}

    use_groups = input("Use Facebook Groups? (y/N): ").strip().lower() == "y"
    group_urls: List[str] = []
    if use_groups:
        print("Enter group URLs (blank line to finish):")
        while True:
            url = input("Group URL: ").strip()
            if not url:
                break
            group_urls.append(url)
    fb_cfg["groups"] = {
        "enabled": use_groups,
        "group_urls": group_urls,
        "allow_manual_login": True,
    }

    return fb_cfg


def run_phase2(source_type: str, config_path: str = "config.yaml") -> Dict:
    """
    Phase 2: Collect source-specific parameters and persist them to config.yaml.
    """
    path = Path(config_path)
    config = _load_config(path)

    if source_type in ("websites", "both"):
        websites = _configure_websites()
        if websites:
            config["websites"] = websites

    if source_type in ("facebook", "both"):
        fb_cfg = _configure_facebook()
        config["facebook"] = fb_cfg

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)

    print(f"Phase 2 complete. Updated configuration written to {path}.")
    return config


if __name__ == "__main__":
    src_type = sys.argv[1] if len(sys.argv) > 1 else "websites"
    cfg_path = sys.argv[2] if len(sys.argv) > 2 else "config.yaml"
    run_phase2(src_type, cfg_path)

