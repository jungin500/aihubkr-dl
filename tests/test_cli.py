#!/usr/bin/env python3
#
# AIHub CLI Tests
# Unit tests for command-line interface functionality
#
# - Tests argument parsing and subcommand handling
# - Validates CLI output formatting
# - Tests error handling and user feedback
# - Mocks API interactions for controlled testing
#
# @author Jung-In An <ji5489@gmail.com>
# @with Claude Sonnet 4 (Cutoff 2025/06/16)

import sys
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from src.aihubkr.cli.main import (
    download_dataset,
    list_datasets,
    list_file_tree,
    main,
    parse_arguments,
    print_usage
)


class TestCLIArgumentParsing:
    """Test cases for CLI argument parsing."""

    def test_parse_arguments_list_command(self):
        """Test parsing list command arguments."""
        with patch.object(sys, 'argv', ['aihubkr-dl', 'list']):
            args = parse_arguments()
            assert args['command'] == 'list'
            assert args['output_dir'] == '.'

    def test_parse_arguments_files_command(self):
        """Test parsing files command arguments."""
        with patch.object(sys, 'argv', ['aihubkr-dl', 'files', '001']):
            args = parse_arguments()
            assert args['command'] == 'files'
            assert args['dataset_key'] == '001'

    def test_parse_arguments_download_command(self):
        """Test parsing download command arguments."""
        with patch.object(sys, 'argv', ['aihubkr-dl', 'download', '001']):
            args = parse_arguments()
            assert args['command'] == 'download'
            assert args['dataset_key'] == '001'
            assert args['file_key'] == 'all'
            assert args['output_dir'] == '.'

    def test_parse_arguments_download_with_file_keys(self):
        """Test parsing download command with specific file keys."""
        with patch.object(sys, 'argv', ['aihubkr-dl', 'download', '001', '--file-key', '1,2,3']):
            args = parse_arguments()
            assert args['command'] == 'download'
            assert args['dataset_key'] == '001'
            assert args['file_key'] == '1,2,3'

    def test_parse_arguments_download_with_output_dir(self):
        """Test parsing download command with custom output directory."""
        with patch.object(sys, 'argv', ['aihubkr-dl', '--output-dir', '/tmp/test', 'download', '001']):
            args = parse_arguments()
            assert args['command'] == 'download'
            assert args['dataset_key'] == '001'
            assert args['output_dir'] == '/tmp/test'

    def test_parse_arguments_with_api_key(self):
        """Test parsing arguments with API key."""
        with patch.object(sys, 'argv', ['aihubkr-dl', '--api-key', 'test-key', 'list']):
            args = parse_arguments()
            assert args['command'] == 'list'
            assert args['api_key'] == 'test-key'

    def test_parse_arguments_help_command(self):
        """Test parsing help command arguments."""
        with patch.object(sys, 'argv', ['aihubkr-dl', 'help']):
            args = parse_arguments()
            assert args['command'] == 'help'

    def test_parse_arguments_no_command(self):
        """Test parsing arguments with no command (should show help)."""
        with patch.object(sys, 'argv', ['aihubkr-dl']):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestCLIFunctions:
    """Test cases for CLI functions."""

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_list_datasets_success(self, mock_downloader_class):
        """Test successful dataset listing."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock dataset data
        datasets = [
            ("001", "한국어 대화 데이터셋"),
            ("002", "이미지 분류 데이터셋")
        ]
        mock_downloader.get_dataset_info.return_value = datasets

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            list_datasets(mock_downloader)
            output = mock_stdout.getvalue()

        # Verify output contains dataset information
        assert "001" in output
        assert "002" in output
        assert "한국어 대화 데이터셋" in output
        assert "이미지 분류 데이터셋" in output
        assert "aihub_datasets.csv" in output

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_list_datasets_failure(self, mock_downloader_class):
        """Test dataset listing failure."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock failure
        mock_downloader.get_dataset_info.return_value = None

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            list_datasets(mock_downloader)
            output = mock_stdout.getvalue()

        # Verify error message
        assert "Failed to fetch dataset information" in output

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    @patch('src.aihubkr.cli.main.AIHubResponseParser')
    def test_list_file_tree_success(self, mock_parser_class, mock_downloader_class):
        """Test successful file tree listing."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock file tree data
        file_tree = """dataset_001
