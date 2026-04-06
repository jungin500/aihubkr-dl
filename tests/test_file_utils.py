#!/usr/bin/env python3
#
# Tests for file_utils.py
# Covers the canonical extract_tar, merge_parts, and merge_parts_in_subdirs
#
# @author Jung-In An <ji5489@gmail.com>

import os
import tarfile
from unittest.mock import patch, MagicMock

import pytest

from src.aihubkr.core.file_utils import (
    extract_tar,
    merge_parts,
    merge_parts_in_subdirs,
)


# ── extract_tar ──────────────────────────────────────────────────────────────


class TestExtractTar:
    """Tests for extract_tar()."""

    def _make_tar(self, temp_dir, arcname="hello.txt", content=b"world"):
        """Helper: create a minimal tar file."""
        src = temp_dir / "src_tmp"
        src.write_bytes(content)
        tar_path = str(temp_dir / "test.tar")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(src), arcname=arcname)
        return tar_path

    def test_basic_extraction(self, temp_dir):
        """Extract a single file from a tar."""
        tar_path = self._make_tar(temp_dir, arcname="data.txt", content=b"hello")
        out = temp_dir / "out"
        out.mkdir()
        extract_tar(tar_path, str(out))
        assert (out / "data.txt").read_bytes() == b"hello"

    def test_preserves_directory_structure(self, temp_dir):
        """Tar with nested dirs extracts correctly."""
        src = temp_dir / "src"
        nested = src / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "deep.txt").write_text("deep")

        tar_path = str(temp_dir / "nested.tar")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(nested / "deep.txt"), arcname="a/b/deep.txt")

        out = temp_dir / "out"
        out.mkdir()
        extract_tar(tar_path, str(out))
        assert (out / "a" / "b" / "deep.txt").read_text() == "deep"

    def test_nonexistent_tar_raises(self, temp_dir):
        """Extracting a nonexistent tar raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            extract_tar(str(temp_dir / "ghost.tar"), str(temp_dir))

    def test_filter_applied_on_python_312_plus(self, temp_dir):
        """On Python 3.12+, extract_tar passes filter='data'."""
        tar_path = self._make_tar(temp_dir)
        out = temp_dir / "out"
        out.mkdir()

        # If data_filter exists (Python 3.12+), verify it's used
        if hasattr(tarfile, "data_filter"):
            with patch("tarfile.TarFile.extractall") as mock_extract:
                extract_tar(tar_path, str(out))
                mock_extract.assert_called_once_with(path=str(out), filter="data")

    def test_filter_not_applied_on_older_python(self, temp_dir):
        """On Python <3.12, extract_tar calls extractall without filter."""
        tar_path = self._make_tar(temp_dir)
        out = temp_dir / "out"
        out.mkdir()

        # Simulate older Python by temporarily hiding data_filter
        with patch("src.aihubkr.core.file_utils.tarfile") as mock_tarfile:
            mock_tar = MagicMock()
            mock_tarfile.open.return_value.__enter__ = MagicMock(return_value=mock_tar)
            mock_tarfile.open.return_value.__exit__ = MagicMock(return_value=False)
            del mock_tarfile.data_filter  # simulate pre-3.12

            extract_tar(tar_path, str(out))
            mock_tar.extractall.assert_called_once_with(path=str(out))


# ── merge_parts ──────────────────────────────────────────────────────────────


class TestMergeParts:
    """Tests for merge_parts()."""

    def test_basic_numbered_merge(self, temp_dir):
        """Merge .part0, .part1, .part2 into a single file."""
        (temp_dir / "model.bin.part0").write_bytes(b"AA")
        (temp_dir / "model.bin.part1").write_bytes(b"BB")
        (temp_dir / "model.bin.part2").write_bytes(b"CC")

        merge_parts(str(temp_dir))

        assert (temp_dir / "model.bin").read_bytes() == b"AABBCC"
        assert not (temp_dir / "model.bin.part0").exists()
        assert not (temp_dir / "model.bin.part1").exists()
        assert not (temp_dir / "model.bin.part2").exists()

    def test_multiple_prefixes(self, temp_dir):
        """Different file prefixes are merged independently."""
        (temp_dir / "a.zip.part0").write_bytes(b"A0")
        (temp_dir / "a.zip.part1").write_bytes(b"A1")
        (temp_dir / "b.tar.part0").write_bytes(b"B0")
        (temp_dir / "b.tar.part1").write_bytes(b"B1")

        merge_parts(str(temp_dir))

        assert (temp_dir / "a.zip").read_bytes() == b"A0A1"
        assert (temp_dir / "b.tar").read_bytes() == b"B0B1"

    def test_no_parts_is_noop(self, temp_dir):
        """Directory with no .partN files — nothing changes."""
        (temp_dir / "complete.zip").write_bytes(b"done")
        merge_parts(str(temp_dir))
        assert (temp_dir / "complete.zip").read_bytes() == b"done"

    def test_part_files_deleted_after_merge(self, temp_dir):
        """Verify all .partN files are removed after merge."""
        (temp_dir / "big.tar.part0").write_bytes(b"X" * 50)
        (temp_dir / "big.tar.part1").write_bytes(b"Y" * 50)
        merge_parts(str(temp_dir))

        part_files = [f for f in temp_dir.iterdir() if ".part" in f.name]
        assert len(part_files) == 0

    def test_numeric_sort_not_lexical(self, temp_dir):
        """Parts are sorted numerically: .part2 before .part10."""
        (temp_dir / "data.csv.part0").write_bytes(b"0")
        (temp_dir / "data.csv.part2").write_bytes(b"2")
        (temp_dir / "data.csv.part10").write_bytes(b"10")

        merge_parts(str(temp_dir))
        # Numeric order: 0, 2, 10 (not lexical: 0, 10, 2)
        assert (temp_dir / "data.csv").read_bytes() == b"0210"

    def test_empty_directory(self, temp_dir):
        """Empty directory — no crash."""
        merge_parts(str(temp_dir))
        assert list(temp_dir.iterdir()) == []


# ── merge_parts_in_subdirs ───────────────────────────────────────────────────


class TestMergePartsInSubdirs:
    """Tests for merge_parts_in_subdirs()."""

    def test_walks_subdirectories(self, temp_dir):
        """Parts in nested subdirectories get merged."""
        sub = temp_dir / "dataset" / "train"
        sub.mkdir(parents=True)
        (sub / "data.csv.part0").write_bytes(b"header\n")
        (sub / "data.csv.part1").write_bytes(b"row1\n")

        merge_parts_in_subdirs(str(temp_dir))

        assert (sub / "data.csv").read_bytes() == b"header\nrow1\n"

    def test_empty_directory_noop(self, temp_dir):
        """Empty directory — no crash."""
        merge_parts_in_subdirs(str(temp_dir))
        assert list(temp_dir.iterdir()) == []

    def test_mixed_dirs(self, temp_dir):
        """Some subdirs have parts, some don't — only the right ones merge."""
        has_parts = temp_dir / "with_parts"
        has_parts.mkdir()
        (has_parts / "f.bin.part0").write_bytes(b"A")
        (has_parts / "f.bin.part1").write_bytes(b"B")

        no_parts = temp_dir / "without_parts"
        no_parts.mkdir()
        (no_parts / "done.txt").write_text("complete")

        merge_parts_in_subdirs(str(temp_dir))

        assert (has_parts / "f.bin").read_bytes() == b"AB"
        assert (no_parts / "done.txt").read_text() == "complete"
