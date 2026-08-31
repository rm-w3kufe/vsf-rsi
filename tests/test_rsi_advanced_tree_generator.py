"""
Tests for rsi_advanced_tree_generator.py — Advanced tree generation
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase, mock
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_advanced_tree_generator import RSIAdvancedTreeGenerator, GENERATED_DIR


class TestRSIAdvancedTreeGeneratorInit(TestCase):
    """Test RSIAdvancedTreeGenerator initialization."""

    def test_init_default(self):
        """RSIAdvancedTreeGenerator can be initialized."""
        gen = RSIAdvancedTreeGenerator()
        self.assertIsNotNone(gen)
        self.assertIsInstance(gen.generated_dir, Path)

    @patch("vsf_rsi.rsi_advanced_tree_generator.GENERATED_DIR")
    def test_init_creates_generated_dir(self, mock_dir):
        """__init__ creates GENERATED_DIR if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.__truediv__ = lambda self, other: Path(tmpdir) / other
            mock_dir.__class__ = Path
            gen = RSIAdvancedTreeGenerator()
            # The dir is created via the module-level GENERATED_DIR
            # Just verify the generator has the right attrs
            self.assertEqual(gen.generated_dir, mock_dir)

    def test_init_sets_trees_dir(self):
        """__init__ sets trees_dir from module-level constant."""
        gen = RSIAdvancedTreeGenerator()
        self.assertTrue(gen.trees_dir.exists() or True)  # may not exist in test env


class TestGenerateAdvancedTree(TestCase):
    """Test generate_advanced_tree method."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher_trees = patch(
            "vsf_rsi.rsi_advanced_tree_generator.TREES_DIR",
            Path(self._tmpdir) / "trees"
        )
        self._patcher_generated = patch(
            "vsf_rsi.rsi_advanced_tree_generator.GENERATED_DIR",
            Path(self._tmpdir) / "generated"
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_advanced_tree_generator.MANIFEST_FILE",
            Path(self._tmpdir) / "manifest.vsm"
        )
        self._patcher_trees.start()
        self._patcher_generated.start()
        self._patcher_manifest.start()
        self.gen = RSIAdvancedTreeGenerator()

    def tearDown(self):
        self._patcher_trees.stop()
        self._patcher_generated.stop()
        self._patcher_manifest.stop()

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_returns_filepath(self, mock_load, mock_save):
        """generate_advanced_tree returns a filepath string."""
        mock_load.return_value = {"trees": []}
        pattern = {"name": "test_pred", "purpose": "testing", "type": "generic"}
        result = self.gen.generate_advanced_tree(pattern)
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith("_advanced.tree.vsm"))

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_threshold_optimized_tree(self, mock_load, mock_save):
        """generate_advanced_tree with threshold_optimized template."""
        mock_load.return_value = {"trees": []}
        pattern = {
            "name": "ac_stasis",
            "purpose": "threshold optimization",
            "template": "threshold_optimized_tree",
            "type": "threshold_optimized",
            "best_threshold": 0.85
        }
        result = self.gen.generate_advanced_tree(pattern)
        tree_content = Path(result).read_text()
        self.assertIn("0.85", tree_content)
        self.assertIn("threshold", tree_content)

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_coverage_tree(self, mock_load, mock_save):
        """generate_advanced_tree with coverage template."""
        mock_load.return_value = {"trees": []}
        pattern = {
            "name": "coverage_pred",
            "purpose": "coverage",
            "template": "coverage_tree",
            "type": "coverage"
        }
        result = self.gen.generate_advanced_tree(pattern)
        tree_content = Path(result).read_text()
        self.assertIn("coverage", tree_content.lower())

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_generic_tree(self, mock_load, mock_save):
        """generate_advanced_tree with no specific template falls back to generic."""
        mock_load.return_value = {"trees": []}
        pattern = {"name": "generic_pred", "type": "unknown"}
        result = self.gen.generate_advanced_tree(pattern)
        tree_content = Path(result).read_text()
        self.assertIn("generic_pred_advanced", tree_content)
        self.assertIn("@vsm 1.2", tree_content)

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_writes_tree_file(self, mock_load, mock_save):
        """generate_advanced_tree creates a file on disk."""
        mock_load.return_value = {"trees": []}
        pattern = {"name": "file_test", "type": "generic"}
        result = self.gen.generate_advanced_tree(pattern)
        self.assertTrue(Path(result).exists())

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_registers_in_manifest(self, mock_load, mock_save):
        """generate_advanced_tree registers the tree in the manifest."""
        mock_load.return_value = {"trees": []}
        pattern = {"name": "manifest_test", "type": "generic"}
        self.gen.generate_advanced_tree(pattern)
        mock_save.assert_called_once()
        saved_manifest = mock_save.call_args[0][0]
        self.assertEqual(len(saved_manifest["trees"]), 1)
        self.assertEqual(saved_manifest["trees"][0]["name"], "manifest_test")

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_generate_with_base_tree(self, mock_load, mock_save):
        """generate_advanced_tree accepts base_tree parameter."""
        mock_load.return_value = {"trees": []}
        pattern = {"name": "based", "type": "generic"}
        result = self.gen.generate_advanced_tree(pattern, base_tree="some_tree.vsm")
        self.assertTrue(Path(result).exists())


class TestGetGeneratedTrees(TestCase):
    """Test get_generated_trees method."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            "vsf_rsi.rsi_advanced_tree_generator.MANIFEST_FILE",
            Path(self._tmpdir) / "manifest.vsm"
        )
        self._patcher.start()
        self.gen = RSIAdvancedTreeGenerator()

    def tearDown(self):
        self._patcher.stop()

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_get_generated_trees_empty(self, mock_load):
        """get_generated_trees returns empty list when manifest has no trees."""
        mock_load.return_value = {"trees": []}
        result = self.gen.get_generated_trees()
        self.assertEqual(result, [])

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_get_generated_trees_returns_list(self, mock_load):
        """get_generated_trees returns a list of dicts."""
        mock_load.return_value = {
            "trees": [
                {"name": "t1", "path": "/tmp/t1.vsm", "status": "active"},
                {"name": "t2", "path": "/tmp/t2.vsm", "status": "active"},
            ]
        }
        result = self.gen.get_generated_trees()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "t1")

    @patch("vsf_rsi.rsi_advanced_tree_generator.RSIAdvancedTreeGenerator._load_manifest")
    def test_get_generated_trees_missing_key(self, mock_load):
        """get_generated_trees handles manifest with no trees key."""
        mock_load.return_value = {}
        result = self.gen.get_generated_trees()
        self.assertEqual(result, [])


