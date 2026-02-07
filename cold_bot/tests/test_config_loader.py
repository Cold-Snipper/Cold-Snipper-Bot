import pytest
import yaml

from silos.config_loader import ConfigLoader


def test_load_success(tmp_path):
    config_path = tmp_path / "config.yaml"
    data = {"start_urls": ["http://example.com"]}
    config_path.write_text(yaml.safe_dump(data))
    loaded = ConfigLoader.load_config(str(config_path))
    assert loaded["start_urls"] == ["http://example.com"]


def test_validate_missing_key():
    with pytest.raises(ValueError):
        ConfigLoader.validate_config({})


def test_validate_sets_defaults():
    config = {"start_urls": ["http://example.com"]}
    ConfigLoader.validate_config(config)
    assert config.get("database") == "leads.db"
    assert "selectors" in config
    assert "listing" in config["selectors"]
    assert "limits" in config
    assert config["limits"].get("cycle_cooldown_seconds") == 300
