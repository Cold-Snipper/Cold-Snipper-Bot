from typing import Any, Dict, List

import yaml


def _derive_start_urls(config: Dict[str, Any]) -> List[str]:
    """Build start_urls from phase2 structure when source_type is set."""
    urls: List[str] = []
    for site in config.get("websites") or []:
        urls.extend(site.get("generated_urls") or [])
    fb = config.get("facebook") or {}
    urls.extend((fb.get("marketplace") or {}).get("generated_urls") or [])
    urls.extend((fb.get("groups") or {}).get("group_urls") or [])
    return list(dict.fromkeys(urls))


class ConfigLoader:
    @staticmethod
    def load_config(file_path: str) -> Dict[str, Any]:
        """Load and validate config; derive start_urls from phase2 when needed."""
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                config = yaml.safe_load(file) or {}
                ConfigLoader.validate_config(config)
                if config.get("source_type") and not config.get("start_urls"):
                    config["start_urls"] = _derive_start_urls(config)
                return config
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Config file not found: {file_path}") from exc

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> None:
        """Require start_urls OR (source_type + phase2 URL sources). Set limits defaults."""
        has_start_urls = "start_urls" in config and isinstance(config.get("start_urls"), list)
        source_type = config.get("source_type")
        has_phase2_urls = bool(_derive_start_urls(config)) if source_type else False
        if not has_start_urls:
            if not source_type:
                raise ValueError("Missing required key: start_urls (or set source_type with websites/facebook URLs)")
            config["start_urls"] = []
        config.setdefault("database", "leads.db")
        config.setdefault("selectors", {})
        config["selectors"].setdefault("listing", '[data-testid="marketplace_feed_card"]')
        if "limits" not in config:
            config["limits"] = {}
        limits = config["limits"]
        limits.setdefault("delay_min", 5)
        limits.setdefault("scroll_depth", 30)
        limits.setdefault("delay_max", 12)
        limits.setdefault("cooldown_min", 1800)
        limits.setdefault("cooldown_max", 3600)
        limits.setdefault("max_contacts_per_hour", 5)
        limits.setdefault("cycle_cooldown_seconds", 300)