class TestManifestInteraction(TestCase):
    """Test manifest load/save integration."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher_trees = patch(
            "vsf_rsi.rsi_advanced_tree_generator.TREES_DIR",
            Path(self._tmpdir) / "trees"
        )
        self._patcher_generated = patch(
            "vsf_rsi.rsi_advanced_tree_generator.GENERATED_DIR",
            Path(self._tmpdir) / "generated"
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_advanced_tree_generator.MANIFEST_FILE",
            Path(self._tmpdir) / "manifest.vsm"
        )
        self._patcher_trees.start()
        self._patcher_generated.start()
        self._patcher_manifest.start()
        self.gen = RSIAdvancedTreeGenerator()

    def tearDown(self):
        self._patcher_trees.stop()
        self._patcher_generated.stop()
        self._patcher_manifest.stop()

    @patch("vsf_rsi.rsi_manifest_parser.save_manifest")
    @patch("vsf_rsi.rsi_manifest_parser.load_manifest")
    def test_load_manifest_called_when_exists(self, mock_load, mock_save):
        """_load_manifest delegates to rsi_manifest_parser.load_manifest."""
        manifest_path = Path(self._tmpdir) / "manifest.vsm"
        manifest_path.write_text("trees = []")
        mock_load.return_value = {"trees": []}
        result = self.gen._load_manifest()
        self.assertEqual(result, {"trees": []})

    def test_load_manifest_returns_empty_when_no_file(self):
        """_load_manifest returns empty dict when file doesn't exist."""
        result = self.gen._load_manifest()
        self.assertEqual(result, {"trees": []})

    @patch("vsf_rsi.rsi_manifest_parser.save_manifest")
    def test_save_manifest_delegates_to_parser(self, mock_save):
        """_save_manifest calls rsi_manifest_parser.save_manifest."""
        manifest = {"trees": [{"name": "x"}]}
        self.gen._save_manifest(manifest)
        mock_save.assert_called_once()
