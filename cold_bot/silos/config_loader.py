from typing import Dict, Any

import yaml


class ConfigLoader:
    @staticmethod
    def load_config(file_path: str) -> Dict[str, Any]:
        """Description.

        Args:
            file_path (type): desc.

        Returns:
            type: desc.

        Raises:
            exc: when.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                config = yaml.safe_load(file)
                ConfigLoader.validate_config(config)
                return config
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Config file not found: {file_path}") from exc

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> None:
        """Description.

        Args:
            config (type): desc.

        Returns:
            type: desc.

        Raises:
            exc: when.
        """
        required_keys = ["start_urls"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"Missing required key: {key}")
        if "limits" not in config:
            config["limits"] = {}
        if "delay_min" not in config["limits"]:
            config["limits"]["delay_min"] = 5
