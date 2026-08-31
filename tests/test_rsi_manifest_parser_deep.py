#!/usr/bin/env python3
"""
Tests for rsi_manifest_parser.py — covering remaining missing lines.

Missing lines:
  46  return [] when list name not found in content
  71  return {} when manifest file doesn't exist
  78  return {} when content has no list pattern
"""

import tempfile
import unittest
from pathlib import Path

from vsf_rsi.rsi_manifest_parser import (
    load_manifest,
    _extract_list_entries,
)


class TestExtractListEntriesNotFound(unittest.TestCase):
    """Line 46: return [] when list name not found in content."""

    def test_returns_empty_list_when_name_absent(self):
        """_extract_list_entries returns [] when list_name is not in content."""
        content = """
⟦ test | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧

@vsm 1.2
@status active

other_list = [
  { key: "value" },
]
"""
        result = _extract_list_entries(content, "trees")
        self.assertEqual(result, [])

    def test_returns_entries_when_name_present(self):
        """_extract_list_entries returns entries when list_name matches."""
        content = """
trees = [
  { name: "tree1", path: "/a/b.vsm" },
  { name: "tree2", path: "/c/d.vsm" },
]
"""
        result = _extract_list_entries(content, "trees")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "tree1")


class TestLoadManifestFileNotFound(unittest.TestCase):
    """Line 71: return {} when manifest file doesn't exist."""

    def test_returns_empty_dict_when_file_missing(self):
        """load_manifest returns {} when path does not exist."""
        result = load_manifest(Path("/nonexistent/path/manifest.vsm"))
        self.assertEqual(result, {})

    def test_returns_empty_dict_for_nonexistent_temp_path(self):
        """load_manifest returns {} for a clearly nonexistent temp path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = Path(tmpdir) / "does_not_exist.vsm"
            result = load_manifest(fake_path)
            self.assertEqual(result, {})


class TestLoadManifestNoListPattern(unittest.TestCase):
    """Line 78: return {} when content has no list pattern."""

    def test_returns_empty_dict_when_no_list_pattern(self):
        """load_manifest returns {} when file has no list_name = [...] pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "empty.vsm"
            manifest_path.write_text(
                "⟦ test | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n\n"
                "@vsm 1.2\n"
                "@status active\n\n"
                "// Just a comment, no lists here\n",
                encoding="utf-8",
            )
            result = load_manifest(manifest_path)
            self.assertEqual(result, {})

    def test_returns_entries_when_list_exists(self):
        """load_manifest returns dict when file has a valid list pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "valid.vsm"
            manifest_path.write_text(
                "⟦ test | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n\n"
                "@vsm 1.2\n"
                "@status active\n\n"
                'trees = [\n'
                '  { name: "t1", path: "/a.vsm" },\n'
                ']\n',
                encoding="utf-8",
            )
            result = load_manifest(manifest_path)
            self.assertIn("trees", result)
            self.assertEqual(len(result["trees"]), 1)


if __name__ == "__main__":
    unittest.main()
