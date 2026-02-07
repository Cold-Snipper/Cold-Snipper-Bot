import sys
from pathlib import Path
from typing import Dict

import yaml


CHOICE_MAPPING = {
    "1": "websites",
    "2": "facebook",
    "3": "both",
}


def _load_existing_config(config_path: Path) -> Dict:
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}


def run_phase1(config_path: str = "config.yaml") -> str:
    """
    Phase 1: Ask the user which source(s) to use and
    persist the choice into config.yaml.

    This function is intentionally console-based so it
    can be run as a standalone step:

        python -m cold_bot.setup.phase1
    """
    path = Path(config_path)
    source_type: str | None = None

    for _ in range(3):
        print("Select source: 1. Websites, 2. Facebook, 3. Both")
        choice = input("Enter (1/2/3): ").strip()
        if choice in CHOICE_MAPPING:
            source_type = CHOICE_MAPPING[choice]
            break
        print("Invalid choice. Please enter 1, 2, or 3.")

    if not source_type:
        raise ValueError("Too many invalid attempts selecting source type.")

    config = _load_existing_config(path)
    config["source_type"] = source_type
    # default agents handling strategy
    config.setdefault("agents_handling", "log_and_export")

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)

    print(f"Selected: {source_type}. Saved to {path}.")
    return source_type


if __name__ == "__main__":
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    run_phase1(cfg_path)

