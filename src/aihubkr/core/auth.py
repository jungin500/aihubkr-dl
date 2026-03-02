#!/usr/bin/env python3
#
# AIHub Authentication Module
# Handles API key authentication for AIHub API
#
# - Validates API key via POST /api/keyValidate.do (JSON response)
# - Manages API key storage and retrieval
#
# @author Jung-In An <ji5489@gmail.com>

from typing import Dict, Optional

import requests
from .config import AIHubConfig


class AIHubAuth:
    """Handles API key authentication for AIHub API."""

    BASE_URL = "https://api.aihub.or.kr"
    KEY_VALIDATE_URL = f"{BASE_URL}/api/keyValidate.do"
    CREDENTIAL_VERSION = "3"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.autosave_enabled = False

    def clear_credential(self) -> None:
        """Clear stored API key credentials."""
        self.api_key = None
        self.autosave_enabled = False

        config_manager = AIHubConfig.get_instance()
        if "api_key" in config_manager.config_db:
            config_manager.config_db.pop("api_key")
        if "version" in config_manager.config_db:
            config_manager.config_db.pop("version")
        config_manager.save_to_disk()

    def save_credential(self) -> None:
        """Save API key and version to configuration."""
        if not self.api_key:
            return

        config_manager = AIHubConfig.get_instance()
        config_manager.config_db["api_key"] = self.api_key
        config_manager.config_db["version"] = self.CREDENTIAL_VERSION
        config_manager.save_to_disk()

    def load_credentials(self) -> Optional[str]:
        """Load API key from configuration, check version, and migrate if needed."""
        config_manager = AIHubConfig.get_instance()
        config_manager.load_from_disk()

        api_key = config_manager.config_db.get("api_key")
        version = config_manager.config_db.get("version")
        if api_key and version == self.CREDENTIAL_VERSION:
            self.api_key = api_key
            self.autosave_enabled = True
            return api_key
        elif api_key and version != self.CREDENTIAL_VERSION:
            # Outdated credential, clear and require re-entry
            self.clear_credential()
            return None
        return None

    def validate_api_key(self) -> bool:
        """Validate API key with AIHub server via POST /api/keyValidate.do.

        Returns True if the server responds with {"msg":"login success","code":200}.
        """
        if not self.api_key:
            return False

        try:
            response = requests.post(
                self.KEY_VALIDATE_URL,
                headers={"apikey": self.api_key},
                timeout=30,
            )

            data = response.json()
            return data.get("code") == 200

        except (requests.Timeout, requests.RequestException):
            return False
        except (ValueError, KeyError):
            # JSON decode error or missing key
            return False

    def get_auth_headers(self) -> Optional[Dict[str, str]]:
        """Get authentication headers for API requests."""
        if not self.api_key:
            return None

        return {"apikey": self.api_key}

    def set_api_key(self, api_key: str) -> None:
        """Set API key and optionally save it."""
        self.api_key = api_key
        if self.autosave_enabled:
            self.save_credential()
