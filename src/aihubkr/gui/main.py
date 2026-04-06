#!/usr/bin/env python3
#
# AIHub GUI Main Module
# Graphical user interface for AIHub dataset operations
#
# - Provides download, list, and search functionality with GUI
# - Uses API key authentication instead of username/password
# - Simplified interface matching the new AIHub API
#
# @author Jung-In An <ji5489@gmail.com>
# @with Claude Sonnet 4 (Cutoff 2025/06/16)

import datetime
import os
import re
import sys
import webbrowser
import time
import platform
import subprocess

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QMainWindow,
                             QMessageBox, QProgressBar, QPushButton,
                             QTableWidget, QTableWidgetItem, QTextEdit,
                             QVBoxLayout, QWidget)

from ..core.auth import AIHubAuth
from ..core.config import AIHubConfig
from ..core.downloader import AIHubDownloader, DownloadStatus
from ..core.filelist_parser import AIHubResponseParser, sizeof_fmt


class DownloadThread(QThread):
    progress = pyqtSignal(int)  # Legacy signal for backward compatibility
    progress_detailed = pyqtSignal(str, float, int, float)  # message, percentage, downloaded_size, speed
    finished = pyqtSignal(DownloadStatus)

    def __init__(
            self, downloader: AIHubDownloader, dataset_key: str, file_keys: str, output_dir: str,
            expected_total_size: int = 0):
        super().__init__()
        self.downloader = downloader
        self.dataset_key = dataset_key
        self.file_keys = file_keys
        self.output_dir = output_dir
        self.expected_total_size = expected_total_size

    def run(self):
        # Progress callback function that will be called by the downloader
        def progress_callback(message: str, percentage: float, downloaded_size: int, speed: float):
            # Calculate percentage based on expected total size if available
            calculated_percentage = percentage
            if self.expected_total_size > 0 and downloaded_size > 0:
                calculated_percentage = (downloaded_size / self.expected_total_size) * 100
                # Cap at 100% to avoid showing more than 100%
                calculated_percentage = min(calculated_percentage, 100.0)

            # Emit detailed progress information
            self.progress_detailed.emit(message, calculated_percentage, downloaded_size, speed)

            # Also emit legacy progress signal for backward compatibility
            if calculated_percentage >= 0:
                self.progress.emit(int(calculated_percentage))
            else:
                # For indeterminate progress, emit a pulsing value
                self.progress.emit(-1)

        status = self.downloader.download_and_process_dataset(
            self.dataset_key, self.file_keys, self.output_dir, progress_callback
        )
        self.finished.emit(status)


class DatasetLoadThread(QThread):
    """Thread for loading dataset information without blocking the main GUI."""
    datasets_loaded = pyqtSignal(list)  # Emits list of (dataset_id, dataset_name) tuples
    error_occurred = pyqtSignal(str)    # Emits error message
    progress_started = pyqtSignal()     # Emits when loading starts
    progress_finished = pyqtSignal()    # Emits when loading finishes

    def __init__(self, downloader: AIHubDownloader):
        super().__init__()
        self.downloader = downloader

    def run(self):
        try:
            self.progress_started.emit()
            datasets = self.downloader.get_dataset_info()
            if datasets:
                self.datasets_loaded.emit(datasets)
            else:
                self.error_occurred.emit("Failed to fetch dataset information.")
        except Exception as e:
            self.error_occurred.emit(f"Error loading datasets: {str(e)}")
        finally:
            self.progress_finished.emit()


class DatasetProcessThread(QThread):
    """Thread for processing and filtering dataset information without blocking the main GUI."""
    processing_started = pyqtSignal()   # Emits when processing starts
    processing_finished = pyqtSignal(list, int)  # Emits (filtered_datasets, total_count)
    error_occurred = pyqtSignal(str)    # Emits error message

    def __init__(self, datasets: list, search_query: str):
        super().__init__()
        self.datasets = datasets
        self.search_query = search_query

    def run(self):
        try:
            self.processing_started.emit()

            # Filter datasets based on search query
            filtered_datasets = []
            for dataset_id, dataset_name in self.datasets:
                if re.search(self.search_query, dataset_id, re.IGNORECASE) or \
                   re.search(self.search_query, dataset_name, re.IGNORECASE):
                    filtered_datasets.append((dataset_id, dataset_name))

            self.processing_finished.emit(filtered_datasets, len(self.datasets))
        except Exception as e:
            self.error_occurred.emit(f"Error processing datasets: {str(e)}")


