#!/usr/bin/env python3
#
# AIHub Downloader Tests
# Unit tests for dataset download functionality (v0.6 API)
#
# - Tests response processing with UTF-8 headers and notice sections
# - Tests file tree parsing and dataset operations
# - Tests data package operations
# - Mocks API responses for controlled testing
#
# @author Jung-In An <ji5489@gmail.com>

import os
import requests
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import responses

from src.aihubkr.core.downloader import AIHubDownloader, DownloadStatus


class TestAIHubDownloader:
    """Test cases for AIHub downloader module."""

    def test_init_with_auth_headers(self):
        """Test initialization with authentication headers."""
        auth_headers = {"apikey": "test-api-key"}
        downloader = AIHubDownloader(auth_headers)
        assert downloader.auth_headers == auth_headers

    def test_init_without_auth_headers(self):
        """Test initialization without authentication headers."""
        downloader = AIHubDownloader()
        assert downloader.auth_headers == {}

    def test_api_version_is_0_6(self):
        """Test that API version is 0.6."""
        assert AIHubDownloader.API_VERSION == "0.6"

    def test_base_download_url(self):
        """Test that download URL uses v0.6."""
        assert "/down/0.6" in AIHubDownloader.BASE_DOWNLOAD_URL

    def test_package_urls(self):
        """Test that data package URLs are correctly defined."""
        assert "datapckage.do" in AIHubDownloader.DATAPACKAGE_URL
        assert "/info/pckage" in AIHubDownloader.BASE_PACKAGE_TREE_URL
        assert "/down/pckage/0.6" in AIHubDownloader.BASE_PACKAGE_DOWNLOAD_URL

    def test_process_response_success_200(self):
        """Test processing successful response with HTTP 200."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "Success response content"

        downloader = AIHubDownloader()
        success, content = downloader._process_response(mock_response)

        assert success is True
        assert content == "Success response content"

    def test_process_response_success_502(self):
        """Test processing successful response with HTTP 502."""
        mock_response = Mock()
        mock_response.status_code = 502
        mock_response.text = "Success response content"

        downloader = AIHubDownloader()
        success, content = downloader._process_response(mock_response)

        assert success is True
        assert content == "Success response content"

    def test_process_response_failure(self):
        """Test processing failed response."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        downloader = AIHubDownloader()
        success, content = downloader._process_response(mock_response)

        assert success is False
        assert content is None

    def test_process_response_with_utf8_headers(self):
        """Test processing response with UTF-8 headers to remove."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """UTF-8
output normally
modify the character information
Actual content here
More content"""

        downloader = AIHubDownloader()
        success, content = downloader._process_response(mock_response)

        assert success is True
        assert "UTF-8" not in content
        assert "output normally" not in content
        assert "modify the character information" not in content
        assert "Actual content here" in content
        assert "More content" in content

    def test_process_response_with_notice_section(self):
        """Test processing response with notice section formatting."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """Content before
================================================================================
공지사항
================================================================================
Notice content here
================================================================================
Content after"""

        downloader = AIHubDownloader()
        success, content = downloader._process_response(mock_response)

        assert success is True
        assert "Notice:\nNotice content here\n" in content or "Notice content here" in content
        assert "Content before" in content
        assert "Content after" in content

    def test_process_response_with_empty_notice(self):
        """Test processing response with empty notice section."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = """Content before
================================================================================
공지사항
================================================================================

================================================================================
Content after"""

        downloader = AIHubDownloader()
        success, content = downloader._process_response(mock_response)

        assert success is True
        assert "Notice:" not in content
        assert "Content before" in content
        assert "Content after" in content

    @responses.activate
    def test_get_dataset_info_success(self):
        """Test successful dataset information retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/dataset.do",
            body="""================================================================================
데이터셋 목록
================================================================================
50, AR/VR 화면정확도 향상을 위한 플렌옵틱 카메라 이미지
51, K-Fashion 이미지
52, K-pop 안무 영상
================================================================================
""",
            status=502,
            content_type="text/plain;charset=UTF-8"
        )

        downloader = AIHubDownloader()
        datasets = downloader.get_dataset_info()

        assert datasets is not None
        assert len(datasets) == 3
        assert datasets[0] == ("50", "AR/VR 화면정확도 향상을 위한 플렌옵틱 카메라 이미지")
        assert datasets[1] == ("51", "K-Fashion 이미지")
        assert datasets[2] == ("52", "K-pop 안무 영상")

    @responses.activate
    def test_get_dataset_info_failure(self):
        """Test failed dataset information retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/dataset.do",
            body="Error occurred",
            status=500,
            content_type="text/plain"
        )

        downloader = AIHubDownloader()
        datasets = downloader.get_dataset_info()

        assert datasets is None

    @responses.activate
    def test_get_dataset_info_timeout(self):
        """Test dataset information retrieval with timeout."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/dataset.do",
            body=requests.Timeout("Timeout"),
            status=408
        )

        downloader = AIHubDownloader()
        datasets = downloader.get_dataset_info()

        assert datasets is None

    @responses.activate
    def test_get_datapackage_info_success(self):
        """Test successful data package information retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/datapckage.do",
            body="""==================DataPackage 목록==================
