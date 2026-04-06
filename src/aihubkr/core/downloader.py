#!/usr/bin/env python3
#
# AIHub Downloader Module
# Handles dataset downloads and file operations for AIHub API
#
# - Downloads datasets using API key authentication
# - Processes and merges file parts
# - Handles file tree and dataset information retrieval
#
# @author Jung-In An <ji5489@gmail.com>
# @with Claude Sonnet 4 (Cutoff 2025/06/16)

import csv
import os
import re
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple

import requests

from .file_utils import extract_tar, merge_parts_in_subdirs


class DownloadStatus(Enum):
    """Enumeration for download operation status."""
    SUCCESS = "success"
    NETWORK_ERROR = "network_error"
    PRIVILEGE_ERROR = "privilege_error"
    AUTHENTICATION_ERROR = "authentication_error"
    FILE_NOT_FOUND = "file_not_found"
    INSUFFICIENT_DISK_SPACE = "insufficient_disk_space"
    UNKNOWN_ERROR = "unknown_error"

    def get_message(self) -> str:
        """Get human-readable message for the status."""
        messages = {
            DownloadStatus.SUCCESS: "Download completed successfully.",
            DownloadStatus.NETWORK_ERROR: "Network connection failed. Please check your internet connection.",
            DownloadStatus.PRIVILEGE_ERROR: "Terms and conditions must be accepted before downloading.",
            DownloadStatus.AUTHENTICATION_ERROR: "Authentication failed. Please check your API key.",
            DownloadStatus.FILE_NOT_FOUND: "The requested dataset or file was not found.",
            DownloadStatus.INSUFFICIENT_DISK_SPACE: "Insufficient disk space for download.",
            DownloadStatus.UNKNOWN_ERROR: "Download failed due to an unknown error."
        }
        return messages.get(self, "Unknown status.")

    def is_success(self) -> bool:
        """Check if the status represents a successful operation."""
        return self == DownloadStatus.SUCCESS

    def is_error(self) -> bool:
        """Check if the status represents an error."""
        return self != DownloadStatus.SUCCESS