class FileTreeLoadThread(QThread):
    """Thread for loading file tree information without blocking the main GUI."""
    file_tree_loaded = pyqtSignal(list)  # Emits list of parsed file paths
    error_occurred = pyqtSignal(str)     # Emits error message
    progress_started = pyqtSignal()      # Emits when loading starts
    progress_finished = pyqtSignal()     # Emits when loading finishes

    def __init__(self, downloader: AIHubDownloader, dataset_key: str):
        super().__init__()
        self.downloader = downloader
        self.dataset_key = dataset_key

    def run(self):
        """Run file tree loading in background thread."""
        try:
            self.progress_started.emit()
            file_tree, error_message = self.downloader.get_file_tree(self.dataset_key)
            if error_message:
                self.error_occurred.emit(error_message)
                return
            if not file_tree:
                self.error_occurred.emit("No files found.")
                return

            # Parse file tree
            parser = AIHubResponseParser()
            tree, paths = parser.parse_tree_output(file_tree)
            if not paths:
                self.error_occurred.emit("No files found.")
                return

            # Filter only files (not directories)
            file_paths = []
            for path, is_file, file_key, file_info in paths:
                if is_file:
                    file_paths.append((path, is_file, file_key, file_info))

            self.file_tree_loaded.emit(file_paths)
        except Exception as e:
            self.error_occurred.emit(f"Error loading file tree: {str(e)}")
        finally:
            self.progress_finished.emit()

    def on_file_tree_load_error(self, error_message):
        """Handle file tree loading error."""
        self.log_status(error_message)
        QMessageBox.warning(self, "Error", error_message)

        # Reset UI state on error
        self.dataset_description.setText(f"Dataset: {self.current_dataset_title}")
        self.dataset_size_description.setText("N/A")
        self.file_list_table.setRowCount(0)
        self.file_db = {}
        self.current_total_file_size = 0


class APIKeyValidationThread(QThread):
    """Thread for validating API key without blocking the main GUI."""
    validation_success = pyqtSignal()    # Emits when validation succeeds
    validation_failed = pyqtSignal(str)  # Emits error message when validation fails
    validation_started = pyqtSignal()    # Emits when validation starts

    def __init__(self, auth):
        super().__init__()
        self.auth = auth

    def run(self):
        """Run API key validation in background thread."""
        try:
            if self.auth.validate_api_key():
                self.validation_success.emit()
            else:
                self.validation_failed.emit("Invalid API key. Please check your API key and try again.")
        except Exception as e:
            self.validation_failed.emit(f"Validation failed: {str(e)}")


