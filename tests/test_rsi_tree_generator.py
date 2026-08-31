"""
Tests for rsi_tree_generator.py — Tree generation from gaps
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase, mock
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_tree_generator import RSITreeGenerator, GENERATED_DIR


class TestRSITreeGeneratorInit(TestCase):
    """Test RSITreeGenerator initialization."""

    def test_init_default(self):
        """RSITreeGenerator can be initialized."""
        gen = RSITreeGenerator()
        self.assertIsNotNone(gen)
        self.assertIsInstance(gen.generated_dir, Path)

    def test_init_sets_trees_dir(self):
        """__init__ sets trees_dir from module-level constant."""
        gen = RSITreeGenerator()
        self.assertTrue(gen.trees_dir is not None)

    @patch("vsf_rsi.rsi_tree_generator.GENERATED_DIR")
    def test_init_creates_generated_dir(self, mock_dir):
        """__init__ calls mkdir on GENERATED_DIR."""
        mock_dir.mkdir = MagicMock()
        gen = RSITreeGenerator()
        mock_dir.mkdir.assert_called_with(parents=True, exist_ok=True)


class TestGenerateTree(TestCase):
    """Test generate_tree method."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher_trees = patch(
            "vsf_rsi.rsi_tree_generator.TREES_DIR",
            Path(self._tmpdir) / "trees"
        )
        self._patcher_generated = patch(
            "vsf_rsi.rsi_tree_generator.GENERATED_DIR",
            Path(self._tmpdir) / "generated"
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_tree_generator.MANIFEST_FILE",
            Path(self._tmpdir) / "manifest.vsm"
        )
        self._patcher_trees.start()
        self._patcher_generated.start()
        self._patcher_manifest.start()
        self.gen = RSITreeGenerator()

    def tearDown(self):
        self._patcher_trees.stop()
        self._patcher_generated.stop()
        self._patcher_manifest.stop()

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_returns_filepath(self, mock_load, mock_save):
        """generate_tree returns a filepath string."""
        mock_load.return_value = {"trees": []}
        gaps = {
            "predicate": "test_pred",
            "gaps": [
                {"type": "low_accuracy", "severity": "high",
                 "accuracy": 0.6, "suggestion": "Adjust threshold"}
            ]
        }
        result = self.gen.generate_tree("test_pred", gaps)
        self.assertIsInstance(result, str)
        self.assertTrue(result.endswith("_auto.tree.vsm"))

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_creates_file(self, mock_load, mock_save):
        """generate_tree writes a tree file to disk."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "low_accuracy", "severity": "high",
             "accuracy": 0.65, "suggestion": "Adjust"}
        ]}
        result = self.gen.generate_tree("p", gaps)
        self.assertTrue(Path(result).exists())

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_content_includes_predicate(self, mock_load, mock_save):
        """Generated tree content contains the predicate name."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "ac_pred", "gaps": []}
        result = self.gen.generate_tree("ac_pred", gaps)
        content = Path(result).read_text()
        self.assertIn("ac_pred_auto", content)
        self.assertIn("@vsm 1.2", content)

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_with_low_accuracy_gap(self, mock_load, mock_save):
        """generate_tree creates adjustment branch for low_accuracy gap."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "low_accuracy", "severity": "high",
             "accuracy": 0.65, "suggestion": "Adjust threshold"}
        ]}
        result = self.gen.generate_tree("p", gaps)
        content = Path(result).read_text()
        self.assertIn("adjustment_needed", content)

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_with_threshold_low_accuracy_gap(self, mock_load, mock_save):
        """generate_tree creates threshold-specific branch."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "threshold_low_accuracy", "severity": "high",
             "threshold": 0.8, "accuracy": 0.55,
             "suggestion": "Add branch"}
        ]}
        result = self.gen.generate_tree("p", gaps)
        content = Path(result).read_text()
        self.assertIn("0.8", content)

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_with_insufficient_thresholds_gap(self, mock_load, mock_save):
        """generate_tree creates test_mode branch for insufficient thresholds."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "insufficient_thresholds", "severity": "medium",
             "tested": 1, "suggestion": "Test more"}
        ]}
        result = self.gen.generate_tree("p", gaps)
        content = Path(result).read_text()
        self.assertIn("test_mode", content)

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_with_high_latency_gap(self, mock_load, mock_save):
        """generate_tree creates optimize branch for high latency."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "high_latency", "severity": "medium",
             "suggestion": "Optimize"}
        ]}
        result = self.gen.generate_tree("p", gaps)
        content = Path(result).read_text()
        self.assertIn("optimize_mode", content)

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_registers_manifest(self, mock_load, mock_save):
        """generate_tree registers the tree in the manifest."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "low_accuracy", "severity": "high",
             "accuracy": 0.6, "suggestion": "Fix"}
        ]}
        self.gen.generate_tree("p", gaps)
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][0]
        self.assertEqual(len(saved["trees"]), 1)
        self.assertEqual(saved["trees"][0]["predicate"], "p")

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_with_no_gaps(self, mock_load, mock_save):
        """generate_tree handles empty gaps list gracefully."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": []}
        result = self.gen.generate_tree("p", gaps)
        content = Path(result).read_text()
        self.assertIn("TRUE", content)  # default branch always present

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._save_manifest")
    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_generate_tree_with_multiple_gaps(self, mock_load, mock_save):
        """generate_tree creates branches for multiple gap types."""
        mock_load.return_value = {"trees": []}
        gaps = {"predicate": "p", "gaps": [
            {"type": "low_accuracy", "severity": "high",
             "accuracy": 0.6, "suggestion": "Adjust"},
            {"type": "high_latency", "severity": "medium",
             "suggestion": "Optimize"},
            {"type": "insufficient_thresholds", "severity": "medium",
             "tested": 1, "suggestion": "Test more"}
        ]}
        result = self.gen.generate_tree("p", gaps)
        content = Path(result).read_text()
        self.assertIn("adjustment_needed", content)
        self.assertIn("optimize_mode", content)
        self.assertIn("test_mode", content)