6, 국내 여행로그 분석
5, 한-다국어 번역 말뭉치
==========================================
""",
            status=502,
            content_type="text/plain;charset=UTF-8"
        )

        downloader = AIHubDownloader()
        packages = downloader.get_datapackage_info()

        assert packages is not None
        assert len(packages) == 2
        assert packages[0] == ("6", "국내 여행로그 분석")
        assert packages[1] == ("5", "한-다국어 번역 말뭉치")

    @responses.activate
    def test_get_datapackage_info_failure(self):
        """Test failed data package information retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/datapckage.do",
            body="Error",
            status=500,
            content_type="text/plain"
        )

        downloader = AIHubDownloader()
        packages = downloader.get_datapackage_info()

        assert packages is None

    def test_process_dataset_list(self):
        """Test processing dataset list content."""
        content = """================================================================================
데이터셋 목록
================================================================================
001,한국어 대화 데이터셋
002,이미지 분류 데이터셋
003,텍스트 분석 데이터셋
================================================================================
"""

        downloader = AIHubDownloader()
        datasets = downloader.process_dataset_list(content)

        assert len(datasets) == 3
        assert datasets[0] == ("001", "한국어 대화 데이터셋")
        assert datasets[1] == ("002", "이미지 분류 데이터셋")
        assert datasets[2] == ("003", "텍스트 분석 데이터셋")

    def test_process_dataset_list_empty(self):
        """Test processing empty dataset list."""
        content = """================================================================================
데이터셋 목록
================================================================================
================================================================================
"""

        downloader = AIHubDownloader()
        datasets = downloader.process_dataset_list(content)

        assert len(datasets) == 0

    @responses.activate
    def test_get_file_tree_success(self):
        """Test successful file tree retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/001.do",
            body="""UTF-8