class AIHubDownloader:
    BASE_URL = "https://api.aihub.or.kr"
    API_VERSION = "0.6"
    BASE_DOWNLOAD_URL = f"{BASE_URL}/down/{API_VERSION}"
    BASE_FILETREE_URL = f"{BASE_URL}/info"
    DATASET_URL = f"{BASE_URL}/info/dataset.do"
    DATAPACKAGE_URL = f"{BASE_URL}/info/datapckage.do"
    BASE_PACKAGE_TREE_URL = f"{BASE_URL}/info/pckage"
    BASE_PACKAGE_DOWNLOAD_URL = f"{BASE_URL}/down/pckage/{API_VERSION}"

    def __init__(self, auth_headers: Optional[Dict[str, str]] = None):
        self.auth_headers = auth_headers or {}

    def _process_response(
        self, response: requests.Response
    ) -> Tuple[bool, Optional[str]]:
        """Process the response and determine if it's a success."""
        if response.status_code == 200 or response.status_code == 502:
            content = response.text

            # Remove the first three lines if they match the specified pattern
            lines = content.split("\n")
            if len(lines) >= 3:
                if (
                    "UTF-8" in lines[0]
                    and "output normally" in lines[1]
                    and "modify the character information" in lines[2]
                ):
                    lines = lines[3:]

            # Find and format the notice section
            notice_start = -1
            notice_end = -1
            for i, line in enumerate(lines):
                if re.search(r"={3,}\s*공지\s*사항\s*={3,}", line, re.IGNORECASE):
                    notice_start = i
                elif notice_start != -1 and re.match(r"={3,}", line):
                    notice_end = i
                    break

            if notice_start != -1 and notice_end != -1:
                notice = "\n".join(lines[notice_start + 1: notice_end])
                if notice.strip() == "":
                    lines = lines[:notice_start] + lines[notice_end + 2:]
                else:
                    formatted_notice = f"Notice:\n{notice}\n"
                    lines = (
                        lines[:notice_start]
                        + [formatted_notice]
                        + lines[notice_end + 2:]
                    )

            content = "\n".join(lines)
            return True, content.strip()
        else:
            return False, None

    def get_file_tree(self, dataset_key: str) -> Tuple[Optional[str], Optional[str]]:
        """Fetch file tree structure for a specific dataset. Returns (content, error_message)."""
        url = f"{self.BASE_FILETREE_URL}/{dataset_key}.do"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 403:
                return None, f"Dataset {dataset_key} is not available on the server (HTTP 403 Forbidden)."
            success, content = self._process_response(response)
            if success:
                return content, None
            else:
                return None, f"Failed to fetch file tree. Status code: {response.status_code}"
        except requests.Timeout:
            return None, "Timeout while fetching file tree."
        except requests.RequestException as e:
            return None, f"Network error: {e}"

    def process_dataset_list(self, content: str) -> List[Tuple[str, str]]:
        """Process the dataset list content."""
        lines = content.split("\n")

        # Remove header and footer lines
        start = next((i for i, line in enumerate(lines) if "=" in line), 0)
        end = next(
            (i for i in range(len(lines) - 1, -1, -1) if "=" in lines[i]), len(lines)
        )

        dataset_lines = lines[start + 1: end]

        datasets = []
        for line in dataset_lines:
            parts = line.split(",", 1)
            if len(parts) == 2:
                datasets.append((parts[0].strip(), parts[1].strip()))

        return datasets

    def export_dataset_list_to_csv(
        self, datasets: List[Tuple[str, str]], filename: str
    ):
        """Export the dataset list to a CSV file."""
        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["ID", "Name"])  # Header
            writer.writerows(datasets)

    def get_dataset_info(self) -> Optional[List[Tuple[str, str]]]:
        """Fetch information about all datasets and return as a list."""
        try:
            response = requests.get(self.DATASET_URL, timeout=30)  # Add 30 second timeout
            success, content = self._process_response(response)
            if success and content:
                return self.process_dataset_list(content)
            else:
                # Remove print statement - let calling code handle errors
                # print(
                #     f"Failed to fetch dataset information. Status code: {response.status_code}"
                # )
                return None
        except requests.Timeout:
            # Remove print statement - let calling code handle errors
            # print("Timeout while fetching dataset information")
            return None
        except requests.RequestException as e:
            # Remove print statement - let calling code handle errors
            # print(f"Request failed while fetching dataset information: {e}")
            return None

    def get_datapackage_info(self) -> Optional[List[Tuple[str, str]]]:
        """Fetch information about all data packages and return as a list."""
        try:
            response = requests.get(self.DATAPACKAGE_URL, timeout=30)
            success, content = self._process_response(response)
            if success and content:
                return self.process_dataset_list(content)
            else:
                return None
        except requests.Timeout:
            return None
        except requests.RequestException:
            return None

    def get_package_file_tree(self, package_key: str) -> Tuple[Optional[str], Optional[str]]:
        """Fetch file tree structure for a data package. Returns (content, error_message)."""
        url = f"{self.BASE_PACKAGE_TREE_URL}/{package_key}.do"
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 403:
                return None, f"Data package {package_key} is not available (HTTP 403)."
            success, content = self._process_response(response)
            if success:
                return content, None
            else:
                return None, f"Failed to fetch package file tree. Status code: {response.status_code}"
        except requests.Timeout:
            return None, "Timeout while fetching package file tree."
        except requests.RequestException as e:
            return None, f"Network error: {e}"

    def download_package(
        self, package_key: str, file_keys: str = "all", output_dir: str = ".",
        progress_callback=None
    ) -> DownloadStatus:
        """Download a data package."""
        url = f"{self.BASE_PACKAGE_DOWNLOAD_URL}/{package_key}.do?fileSn={file_keys}"
        return self._download_with_requests(url, package_key, output_dir, progress_callback)

    def download_and_process_package(
        self, package_key: str, file_keys: str = "all", output_dir: str = ".",
        progress_callback=None
    ) -> DownloadStatus:
        """Download a data package, extract it, merge parts, and clean up."""
        download_status = self.download_package(package_key, file_keys, output_dir, progress_callback)

        if download_status == DownloadStatus.SUCCESS:
            if progress_callback:
                progress_callback("Extracting files...", -1, -1, -1)
            tar_file = os.path.join(output_dir, "download.tar")
            extract_tar(tar_file, output_dir)

            if progress_callback:
                progress_callback("Merging file parts...", -1, -1, -1)
            merge_parts_in_subdirs(output_dir)
            os.remove(tar_file)
            return DownloadStatus.SUCCESS
        else:
            return download_status

    def download_and_process_dataset(
        self, dataset_key: str, file_keys: str = "all", output_dir: str = ".",
        progress_callback=None
    ) -> DownloadStatus:
        """Download a dataset, extract it, merge parts, and clean up."""
        download_status = self.download_dataset(dataset_key, file_keys, output_dir, progress_callback)

        if download_status == DownloadStatus.SUCCESS:
            if progress_callback:
                progress_callback("Extracting files...", -1, -1, -1)
            tar_file = os.path.join(output_dir, "download.tar")
            extract_tar(tar_file, output_dir)

            if progress_callback:
                progress_callback("Merging file parts...", -1, -1, -1)
            merge_parts_in_subdirs(output_dir)
            os.remove(tar_file)
            return DownloadStatus.SUCCESS
        else:
            return download_status

    def _check_disk_space(self, required_size: int, output_dir: str) -> bool:
        """Check if there's sufficient disk space for the download."""
        try:
            fstat = os.statvfs(output_dir)
            available_space = fstat.f_frsize * fstat.f_bavail
            return available_space >= required_size
        except OSError:
            # If we can't check disk space, assume it's available
            return True

    def download_dataset(
        self, dataset_key: str, file_keys: str = "all", output_dir: str = ".",
        progress_callback=None
    ) -> DownloadStatus:
        """Download a dataset using requests."""
        url = f"{self.BASE_DOWNLOAD_URL}/{dataset_key}.do?fileSn={file_keys}"
        return self._download_with_requests(url, dataset_key, output_dir, progress_callback)

    def download_dataset_with_size_check(
        self, dataset_key: str, file_keys: str = "all", output_dir: str = ".",
        estimated_size: int = 0, progress_callback=None
    ) -> DownloadStatus:
        """Download a dataset with disk space checking."""
        # Check disk space if estimated size is provided
        if estimated_size > 0:
            if not self._check_disk_space(estimated_size, output_dir):
                return DownloadStatus.INSUFFICIENT_DISK_SPACE

        return self.download_dataset(dataset_key, file_keys, output_dir, progress_callback)

    def _download_with_requests(
            self, url: str, dataset_key: str, output_dir: str, progress_callback=None) -> DownloadStatus:
        """Download using requests with progress tracking."""
        output_file = os.path.join(output_dir, "download.tar")

        # Check if download.tar already exists and backup it
        if os.path.exists(output_file):
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(output_dir, f"download_{timestamp}.tar")
            os.rename(output_file, backup_file)
            # Remove the Korean print statement - this information is not essential for users
            # print(f"msg : download.tar 파일이 존재하여 {backup_file}로 백업하였습니다.")

        try:
            with requests.get(url, headers=self.auth_headers, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                # Initialize progress tracking
                downloaded_size = 0
                start_time = time.time()
                last_update_time = start_time
                last_downloaded_size = 0

                with open(output_file, "wb") as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:  # Filter out keep-alive chunks
                            file.write(chunk)
                            downloaded_size += len(chunk)

                            # Calculate speed and progress
                            current_time = time.time()
                            elapsed_time = current_time - start_time

                            # Update progress every 100ms to avoid overwhelming the GUI
                            if current_time - last_update_time >= 0.1:
                                # Calculate speed (bytes per second)
                                time_diff = current_time - last_update_time
                                size_diff = downloaded_size - last_downloaded_size
                                speed = size_diff / time_diff if time_diff > 0 else 0

                                # Calculate progress percentage (if total size is known from server)
                                # Note: The GUI will calculate its own percentage based on expected size
                                progress_percent = (downloaded_size / total_size * 100) if total_size > 0 else -1

                                # Call progress callback if provided
                                if progress_callback:
                                    progress_callback(
                                        f"Downloading... {self._format_size(downloaded_size)}",
                                        progress_percent,
                                        downloaded_size,
                                        speed
                                    )

                                last_update_time = current_time
                                last_downloaded_size = downloaded_size

                # Final progress update
                if progress_callback:
                    total_time = time.time() - start_time
                    avg_speed = downloaded_size / total_time if total_time > 0 else 0
                    progress_callback(
                        f"Download completed: {self._format_size(downloaded_size)}",
                        100,
                        downloaded_size,
                        avg_speed
                    )

                # Log download completion instead of printing
                # print("Download completed.")
                return DownloadStatus.SUCCESS

        except requests.RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                resp = e.response
                if resp.status_code == 502:
                    body = resp.text if hasattr(resp, 'text') else ""
                    if "승인" in body or "신청" in body:
                        return DownloadStatus.PRIVILEGE_ERROR
                    elif "인증" in body or "키" in body:
                        return DownloadStatus.AUTHENTICATION_ERROR
                    else:
                        return DownloadStatus.PRIVILEGE_ERROR
                elif resp.status_code == 401:
                    return DownloadStatus.AUTHENTICATION_ERROR
                elif resp.status_code == 404:
                    return DownloadStatus.FILE_NOT_FOUND
                else:
                    return DownloadStatus.NETWORK_ERROR
            else:
                return DownloadStatus.NETWORK_ERROR

    def _format_size(self, size_bytes: float) -> str:
        """Format bytes into human readable format (cross-platform)."""
        if size_bytes == 0:
            return "0B"

        size_names = ["B", "KiB", "MiB", "GiB", "TiB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f}{size_names[i]}"

    def get_raw_url(self, dataset_key: str, file_keys: str = "all") -> str:
        """Get the raw download URL for a dataset."""
        return f"{self.BASE_DOWNLOAD_URL}/{dataset_key}.do?fileSn={file_keys}"

    def get_raw_package_url(self, package_key: str, file_keys: str = "all") -> str:
        """Get the raw download URL for a data package."""
        return f"{self.BASE_PACKAGE_DOWNLOAD_URL}/{package_key}.do?fileSn={file_keys}"
