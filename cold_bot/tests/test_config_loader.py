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
