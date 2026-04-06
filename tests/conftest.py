#!/usr/bin/env python3
#
# AIHubKR Test Configuration
# Shared fixtures and test utilities for AIHub API testing (v0.6)
#
# - Common test fixtures for API mocking
# - Response simulation utilities
# - Test data and constants
#
# @author Jung-In An <ji5489@gmail.com>

import os
import tempfile
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import Mock

import pytest
import responses


class AIHubTestResponses:
    """Test response data for AIHub API v0.6 endpoints."""

    # API Key Validation Responses (POST /api/keyValidate.do → JSON)
    VALID_API_KEY_RESPONSE = '{"msg":"login success","code":200}'
    INVALID_API_KEY_RESPONSE = '{"msg":"login fail","code":401}'

    # Dataset List Response
    DATASET_LIST_RESPONSE = """UTF-8
output normally
modify the character information
================================================================================
공지사항
================================================================================

================================================================================
데이터셋 목록
================================================================================
001,한국어 대화 데이터셋
002,이미지 분류 데이터셋
003,텍스트 분석 데이터셋
================================================================================
"""

    # Data Package List Response
    DATAPACKAGE_LIST_RESPONSE = """UTF-8
output normally
modify the character information
==================DataPackage 목록==================
6, 국내 여행로그 분석
5, 한-다국어 번역 말뭉치
4, 한-영 번역 말뭉치
==========================================
"""

    # File Tree Response
    FILE_TREE_RESPONSE = """UTF-8
output normally
modify the character information
dataset_001
├── README.txt | 1.5KB | 1
├── data/
│   ├── train/
│   │   ├── file1.txt | 2.3MB | 2
│   │   └── file2.txt | 1.8MB | 3
│   └── test/
│       └── test.txt | 500KB | 4
└── metadata.json | 15KB | 5"""

    # Download Response (failure - privilege error, HTTP 502)
    DOWNLOAD_PRIVILEGE_ERROR = "다운로드 서비스는 홈페이지(https://aihub.or.kr)에서 신청 및 승인 후 이용 가능 합니다."

    # Download Response (failure - old version rejected)
    DOWNLOAD_VERSION_REJECTED = "aihubshell 신규 버전을 다운로드해 주시기 바랍니다."


class AIHubTestUtils:
    """Utility functions for AIHub API testing."""

    @staticmethod
    def create_mock_response(
        status_code: int,
        content: str,
        headers: Optional[Dict[str, str]] = None
    ) -> Mock:
        """Create a mock response object for testing."""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.text = content
        mock_response.headers = headers or {}
        return mock_response

    @staticmethod
    def get_test_api_key() -> str:
        """Get a test API key for testing purposes."""
        return "test-api-key-12345"

    @staticmethod
    def get_test_dataset_key() -> str:
        """Get a test dataset key for testing purposes."""
        return "001"


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test file operations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_api_responses():
    """Mock AIHub API v0.6 responses for testing."""
    with responses.RequestsMock() as rsps:
        # Mock API key validation endpoint (POST, JSON response)
        rsps.add(
            responses.POST,
            "https://api.aihub.or.kr/api/keyValidate.do",
            body=AIHubTestResponses.VALID_API_KEY_RESPONSE,
            status=200,
            content_type="application/json"
        )

        # Mock dataset list endpoint
        rsps.add(
            responses.GET,
            "https://api.aihub.or.kr/info/dataset.do",
            body=AIHubTestResponses.DATASET_LIST_RESPONSE,
            status=200,
            content_type="text/plain"
        )

        # Mock file tree endpoint
        rsps.add(
            responses.GET,
            "https://api.aihub.or.kr/info/001.do",
            body=AIHubTestResponses.FILE_TREE_RESPONSE,
            status=200,
            content_type="text/plain"
        )

        # Mock data package list endpoint
        rsps.add(
            responses.GET,
            "https://api.aihub.or.kr/info/datapckage.do",
            body=AIHubTestResponses.DATAPACKAGE_LIST_RESPONSE,
            status=502,
            content_type="text/plain"
        )

        yield rsps


@pytest.fixture
def test_api_key():
    """Provide a test API key."""
    return AIHubTestUtils.get_test_api_key()


@pytest.fixture
def test_dataset_key():
    """Provide a test dataset key."""
    return AIHubTestUtils.get_test_dataset_key()


@pytest.fixture
def auth_headers(test_api_key):
    """Provide authentication headers for testing."""
    return {"apikey": test_api_key}


@pytest.fixture
def mock_config():
    """Mock configuration for testing."""
    config_data = {
        "api_key": "test-api-key-12345",
        "version": "3"
    }
    return config_data


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Ensure clean environment between tests — no AIHUB_APIKEY set by default."""
    saved = os.environ.pop("AIHUB_APIKEY", None)
    yield
    # Restore or clean up
    if saved is not None:
        os.environ["AIHUB_APIKEY"] = saved
    elif "AIHUB_APIKEY" in os.environ:
        del os.environ["AIHUB_APIKEY"]
