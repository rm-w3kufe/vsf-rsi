"""
Tests for rsi_forest_generator.py CLI main() — covers lines 282-283,
285-288, 292-295, 302, 308.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from vsf_rsi.rsi_forest_generator import main, RSIForestGenerator


class _ForestCLIHelper:
    """Shared setUp/tearDown for forest CLI tests."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_forests = patch(
            "vsf_rsi.rsi_forest_generator.FORESTS_DIR", self._tmpdir
        )
        self._patcher_manifest = patch(
            "vsf_rsi.rsi_forest_generator.MANIFEST_FILE",
            self._tmpdir / "manifest.vsm",
        )
        self._patcher_ga = patch("vsf_rsi.rsi_forest_generator.RSIGeneticAlgorithm")
        self._mock_ga_cls = self._patcher_ga.start()
        self._patcher_forests.start()
        self._patcher_manifest.start()

    def tearDown(self):
        self._patcher_ga.stop()
        self._patcher_forests.stop()
        self._patcher_manifest.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_gen(self):
        gen = RSIForestGenerator()
        return gen


class TestForestCLIGenerate(_ForestCLIHelper, unittest.TestCase):
    """Test the 'generate' subcommand (lines 281-283)."""

    @patch("sys.argv", ["rsi-forest-generator", "generate", "test_pred"])
    def test_generate(self):
        """generate prints forest path."""
        gen = self._make_gen()
        with patch.object(gen, "generate_forest") as mock_gen:
            mock_gen.return_value = str(self._tmpdir / "test_pred")
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print") as mock_print:
                    main()
            mock_gen.assert_called_once_with("test_pred", 10)
            calls = [c[0][0] for c in mock_print.call_args_list]
            self.assertTrue(any("Generated forest:" in c for c in calls))

    @patch("sys.argv", ["rsi-forest-generator", "generate", "test_pred", "--population", "20"])
    def test_generate_custom_population(self):
        """generate with --population passes it through."""
        gen = self._make_gen()
        with patch.object(gen, "generate_forest") as mock_gen:
            mock_gen.return_value = str(self._tmpdir / "test_pred")
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print"):
                    main()
            mock_gen.assert_called_once_with("test_pred", 20)


class TestForestCLIEvolve(_ForestCLIHelper, unittest.TestCase):
    """Test the 'evolve' subcommand (lines 284-288)."""

    @patch("sys.argv", ["rsi-forest-generator", "evolve", "test_pred"])
    def test_evolve(self):
        """evolve prints generations, best fitness, improvement."""
        gen = self._make_gen()
        mock_best = MagicMock()
        mock_best.fitness = 0.95
        mock_result = {
            "generations": 10,
            "best_tree": mock_best,
            "improvement": 0.15,
            "final_forest": [],
        }
        with patch.object(gen, "evolve_forest", return_value=mock_result):
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print") as mock_print:
                    main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Evolved forest: 10 generations" in c for c in calls))
        self.assertTrue(any("Best fitness: 0.9500" in c for c in calls))
        self.assertTrue(any("Improvement: 0.1500" in c for c in calls))

    @patch("sys.argv", ["rsi-forest-generator", "evolve", "test_pred", "--generations", "5"])
    def test_evolve_custom_generations(self):
        """evolve with --generations passes it through."""
        gen = self._make_gen()
        mock_result = {
            "generations": 5,
            "best_tree": MagicMock(fitness=0.80),
            "improvement": 0.10,
            "final_forest": [],
        }
        with patch.object(gen, "evolve_forest", return_value=mock_result) as mock_ev:
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print"):
                    main()
            mock_ev.assert_called_once_with("test_pred", 5)


class TestForestCLIBest(_ForestCLIHelper, unittest.TestCase):
    """Test the 'best' subcommand (lines 289-297)."""

    @patch("sys.argv", ["rsi-forest-generator", "best", "test_pred"])
    def test_best_found(self):
        """best prints tree name, fitness, generation, path."""
        gen = self._make_gen()
        best_tree = {
            "name": "best_tree_1",
            "fitness": 0.98,
            "generation": 3,
            "tree_path": "/tmp/best.tree.vsm",
        }
        with patch.object(gen, "get_best_tree", return_value=best_tree):
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print") as mock_print:
                    main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Best tree: best_tree_1" in c for c in calls))
        self.assertTrue(any("Fitness: 0.9800" in c for c in calls))
        self.assertTrue(any("Generation: 3" in c for c in calls))
        self.assertTrue(any("Path: /tmp/best.tree.vsm" in c for c in calls))

    @patch("sys.argv", ["rsi-forest-generator", "best", "nonexistent"])
    def test_best_not_found(self):
        """best prints 'No forest found' when None."""
        gen = self._make_gen()
        with patch.object(gen, "get_best_tree", return_value=None):
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print") as mock_print:
                    main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("No forest found" in c for c in calls))


class TestForestCLIList(_ForestCLIHelper, unittest.TestCase):
    """Test the 'list' subcommand (lines 298-302)."""

    @patch("sys.argv", ["rsi-forest-generator", "list"])
    def test_list_with_forests(self):
        """list prints forest count and entries."""
        gen = self._make_gen()
        forests = [
            {"predicate": "pred_a", "population_size": 10},
            {"predicate": "pred_b", "population_size": 20},
        ]
        with patch.object(gen, "list_forests", return_value=forests):
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print") as mock_print:
                    main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Forests: 2" in c for c in calls))
        self.assertTrue(any("pred_a" in c and "10" in c for c in calls))
        self.assertTrue(any("pred_b" in c and "20" in c for c in calls))

    @patch("sys.argv", ["rsi-forest-generator", "list"])
    def test_list_empty(self):
        """list with no forests prints count 0."""
        gen = self._make_gen()
        with patch.object(gen, "list_forests", return_value=[]):
            with patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
                with patch("builtins.print") as mock_print:
                    main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Forests: 0" in c for c in calls))


class TestForestCLIHelp(_ForestCLIHelper, unittest.TestCase):
    """Test no-subcommand prints help."""

    @patch("sys.argv", ["rsi-forest-generator"])
    def test_no_command_prints_help(self):
        """No subcommand prints help (line 304)."""
        gen = self._make_gen()
        with patch.object(gen, "generate_forest") as mock_gen, \
             patch.object(gen, "evolve_forest") as mock_ev, \
             patch.object(gen, "get_best_tree") as mock_best, \
             patch.object(gen, "list_forests") as mock_list, \
             patch("vsf_rsi.rsi_forest_generator.RSIForestGenerator", return_value=gen):
            with patch("builtins.print"):
                main()
        mock_gen.assert_not_called()
        mock_ev.assert_not_called()
        mock_best.assert_not_called()
        mock_list.assert_not_called()


if __name__ == "__main__":
    unittest.main()