class AIHubDownloaderGUI(QMainWindow):

    DATASET_SEARCH_DEFAULT_QUERY = ".*"  # Default search query
    API_KEY_GENERATION_URL = "https://aihub.or.kr/devsport/apishell/list.do?currMenu=403&topMenu=100"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AIHub Dataset Downloader")
        self.setGeometry(100, 100, 800, 900)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Dataset database & search filtering
        self.dataset_db = []
        self.search_query = AIHubDownloaderGUI.DATASET_SEARCH_DEFAULT_QUERY
        self.file_db = {}
        self.is_downloading = False
        self.is_loading_datasets = False
        self.is_loading_file_tree = False

        self.current_dataset_id = None
        self.current_dataset_title = None
        self.current_total_file_size = 0

        # Authentication
        self.auth = AIHubAuth()
        loaded_api_key = self.auth.load_credentials()

        # Notify user if credential was reset due to version migration
        config_manager = AIHubConfig.get_instance()
        if not loaded_api_key and config_manager.config_db.get("api_key") is None and os.path.exists(
                AIHubConfig.CONFIG_PATH):
            os.remove(AIHubConfig.CONFIG_PATH)
            QMessageBox.information(
                self, "Credential Migration",
                "Your saved API key credential was from an old version and has been reset. Please re-enter your API key.")

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(20)
        self.main_layout.addWidget(self.progress_bar)

        # API Key authentication
        auth_layout = QHBoxLayout()
        auth_layout.addWidget(QLabel("AIHub API Key:"))
        self.api_key_input = QLineEdit()
        # API key is safe to show
        # self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        auth_layout.addWidget(self.api_key_input)
        self.auth_button = QPushButton("Validate API Key")
        self.auth_button.clicked.connect(self.validate_api_key)
        auth_layout.addWidget(self.auth_button)

        self.helper_reset_button = QPushButton("Generate API Key")
        self.helper_reset_button.clicked.connect(self.generate_api_key)
        auth_layout.addWidget(self.helper_reset_button)

        self.main_layout.addLayout(auth_layout)

        # Dataset key and file keys
        dataset_layout = QHBoxLayout()
        dataset_layout.addWidget(QLabel("Dataset Key:"))
        self.dataset_key_input = QLineEdit()
        dataset_layout.addWidget(self.dataset_key_input)
        dataset_layout.addWidget(QLabel("File Keys:"))
        self.file_keys_input = QLineEdit()
        self.file_keys_input.setText("all")
        dataset_layout.addWidget(self.file_keys_input)
        self.main_layout.addLayout(dataset_layout)

        # Output directory
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Output Directory:"))
        self.output_dir_input = QLineEdit()
        output_layout.addWidget(self.output_dir_input)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(self.browse_button)
        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(self.open_output_folder)
        output_layout.addWidget(self.open_folder_button)
        self.main_layout.addLayout(output_layout)

        # Download button
        self.download_button = QPushButton("Download")
        self.download_button.clicked.connect(self.start_download)
        self.download_button.setEnabled(False)
        self.main_layout.addWidget(self.download_button)

        # Status log
        self.status_log = QTextEdit()
        self.status_log.setFixedHeight(160)
        self.status_log.setReadOnly(True)
        self.main_layout.addWidget(self.status_log)

        # Add Dataset List button
        update_btn_layout = QHBoxLayout()
        self.dataset_list_button = QPushButton("Update Dataset List")
        self.dataset_list_button.clicked.connect(self.update_dataset_list)
        update_btn_layout.addWidget(self.dataset_list_button)
        self.dataset_list_csv_save_button = QPushButton("Save to CSV")
        self.dataset_list_csv_save_button.clicked.connect(self.save_to_csv)
        self.dataset_list_csv_save_button.setFixedWidth(100)
        update_btn_layout.addWidget(self.dataset_list_csv_save_button)
        self.main_layout.addLayout(update_btn_layout)

        # Dataset ID/Name search function
        self.dataset_search_query = QLineEdit()
        self.dataset_search_query.setPlaceholderText("Search dataset by ID or Name")
        self.dataset_search_query.textChanged.connect(self.search_dataset)
        self.main_layout.addWidget(self.dataset_search_query)

        # Table for dataset list
        self.dataset_table = QTableWidget()
        self.dataset_table.setColumnCount(2)
        self.dataset_table.setHorizontalHeaderLabels(["Dataset Key", "Dataset Name"])
        dataset_table_headers = self.dataset_table.horizontalHeader()
        if dataset_table_headers:
            dataset_table_headers.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            dataset_table_headers.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.dataset_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.dataset_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dataset_table.itemActivated.connect(self.choose_dataset)
        self.main_layout.addWidget(self.dataset_table)

        # Table for file list
        self.file_list_table = QTableWidget()
        self.file_list_table.setColumnCount(4)  # Select checkbox, Key, Filename, Estimated Size (Max size)
        self.file_list_table.setHorizontalHeaderLabels(["", "File Key", "File Name", "File Size"])
        file_list_headers = self.file_list_table.horizontalHeader()
        if file_list_headers:
            file_list_headers.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            file_list_headers.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            file_list_headers.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            file_list_headers.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.file_list_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.file_list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.file_list_table.cellChanged.connect(self.on_checkbox_changed)
        # Store original method before overriding
        if not hasattr(self.file_list_table, '_original_keyPressEvent'):
            self.file_list_table._original_keyPressEvent = self.file_list_table.keyPressEvent
        self.file_list_table.keyPressEvent = self.file_list_key_press_event
        self.main_layout.addWidget(self.file_list_table)

        # Data description
        dataset_description_layout = QHBoxLayout()
        self.dataset_description = QLabel("Dataset: Please choose dataset from above list.")
        self.dataset_size_description = QLabel("N/A")
        self.dataset_size_description.setAlignment(Qt.AlignmentFlag.AlignRight)
        dataset_description_layout.addWidget(self.dataset_description)
        dataset_description_layout.addWidget(self.dataset_size_description)
        self.main_layout.addLayout(dataset_description_layout)

        # Disable normal close behaviour (X button, or ALT+F4)
        self.closeEvent = self.on_close

        # Update button based on initial status
        if self.auth.api_key:
            self.api_key_input.setText(self.auth.api_key)
            self.validate_api_key()

        config_manager = AIHubConfig.get_instance()
        config_manager.load_from_disk()
        if config_manager.config_db.get("last_output_dir") is not None:
            last_output_dir = config_manager.config_db.get("last_output_dir")
            self.output_dir_input.setText(last_output_dir)

        # Create downloader
        self.downloader = AIHubDownloader()

        # Automatically click the update button
        self.update_dataset_list()

    def on_close(self, event):
        """Handle window close event."""
        if self.is_downloading or self.is_loading_datasets or self.is_loading_file_tree:
            reply = QMessageBox.question(
                self, "Operation in Progress",
                "An operation is in progress. Are you sure you want to exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def on_checkbox_changed(self, row, column):
        """Handle checkbox changes in file list table."""
        if column == 0:  # Checkbox column
            self.update_filekey_list()
            self.update_dataset_description_from_selection()

    def update_filekey_list(self):
        """Update file key list based on selected files."""
        # If all items are checked, set file_keys_input to "all"
        checked_count = 0
        total_count = self.file_list_table.rowCount()

        for row in range(total_count):
            checkbox_item = self.file_list_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                checked_count += 1

        if checked_count == 0:
            self.file_keys_input.setText("")
        elif checked_count == total_count:
            self.file_keys_input.setText("all")
        else:
            # Get selected file keys
            selected_keys = []
            for row in range(total_count):
                checkbox_item = self.file_list_table.item(row, 0)
                if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                    key_item = self.file_list_table.item(row, 1)
                    if key_item:
                        selected_keys.append(key_item.text())
            self.file_keys_input.setText(",".join(selected_keys))

    def toggle_filekey(self, event):
        """Toggle file key selection with spacebar."""
        # Get selected rows
        selected_rows = set()
        for item in self.file_list_table.selectedItems():
            selected_rows.add(item.row())

        # If no rows are selected, use current row
        if not selected_rows:
            current_row = self.file_list_table.currentRow()
            if current_row >= 0:
                selected_rows.add(current_row)

        # Toggle checkboxes for all selected rows
        if selected_rows:
            # Determine the action based on the first selected row's state
            first_row = min(selected_rows)
            first_checkbox = self.file_list_table.item(first_row, 0)

            if first_checkbox:
                # If first checkbox is checked, uncheck all; otherwise check all
                new_state = Qt.CheckState.Unchecked if first_checkbox.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked

                # Apply the same state to all selected rows
                for row in selected_rows:
                    checkbox_item = self.file_list_table.item(row, 0)
                    if checkbox_item:
                        checkbox_item.setCheckState(new_state)

                # Update the dataset description after toggling
                self.update_filekey_list()
                self.update_dataset_description_from_selection()

    def choose_dataset(self):
        """Update dataset ID to selected items."""
        current_row = self.dataset_table.currentRow()
        if current_row >= 0:
            dataset_key_item = self.dataset_table.item(current_row, 0)
            dataset_name_item = self.dataset_table.item(current_row, 1)

            if dataset_key_item and dataset_name_item:
                self.current_dataset_id = dataset_key_item.text()
                self.current_dataset_title = dataset_name_item.text()
                self.dataset_key_input.setText(self.current_dataset_id)

                # Update dataset description
                self.dataset_description.setText(f"Dataset: {self.current_dataset_title}")

                # Update file list for this dataset (this will trigger background loading)
                self.update_file_list()

                # Note: dataset size description will be updated after file tree loads

    def update_file_list(self):
        """Update file list for the selected dataset using background thread."""
        if not self.current_dataset_id or self.is_loading_file_tree:
            return

        self.is_loading_file_tree = True

        # Show loading status in dataset description
        self.dataset_description.setText(f"Dataset: {self.current_dataset_title} (Loading files...)")
        self.dataset_size_description.setText("Loading...")

        # Start file tree loading thread
        self.file_tree_load_thread = FileTreeLoadThread(self.downloader, self.current_dataset_id)
        self.file_tree_load_thread.file_tree_loaded.connect(self.on_file_tree_loaded)
        self.file_tree_load_thread.error_occurred.connect(self.on_file_tree_load_error)
        self.file_tree_load_thread.finished.connect(self.on_file_tree_load_finished)
        self.file_tree_load_thread.progress_started.connect(
            lambda: self.start_loading_progress(f"Loading file tree for dataset {self.current_dataset_id}..."))
        self.file_tree_load_thread.progress_finished.connect(
            lambda: self.stop_loading_progress("File tree ready"))
        self.file_tree_load_thread.start()

    def on_file_tree_loaded(self, file_paths):
        """Handle successful file tree loading."""
        # Clear existing table
        self.file_list_table.setRowCount(0)
        self.file_db = {}
        self.current_total_file_size = 0

        # Set table row count
        self.file_list_table.setRowCount(len(file_paths))

        # Populate table
        for row, (path, is_file, file_key, file_info) in enumerate(file_paths):
            (file_display_size, file_min_size, file_max_size) = file_info
            self.file_db[file_key] = (path, file_display_size, file_min_size, file_max_size)
            self.current_total_file_size += file_display_size

            # Checkbox
            checkbox_item = QTableWidgetItem()
            checkbox_item.setCheckState(Qt.CheckState.Checked)
            self.file_list_table.setItem(row, 0, checkbox_item)

            # File key
            key_item = QTableWidgetItem(file_key)
            self.file_list_table.setItem(row, 1, key_item)

            # File path
            path_item = QTableWidgetItem(path)
            self.file_list_table.setItem(row, 2, path_item)

            # File size
            size_item = QTableWidgetItem(sizeof_fmt(file_display_size, ignore_float=True))
            self.file_list_table.setItem(row, 3, size_item)

        # Update file key input
        self.update_filekey_list()

        # Update dataset size description with actual loaded data
        self.update_dataset_size_description()

        # Update dataset description to show selected file count and total size
        self.update_dataset_description_from_selection()

        # Note: keyPressEvent override is already set in __init__, no need to re-apply

        self.log_status(f"Loaded {len(file_paths)} files for dataset {self.current_dataset_id}.")

    def on_file_tree_load_error(self, error_message):
        """Handle file tree loading error."""
        self.log_status(error_message)
        QMessageBox.warning(self, "Error", error_message)

        # Reset UI state on error
        self.dataset_description.setText(f"Dataset: {self.current_dataset_title}")
        self.dataset_size_description.setText("N/A")
        self.file_list_table.setRowCount(0)
        self.file_db = {}
        self.current_total_file_size = 0

    def on_file_tree_load_finished(self):
        """Handle file tree loading thread completion."""
        self.is_loading_file_tree = False

    def update_dataset_size_description(self):
        """Update dataset size description."""
        if self.current_total_file_size > 0:
            self.dataset_size_description.setText(f"Total Size: {sizeof_fmt(self.current_total_file_size)}")
        else:
            self.dataset_size_description.setText("N/A")

    def search_dataset(self, value):
        """Search for dataset ID/Name by the query and filter the results."""
        self.search_query = value if value else AIHubDownloaderGUI.DATASET_SEARCH_DEFAULT_QUERY
        self.update_dataset_list_table()

    def validate_api_key(self):
        """Validate API key and update UI accordingly."""
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Error", "Please enter an API key.")
            return

        self.auth.set_api_key(api_key)

        # Disable button and show loading state
        self.auth_button.setEnabled(False)
        self.auth_button.setText("Validating...")
        self.start_loading_progress("Validating API key...")

        # Start validation in background thread
        self.api_key_validation_thread = APIKeyValidationThread(self.auth)
        self.api_key_validation_thread.validation_started.connect(
            lambda: self.log_status("Starting API key validation..."))
        self.api_key_validation_thread.validation_success.connect(self.on_api_key_validation_success)
        self.api_key_validation_thread.validation_failed.connect(self.on_api_key_validation_failed)
        self.api_key_validation_thread.start()

    def on_api_key_validation_success(self):
        """Handle successful API key validation."""
        self.auth.save_credential()
        self.download_button.setEnabled(True)
        self.api_key_input.setDisabled(True)
        self.auth_button.setText("API Key Valid")
        self.auth_button.setEnabled(False)
        self.log_status("API key validated successfully.")
        self.stop_loading_progress("API key validation successful")

        # Update downloader with auth headers
        auth_headers = self.auth.get_auth_headers()
        self.downloader = AIHubDownloader(auth_headers)

        # Update helper button
        self.helper_reset_button.setText("Reset API Key")
        self.helper_reset_button.clicked.disconnect(self.generate_api_key)
        self.helper_reset_button.clicked.connect(self.reset_credential)

    def on_api_key_validation_failed(self, error_message):
        """Handle failed API key validation."""
        self.auth_button.setEnabled(True)
        self.auth_button.setText("Validate API Key")
        self.download_button.setEnabled(False)
        self.stop_loading_progress("API key validation failed")

        QMessageBox.critical(self, "Error", error_message)

    def reset_credential(self):
        """Reset API key and clear credential."""
        self.auth.clear_credential()
        self.api_key_input.setText("")
        self.api_key_input.setPlaceholderText("Enter API key")
        self.download_button.setEnabled(False)
        self.api_key_input.setDisabled(False)
        self.auth_button.setText("Validate API Key")
        self.auth_button.setEnabled(True)
        self.helper_reset_button.setText("Generate API Key")
        self.helper_reset_button.clicked.disconnect(self.reset_credential)
        self.helper_reset_button.clicked.connect(self.generate_api_key)
        self.log_status("API key reset successfully.")

    def generate_api_key(self):
        """Open Browser and go to API Generation page"""
        QMessageBox.information(
            self, "Info",
            "Browser will be opened.\nPlease request an API key, Go to E-mail inbox and copy the API Key.")
        webbrowser.open(AIHubDownloaderGUI.API_KEY_GENERATION_URL)

    def browse_output_dir(self):
        """Browse for output directory."""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir_input.setText(dir_path)

            # Save to config
            config_manager = AIHubConfig.get_instance()
            config_manager.config_db["last_output_dir"] = dir_path
            config_manager.save_to_disk()

    def open_output_folder(self):
        """Open selected output directory."""
        dir_path = self.output_dir_input.text().strip()
        if not dir_path:
            QMessageBox.warning(self, "Error", "Please enter an output directory.")
            return

        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            QMessageBox.warning(self, "Error", "Output directory does not exist.")
            return

        system = platform.system()

        if system == "Windows":
            subprocess.run(["explorer", dir_path], check=True)
        elif system == "Darwin":  # macOS
            subprocess.run(["open", dir_path], check=True)
        elif system == "Linux":
            subprocess.run(["xdg-open", dir_path], check=True)
        else:
            raise NotImplementedError(f"Unsupported platform: {system}")

    def start_download(self):
        """Start the download process."""
        if self.is_downloading:
            return

        dataset_key = self.dataset_key_input.text().strip()
        file_keys = self.file_keys_input.text().strip()
        output_dir = self.output_dir_input.text().strip()

        if not dataset_key:
            QMessageBox.warning(self, "Error", "Please enter a dataset key.")
            return

        if not file_keys:
            QMessageBox.warning(self, "Error", "Please enter file keys.")
            return

        if not output_dir:
            QMessageBox.warning(self, "Error", "Please select an output directory.")
            return

        if not os.path.exists(output_dir) or not os.path.isdir(output_dir):
            QMessageBox.warning(self, "Error", "Output directory does not exist.")
            return

        # Check if API key is set (validation should be done when user clicks "Validate API Key")
        if not self.auth.api_key:
            QMessageBox.critical(self, "Error", "API key is not set. Please validate your API key first.")
            return

        # Update downloader with current auth headers
        auth_headers = self.auth.get_auth_headers()
        self.downloader = AIHubDownloader(auth_headers)

        self.is_downloading = True
        self.download_button.setEnabled(False)

        # Disable UI elements during download
        self.disable_ui_during_download()

        # Set up progress bar for download
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Preparing download...")

        self.log_status(f"Starting download: Dataset {dataset_key}, Files: {file_keys}")

        # Calculate expected total size based on selected files
        expected_total_size = self.calculate_selected_files_total_size()

        # Log the expected download size
        if expected_total_size > 0:
            expected_size_str = self._format_size(expected_total_size)
            self.log_status(f"Expected download size: {expected_size_str}")
        else:
            self.log_status("Warning: Could not determine expected download size")

        # Start download thread
        self.download_thread = DownloadThread(
            self.downloader, dataset_key, file_keys, output_dir, expected_total_size
        )
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.progress_detailed.connect(self.update_progress_detailed)
        self.download_thread.finished.connect(self.download_finished)
        self.download_thread.start()

    def update_progress(self, value):
        """Update progress bar (legacy method for backward compatibility)."""
        if value >= 0:
            self.progress_bar.setValue(value)
        else:
            # Indeterminate progress
            self.progress_bar.setRange(0, 0)

    def update_progress_detailed(self, message: str, percentage: float, downloaded_size: int, speed: float):
        """Update progress bar with detailed information including speed and size."""
        # Update progress bar
        if percentage >= 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(percentage))
        else:
            # Indeterminate progress for operations like extracting/merging
            self.progress_bar.setRange(0, 0)

        # Get expected total size from the download thread if available
        expected_total_size = 0
        if hasattr(self, 'download_thread') and hasattr(self.download_thread, 'expected_total_size'):
            expected_total_size = self.download_thread.expected_total_size

        # Format speed for display
        if speed > 0:
            speed_str = self._format_speed(speed)
            downloaded_str = self._format_size(downloaded_size)

            if percentage >= 0 and expected_total_size > 0:
                expected_str = self._format_size(expected_total_size)
                progress_text = f"{message} - {downloaded_str}/{expected_str} ({percentage:.1f}%) - {speed_str}"
            elif percentage >= 0:
                progress_text = f"{message} - {downloaded_str} ({percentage:.1f}%) - {speed_str}"
            else:
                progress_text = f"{message} - {downloaded_str} - {speed_str}"
        else:
            downloaded_str = self._format_size(downloaded_size)
            if percentage >= 0 and expected_total_size > 0:
                expected_str = self._format_size(expected_total_size)
                progress_text = f"{message} - {downloaded_str}/{expected_str} ({percentage:.1f}%)"
            elif percentage >= 0:
                progress_text = f"{message} - {downloaded_str} ({percentage:.1f}%)"
            else:
                progress_text = f"{message} - {downloaded_str}"

        self.progress_bar.setFormat(progress_text)

        # Log detailed progress to status log (but not too frequently)
        if hasattr(self, '_last_log_time'):
            current_time = time.time()
            if current_time - self._last_log_time >= 2.0:  # Log every 2 seconds
                self.log_status(f"Download progress: {progress_text}")
                self._last_log_time = current_time
        else:
            self._last_log_time = time.time()
            self.log_status(f"Download started: {progress_text}")

    def _format_speed(self, speed_bytes_per_sec: float) -> str:
        """Format download speed into human readable format."""
        if speed_bytes_per_sec == 0:
            return "0 B/s"

        speed_names = ["B/s", "KiB/s", "MiB/s", "GiB/s"]
        i = 0
        while speed_bytes_per_sec >= 1024 and i < len(speed_names) - 1:
            speed_bytes_per_sec /= 1024.0
            i += 1

        return f"{speed_bytes_per_sec:.1f} {speed_names[i]}"

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes into human readable format."""
        if size_bytes == 0:
            return "0B"

        size_names = ["B", "KiB", "MiB", "GiB", "TiB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1

        return f"{size_bytes:.1f}{size_names[i]}"

    def start_loading_progress(self, message: str = "Loading..."):
        """Start indeterminate progress bar for loading operations."""
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setFormat(message)
        self.log_status(message)

    def stop_loading_progress(self, message: str = "Ready"):
        """Stop indeterminate progress bar."""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")
        self.log_status(message)

    def download_finished(self, status):
        """Handle download completion."""
        self.is_downloading = False
        self.download_button.setEnabled(True)

        # Re-enable UI elements after download
        self.enable_ui_after_download()

        # Reset progress bar to normal state
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("")

        # Clear last log time
        if hasattr(self, '_last_log_time'):
            delattr(self, '_last_log_time')

        # Log the status message
        self.log_status(status.get_message())

        if status.is_success():
            QMessageBox.information(self, "Success", status.get_message())
        elif status == DownloadStatus.PRIVILEGE_ERROR:
            dataset_key = self.dataset_key_input.text().strip()
            form_url = f"https://aihub.or.kr/aihubdata/data/dwld.do?dataSetSn={dataset_key}"
            webbrowser.open(form_url)
            QMessageBox.critical(self, "Privilege Error",
                                 f"{status.get_message()}\n"
                                 "The browser has been opened. Please accept the terms and try again.")
        elif status == DownloadStatus.AUTHENTICATION_ERROR:
            QMessageBox.critical(self, "Authentication Error",
                                 f"{status.get_message()}\n"
                                 "Please check your API key and try again.")
        elif status == DownloadStatus.FILE_NOT_FOUND:
            QMessageBox.critical(self, "File Not Found",
                                 f"{status.get_message()}\n"
                                 "Please check the dataset key and file keys.")
        elif status == DownloadStatus.NETWORK_ERROR:
            QMessageBox.critical(self, "Network Error",
                                 f"{status.get_message()}\n"
                                 "Please check your internet connection and try again.")
        elif status == DownloadStatus.INSUFFICIENT_DISK_SPACE:
            QMessageBox.critical(self, "Insufficient Disk Space",
                                 f"{status.get_message()}\n"
                                 "Please free up space and try again.")
        else:
            QMessageBox.critical(self, "Unknown Error",
                                 f"{status.get_message()}\n"
                                 "Please check the status log for details.")

    def log_status(self, message):
        """Log status message."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.status_log.append(f"[{timestamp}] {message}")

    def update_dataset_list_table(self):
        """Update dataset list table based on search query."""
        if not self.dataset_db:
            return

        # Process and filter datasets in background thread to avoid GUI freezing
        self.process_datasets_in_background()

    def save_to_csv(self):
        """Save dataset list to CSV file."""
        if self.dataset_db:
            csv_filename = "aihub_datasets.csv"
            try:
                self.downloader.export_dataset_list_to_csv(self.dataset_db, csv_filename)
                self.log_status(f"Dataset list saved to {csv_filename}")
                QMessageBox.information(self, "Success", f"Dataset list saved to {csv_filename}")
            except Exception as e:
                self.log_status(f"Error saving CSV: {str(e)}")
                QMessageBox.critical(self, "Error", f"Failed to save CSV file: {str(e)}")
        else:
            QMessageBox.warning(self, "Error", "No dataset information available to save.")

    def update_dataset_list(self):
        """Update the dataset list using background thread."""
        if self.is_loading_datasets:
            return

        self.is_loading_datasets = True
        self.dataset_list_button.setEnabled(False)
        self.dataset_list_button.setText("Loading...")

        # Start dataset loading thread
        self.dataset_load_thread = DatasetLoadThread(self.downloader)
        self.dataset_load_thread.datasets_loaded.connect(self.on_datasets_loaded)
        self.dataset_load_thread.error_occurred.connect(self.on_dataset_load_error)
        self.dataset_load_thread.finished.connect(self.on_dataset_load_finished)
        self.dataset_load_thread.progress_started.connect(
            lambda: self.start_loading_progress("Loading dataset list..."))
        self.dataset_load_thread.start()

    def on_datasets_loaded(self, datasets):
        """Handle successful dataset loading."""
        self.dataset_db = datasets
        self.log_status(f"Successfully loaded {len(datasets)} datasets.")

        # Process and filter datasets in background thread
        self.process_datasets_in_background()

    def process_datasets_in_background(self):
        """Process and filter datasets in background thread to avoid GUI freezing."""
        self.dataset_process_thread = DatasetProcessThread(self.dataset_db, self.search_query)
        self.dataset_process_thread.processing_started.connect(
            lambda: self.start_loading_progress("Processing dataset list..."))
        self.dataset_process_thread.processing_finished.connect(self.on_datasets_processed)
        self.dataset_process_thread.error_occurred.connect(self.on_dataset_process_error)
        self.dataset_process_thread.start()

    def on_datasets_processed(self, filtered_datasets, total_count):
        """Handle successful dataset processing."""
        # Update table with filtered datasets
        self.dataset_table.setRowCount(len(filtered_datasets))
        for row, (dataset_id, dataset_name) in enumerate(filtered_datasets):
            self.dataset_table.setItem(row, 0, QTableWidgetItem(dataset_id))
            self.dataset_table.setItem(row, 1, QTableWidgetItem(dataset_name))

        self.log_status(f"Found {len(filtered_datasets)} datasets matching search criteria.")
        self.stop_loading_progress("Dataset list ready")

        # Reset button state
        self.is_loading_datasets = False
        self.dataset_list_button.setEnabled(True)
        self.dataset_list_button.setText("Update Dataset List")

    def on_dataset_process_error(self, error_message):
        """Handle dataset processing error."""
        self.log_status(error_message)
        self.stop_loading_progress("Error processing datasets")

        # Reset button state
        self.is_loading_datasets = False
        self.dataset_list_button.setEnabled(True)
        self.dataset_list_button.setText("Update Dataset List")

    def on_dataset_load_error(self, error_message):
        """Handle dataset loading error."""
        self.log_status(error_message)
        QMessageBox.warning(self, "Error", error_message)

        # Reset button state and progress bar
        self.is_loading_datasets = False
        self.dataset_list_button.setEnabled(True)
        self.dataset_list_button.setText("Update Dataset List")
        self.stop_loading_progress("Error loading datasets")

    def on_dataset_load_finished(self):
        """Handle dataset loading thread completion."""
        # Note: Progress bar and button state are managed by the processing thread
        # This method is called when the initial loading is complete
        pass

    def update_dataset_description_from_selection(self):
        """Update dataset description to show selected file count and total size."""
        if not self.current_dataset_title:
            return

        total_count = self.file_list_table.rowCount()
        checked_count = 0
        selected_total_size = 0

        for row in range(total_count):
            checkbox_item = self.file_list_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                checked_count += 1
                # Get file key to look up size
                key_item = self.file_list_table.item(row, 1)
                if key_item and key_item.text() in self.file_db:
                    file_info = self.file_db[key_item.text()]
                    selected_total_size += file_info[1]  # file_display_size

        if checked_count == 0:
            self.dataset_description.setText(f"Dataset: {self.current_dataset_title} (No files selected)")
        else:
            total_size_str = sizeof_fmt(selected_total_size)
            self.dataset_description.setText(
                f"Dataset: {self.current_dataset_title} ({checked_count}/{total_count} files, {total_size_str})")

    def file_list_key_press_event(self, event):
        """Handle key press events for the file list table."""
        # Handle spacebar, enter, and return keys for toggling file selection
        if event.key() in [Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            self.toggle_filekey(event)
            event.accept()  # Mark event as handled
        else:
            # Call the original keyPressEvent method for other keys
            if hasattr(self.file_list_table, '_original_keyPressEvent'):
                self.file_list_table._original_keyPressEvent(event)
            else:
                # Fallback to default behavior
                QTableWidget.keyPressEvent(self.file_list_table, event)

    def calculate_selected_files_total_size(self) -> int:
        """Calculate the total size of selected files for download."""
        total_size = 0
        total_count = self.file_list_table.rowCount()

        for row in range(total_count):
            checkbox_item = self.file_list_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                # Get file key to look up size
                key_item = self.file_list_table.item(row, 1)
                if key_item and key_item.text() in self.file_db:
                    file_info = self.file_db[key_item.text()]
                    total_size += file_info[1]  # file_display_size

        return total_size

    def disable_ui_during_download(self):
        """Disable UI elements during download to prevent user interference."""
        # Disable buttons
        self.helper_reset_button.setEnabled(False)  # Reset API Key button
        self.dataset_list_button.setEnabled(False)  # Update Dataset List button
        self.dataset_list_csv_save_button.setEnabled(False)  # Save to CSV button

        # Disable input fields
        self.api_key_input.setEnabled(False)
        self.dataset_key_input.setEnabled(False)
        self.file_keys_input.setEnabled(False)
        self.output_dir_input.setEnabled(False)
        self.browse_button.setEnabled(False)

        # Store original selection modes to restore later
        if not hasattr(self, '_original_dataset_selection_mode'):
            self._original_dataset_selection_mode = self.dataset_table.selectionMode()
        if not hasattr(self, '_original_file_list_selection_mode'):
            self._original_file_list_selection_mode = self.file_list_table.selectionMode()

        # Disable dataset table interactions (but allow scrolling)
        self.dataset_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        # Disable file list table interactions (but allow scrolling)
        self.file_list_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        # Store original keyPressEvent to restore later
        if not hasattr(self.file_list_table, '_original_keyPressEvent_backup'):
            self.file_list_table._original_keyPressEvent_backup = self.file_list_table.keyPressEvent

        # Store original mousePressEvent to restore later
        if not hasattr(self.file_list_table, '_original_mousePressEvent_backup'):
            self.file_list_table._original_mousePressEvent_backup = self.file_list_table.mousePressEvent

        # Store original cellChanged signal connection
        if not hasattr(self, '_original_cellChanged_connected'):
            self._original_cellChanged_connected = True  # Assume it was connected

        # Override keyPressEvent to block spacebar and other interactions
        self.file_list_table.keyPressEvent = self.blocked_keyPressEvent

        # Override mousePressEvent to block checkbox clicks
        self.file_list_table.mousePressEvent = self.blocked_mousePressEvent

        # Disconnect cellChanged signal to prevent checkbox changes
        self.file_list_table.cellChanged.disconnect(self.on_checkbox_changed)

        # Disable cell editing
        self.file_list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def enable_ui_after_download(self):
        """Re-enable UI elements after download completes."""
        # Re-enable buttons
        self.helper_reset_button.setEnabled(True)   # Reset API Key button
        self.dataset_list_button.setEnabled(True)   # Update Dataset List button
        self.dataset_list_csv_save_button.setEnabled(True)  # Save to CSV button

        # Re-enable input fields
        self.api_key_input.setEnabled(True)
        self.dataset_key_input.setEnabled(True)
        self.file_keys_input.setEnabled(True)
        self.output_dir_input.setEnabled(True)
        self.browse_button.setEnabled(True)

        # Restore original selection modes
        if hasattr(self, '_original_dataset_selection_mode'):
            self.dataset_table.setSelectionMode(self._original_dataset_selection_mode)
            delattr(self, '_original_dataset_selection_mode')
        else:
            # Fallback to default selection mode
            self.dataset_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        if hasattr(self, '_original_file_list_selection_mode'):
            self.file_list_table.setSelectionMode(self._original_file_list_selection_mode)
            delattr(self, '_original_file_list_selection_mode')
        else:
            # Fallback to default selection mode
            self.file_list_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        # Restore original keyPressEvent
        if hasattr(self.file_list_table, '_original_keyPressEvent_backup'):
            self.file_list_table.keyPressEvent = self.file_list_table._original_keyPressEvent_backup
            delattr(self.file_list_table, '_original_keyPressEvent_backup')

        # Restore original mousePressEvent
        if hasattr(self.file_list_table, '_original_mousePressEvent_backup'):
            self.file_list_table.mousePressEvent = self.file_list_table._original_mousePressEvent_backup
            delattr(self.file_list_table, '_original_mousePressEvent_backup')

        # Reconnect cellChanged signal
        if hasattr(self, '_original_cellChanged_connected') and self._original_cellChanged_connected:
            self.file_list_table.cellChanged.connect(self.on_checkbox_changed)
            delattr(self, '_original_cellChanged_connected')

        # Re-enable cell editing for checkboxes
        self.file_list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

    def blocked_keyPressEvent(self, event):
        """Block key press events during download while allowing scrolling."""
        # Allow scrolling keys (arrow keys, page up/down, home/end)
        if event.key() in [
            Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right,
            Qt.Key.Key_PageUp, Qt.Key.Key_PageDown, Qt.Key.Key_Home, Qt.Key.Key_End
        ]:
            # Call the original keyPressEvent for scrolling
            if hasattr(self.file_list_table, '_original_keyPressEvent_backup'):
                self.file_list_table._original_keyPressEvent_backup(event)
        else:
            # Block all other key events (including spacebar)
            event.accept()  # Mark as handled to prevent further processing

    def blocked_mousePressEvent(self, event):
        """Block mouse press events during download while allowing scrolling."""
        # Allow scrolling with mouse wheel and drag
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if the click is in the checkbox column (column 0)
            item = self.file_list_table.itemAt(event.pos())
            if item and item.column() == 0:
                # Block checkbox clicks
                event.accept()
                return

        # Allow other mouse interactions for scrolling
        if hasattr(self.file_list_table, '_original_mousePressEvent_backup'):
            self.file_list_table._original_mousePressEvent_backup(event)
        else:
            # Fallback to default behavior
            QTableWidget.mousePressEvent(self.file_list_table, event)


def main():
    app = QApplication(sys.argv)
    window = AIHubDownloaderGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
