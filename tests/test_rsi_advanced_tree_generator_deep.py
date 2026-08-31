"""
Deep tests for rsi_advanced_tree_generator.py — covers CLI main() and all templates.
Targets lines: 226-258, 262
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from vsf_rsi.rsi_advanced_tree_generator import RSIAdvancedTreeGenerator, main as cli_main


class TestAdvancedTreeTemplates(TestCase):
    """Cover all tree template creation methods."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_advanced_tree_generator as mod
        self._original_generated = mod.GENERATED_DIR
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import vsf_rsi.rsi_advanced_tree_generator as mod
        mod.GENERATED_DIR = self._original_generated

    def test_threshold_optimized_tree(self):
        """_create_threshold_optimized_tree generates valid VSM content."""
        gen = RSIAdvancedTreeGenerator()
        pattern = {"name": "thr_pred", "purpose": "threshold test", "template": "threshold_optimized_tree", "best_threshold": 0.75}
        content = gen._create_threshold_optimized_tree("thr_pred", "test", "2026-01-01T00:00:00Z", pattern)
        self.assertIn("⟦ thr_pred_advanced", content)
        self.assertIn("@vsm 1.2", content)
        self.assertIn("@status active", content)
        self.assertIn("thr_pred_advanced = decision(", content)
        self.assertIn("0.85", content)  # best_threshold + 0.1
        self.assertIn("0.65", content)  # best_threshold - 0.1

    def test_coverage_tree(self):
        """_create_coverage_tree generates valid VSM content."""
        gen = RSIAdvancedTreeGenerator()
        content = gen._create_coverage_tree("cov_pred", "coverage test", "2026-01-01T00:00:00Z", {})
        self.assertIn("⟦ cov_pred_advanced", content)
        self.assertIn("very_low", content)
        self.assertIn("very_high", content)
        self.assertIn("Default branch", content)

    def test_generic_advanced_tree(self):
        """_create_generic_advanced_tree generates valid VSM content."""
        gen = RSIAdvancedTreeGenerator()
        content = gen._create_generic_advanced_tree("gen_pred", "generic test", "2026-01-01T00:00:00Z")
        self.assertIn("⟦ gen_pred_advanced", content)
        self.assertIn("active", content)
        self.assertIn("inactive", content)


class TestAdvancedTreeGenerate(TestCase):
    """Test generate_advanced_tree with different templates."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_advanced_tree_generator as mod
        self._original_generated = mod.GENERATED_DIR
        self._original_manifest = mod.MANIFEST_FILE
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"

    def tearDown(self):
        import vsf_rsi.rsi_advanced_tree_generator as mod
        mod.GENERATED_DIR = self._original_generated
        mod.MANIFEST_FILE = self._original_manifest

    def test_generate_threshold_optimized(self):
        """generate_advanced_tree with threshold_optimized template."""
        gen = RSIAdvancedTreeGenerator()
        pattern = {"name": "thr", "purpose": "test", "template": "threshold_optimized_tree", "best_threshold": 0.8}
        path = gen.generate_advanced_tree(pattern)
        self.assertTrue(Path(path).exists())
        content = Path(path).read_text()
        self.assertIn("threshold: 0.8", content)

    def test_generate_coverage(self):
        """generate_advanced_tree with coverage template."""
        gen = RSIAdvancedTreeGenerator()
        pattern = {"name": "cov", "purpose": "test", "template": "coverage_tree"}
        path = gen.generate_advanced_tree(pattern)
        self.assertTrue(Path(path).exists())

    def test_generate_generic(self):
        """generate_advanced_tree with generic template (default)."""
        gen = RSIAdvancedTreeGenerator()
        pattern = {"name": "gen", "purpose": "test"}
        path = gen.generate_advanced_tree(pattern)
        self.assertTrue(Path(path).exists())

    def test_generate_with_base_tree(self):
        """generate_advanced_tree accepts base_tree parameter."""
        gen = RSIAdvancedTreeGenerator()
        pattern = {"name": "based", "purpose": "test", "template": "generic_tree"}
        path = gen.generate_advanced_tree(pattern, base_tree="/some/base.vsm")
        self.assertTrue(Path(path).exists())


class TestGetGeneratedTrees(TestCase):
    """Test get_generated_trees."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_get_generated_trees_empty(self):
        """get_generated_trees returns empty list when no manifest."""
        import vsf_rsi.rsi_advanced_tree_generator as mod
        original_manifest = mod.MANIFEST_FILE
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"
        try:
            gen = RSIAdvancedTreeGenerator()
            result = gen.get_generated_trees()
            self.assertEqual(result, [])
        finally:
            mod.MANIFEST_FILE = original_manifest


class TestCLIMain(TestCase):
    """Cover lines 226-258, 262: CLI main() function."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_advanced_tree_generator as mod
        self._original_generated = mod.GENERATED_DIR
        self._original_manifest = mod.MANIFEST_FILE
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"

    def tearDown(self):
        import vsf_rsi.rsi_advanced_tree_generator as mod
        mod.GENERATED_DIR = self._original_generated
        mod.MANIFEST_FILE = self._original_manifest

    def test_cli_generate_generic(self):
        """Lines 243-251: generate with generic template."""
        with patch("sys.argv", ["prog", "generate", "my_tree", "--template", "generic"]):
            cli_main()
        gen = RSIAdvancedTreeGenerator()
        trees = gen.get_generated_trees()
        self.assertEqual(len(trees), 1)

    def test_cli_generate_threshold_optimized(self):
        """Lines 243-251: generate with threshold_optimized template."""
        with patch("sys.argv", ["prog", "generate", "thr_tree", "--template", "threshold_optimized"]):
            cli_main()

    def test_cli_generate_coverage(self):
        """Lines 243-251: generate with coverage template."""
        with patch("sys.argv", ["prog", "generate", "cov_tree", "--template", "coverage"]):
            cli_main()

    def test_cli_list(self):
        """Lines 252-256: list command."""
        with patch("sys.argv", ["prog", "list"]):
            cli_main()

    def test_cli_no_command(self):
        """Lines 257-258: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


if __name__ == "__main__":
    main()