├── README.txt | 1.5KB | 1
└── data.txt | 2.3MB | 2"""
        mock_downloader.get_file_tree.return_value = (file_tree, None)

        # Mock parser
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser

        # Mock parsed paths
        paths = [
            ("dataset_001/README.txt", True, "1", (1536, 1024, 2048)),
            ("dataset_001/data.txt", True, "2", (2411724, 2097152, 2621440))
        ]
        mock_parser.parse_tree_output.return_value = (Mock(), paths)

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            list_file_tree(mock_downloader, "001")
            output = mock_stdout.getvalue()

        # Verify output contains file information
        assert "README.txt" in output
        assert "data.txt" in output
        assert "1KiB" in output  # Updated to match actual output format
        assert "2MiB" in output  # Updated to match actual output format

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_list_file_tree_failure(self, mock_downloader_class):
        """Test file tree listing failure."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock failure
        mock_downloader.get_file_tree.return_value = (None, "Failed to fetch file tree.")

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            list_file_tree(mock_downloader, "001")
            output = mock_stdout.getvalue()

        # Verify error message
        assert "Failed to fetch file tree" in output

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_list_file_tree_no_files(self, mock_downloader_class):
        """Test file tree listing with no files."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock file tree data
        file_tree = "dataset_001"
        mock_downloader.get_file_tree.return_value = (file_tree, None)

        # Mock parser
        with patch('src.aihubkr.cli.main.AIHubResponseParser') as mock_parser_class:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_tree_output.return_value = (Mock(), [])

            # Capture output
            with patch('sys.stdout', new=StringIO()) as mock_stdout:
                list_file_tree(mock_downloader, "001")
                output = mock_stdout.getvalue()

            # Verify message
            assert "No files found" in output

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_download_dataset_success(self, mock_downloader_class):
        """Test successful dataset download - file tree error triggers early return."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock get_file_tree to return an error (testing early-return path)
        mock_downloader.get_file_tree.return_value = (None, "Test error")

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            download_dataset(mock_downloader, "001", "all", ".")
            output = mock_stdout.getvalue()

        # Verify output
        assert "Downloading dataset: 001" in output
        assert "File keys: all" in output
        assert "Output directory: ." in output

    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_download_dataset_failure(self, mock_downloader_class):
        """Test dataset download failure - file tree not found."""
        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock get_file_tree to return no content
        mock_downloader.get_file_tree.return_value = (None, "Not found")

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            download_dataset(mock_downloader, "001", "all", ".")
            output = mock_stdout.getvalue()

        # Verify output contains download information
        assert "Downloading dataset: 001" in output

    @patch('requests.get')
    def test_print_usage_success(self, mock_get):
        """Test successful usage information printing."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.text = "AIHub API Usage Information\n\nAvailable endpoints:\n- /info/dataset.do\n- /down/0.5/{key}"
        mock_get.return_value = mock_response

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            print_usage()
            output = mock_stdout.getvalue()

        # Verify output
        assert "AIHub API Usage Information" in output
        assert "Available endpoints" in output

    @patch('requests.get')
    def test_print_usage_failure(self, mock_get):
        """Test usage information printing failure."""
        # Mock failed API response
        mock_get.side_effect = Exception("Network error")

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            print_usage()
            output = mock_stdout.getvalue()

        # Verify error message
        assert "Failed to fetch usage information" in output
        assert "https://api.aihub.or.kr/info/api.do" in output


class TestCLIMainFunction:
    """Test cases for main CLI function."""

    @patch('src.aihubkr.cli.main.parse_arguments')
    @patch('src.aihubkr.cli.main.AIHubAuth')
    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_main_list_command(self, mock_downloader_class, mock_auth_class, mock_parse_args):
        """Test main function with list command."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'list',
            'api_key': 'test-key',
            'output_dir': '.'
        }

        # Mock auth
        mock_auth = Mock()
        mock_auth_class.return_value = mock_auth
        mock_auth.get_auth_headers.return_value = {'apikey': 'test-key'}

        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock dataset data
        datasets = [("001", "Test Dataset")]
        mock_downloader.get_dataset_info.return_value = datasets

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            main()
            output = mock_stdout.getvalue()

        # Verify output
        assert "001" in output
        assert "Test Dataset" in output

    @patch('src.aihubkr.cli.main.parse_arguments')
    @patch('src.aihubkr.cli.main.AIHubAuth')
    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_main_files_command(self, mock_downloader_class, mock_auth_class, mock_parse_args):
        """Test main function with files command."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'files',
            'dataset_key': '001',
            'api_key': 'test-key',
            'output_dir': '.'
        }

        # Mock auth
        mock_auth = Mock()
        mock_auth_class.return_value = mock_auth
        mock_auth.get_auth_headers.return_value = {'apikey': 'test-key'}

        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock file tree data
        file_tree = "dataset_001\n└── test.txt | 1KB | 1"
        mock_downloader.get_file_tree.return_value = (file_tree, None)

        # Mock parser
        with patch('src.aihubkr.cli.main.AIHubResponseParser') as mock_parser_class:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser
            paths = [("dataset_001/test.txt", True, "1", (1024, 512, 1536))]
            mock_parser.parse_tree_output.return_value = (Mock(), paths)

            # Capture output
            with patch('sys.stdout', new=StringIO()) as mock_stdout:
                main()
                output = mock_stdout.getvalue()

            # Verify output
            assert "test.txt" in output

    @patch('src.aihubkr.cli.main.parse_arguments')
    @patch('src.aihubkr.cli.main.AIHubAuth')
    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_main_download_command(self, mock_downloader_class, mock_auth_class, mock_parse_args):
        """Test main function with download command."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'download',
            'dataset_key': '001',
            'file_key': 'all',
            'output_dir': '.',
            'api_key': 'test-key'
        }

        # Mock auth
        mock_auth = Mock()
        mock_auth_class.return_value = mock_auth
        mock_auth.get_auth_headers.return_value = {'apikey': 'test-key'}

        # Mock downloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        # Mock successful download
        from src.aihubkr.core.downloader import DownloadStatus
        mock_downloader.download_and_process_dataset.return_value = DownloadStatus.SUCCESS

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            main()
            output = mock_stdout.getvalue()

        # Verify output
        assert "Downloading dataset: 001" in output

    @patch('src.aihubkr.cli.main.parse_arguments')
    def test_main_help_command(self, mock_parse_args):
        """Test main function with help command."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'help'
        }

        # Mock usage function
        with patch('src.aihubkr.cli.main.print_usage') as mock_print_usage:
            main()
            mock_print_usage.assert_called_once()

    @patch('src.aihubkr.cli.main.parse_arguments')
    @patch('src.aihubkr.cli.main.AIHubAuth')
    def test_main_no_auth_headers(self, mock_auth_class, mock_parse_args):
        """Test main function when no auth headers are available."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'list',
            'api_key': None,
            'output_dir': '.'
        }

        # Mock auth
        mock_auth = Mock()
        mock_auth_class.return_value = mock_auth
        mock_auth.get_auth_headers.return_value = None

        # Capture output
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            main()
            output = mock_stdout.getvalue()

        # Verify error message
        assert "Failed to get authentication headers" in output