class TestGetGeneratedTrees(TestCase):
    """Test get_generated_trees method."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            "vsf_rsi.rsi_tree_generator.MANIFEST_FILE",
            Path(self._tmpdir) / "manifest.vsm"
        )
        self._patcher.start()
        self.gen = RSITreeGenerator()

    def tearDown(self):
        self._patcher.stop()

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_get_generated_trees_empty(self, mock_load):
        """get_generated_trees returns empty list when no trees."""
        mock_load.return_value = {"trees": []}
        result = self.gen.get_generated_trees()
        self.assertEqual(result, [])

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_get_generated_trees_returns_entries(self, mock_load):
        """get_generated_trees returns all tree entries."""
        mock_load.return_value = {
            "trees": [
                {"predicate": "p1", "path": "/tmp/t1.vsm", "gaps": 2},
                {"predicate": "p2", "path": "/tmp/t2.vsm", "gaps": 0},
            ]
        }
        result = self.gen.get_generated_trees()
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["predicate"], "p1")

    @patch("vsf_rsi.rsi_tree_generator.RSITreeGenerator._load_manifest")
    def test_get_generated_trees_missing_trees_key(self, mock_load):
        """get_generated_trees handles manifest with no trees key."""
        mock_load.return_value = {}
        result = self.gen.get_generated_trees()
        self.assertEqual(result, [])


class TestAnalyzeGaps(TestCase):
    """Test _analyze_gaps internal method."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            "vsf_rsi.rsi_tree_generator.GENERATED_DIR",
            Path(self._tmpdir) / "generated"
        )
        self._patcher.start()
        self.gen = RSITreeGenerator()

    def tearDown(self):
        self._patcher.stop()

    def test_analyze_gaps_low_accuracy(self):
        """_analyze_gaps returns adjust_threshold for low_accuracy."""
        gaps = {"gaps": [
            {"type": "low_accuracy", "severity": "high",
             "accuracy": 0.6, "suggestion": "Adjust"}
        ]}
        mods = self.gen._analyze_gaps(gaps)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["type"], "adjust_threshold")

    def test_analyze_gaps_threshold_low_accuracy(self):
        """_analyze_gaps returns add_branch for threshold_low_accuracy."""
        gaps = {"gaps": [
            {"type": "threshold_low_accuracy", "severity": "high",
             "threshold": 0.8, "suggestion": "Add branch"}
        ]}
        mods = self.gen._analyze_gaps(gaps)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["type"], "add_branch")
        self.assertEqual(mods[0]["threshold"], 0.8)

    def test_analyze_gaps_insufficient_thresholds(self):
        """_analyze_gaps returns test_thresholds for insufficient_thresholds."""
        gaps = {"gaps": [
            {"type": "insufficient_thresholds", "severity": "medium",
             "tested": 1, "suggestion": "Test more"}
        ]}
        mods = self.gen._analyze_gaps(gaps)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["type"], "test_thresholds")

    def test_analyze_gaps_high_latency(self):
        """_analyze_gaps returns optimize for high_latency."""
        gaps = {"gaps": [
            {"type": "high_latency", "severity": "medium",
             "suggestion": "Optimize"}
        ]}
        mods = self.gen._analyze_gaps(gaps)
        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0]["type"], "optimize")

    def test_analyze_gaps_unknown_type(self):
        """_analyze_gaps ignores unknown gap types."""
        gaps = {"gaps": [
            {"type": "unknown_gap", "severity": "low", "suggestion": "????"}
        ]}
        mods = self.gen._analyze_gaps(gaps)
        self.assertEqual(len(mods), 0)

    def test_analyze_gaps_empty(self):
        """_analyze_gaps returns empty list for empty gaps."""
        mods = self.gen._analyze_gaps({"gaps": []})
        self.assertEqual(mods, [])


class TestCreateBranch(TestCase):
    """Test _create_branch internal method."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._patcher = patch(
            "vsf_rsi.rsi_tree_generator.GENERATED_DIR",
            Path(self._tmpdir) / "generated"
        )
        self._patcher.start()
        self.gen = RSITreeGenerator()

    def tearDown(self):
        self._patcher.stop()

    def test_create_branch_adjust_threshold(self):
        """_create_branch returns adjustment content."""
        mod = {"type": "adjust_threshold", "reason": "Fix accuracy"}
        branch = self.gen._create_branch(mod, 0)
        self.assertIn("adjustment_needed", branch)
        self.assertIn("Branch 1", branch)

    def test_create_branch_add_branch(self):
        """_create_branch returns threshold-specific content."""
        mod = {"type": "add_branch", "threshold": 0.75, "reason": "Add branch"}
        branch = self.gen._create_branch(mod, 2)
        self.assertIn("0.75", branch)
        self.assertIn("Branch 3", branch)

    def test_create_branch_test_thresholds(self):
        """_create_branch returns test mode content."""
        mod = {"type": "test_thresholds", "reason": "Test more"}
        branch = self.gen._create_branch(mod, 1)
        self.assertIn("test_mode", branch)

    def test_create_branch_optimize(self):
        """_create_branch returns optimization content."""
        mod = {"type": "optimize", "reason": "Optimize logic"}
        branch = self.gen._create_branch(mod, 0)
        self.assertIn("optimize_mode", branch)

    def test_create_branch_unknown_type(self):
        """_create_branch returns empty string for unknown type."""
        mod = {"type": "unknown", "reason": "???"}
        branch = self.gen._create_branch(mod, 0)
        self.assertEqual(branch, "")
