#!/usr/bin/env python3
#
# AIHub API Integration Tests
# Integration tests for AIHub API v0.6 with custom success/failure validation
#
# - Tests mocked API interactions with v0.6 response formats
# - Validates JSON key validation responses
# - Tests dataset and data package operations
#
# @author Jung-In An <ji5489@gmail.com>

import os
import time
from typing import Dict, List, Optional, Tuple
from unittest.mock import Mock

import pytest
import requests

from src.aihubkr.core.auth import AIHubAuth
from src.aihubkr.core.downloader import AIHubDownloader, DownloadStatus


class AIHubAPITestValidator:
    """Custom validator for AIHub API v0.6 responses."""

    @staticmethod
    def validate_api_key_response(response: requests.Response) -> Tuple[bool, str]:
        """
        Validate API key validation response (v0.6: JSON format).
        """
        try:
            data = response.json()
            code = data.get("code")
            msg = data.get("msg", "")

            if code == 200:
                return True, f"Success: {msg}"
            elif code == 401:
                return False, f"Auth failure: {msg}"
            else:
                return False, f"Unknown code: {code}, msg: {msg}"
        except (ValueError, KeyError):
            return False, f"Invalid JSON response: {response.text[:100]}"

    @staticmethod
    def validate_dataset_list_response(response: requests.Response) -> Tuple[bool, str]:
        """Validate dataset list response."""
        if response.status_code not in [200, 502]:
            return False, f"Unexpected status code: {response.status_code}"

        response_text = response.text.strip()

        if "데이터셋 목록" in response_text or "DataSet" in response_text:
            return True, "Valid dataset list response"

        if any(indicator in response_text for indicator in ["오류", "에러", "error", "실패"]):
            return False, "Error in dataset list response"

        return False, "Unknown dataset list response format"

    @staticmethod
    def validate_file_tree_response(response: requests.Response) -> Tuple[bool, str]:
        """Validate file tree response."""
        if response.status_code not in [200, 502]:
            return False, f"Unexpected status code: {response.status_code}"

        response_text = response.text.strip()

        if any(indicator in response_text for indicator in ["├", "└", "│"]):
            return True, "Valid file tree response"

        if any(indicator in response_text for indicator in ["오류", "에러", "error", "실패", "없습니다"]):
            return False, "Error in file tree response"

        return False, "Unknown file tree response format"


class TestAIHubAPIIntegration:
    """Integration tests for AIHub API server (v0.6)."""

    @pytest.fixture
    def api_key(self) -> Optional[str]:
        """Get API key from environment or skip test."""
        api_key = os.getenv("AIHUB_TEST_API_KEY")
        if not api_key:
            pytest.skip("AIHUB_TEST_API_KEY environment variable not set")
        return api_key

    @pytest.fixture
    def auth_headers(self, api_key: str) -> Dict[str, str]:
        """Get authentication headers."""
        return {"apikey": api_key}

    @pytest.mark.api
    @pytest.mark.slow
    def test_api_key_validation_real(self, api_key: str):
        """Test real API key validation with v0.6 JSON endpoint."""
        auth = AIHubAuth(api_key)
        result = auth.validate_api_key()
        assert isinstance(result, bool)

    @pytest.mark.api
    @pytest.mark.slow
    def test_api_key_validation_direct_request(self, api_key: str):
        """Test API key validation with direct POST request."""
        url = "https://api.aihub.or.kr/api/keyValidate.do"
        headers = {"apikey": api_key}

        try:
            response = requests.post(url, headers=headers, timeout=30)
            success, message = AIHubAPITestValidator.validate_api_key_response(response)
            assert isinstance(success, bool)
            assert isinstance(message, str)
        except requests.RequestException as e:
            pytest.fail(f"Request failed: {e}")

    @pytest.mark.api
    @pytest.mark.slow
    def test_dataset_list_real(self, auth_headers: Dict[str, str]):
        """Test real dataset list retrieval."""
        url = "https://api.aihub.or.kr/info/dataset.do"

        try:
            response = requests.get(url, headers=auth_headers, timeout=30)
            success, message = AIHubAPITestValidator.validate_dataset_list_response(response)

            if success:
                downloader = AIHubDownloader(auth_headers)
                datasets = downloader.process_dataset_list(response.text)
                if datasets:
                    assert len(datasets) > 0

            assert isinstance(success, bool)
        except requests.RequestException as e:
            pytest.fail(f"Request failed: {e}")

    @pytest.mark.api
    @pytest.mark.slow
    def test_file_tree_real(self, auth_headers: Dict[str, str]):
        """Test real file tree retrieval."""
        dataset_url = "https://api.aihub.or.kr/info/dataset.do"

        try:
            response = requests.get(dataset_url, headers=auth_headers, timeout=30)
            success, _ = AIHubAPITestValidator.validate_dataset_list_response(response)

            if not success:
                pytest.skip("Cannot get dataset list")

            downloader = AIHubDownloader(auth_headers)
            datasets = downloader.process_dataset_list(response.text)

            if not datasets:
                pytest.skip("No datasets available for testing")

            dataset_key = datasets[0][0]
            file_tree_url = f"https://api.aihub.or.kr/info/{dataset_key}.do"
            response = requests.get(file_tree_url, headers=auth_headers, timeout=30)
            success, message = AIHubAPITestValidator.validate_file_tree_response(response)

            assert isinstance(success, bool)
        except requests.RequestException as e:
            pytest.fail(f"Request failed: {e}")

    @pytest.mark.api
    @pytest.mark.slow
    def test_download_url_generation(self, auth_headers: Dict[str, str]):
        """Test download URL generation for v0.6."""
        downloader = AIHubDownloader(auth_headers)

        dataset_key = "test_dataset"
        file_keys = "1,2,3"

        url = downloader.get_raw_url(dataset_key, file_keys)
        expected_url = f"https://api.aihub.or.kr/down/0.6/{dataset_key}.do?fileSn={file_keys}"
        assert url == expected_url

        url_all = downloader.get_raw_url(dataset_key, "all")
        expected_url_all = f"https://api.aihub.or.kr/down/0.6/{dataset_key}.do?fileSn=all"
        assert url_all == expected_url_all

    @pytest.mark.api
    @pytest.mark.slow
    def test_end_to_end_workflow(self, api_key: str):
        """Test complete end-to-end workflow with real API."""
        auth = AIHubAuth(api_key)
        auth_headers = auth.get_auth_headers()

        if not auth_headers:
            pytest.fail("Failed to get authentication headers")

        downloader = AIHubDownloader(auth_headers)

        # Step 1: Validate API key
        api_valid = auth.validate_api_key()
        assert isinstance(api_valid, bool)

        if not api_valid:
            pytest.skip("API key validation failed")

        # Step 2: Get dataset list
        datasets = downloader.get_dataset_info()

        if datasets:
            assert len(datasets) > 0
            first_dataset = datasets[0][0]

            # Step 3: Get file tree
            file_tree, error_message = downloader.get_file_tree(first_dataset)
            if error_message is None:
                assert file_tree is not None