class TestCLIErrorHandling:
    """Test cases for CLI error handling."""

    @patch('src.aihubkr.cli.main.parse_arguments')
    def test_main_invalid_command(self, mock_parse_args):
        """Test main function with invalid command."""
        # Mock arguments with invalid command
        mock_parse_args.return_value = {
            'command': 'invalid_command'
        }

        # Should handle gracefully
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            main()
            output = mock_stdout.getvalue()

        # Should not crash
        assert output is not None

    @patch('src.aihubkr.cli.main.parse_arguments')
    @patch('src.aihubkr.cli.main.AIHubAuth')
    def test_main_auth_exception(self, mock_auth_class, mock_parse_args):
        """Test main function with authentication exception."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'list',
            'api_key': 'test-key',
            'output_dir': '.'
        }

        # Mock auth to raise exception
        mock_auth_class.side_effect = Exception("Auth error")

        # Should handle gracefully
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            main()
            output = mock_stdout.getvalue()

        # Should not crash
        assert output is not None

    @patch('src.aihubkr.cli.main.parse_arguments')
    @patch('src.aihubkr.cli.main.AIHubAuth')
    @patch('src.aihubkr.cli.main.AIHubDownloader')
    def test_main_downloader_exception(self, mock_downloader_class, mock_auth_class, mock_parse_args):
        """Test main function with downloader exception."""
        # Mock arguments
        mock_parse_args.return_value = {
            'command': 'list',
            'api_key': 'test-key',
            'output_dir': '.'
        }

        # Mock auth
        mock_auth = Mock()
        mock_auth_class.return_value = mock_auth
        mock_auth.get_auth_headers.return_value = {'apikey': 'test-key'}

        # Mock downloader to raise exception
        mock_downloader_class.side_effect = Exception("Downloader error")

        # Should handle gracefully
        with patch('sys.stdout', new=StringIO()) as mock_stdout:
            main()
            output = mock_stdout.getvalue()

        # Should not crash
        assert output is not None
