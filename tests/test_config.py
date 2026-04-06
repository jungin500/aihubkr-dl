#!/usr/bin/env python3
#
# Tests for config.py
# Covers singleton pattern, disk I/O, base64 encoding, and error recovery
#
# @author Jung-In An <ji5489@gmail.com>

import base64
import json
import os

import pytest

from src.aihubkr.core.config import AIHubConfig


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton between tests so each test gets a fresh instance."""
    AIHubConfig._instance = None
    yield
    AIHubConfig._instance = None


@pytest.fixture
def config_path(temp_dir, monkeypatch):
    """Redirect CONFIG_PATH to a temp directory so tests don't touch real config."""
    path = str(temp_dir / "config.json")
    monkeypatch.setattr(AIHubConfig, "CONFIG_PATH", path)
    return path


class TestSingletonPattern:
    """Tests for the singleton lifecycle."""

    def test_get_instance_returns_same_object(self, config_path):
        """get_instance() returns the same object on repeated calls."""
        a = AIHubConfig.get_instance()
        b = AIHubConfig.get_instance()
        assert a is b

    def test_singleton_enforcement_load(self, config_path):
        """Calling load_from_disk on a raw instance raises RuntimeError."""
        rogue = AIHubConfig()
        with pytest.raises(RuntimeError, match="Singleton"):
            rogue.load_from_disk()

    def test_singleton_enforcement_save(self, config_path):
        """Calling save_to_disk on a raw instance raises RuntimeError."""
        # Need to init the singleton first so _instance exists
        AIHubConfig.get_instance()
        rogue = AIHubConfig()
        with pytest.raises(RuntimeError, match="Singleton"):
            rogue.save_to_disk()

    def test_singleton_enforcement_clear(self, config_path):
        """Calling clear on a raw instance raises RuntimeError."""
        AIHubConfig.get_instance()
        rogue = AIHubConfig()
        with pytest.raises(RuntimeError, match="Singleton"):
            rogue.clear()


class TestDiskIO:
    """Tests for save_to_disk / load_from_disk roundtrip."""

    def test_save_and_load_roundtrip(self, config_path):
        """Save config, reload it, verify values survive the trip."""
        cfg = AIHubConfig.get_instance()
        cfg.config_db["api_key"] = "MY-SECRET-KEY"
        cfg.config_db["version"] = "3"
        cfg.save_to_disk()

        # Reset and reload
        cfg.config_db = {}
        cfg.load_from_disk()

        assert cfg.config_db["api_key"] == "MY-SECRET-KEY"
        assert cfg.config_db["version"] == "3"

    def test_values_are_base64_on_disk(self, config_path):
        """Verify the JSON file contains base64-encoded values, not plaintext."""
        cfg = AIHubConfig.get_instance()
        cfg.config_db["api_key"] = "PLAINTEXT-KEY"
        cfg.save_to_disk()

        with open(config_path, "r") as f:
            raw = json.load(f)

        # The raw value should be base64, not the plaintext
        assert raw["api_key"] != "PLAINTEXT-KEY"
        decoded = base64.b64decode(raw["api_key"]).decode()
        assert decoded == "PLAINTEXT-KEY"

    def test_load_nonexistent_config(self, config_path):
        """Loading when no config file exists returns empty db (not an error)."""
        cfg = AIHubConfig.get_instance()
        assert cfg.config_db == {}

    def test_load_corrupt_json(self, config_path):
        """Corrupt JSON file results in empty config_db and returns False."""
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            f.write("{{{not valid json")

        cfg = AIHubConfig.get_instance()
        # get_instance calls load_from_disk which should handle this gracefully
        assert cfg.config_db == {}

    def test_load_invalid_base64(self, config_path):
        """Config file with non-base64 values — should not crash."""
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            json.dump({"api_key": "!!not-base64!!"}, f)

        cfg = AIHubConfig.get_instance()
        # Should handle gracefully (base64 decode error)
        # The current implementation may crash here — this is a bug-finding test
        # If it crashes, it means error handling needs improvement
        assert isinstance(cfg.config_db, dict)

    def test_save_creates_parent_directory(self, temp_dir, monkeypatch):
        """save_to_disk creates the ~/.aihubkr-cli/ directory if missing."""
        nested_path = str(temp_dir / "new_dir" / "config.json")
        monkeypatch.setattr(AIHubConfig, "CONFIG_PATH", nested_path)

        cfg = AIHubConfig.get_instance()
        cfg.config_db["test"] = "value"
        cfg.save_to_disk()

        assert os.path.exists(nested_path)


class TestClear:
    """Tests for clear()."""

    def test_clear_removes_file_and_db(self, config_path):
        """clear(save=True) removes the file and empties config_db."""
        cfg = AIHubConfig.get_instance()
        cfg.config_db["api_key"] = "to-be-deleted"
        cfg.save_to_disk()
        assert os.path.exists(config_path)

        cfg.clear(save=True)
        assert not os.path.exists(config_path)
        assert cfg.config_db == {}

    def test_clear_no_save(self, config_path):
        """clear(save=False) clears db but does NOT delete the file."""
        cfg = AIHubConfig.get_instance()
        cfg.config_db["api_key"] = "keep-on-disk"
        cfg.save_to_disk()

        cfg.clear(save=False)
        assert cfg.config_db == {}
        # File should still exist on disk
        assert os.path.exists(config_path)

    def test_clear_when_no_file_exists(self, config_path):
        """clear() when no config file exists — no crash."""
        cfg = AIHubConfig.get_instance()
        cfg.clear(save=True)
        assert cfg.config_db == {}