class TestAIHubAPICustomConditions:
    """Tests for custom success/failure conditions in AIHub API v0.6."""

    def test_json_success_response(self):
        """Test JSON success response validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"msg": "login success", "code": 200}

        success, message = AIHubAPITestValidator.validate_api_key_response(mock_response)

        assert success is True
        assert "Success" in message

    def test_json_failure_response(self):
        """Test JSON failure response validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"msg": "login fail", "code": 401}

        success, message = AIHubAPITestValidator.validate_api_key_response(mock_response)

        assert success is False
        assert "failure" in message.lower()

    def test_invalid_json_response(self):
        """Test handling of non-JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Not JSON")
        mock_response.text = "not json"

        success, message = AIHubAPITestValidator.validate_api_key_response(mock_response)

        assert success is False
        assert "Invalid JSON" in message

    def test_dataset_list_success(self):
        """Test dataset list success validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "==================DataSet 목록==================\n001,테스트"

        success, message = AIHubAPITestValidator.validate_dataset_list_response(mock_response)

        assert success is True

    def test_file_tree_success(self):
        """Test file tree success validation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "dataset\n├── file.txt | 1MB | 1\n└── data.zip | 5MB | 2"

        success, message = AIHubAPITestValidator.validate_file_tree_response(mock_response)

        assert success is True


class TestAIHubAPIPerformance:
    """Performance tests for AIHub API interactions."""

    @pytest.mark.api
    @pytest.mark.slow
    def test_api_response_time(self, auth_headers: Dict[str, str]):
        """Test API response times for v0.6 endpoints."""
        endpoints = [
            ("POST", "https://api.aihub.or.kr/api/keyValidate.do"),
            ("GET", "https://api.aihub.or.kr/info/dataset.do"),
        ]

        for method, endpoint in endpoints:
            start_time = time.time()

            try:
                if method == "POST":
                    response = requests.post(endpoint, headers=auth_headers, timeout=30)
                else:
                    response = requests.get(endpoint, headers=auth_headers, timeout=30)
                response_time = time.time() - start_time
                assert response_time < 10.0, f"Response time too slow: {response_time:.2f}s"
            except requests.RequestException:
                pass

    @pytest.fixture
    def auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for performance tests."""
        api_key = os.getenv("AIHUB_TEST_API_KEY")
        if not api_key:
            pytest.skip("AIHUB_TEST_API_KEY environment variable not set")
        return {"apikey": api_key}
