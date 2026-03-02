#!/usr/bin/env python3
#
# AIHub API Version Pinning Tests
# Unit tests for shell script hash verification and version detection
#
# @author Jung-In An <ji5489@gmail.com>

import hashlib
from unittest.mock import Mock, patch

import pytest
import requests
import responses

from src.aihubkr.core.api_version import (
    KNOWN_API_VERSION,
    KNOWN_SHELL_SHA256,
    SHELL_SCRIPT_URL,
    check_api_version,
    reset_cache,
    _parse_version_from_script,
    _parse_version_string_from_script,
    get_known_version,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset the session cache before each test."""
    reset_cache()
    yield
    reset_cache()


# A fake script that matches the known hash (for testing cache/force logic only)
FAKE_SCRIPT_MATCHING = "fake script content"


class TestVersionParsing:
    """Test version string parsing from shell script content."""

    def test_parse_ver_variable(self):
        """Test extracting VER variable."""
        content = '''#!/bin/bash
VER="0.6"
BASE_URL="https://api.aihub.or.kr"
'''
        assert _parse_version_from_script(content) == "0.6"

    def test_parse_ver_variable_different_version(self):
        """Test extracting VER with a different version."""
        content = 'VER="1.0"'
        assert _parse_version_from_script(content) == "1.0"

    def test_parse_ver_variable_missing(self):
        """Test when VER variable is absent."""
        content = "no version here"
        assert _parse_version_from_script(content) is None

    def test_parse_version_string(self):
        """Test extracting full version string from echo line."""
        content = 'echo "aihubshell version 25.09.19 v0.6"'
        assert _parse_version_string_from_script(content) == "25.09.19 v0.6"

    def test_parse_version_string_missing(self):
        """Test when version string is absent."""
        content = "echo hello"
        assert _parse_version_string_from_script(content) is None


class TestCheckApiVersion:
    """Test the check_api_version function."""

    def test_force_bypasses_check(self):
        """Test that force=True bypasses version check."""
        is_ok, msg = check_api_version(force=True)
        assert is_ok is True
        assert "bypass" in msg.lower()

    @responses.activate
    def test_matching_hash(self):
        """Test that matching hash returns compatible."""
        # Build a fake script whose SHA-256 matches KNOWN_SHELL_SHA256
        # We need to mock the actual response to have the right hash
        # Instead, we patch the constant
        fake_content = "test content for hash"
        fake_hash = hashlib.sha256(fake_content.encode("utf-8")).hexdigest()

        with patch("src.aihubkr.core.api_version.KNOWN_SHELL_SHA256", fake_hash):
            responses.add(
                responses.GET,
                SHELL_SCRIPT_URL,
                body=fake_content,
                status=200,
            )

            is_ok, msg = check_api_version()
            assert is_ok is True
            assert "verified" in msg.lower()

    @responses.activate
    def test_mismatching_hash(self):
        """Test that mismatching hash returns incompatible."""
        content_with_version = '''#!/bin/bash
echo "aihubshell version 26.01.01 v0.7"
VER="0.7"
'''
        responses.add(
            responses.GET,
            SHELL_SCRIPT_URL,
            body=content_with_version,
            status=200,
        )

        is_ok, msg = check_api_version()
        assert is_ok is False
        assert "updated" in msg.lower()
        assert "0.7" in msg

    @responses.activate
    def test_mismatching_hash_no_version(self):
        """Test hash mismatch with no parseable version."""
        responses.add(
            responses.GET,
            SHELL_SCRIPT_URL,
            body="completely different script content",
            status=200,
        )

        is_ok, msg = check_api_version()
        assert is_ok is False
        assert "updated" in msg.lower()

    @responses.activate
    def test_http_error_graceful(self):
        """Test that HTTP errors allow operation to continue."""
        responses.add(
            responses.GET,
            SHELL_SCRIPT_URL,
            body="error",
            status=500,
        )

        is_ok, msg = check_api_version()
        assert is_ok is True
        assert "could not verify" in msg.lower()

    @responses.activate
    def test_timeout_graceful(self):
        """Test that timeout allows operation to continue."""
        responses.add(
            responses.GET,
            SHELL_SCRIPT_URL,
            body=requests.Timeout("timeout"),
        )

        is_ok, msg = check_api_version()
        assert is_ok is True
        assert "timed out" in msg.lower()

    @responses.activate
    def test_network_error_graceful(self):
        """Test that network errors allow operation to continue."""
        responses.add(
            responses.GET,
            SHELL_SCRIPT_URL,
            body=requests.ConnectionError("no network"),
        )

        is_ok, msg = check_api_version()
        assert is_ok is True
        assert "failed" in msg.lower()

    @responses.activate
    def test_result_is_cached(self):
        """Test that results are cached for the session."""
        fake_content = "test content"
        fake_hash = hashlib.sha256(fake_content.encode("utf-8")).hexdigest()

        with patch("src.aihubkr.core.api_version.KNOWN_SHELL_SHA256", fake_hash):
            responses.add(
                responses.GET,
                SHELL_SCRIPT_URL,
                body=fake_content,
                status=200,
            )

            # First call
            result1 = check_api_version()
            # Second call should use cache (no new HTTP request)
            result2 = check_api_version()

            assert result1 == result2
            assert len(responses.calls) == 1  # Only one HTTP call

    def test_reset_cache(self):
        """Test that reset_cache clears the cached result."""
        from src.aihubkr.core.api_version import _cached_result
        # After reset, cache should be None
        reset_cache()
        from src.aihubkr.core import api_version
        assert api_version._cached_result is None


class TestKnownValues:
    """Test that known values are properly defined."""

    def test_known_api_version(self):
        assert KNOWN_API_VERSION == "0.6"

    def test_known_hash_is_valid_sha256(self):
        assert len(KNOWN_SHELL_SHA256) == 64
        int(KNOWN_SHELL_SHA256, 16)  # Should not raise

    def test_shell_script_url(self):
        assert SHELL_SCRIPT_URL == "https://api.aihub.or.kr/api/aihubshell.do"

    def test_get_known_version(self):
        assert get_known_version() == "0.6"
