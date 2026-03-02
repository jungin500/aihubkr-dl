#!/usr/bin/env python3
#
# AIHub API v0.6 Live Tests
# Broad, reproducible test set for verifying the v0.6 API with a real API key
#
# Run with: AIHUB_TEST_API_KEY=<your-key> pytest tests/test_api_v06_live.py -v
#
# These tests hit the real AIHub API and require:
# - Internet connection
# - Valid AIHUB_TEST_API_KEY environment variable
#
# @author Jung-In An <ji5489@gmail.com>

import hashlib
import json
import os
from typing import Dict, Optional

import pytest
import requests

from src.aihubkr.core.api_version import (
    KNOWN_SHELL_SHA256,
    SHELL_SCRIPT_URL,
    check_api_version,
    reset_cache,
)
from src.aihubkr.core.auth import AIHubAuth
from src.aihubkr.core.downloader import AIHubDownloader


@pytest.fixture(autouse=True)
def clear_version_cache():
    """Reset version cache between tests."""
    reset_cache()
    yield
    reset_cache()


@pytest.fixture
def api_key() -> str:
    """Get API key from environment or skip test."""
    key = os.getenv("AIHUB_TEST_API_KEY")
    if not key:
        pytest.skip("AIHUB_TEST_API_KEY environment variable not set")
    return key


@pytest.fixture
def auth_headers(api_key: str) -> Dict[str, str]:
    """Get authentication headers."""
    return {"apikey": api_key}


# ─── Version Pinning ──────────────────────────────────────────────────────────

class TestVersionPinning:
    """Test that the AIHub shell script hash matches our known-good value."""

    @pytest.mark.live
    def test_shell_script_hash_matches(self):
        """Download the official shell script and verify its SHA-256 hash."""
        response = requests.get(SHELL_SCRIPT_URL, timeout=15)
        assert response.status_code == 200, f"Failed to download shell script: HTTP {response.status_code}"

        sha256 = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
        assert sha256 == KNOWN_SHELL_SHA256, (
            f"Shell script hash mismatch! AIHub may have updated their API.\n"
            f"Expected: {KNOWN_SHELL_SHA256}\n"
            f"Got:      {sha256}"
        )

    @pytest.mark.live
    def test_check_api_version_returns_compatible(self):
        """Test that check_api_version() reports compatible."""
        is_ok, msg = check_api_version()
        assert is_ok is True, f"Version check failed: {msg}"

    @pytest.mark.live
    def test_shell_script_contains_expected_version(self):
        """Verify the shell script contains VER="0.6"."""
        response = requests.get(SHELL_SCRIPT_URL, timeout=15)
        assert 'VER="0.6"' in response.text


# ─── Key Validation ───────────────────────────────────────────────────────────