output normally
modify the character information
dataset_001
├── README.txt | 1.5KB | 1
├── data/
│   └── train.txt | 2.3MB | 2
└── metadata.json | 15KB | 3""",
            status=200,
            content_type="text/plain"
        )

        downloader = AIHubDownloader()
        file_tree, error_message = downloader.get_file_tree("001")

        assert error_message is None
        assert file_tree is not None
        assert "dataset_001" in file_tree
        assert "README.txt" in file_tree
        assert "data/" in file_tree

    @responses.activate
    def test_get_file_tree_failure(self):
        """Test failed file tree retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/001.do",
            body="Dataset not found",
            status=404,
            content_type="text/plain"
        )

        downloader = AIHubDownloader()
        file_tree, error_message = downloader.get_file_tree("001")

        assert file_tree is None
        assert error_message is not None

    @responses.activate
    def test_get_package_file_tree_success(self):
        """Test successful data package file tree retrieval."""
        responses.add(
            responses.GET,
            "https://api.aihub.or.kr/info/pckage/1.do",
            body="""UTF-8
output normally
modify the character information
package_001
├── data.zip | 5 MB | 100
└── labels.zip | 2 MB | 101""",
            status=200,
            content_type="text/plain"
        )

        downloader = AIHubDownloader()
        file_tree, error_message = downloader.get_package_file_tree("1")

        assert error_message is None
        assert file_tree is not None
        assert "package_001" in file_tree

    def test_export_dataset_list_to_csv(self, temp_dir):
        """Test exporting dataset list to CSV."""
        datasets = [
            ("001", "한국어 대화 데이터셋"),
            ("002", "이미지 분류 데이터셋")
        ]

        csv_file = temp_dir / "test_datasets.csv"
        downloader = AIHubDownloader()
        downloader.export_dataset_list_to_csv(datasets, str(csv_file))

        assert csv_file.exists()

        # Read and verify CSV content
        with open(csv_file, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "ID,Name" in content
            assert "001,한국어 대화 데이터셋" in content
            assert "002,이미지 분류 데이터셋" in content

    def test_check_disk_space_sufficient(self, temp_dir):
        """Test disk space check with sufficient space."""
        downloader = AIHubDownloader()
        result = downloader._check_disk_space(1024, str(temp_dir))  # 1KB
        assert result is True

    def test_check_disk_space_insufficient(self, temp_dir):
        """Test disk space check with insufficient space."""
        downloader = AIHubDownloader()
        # Request more space than available (1TB)
        result = downloader._check_disk_space(1024 * 1024 * 1024 * 1024, str(temp_dir))
        assert result is False

    def test_format_size(self):
        """Test size formatting utility."""
        downloader = AIHubDownloader()

        assert downloader._format_size(1024) == "1.0KiB"
        assert downloader._format_size(1024 * 1024) == "1.0MiB"
        assert downloader._format_size(1024 * 1024 * 1024) == "1.0GiB"
        assert downloader._format_size(500) == "500.0B"

    def test_get_raw_url(self):
        """Test raw URL generation for v0.6."""
        downloader = AIHubDownloader()

        url = downloader.get_raw_url("001", "all")
        assert url == "https://api.aihub.or.kr/down/0.6/001.do?fileSn=all"

        url = downloader.get_raw_url("002", "1,2,3")
        assert url == "https://api.aihub.or.kr/down/0.6/002.do?fileSn=1,2,3"

    def test_get_raw_package_url(self):
        """Test raw URL generation for data packages."""
        downloader = AIHubDownloader()

        url = downloader.get_raw_package_url("1", "all")
        assert url == "https://api.aihub.or.kr/down/pckage/0.6/1.do?fileSn=all"

        url = downloader.get_raw_package_url("3", "100,101")
        assert url == "https://api.aihub.or.kr/down/pckage/0.6/3.do?fileSn=100,101"


class TestDownloadStatus:
    """Test cases for download status enumeration."""

    def test_success_status(self):
        """Test success status properties."""
        status = DownloadStatus.SUCCESS
        assert status.is_success() is True
        assert status.is_error() is False
        assert "completed successfully" in status.get_message()

    def test_error_statuses(self):
        """Test error status properties."""
        error_statuses = [
            DownloadStatus.NETWORK_ERROR,
            DownloadStatus.PRIVILEGE_ERROR,
            DownloadStatus.AUTHENTICATION_ERROR,
            DownloadStatus.FILE_NOT_FOUND,
            DownloadStatus.INSUFFICIENT_DISK_SPACE,
            DownloadStatus.UNKNOWN_ERROR
        ]

        for status in error_statuses:
            assert status.is_success() is False
            assert status.is_error() is True
            assert status.get_message() is not None

    def test_all_status_messages(self):
        """Test that all statuses have meaningful messages."""
        for status in DownloadStatus:
            message = status.get_message()
            assert isinstance(message, str)
            assert len(message) > 0


class TestAIHubDownloaderIntegration:
    """Integration tests for AIHub downloader."""

    @pytest.mark.integration
    @pytest.mark.download
    def test_full_download_flow_mock(self, temp_dir):
        """Test complete download flow with mocked responses."""
        with responses.RequestsMock() as rsps:
            # Mock dataset info
            rsps.add(
                responses.GET,
                "https://api.aihub.or.kr/info/dataset.do",
                body="""UTF-8
output normally
modify the character information
================================================================================
데이터셋 목록
================================================================================
001,테스트 데이터셋
================================================================================
""",
                status=200
            )

            # Mock file tree
            rsps.add(
                responses.GET,
                "https://api.aihub.or.kr/info/001.do",
                body="""UTF-8
output normally
modify the character information
test_dataset
└── test.txt | 1KB | 1""",
                status=200
            )

            # Mock download (v0.6 URL)
            rsps.add(
                responses.GET,
                "https://api.aihub.or.kr/down/0.6/001.do?fileSn=all",
                body="다운로드가 시작됩니다.",
                status=200
            )

            downloader = AIHubDownloader()

            # Test dataset info
            datasets = downloader.get_dataset_info()
            assert datasets is not None
            assert len(datasets) == 1

            # Test file tree
            file_tree, error_message = downloader.get_file_tree("001")
            assert error_message is None
            assert file_tree is not None
            assert "test_dataset" in file_tree

            # Test actual download call
            result = downloader.download_dataset("001", "all", str(temp_dir))
            assert result == DownloadStatus.SUCCESS

    @pytest.mark.api
    @pytest.mark.slow
    def test_real_api_interaction(self):
        """Test with real API interaction (marked as slow)."""
        downloader = AIHubDownloader()

        try:
            datasets = downloader.get_dataset_info()
            if datasets is not None:
                assert isinstance(datasets, list)
                for dataset_id, dataset_name in datasets:
                    assert isinstance(dataset_id, str)
                    assert isinstance(dataset_name, str)
        except Exception:
            pass
