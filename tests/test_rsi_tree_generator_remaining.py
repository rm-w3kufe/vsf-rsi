#!/usr/bin/env python3
"""
Tests for rsi_tree_generator.py — covering remaining missing line.

Missing line:
  185  return {"trees": []} default manifest when MANIFEST_FILE doesn't exist
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestLoadManifestDefault(unittest.TestCase):
    """Line 185: return {'trees': []} when MANIFEST_FILE doesn't exist."""

    def test_returns_empty_trees_when_manifest_missing(self):
        """_load_manifest returns {'trees': []} when MANIFEST_FILE absent."""
        from vsf_rsi.rsi_tree_generator import RSITreeGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_manifest = Path(tmpdir) / "nonexistent.vsm"
            import vsf_rsi.rsi_tree_generator as mod
            original = mod.MANIFEST_FILE
            mod.MANIFEST_FILE = fake_manifest
            try:
                gen = RSITreeGenerator()
                result = gen._load_manifest()
                self.assertEqual(result, {"trees": []})
            finally:
                mod.MANIFEST_FILE = original

    def test_returns_parsed_manifest_when_file_exists(self):
        """_load_manifest returns parsed content when MANIFEST_FILE exists."""
        from vsf_rsi.rsi_tree_generator import RSITreeGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.vsm"
            manifest_path.write_text(
                "⟦ test | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n\n"
                "@vsm 1.2\n"
                "@status active\n\n"
                'trees = [\n'
                '  { name: "t1", path: "/a.vsm" },\n'
                ']\n',
                encoding="utf-8",
            )
            import vsf_rsi.rsi_tree_generator as mod
            original = mod.MANIFEST_FILE
            mod.MANIFEST_FILE = manifest_path
            try:
                gen = RSITreeGenerator()
                result = gen._load_manifest()
                self.assertIn("trees", result)
                self.assertEqual(len(result["trees"]), 1)
            finally:
                mod.MANIFEST_FILE = original


if __name__ == "__main__":
    unittest.main()
