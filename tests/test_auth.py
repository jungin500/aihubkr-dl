#!/usr/bin/env python3
#
# AIHub Authentication Tests
# Unit tests for API key authentication with v0.6 JSON key validation
#
# - Tests API key validation via POST /api/keyValidate.do (JSON response)
# - Tests credential management and storage
# - Mocks API responses for controlled testing
#
# @author Jung-In An <ji5489@gmail.com>

import os
from unittest.mock import Mock, patch

import pytest
import requests
import responses

from src.aihubkr.core.auth import AIHubAuth
from src.aihubkr.core.config import AIHubConfig


class TestAIHubAuth:
    """Test cases for AIHub authentication module."""

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        api_key = "test-api-key-12345"
        auth = AIHubAuth(api_key)
        assert auth.api_key == api_key
        assert auth.autosave_enabled is False

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        auth = AIHubAuth()
        assert auth.api_key is None
        assert auth.autosave_enabled is False

    def test_set_api_key(self):
        """Test setting API key."""
        auth = AIHubAuth()
        api_key = "new-api-key-67890"
        auth.set_api_key(api_key)
        assert auth.api_key == api_key

    def test_set_api_key_with_autosave(self):
        """Test setting API key with autosave enabled."""
        auth = AIHubAuth()
        auth.autosave_enabled = True

        with patch.object(auth, 'save_credential') as mock_save:
            api_key = "new-api-key-67890"
            auth.set_api_key(api_key)
            mock_save.assert_called_once()

    def test_get_auth_headers_with_api_key(self):
        """Test getting authentication headers with API key."""
        api_key = "test-api-key-12345"
        auth = AIHubAuth(api_key)
        headers = auth.get_auth_headers()
        assert headers == {"apikey": api_key}

    def test_get_auth_headers_without_api_key(self):
        """Test getting authentication headers without API key."""
        auth = AIHubAuth()
        headers = auth.get_auth_headers()
        assert headers is None

    @responses.activate
    def test_validate_api_key_success(self):
        """Test API key validation success with JSON response."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            json={"msg": "login success", "code": 200},
            status=200,
            content_type="application/json"
        )

        auth = AIHubAuth("valid-api-key")
        result = auth.validate_api_key()
        assert result is True

    @responses.activate
    def test_validate_api_key_failure(self):
        """Test API key validation failure with JSON response."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            json={"msg": "login fail", "code": 401},
            status=200,
            content_type="application/json"
        )

        auth = AIHubAuth("invalid-api-key")
        result = auth.validate_api_key()
        assert result is False

    @responses.activate
    def test_validate_api_key_malformed_json(self):
        """Test API key validation with malformed JSON response."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            body="not json at all",
            status=200,
            content_type="text/plain"
        )

        auth = AIHubAuth("some-api-key")
        result = auth.validate_api_key()
        assert result is False

    @responses.activate
    def test_validate_api_key_missing_code_field(self):
        """Test API key validation with JSON missing the code field."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            json={"msg": "something"},
            status=200,
            content_type="application/json"
        )

        auth = AIHubAuth("some-api-key")
        result = auth.validate_api_key()
        assert result is False

    @responses.activate
    def test_validate_api_key_timeout(self):
        """Test API key validation with timeout."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            body=requests.Timeout("Request timed out"),
        )

        auth = AIHubAuth("timeout-api-key")
        result = auth.validate_api_key()
        assert result is False

    @responses.activate
    def test_validate_api_key_network_error(self):
        """Test API key validation with network error."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            body=requests.ConnectionError("Connection failed"),
        )

        auth = AIHubAuth("network-error-api-key")
        result = auth.validate_api_key()
        assert result is False

    def test_validate_api_key_without_key(self):
        """Test API key validation without API key."""
        auth = AIHubAuth()
        result = auth.validate_api_key()
        assert result is False

    @responses.activate
    def test_validate_uses_post_method(self):
        """Test that validation uses POST, not GET."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            json={"msg": "login success", "code": 200},
            status=200,
        )

        auth = AIHubAuth("test-key")
        auth.validate_api_key()

        assert len(responses.calls) == 1
        assert responses.calls[0].request.method == "POST"

    @responses.activate
    def test_validate_sends_apikey_header(self):
        """Test that validation sends the apikey header."""
        responses.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            json={"msg": "login success", "code": 200},
            status=200,
        )

        auth = AIHubAuth("MY-TEST-KEY")
        auth.validate_api_key()

        assert responses.calls[0].request.headers["apikey"] == "MY-TEST-KEY"

    @patch.object(AIHubConfig, 'get_instance')
    def test_save_credential(self, mock_config_instance):
        """Test saving API key credentials."""
        mock_config = Mock()
        mock_config.config_db = {}
        mock_config_instance.return_value = mock_config

        auth = AIHubAuth("test-api-key")
        auth.save_credential()

        assert mock_config.config_db["api_key"] == "test-api-key"
        assert mock_config.config_db["version"] == "3"
        mock_config.save_to_disk.assert_called_once()

    def test_save_credential_without_api_key(self):
        """Test saving credentials without API key."""
        auth = AIHubAuth()
        # Should not raise an exception
        auth.save_credential()

    @patch.object(AIHubConfig, 'get_instance')
    def test_load_credentials_success(self, mock_config_instance):
        """Test loading credentials successfully."""
        mock_config = Mock()
        mock_config.config_db = {
            "api_key": "saved-api-key",
            "version": "3"
        }
        mock_config_instance.return_value = mock_config

        auth = AIHubAuth()
        result = auth.load_credentials()

        assert result == "saved-api-key"
        assert auth.api_key == "saved-api-key"
        assert auth.autosave_enabled is True

    @patch.object(AIHubConfig, 'get_instance')
    def test_load_credentials_outdated_version(self, mock_config_instance):
        """Test loading credentials with outdated version (v2 from old API)."""
        mock_config = Mock()
        mock_config.config_db = {
            "api_key": "old-api-key",
            "version": "2"  # Outdated version (from v0.5 API)
        }
        mock_config.save_to_disk = Mock()
        mock_config.load_from_disk = Mock()
        mock_config_instance.return_value = mock_config

        auth = AIHubAuth()
        result = auth.load_credentials()

        assert result is None
        assert auth.api_key is None
        assert auth.autosave_enabled is False
        # Should clear the outdated credentials
        assert "api_key" not in mock_config.config_db
        assert "version" not in mock_config.config_db
        mock_config.save_to_disk.assert_called_once()

    @patch.object(AIHubConfig, 'get_instance')
    def test_load_credentials_no_saved_key(self, mock_config_instance):
        """Test loading credentials when no key is saved."""
        mock_config = Mock()
        mock_config.config_db = {}
        mock_config_instance.return_value = mock_config

        auth = AIHubAuth()
        result = auth.load_credentials()

        assert result is None
        assert auth.api_key is None
        assert auth.autosave_enabled is False

    @patch.object(AIHubConfig, 'get_instance')
    def test_clear_credential(self, mock_config_instance):
        """Test clearing stored credentials."""
        mock_config = Mock()
        mock_config.config_db = {
            "api_key": "test-api-key",
            "version": "3"
        }
        mock_config.save_to_disk = Mock()
        mock_config.load_from_disk = Mock()
        mock_config_instance.return_value = mock_config

        auth = AIHubAuth("test-api-key")
        auth.autosave_enabled = True
        auth.clear_credential()

        assert auth.api_key is None
        assert auth.autosave_enabled is False
        assert "api_key" not in mock_config.config_db
        assert "version" not in mock_config.config_db
        mock_config.save_to_disk.assert_called_once()

    def test_credential_version_is_3(self):
        """Test that credential version is 3 for v0.6 API."""
        assert AIHubAuth.CREDENTIAL_VERSION == "3"

    def test_key_validate_url(self):
        """Test that key validation URL is the v0.6 endpoint."""
        assert AIHubAuth.KEY_VALIDATE_URL == "https://api.aihub.or.kr/api/keyValidate.do"


class TestAIHubAuthIntegration:
    """Integration tests for AIHub authentication."""

    @pytest.mark.integration
    @pytest.mark.auth
    def test_full_authentication_flow(self):
        """Test complete authentication flow."""
        auth = AIHubAuth()

        # Test setting API key
        api_key = "integration-test-key"
        auth.set_api_key(api_key)
        assert auth.api_key == api_key

        # Test getting auth headers
        headers = auth.get_auth_headers()
        assert headers == {"apikey": api_key}

        # Test clearing credentials
        auth.clear_credential()
        assert auth.api_key is None
        assert auth.autosave_enabled is False

    @pytest.mark.api
    @pytest.mark.slow
    def test_real_api_key_validation(self):
        """Test with real API key validation (marked as slow)."""
        api_key = os.getenv("AIHUB_TEST_API_KEY")
        if not api_key:
            pytest.skip("AIHUB_TEST_API_KEY environment variable not set")

        auth = AIHubAuth(api_key)
        result = auth.validate_api_key()

        assert isinstance(result, bool)