class TestKeyValidation:
    """Test the new POST /api/keyValidate.do endpoint."""

    @pytest.mark.live
    def test_valid_key_returns_success(self, api_key: str):
        """POST with valid API key returns {"msg":"login success","code":200}."""
        response = requests.post(
            "https://api.aihub.or.kr/api/keyValidate.do",
            headers={"apikey": api_key},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["msg"] == "login success"

    @pytest.mark.live
    def test_invalid_key_returns_failure(self):
        """POST with invalid API key returns {"msg":"login fail","code":401}."""
        response = requests.post(
            "https://api.aihub.or.kr/api/keyValidate.do",
            headers={"apikey": "INVALID-FAKE-KEY-12345"},
            timeout=15,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 401
        assert data["msg"] == "login fail"

    @pytest.mark.live
    def test_auth_class_validates_successfully(self, api_key: str):
        """Test that AIHubAuth.validate_api_key() returns True for valid key."""
        auth = AIHubAuth(api_key)
        assert auth.validate_api_key() is True

    @pytest.mark.live
    def test_auth_class_rejects_invalid_key(self):
        """Test that AIHubAuth.validate_api_key() returns False for invalid key."""
        auth = AIHubAuth("INVALID-FAKE-KEY-12345")
        assert auth.validate_api_key() is False


# ─── Dataset List ─────────────────────────────────────────────────────────────

class TestDatasetList:
    """Test the dataset listing endpoint."""

    @pytest.mark.live
    def test_dataset_list_returns_data(self):
        """GET /info/dataset.do returns a non-empty dataset list."""
        response = requests.get("https://api.aihub.or.kr/info/dataset.do", timeout=15)
        assert response.status_code in [200, 502]
        assert len(response.text) > 100

    @pytest.mark.live
    def test_dataset_list_is_parseable(self):
        """Dataset list can be parsed by AIHubDownloader."""
        downloader = AIHubDownloader()
        datasets = downloader.get_dataset_info()
        assert datasets is not None
        assert len(datasets) > 10  # AIHub has many datasets
        for dataset_id, dataset_name in datasets[:5]:
            assert dataset_id.strip().isdigit()
            assert len(dataset_name.strip()) > 0


# ─── Data Package List ────────────────────────────────────────────────────────

class TestDataPackageList:
    """Test the data package listing endpoint."""

    @pytest.mark.live
    def test_datapackage_list_returns_data(self):
        """GET /info/datapckage.do returns a non-empty package list."""
        response = requests.get("https://api.aihub.or.kr/info/datapckage.do", timeout=15)
        assert response.status_code in [200, 502]
        assert "DataPackage" in response.text or "목록" in response.text

    @pytest.mark.live
    def test_datapackage_list_is_parseable(self):
        """Data package list can be parsed by AIHubDownloader."""
        downloader = AIHubDownloader()
        packages = downloader.get_datapackage_info()
        assert packages is not None
        assert len(packages) >= 1


# ─── File Trees ───────────────────────────────────────────────────────────────

class TestFileTrees:
    """Test file tree retrieval for datasets and packages."""

    @pytest.mark.live
    @pytest.mark.parametrize("dataset_key", ["71", "86", "50"])
    def test_dataset_file_tree(self, dataset_key: str):
        """File tree for known datasets contains tree characters."""
        response = requests.get(
            f"https://api.aihub.or.kr/info/{dataset_key}.do",
            timeout=15,
        )
        assert response.status_code in [200, 502]
        # Should contain tree structure characters
        assert any(ch in response.text for ch in ["├", "└", "│"])

    @pytest.mark.live
    @pytest.mark.parametrize("dataset_key", ["71", "86", "50"])
    def test_dataset_file_tree_via_downloader(self, dataset_key: str):
        """AIHubDownloader.get_file_tree() returns valid data for known datasets."""
        downloader = AIHubDownloader()
        file_tree, error_message = downloader.get_file_tree(dataset_key)
        assert error_message is None, f"Error for dataset {dataset_key}: {error_message}"
        assert file_tree is not None
        assert len(file_tree) > 50

    @pytest.mark.live
    def test_package_file_tree(self):
        """File tree for data package 1 contains tree characters."""
        response = requests.get(
            "https://api.aihub.or.kr/info/pckage/1.do",
            timeout=15,
        )
        assert response.status_code in [200, 502]
        assert any(ch in response.text for ch in ["├", "└", "│"])

    @pytest.mark.live
    def test_package_file_tree_via_downloader(self):
        """AIHubDownloader.get_package_file_tree() returns valid data."""
        downloader = AIHubDownloader()
        file_tree, error_message = downloader.get_package_file_tree("1")
        assert error_message is None, f"Error: {error_message}"
        assert file_tree is not None
        assert len(file_tree) > 50


# ─── Download Privilege Check ─────────────────────────────────────────────────

class TestDownloadPrivilege:
    """Test download endpoint error responses."""

    @pytest.mark.live
    def test_unapproved_dataset_returns_502(self, api_key: str):
        """Downloading an unapproved dataset returns HTTP 502 with error message."""
        response = requests.get(
            "https://api.aihub.or.kr/down/0.6/71.do?fileSn=39410",
            headers={"apikey": api_key},
            timeout=15,
        )
        # Should be 502 with privilege error (unless the key has approval for dataset 71)
        if response.status_code == 502:
            assert "홈페이지" in response.text or "승인" in response.text or "신청" in response.text

    @pytest.mark.live
    def test_old_v05_endpoint_is_rejected(self, api_key: str):
        """The old v0.5 download endpoint rejects requests."""
        response = requests.get(
            "https://api.aihub.or.kr/down/0.5/71.do?fileSn=39410",
            headers={"apikey": api_key},
            timeout=15,
        )
        assert response.status_code == 502
        assert "신규 버전" in response.text


# ─── API Manual ───────────────────────────────────────────────────────────────

class TestApiManual:
    """Test the API documentation endpoint."""

    @pytest.mark.live
    def test_api_manual_returns_data(self):
        """GET /info/api.do returns response containing command documentation.

        Note: The API returns non-standard JSON (unquoted datetime values),
        so we validate the raw text content rather than parsing as JSON.
        """
        response = requests.get("https://api.aihub.or.kr/info/api.do", timeout=15)
        assert response.status_code == 200
        assert '"result"' in response.text
        assert len(response.text) > 100

    @pytest.mark.live
    def test_api_manual_contains_commands(self):
        """API manual contains expected command documentation."""
        response = requests.get("https://api.aihub.or.kr/info/api.do", timeout=15)
        text = response.text
        assert "-aihubapikey" in text
        assert "-mode" in text
        assert "-datasetkey" in text
        assert "-datapckagekey" in text


# ─── End-to-End Flow ──────────────────────────────────────────────────────────

class TestEndToEnd:
    """Test the complete workflow from validation to file tree retrieval."""

    @pytest.mark.live
    def test_full_workflow(self, api_key: str):
        """Complete workflow: validate key → list datasets → get file tree → check URLs."""
        # Step 1: Validate API key
        auth = AIHubAuth(api_key)
        assert auth.validate_api_key() is True

        # Step 2: Get auth headers
        headers = auth.get_auth_headers()
        assert headers is not None
        assert "apikey" in headers

        # Step 3: Create downloader
        downloader = AIHubDownloader(headers)

        # Step 4: List datasets
        datasets = downloader.get_dataset_info()
        assert datasets is not None
        assert len(datasets) > 0

        # Step 5: Get file tree for first dataset
        first_key = datasets[0][0].strip()
        file_tree, error_message = downloader.get_file_tree(first_key)
        assert error_message is None
        assert file_tree is not None

        # Step 6: Verify URL generation uses v0.6
        url = downloader.get_raw_url(first_key, "all")
        assert "/down/0.6/" in url
        assert f"/{first_key}.do" in url

    @pytest.mark.live
    def test_package_workflow(self, api_key: str):
        """Complete workflow for data packages."""
        auth = AIHubAuth(api_key)
        assert auth.validate_api_key() is True

        downloader = AIHubDownloader(auth.get_auth_headers())

        # List packages
        packages = downloader.get_datapackage_info()
        assert packages is not None
        assert len(packages) >= 1

        # Get file tree for first package
        first_key = packages[0][0].strip()
        file_tree, error_message = downloader.get_package_file_tree(first_key)
        assert error_message is None
        assert file_tree is not None

        # Verify package URL generation
        url = downloader.get_raw_package_url(first_key, "all")
        assert "/down/pckage/0.6/" in url
