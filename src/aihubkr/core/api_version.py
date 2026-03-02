#!/usr/bin/env python3
#
# AIHub API Version Pinning Module
# Detects silent API updates by verifying the official shell script hash
#
# - Downloads and hashes the official aihubshell.do script
# - Compares against known-good SHA-256 hash
# - Parses version string from script content
# - Caches result for the session to avoid repeated downloads
#
# @author Jung-In An <ji5489@gmail.com>

import hashlib
import re
from typing import Optional, Tuple

import requests

# Known-good values for the current API version (v0.6)
KNOWN_SHELL_SHA256 = "3475a89b89ca10cdebfd7ef0542ec54650759bd5c15491e4dc0da6c15d93390e"
KNOWN_API_VERSION = "0.6"
KNOWN_SHELL_VERSION_STRING = "25.09.19 v0.6"

SHELL_SCRIPT_URL = "https://api.aihub.or.kr/api/aihubshell.do"

# Session cache
_cached_result: Optional[Tuple[bool, str]] = None


def _parse_version_from_script(content: str) -> Optional[str]:
    """Extract the VER variable value from the shell script content."""
    match = re.search(r'^VER="([^"]+)"', content, re.MULTILINE)
    if match:
        return match.group(1)
    return None


def _parse_version_string_from_script(content: str) -> Optional[str]:
    """Extract the full version string (e.g. '25.09.19 v0.6') from the echo line."""
    match = re.search(r'aihubshell version\s+(.+?)(?:"|\s*$)', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def check_api_version(force: bool = False) -> Tuple[bool, str]:
    """
    Check if the AIHub API version matches our known-good version.

    Downloads the official shell script, computes its SHA-256 hash,
    and compares against the known-good hash.

    Args:
        force: If True, bypass the version check and return compatible.

    Returns:
        (is_compatible, message) tuple.
        is_compatible is True if the hash matches or force is True.
        message contains details about the version status.
    """
    global _cached_result

    if force:
        return True, "Version check bypassed with --force."

    if _cached_result is not None:
        return _cached_result

    try:
        response = requests.get(SHELL_SCRIPT_URL, timeout=15)
        if response.status_code != 200:
            # Can't verify - allow operation with warning
            result = (True, f"Could not verify API version (HTTP {response.status_code}). Proceeding anyway.")
            _cached_result = result
            return result

        content = response.text
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        if sha256 == KNOWN_SHELL_SHA256:
            result = (True, f"API version verified: v{KNOWN_API_VERSION}")
            _cached_result = result
            return result

        # Hash mismatch - API has been updated
        new_version = _parse_version_from_script(content)
        new_version_string = _parse_version_string_from_script(content)

        version_info = ""
        if new_version:
            version_info = f" (detected: v{new_version})"
            if new_version_string:
                version_info = f" (detected: {new_version_string})"

        message = (
            f"AIHub API has been updated{version_info}. "
            f"This version of aihubkr-dl supports v{KNOWN_API_VERSION}. "
            f"Please update aihubkr-dl or use --force to bypass this check."
        )
        result = (False, message)
        _cached_result = result
        return result

    except requests.Timeout:
        result = (True, "Version check timed out. Proceeding anyway.")
        _cached_result = result
        return result
    except requests.RequestException as e:
        result = (True, f"Version check failed ({e}). Proceeding anyway.")
        _cached_result = result
        return result


def reset_cache() -> None:
    """Reset the session cache. Useful for testing."""
    global _cached_result
    _cached_result = None


def get_known_version() -> str:
    """Get the known API version this release supports."""
    return KNOWN_API_VERSION
