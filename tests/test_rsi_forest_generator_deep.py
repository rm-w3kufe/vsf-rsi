"""
Deep tests for rsi_forest_generator.py — covers _genome_to_tree, manifest I/O, CLI.
Targets lines: 235-238, 242-244, 256-304, 308
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_forest_generator import RSIForestGenerator, main as cli_main


class TestGenomeToTree(TestCase):
    """Cover lines 256-304 (in source context) — _genome_to_tree method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._forest_dir = self._tmpdir / "forests" / "test_pred"
        self._forest_dir.mkdir(parents=True)

    def test_genome_to_tree_creates_file(self):
        """_genome_to_tree creates a .tree.vsm file with correct content."""
        genome = MagicMock()
        genome.name = "test_genome"
        genome.generation = 1
        genome.fitness = 0.85
        genome.id = "genome_001"
        genome.genes = {
            "branches": [
                {"condition": "ctx_equals($ctx, 'value', TRUE)", "action": '{"home": "high", "truth": "above", "certified": TRUE}'},
                {"condition": "TRUE", "action": '{"home": "default", "truth": "default", "certified": TRUE}'},
            ]
        }

        # Use a real generator with temp dirs
        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        mod.FORESTS_DIR = self._tmpdir / "forests"
        try:
            gen = RSIForestGenerator()
            tree_path = gen._genome_to_tree(genome, self._forest_dir)
            self.assertTrue(tree_path.exists())
            self.assertTrue(tree_path.name.endswith(".tree.vsm"))
            content = tree_path.read_text()
            self.assertIn("⟦ test_genome", content)
            self.assertIn("@vsm 1.2", content)
            self.assertIn("@status active", content)
            self.assertIn("test_genome = decision(", content)
            self.assertIn("FOREST TREE: test_genome", content)
        finally:
            mod.FORESTS_DIR = original_forests

    def test_genome_to_tree_empty_branches(self):
        """_genome_to_tree handles genome with no branches."""
        genome = MagicMock()
        genome.name = "empty_genome"
        genome.generation = 0
        genome.fitness = 0.0
        genome.id = "genome_empty"
        genome.genes = {"branches": []}

        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        mod.FORESTS_DIR = self._tmpdir / "forests"
        try:
            gen = RSIForestGenerator()
            tree_path = gen._genome_to_tree(genome, self._forest_dir)
            content = tree_path.read_text()
            self.assertIn("Default branch", content)
        finally:
            mod.FORESTS_DIR = original_forests

    def test_genome_to_tree_no_branches_key(self):
        """_genome_to_tree handles genome without branches key."""
        genome = MagicMock()
        genome.name = "no_branches"
        genome.generation = 2
        genome.fitness = 0.5
        genome.id = "genome_nb"
        genome.genes = {}

        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        mod.FORESTS_DIR = self._tmpdir / "forests"
        try:
            gen = RSIForestGenerator()
            tree_path = gen._genome_to_tree(genome, self._forest_dir)
            self.assertTrue(tree_path.exists())
        finally:
            mod.FORESTS_DIR = original_forests


class TestManifestIO(TestCase):
    """Cover lines 235-238, 242-244: _load_manifest and _save_manifest."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_load_manifest_no_file(self):
        """Lines 235-238: _load_manifest returns empty when no file."""
        import vsf_rsi.rsi_forest_generator as mod
        original_manifest = mod.MANIFEST_FILE
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"
        try:
            gen = RSIForestGenerator()
            result = gen._load_manifest()
            self.assertEqual(result, {"forests": []})
        finally:
            mod.MANIFEST_FILE = original_manifest

    def test_save_manifest(self):
        """Lines 242-244: _save_manifest writes manifest."""
        import vsf_rsi.rsi_forest_generator as mod
        original_manifest = mod.MANIFEST_FILE
        manifest_file = self._tmpdir / "rsi_forests.vsm"
        mod.MANIFEST_FILE = manifest_file
        try:
            gen = RSIForestGenerator()
            # Ensure parent directory exists for save
            manifest_file.parent.mkdir(parents=True, exist_ok=True)
            # Create a minimal valid VSM file first
            manifest_file.write_text(
                "⟦ rsi_forests | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
                "@vsm 1.2\n"
                "@status active\n"
                "forests = []\n"
                "⟦ /rsi_forests ⟧\n"
            )
            manifest = {"forests": [{"predicate": "test", "path": "/tmp/test"}]}
            gen._save_manifest(manifest)
            # Verify the file was written
            content = manifest_file.read_text()
            self.assertIn("test", content)
        finally:
            mod.MANIFEST_FILE = original_manifest


class TestForestGeneratorGetters(TestCase):
    """Cover get_forest, get_best_tree edge cases."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_get_forest_not_found(self):
        """get_forest returns None when forest doesn't exist."""
        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        mod.FORESTS_DIR = self._tmpdir / "forests"
        try:
            gen = RSIForestGenerator()
            result = gen.get_forest("nonexistent")
            self.assertIsNone(result)
        finally:
            mod.FORESTS_DIR = original_forests

    def test_get_best_tree_not_found(self):
        """get_best_tree returns None when no forest."""
        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        mod.FORESTS_DIR = self._tmpdir / "forests"
        try:
            gen = RSIForestGenerator()
            result = gen.get_best_tree("nonexistent")
            self.assertIsNone(result)
        finally:
            mod.FORESTS_DIR = original_forests

    def test_get_best_tree_empty_trees(self):
        """get_best_tree returns None when forest has no trees."""
        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        forest_dir = self._tmpdir / "test_pred"
        forest_dir.mkdir()
        (forest_dir / "forest.json").write_text(json.dumps({"trees": []}))
        mod.FORESTS_DIR = self._tmpdir
        try:
            gen = RSIForestGenerator()
            result = gen.get_best_tree("test_pred")
            self.assertIsNone(result)
        finally:
            mod.FORESTS_DIR = original_forests


class TestCLIMain(TestCase):
    """Cover lines 256-304, 308: CLI main() function."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_cli_list(self):
        """Lines 298-303: list command."""
        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        original_manifest = mod.MANIFEST_FILE
        mod.FORESTS_DIR = self._tmpdir / "forests"
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"
        try:
            with patch("sys.argv", ["prog", "list"]):
                cli_main()
        finally:
            mod.FORESTS_DIR = original_forests
            mod.MANIFEST_FILE = original_manifest

    def test_cli_best_not_found(self):
        """Lines 289-297: best command with no forest."""
        import vsf_rsi.rsi_forest_generator as mod
        original_forests = mod.FORESTS_DIR
        mod.FORESTS_DIR = self._tmpdir / "forests"
        try:
            with patch("sys.argv", ["prog", "best", "nonexistent"]):
                cli_main()
        finally:
            mod.FORESTS_DIR = original_forests

    def test_cli_no_command(self):
        """Lines 303-304: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


if __name__ == "__main__":
    main()
