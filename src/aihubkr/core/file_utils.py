#!/usr/bin/env python3
#
# AIHub File Utilities
# Canonical implementations for tar extraction and part-file merging
#
# @author Jung-In An <ji5489@gmail.com>

import os
import re
import shutil
import tarfile
from typing import List


def extract_tar(tar_file: str, output_dir: str) -> None:
    """Extract a tar file to the specified output directory.

    Uses the 'data' filter on Python 3.12+ to prevent path traversal attacks.
    Falls back to unfiltered extraction on older Python versions.
    """
    with tarfile.open(tar_file, "r") as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(path=output_dir, filter="data")
        else:
            tar.extractall(path=output_dir)


def merge_parts(target_dir: str) -> None:
    """Merge numbered part files (.part0, .part1, ...) in the given directory.

    Groups files by prefix, sorts parts numerically, concatenates them into
    a single output file, and deletes the part files.
    Uses shutil.copyfileobj for memory-safe streaming of large files.
    """
    part_files = [
        f for f in os.listdir(target_dir)
        if re.search(r".*\.part[0-9]+", f, re.IGNORECASE)
    ]
    if not part_files:
        return

    prefixes = set(f.rsplit(".part", 1)[0] for f in part_files)

    for prefix in prefixes:
        parts = sorted(
            [f for f in part_files if f.startswith(prefix)],
            key=lambda x: int(x.rsplit(".part", 1)[1]),
        )

        with open(os.path.join(target_dir, prefix), "wb") as outfile:
            for part in parts:
                with open(os.path.join(target_dir, part), "rb") as infile:
                    shutil.copyfileobj(infile, outfile)

        for part in parts:
            os.remove(os.path.join(target_dir, part))


def merge_parts_in_subdirs(root_dir: str) -> None:
    """Walk all subdirectories and merge part files where found."""
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if any(
            re.search(r".*\.part[0-9]+", filename, re.IGNORECASE)
            for filename in filenames
        ):
            merge_parts(dirpath)
