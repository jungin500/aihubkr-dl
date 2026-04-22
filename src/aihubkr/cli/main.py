#!/usr/bin/env python3
#
# AIHub CLI Main Module
# Command-line interface for AIHub dataset and data package operations
#
# - Provides download, list, and help functionality for datasets and data packages
# - Uses API key authentication via POST /api/keyValidate.do
# - Version pinning to detect silent AIHub API updates
#
# @author Jung-In An <ji5489@gmail.com>

import argparse
import json
import os
import sys
from typing import Any, Dict

from ..core.api_version import check_api_version
from ..core.auth import AIHubAuth
from ..core.config import AIHubConfig
from ..core.downloader import AIHubDownloader, DownloadStatus
from ..core.filelist_parser import AIHubResponseParser, sizeof_fmt
from prettytable import PrettyTable
from tqdm import tqdm


def parse_arguments() -> Dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="AIHub Dataset Downloader CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                                    # List all available datasets
  %(prog)s files DATASET_KEY                       # List files in a dataset
  %(prog)s download DATASET_KEY                    # Download all files in a dataset
  %(prog)s download DATASET_KEY --file-key 1,2,3   # Download specific files
  %(prog)s package-list                            # List all data packages
  %(prog)s package-files PACKAGE_KEY               # List files in a data package
  %(prog)s package-download PACKAGE_KEY            # Download a data package
  %(prog)s help                                    # Show API usage information
        """
    )

    # Global options
    parser.add_argument(
        "--api-key",
        help="AIHub API key (can also use AIHUB_APIKEY environment variable)"
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for downloads (default: current directory)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass API version check (use if aihubkr-dl reports a version mismatch)"
    )

    # Subcommands
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
        metavar="COMMAND"
    )

    # List command
    subparsers.add_parser(
        "list",
        help="List all available datasets",
        description="List all available datasets and export to CSV"
    )

    # Files command
    files_parser = subparsers.add_parser(
        "files",
        help="List files in a specific dataset",
        description="Show file tree structure and sizes for a dataset"
    )
    files_parser.add_argument(
        "dataset_key",
        help="Dataset key to list files for"
    )

    # Download command
    download_parser = subparsers.add_parser(
        "download",
        help="Download a dataset",
        description="Download dataset files with progress tracking"
    )
    download_parser.add_argument(
        "dataset_key",
        help="Dataset key to download"
    )
    download_parser.add_argument(
        "--file-key",
        default="all",
        help="File key(s) to download, comma-separated (default: all files)"
    )
    download_parser.add_argument(
        "--check-space",
        action="store_true",
        help="Check available disk space before downloading"
    )

    # Package list command
    subparsers.add_parser(
        "package-list",
        help="List all available data packages",
        description="List all available data packages"
    )

    # Package files command
    package_files_parser = subparsers.add_parser(
        "package-files",
        help="List files in a data package",
        description="Show file tree structure and sizes for a data package"
    )
    package_files_parser.add_argument(
        "package_key",
        help="Data package key to list files for"
    )

    # Package download command
    package_download_parser = subparsers.add_parser(
        "package-download",
        help="Download a data package",
        description="Download data package files with progress tracking"
    )
    package_download_parser.add_argument(
        "package_key",
        help="Data package key to download"
    )
    package_download_parser.add_argument(
        "--file-key",
        default="all",
        help="File key(s) to download, comma-separated (default: all files)"
    )

    # Help command
    subparsers.add_parser(
        "help",
        help="Show API usage information",
        description="Display AIHub API usage information"
    )

    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    return vars(parser.parse_args())


def print_usage() -> None:
    """Print usage information from AIHub API.

    Note: The API returns non-standard JSON (unquoted datetime values),
    so we use regex extraction rather than json.loads().
    """
    import requests

    manual_url = "https://api.aihub.or.kr/info/api.do"
    try:
        response = requests.get(manual_url, timeout=15)
        text = response.text

        # Extract command entries using regex (API returns non-standard JSON)
        import re
        entries = re.findall(
            r'"ENGL_CMGG"\s*:\s*"([^"]*)".*?"KOREAN_CMGG"\s*:\s*"([^"]*)".*?"DETAIL_CN"\s*:\s*"([^"]*)"',
            text,
            re.DOTALL,
        )

        if not entries:
            # Fallback: print raw
            print(text)
            return

        print("\nAIHub API Usage Information")
        print("=" * 60)
        print(f"{'COMMAND':<15} {'OPTION':<20} DETAIL")
        print("-" * 60)

        for engl, korean, detail in entries:
            detail = detail.replace("\\n", "\n").replace("\\t", "\t").replace("\\/", "/")
            print(f"{engl:<15} {korean:<20} {detail}")
            print()

    except Exception as e:
        print(f"Failed to fetch usage information: {e}")
        print("Please visit https://api.aihub.or.kr/info/api.do for detailed usage information.")


def list_datasets(downloader: AIHubDownloader) -> None:
    """List all available datasets."""
    print("Fetching dataset list...")
    datasets = downloader.get_dataset_info()
    if datasets:
        table = PrettyTable(
            field_names=["Dataset Key", "Dataset Name"],
            align="l",
        )

        for dataset_id, dataset_name in datasets:
            table.add_row([dataset_id, dataset_name])

        print(table)

        # Export to CSV
        csv_filename = "aihub_datasets.csv"
        downloader.export_dataset_list_to_csv(datasets, csv_filename)
        print(f"Dataset list exported to {csv_filename}")
    else:
        print("Failed to fetch dataset information.")


def list_packages(downloader: AIHubDownloader) -> None:
    """List all available data packages."""
    print("Fetching data package list...")
    packages = downloader.get_datapackage_info()
    if packages:
        table = PrettyTable(
            field_names=["Package Key", "Package Name"],
            align="l",
        )

        for pkg_id, pkg_name in packages:
            table.add_row([pkg_id, pkg_name])

        print(table)
    else:
        print("Failed to fetch data package information.")


def list_file_tree(downloader: AIHubDownloader, dataset_key: str) -> None:
    """List file tree structure for a specific dataset."""
    print(f"Fetching file tree for dataset: {dataset_key}")
    file_tree, error_message = downloader.get_file_tree(dataset_key)
    if error_message:
        print(f"Error: {error_message}")
        return
    if not file_tree:
        print("No files found.")
        return

    _print_file_tree_table(file_tree)


def list_package_file_tree(downloader: AIHubDownloader, package_key: str) -> None:
    """List file tree structure for a data package."""
    print(f"Fetching file tree for data package: {package_key}")
    file_tree, error_message = downloader.get_package_file_tree(package_key)
    if error_message:
        print(f"Error: {error_message}")
        return
    if not file_tree:
        print("No files found.")
        return

    _print_file_tree_table(file_tree)


def _print_file_tree_table(file_tree: str) -> None:
    """Parse and print a file tree as a table."""
    parser = AIHubResponseParser()
    tree, paths = parser.parse_tree_output(file_tree)
    if not paths:
        print("No files found.")
        return

    table = PrettyTable(
        field_names=["File Key", "File Path", "File Size"],
        align="l",
    )
    total_file_size = 0
    for idx, (path, is_file, file_key, file_info) in enumerate(paths):
        if is_file:
            (file_display_size, file_min_size, file_max_size) = file_info
            table.add_row(
                [file_key, path, sizeof_fmt(file_display_size, ignore_float=True)],
                divider=idx == len(paths) - 1)
            total_file_size += file_display_size
        else:
            table.add_row(["-", path, "-"], divider=idx == len(paths) - 1)

    table.add_row(["", "Total File Size", sizeof_fmt(total_file_size)])
    print(table)


def download_dataset(
    downloader: AIHubDownloader, dataset_key: str, file_keys: str, output_dir: str = "."
) -> None:
    """Download a dataset."""
    print(f"Downloading dataset: {dataset_key}")
    print(f"File keys: {file_keys}")
    print(f"Output directory: {output_dir}")

    # Pre-download validation: fetch file tree and check disk space
    file_tree, error_message = downloader.get_file_tree(dataset_key)
    if error_message:
        print(f"Error: {error_message}")
        return
    if not file_tree:
        print(f"Failed to fetch file tree for dataset {dataset_key}")
        return

    parser = AIHubResponseParser()
    tree, paths = parser.parse_tree_output(file_tree)
    if not paths:
        print(f"No files found for dataset {dataset_key}")
        return

    file_paths = [item for item in paths if item[1]]
    file_db = {}

    for row, (path, _, file_key, (file_display_size, file_min_size, file_max_size)) in enumerate(file_paths):
        file_db[file_key] = (path, file_display_size, file_min_size, file_max_size)

    min_total_size = 0
    max_total_size = 0
    for filekey in file_keys.split(","):
        if filekey == "all":
            min_total_size = sum(file_db[key][2] for key in file_db)
            max_total_size = sum(file_db[key][3] for key in file_db)
            break
        if filekey not in file_db:
            print(f"File key {filekey} not found.")
            return
        min_total_size += file_db[filekey][2]
        max_total_size += file_db[filekey][3]

    fstat = os.statvfs(output_dir)
    available_space = fstat.f_frsize * fstat.f_bavail

    print(f"Estimated download size: {sizeof_fmt(min_total_size)} ~ {sizeof_fmt(max_total_size)}")
    print(f"Free disk space: {sizeof_fmt(available_space)}")

    if max_total_size > available_space:
        print("Insufficient disk space.")
        return

    # Download, extract, merge, and clean up (with progress bar)
    pbar = tqdm(
        total=max_total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
        desc="Downloading",
        dynamic_ncols=True,
    )
    total_adjusted = [False]

    def progress_cb(msg, pct, downloaded, speed):
        if downloaded < 0:
            # Phase transition (extract/merge): write above bar
            pbar.write(f"  {msg}")
            return
        # Adjust total from actual Content-Length on first real tick
        if pct > 0 and not total_adjusted[0]:
            actual_total = int(downloaded * 100 / pct)
            if actual_total != pbar.total:
                pbar.total = actual_total
                pbar.refresh()
            total_adjusted[0] = True
        pbar.n = downloaded
        pbar.refresh()

    try:
        status = downloader.download_and_process_dataset(
            dataset_key, file_keys, output_dir, progress_callback=progress_cb
        )
    finally:
        pbar.close()

    print(status.get_message())

    if status == DownloadStatus.PRIVILEGE_ERROR:
        form_url = f"https://aihub.or.kr/aihubdata/data/dwld.do?dataSetSn={dataset_key}"
        print(f"Please visit {form_url} and accept the terms before downloading.")
    elif status == DownloadStatus.AUTHENTICATION_ERROR:
        print("Please check your API key and try again.")
    elif status == DownloadStatus.FILE_NOT_FOUND:
        print("Please check the dataset key and file keys.")
    elif status == DownloadStatus.NETWORK_ERROR:
        print("Please check your internet connection and try again.")
    elif status == DownloadStatus.INSUFFICIENT_DISK_SPACE:
        print("Please free up space and try again.")


def prompt_api_key() -> str:
    """Prompt user for API key."""
    from getpass import getpass

    while True:
        api_key = getpass(prompt="Enter your AIHub API key: ").strip()
        if not api_key:
            print("API key cannot be empty.")
            continue
        return api_key


def main() -> None:
    try:
        args = parse_arguments()

        # Handle help command (no auth needed)
        if args["command"] == "help":
            print_usage()
            return

        # Version check
        force = args.get("force", False)
        is_compatible, version_msg = check_api_version(force=force)
        if not is_compatible:
            print(f"ERROR: {version_msg}")
            sys.exit(1)

        # Get API key
        api_key = args.get("api_key")
        if not api_key:
            # Try to get from environment variable
            api_key = os.environ.get("AIHUB_APIKEY")

        if not api_key:
            # Try to load from saved credentials
            auth = AIHubAuth()
            api_key = auth.load_credentials()

        if not api_key:
            # Prompt user for API key
            api_key = prompt_api_key()
            auth = AIHubAuth(api_key)
            auth.save_credential()
        else:
            auth = AIHubAuth(api_key)

        # Validate API key
        if not auth.validate_api_key():
            print("Invalid API key. Please check your API key and try again.")
            return

        # Get authentication headers
        auth_headers = auth.get_auth_headers()
        if not auth_headers:
            print("Failed to get authentication headers.")
            return

        # Create downloader with authentication
        downloader = AIHubDownloader(auth_headers)

        # Handle different commands
        if args["command"] == "list":
            list_datasets(downloader)
        elif args["command"] == "files":
            list_file_tree(downloader, args["dataset_key"])
        elif args["command"] == "download":
            file_keys = args.get("file_key", "all")
            output_dir = args.get("output_dir", ".")
            download_dataset(downloader, args["dataset_key"], file_keys, output_dir)
        elif args["command"] == "package-list":
            list_packages(downloader)
        elif args["command"] == "package-files":
            list_package_file_tree(downloader, args["package_key"])
        elif args["command"] == "package-download":
            file_keys = args.get("file_key", "all")
            output_dir = args.get("output_dir", ".")
            download_status = downloader.download_and_process_package(
                args["package_key"], file_keys, output_dir
            )
            print(download_status.get_message())
        else:
            print("Invalid command. Use --help for usage information.")
    except Exception as e:
        print(f"An error occurred: {e}")
        return


if __name__ == "__main__":
    main()
