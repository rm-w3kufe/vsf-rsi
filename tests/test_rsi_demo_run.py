"""
Tests for rsi_demo.py — full run_complete_demo coverage.
Uses importlib to reload rsi_demo with fresh mocks each test.
"""

import importlib
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, mock
from io import StringIO

from vsf_rsi.rsi_metrics import RSIMetrics
from vsf_rsi.rsi_feedback_loop import RSIFeedbackLoop
from vsf_rsi.rsi_gap_detector import RSIGapDetector
from vsf_rsi.rsi_tree_generator import RSITreeGenerator
from vsf_rsi.rsi_pattern_detector import RSIPatternDetector
from vsf_rsi.rsi_predicate_generator import RSIPredicateGenerator
from vsf_rsi.rsi_advanced_tree_generator import RSIAdvancedTreeGenerator
from vsf_rsi.rsi_genetic_algorithm import RSIGeneticAlgorithm
from vsf_rsi.rsi_forest_generator import RSIForestGenerator


def _get_demo_module():
    """Get a freshly-imported rsi_demo module."""
    # Remove cached module so we get a fresh import
    sys.modules.pop("vsf_rsi.rsi_demo", None)
    import vsf_rsi.rsi_demo as demo_mod
    return demo_mod


class TestRsiDemoHelperFunctions(TestCase):
    """Test the print helper functions."""

    def setUp(self):
        self.demo_mod = _get_demo_module()

    def test_print_header(self):
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.demo_mod.print_header("TEST TITLE")
            output = mock_out.getvalue()
            self.assertIn("TEST TITLE", output)

    def test_print_step(self):
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.demo_mod.print_step(3, "Step Title")
            output = mock_out.getvalue()
            self.assertIn("Step 3", output)

    def test_print_result_float(self):
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.demo_mod.print_result("accuracy", 0.8543)
            output = mock_out.getvalue()
            self.assertIn("0.8543", output)

    def test_print_result_string(self):
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.demo_mod.print_result("status", "ok")
            output = mock_out.getvalue()
            self.assertIn("ok", output)

    def test_print_footer(self):
        with mock.patch("sys.stdout", new_callable=StringIO) as mock_out:
            self.demo_mod.print_footer()
            output = mock_out.getvalue()
            self.assertIn("\u2514", output)


class TestRsiDemoRunComplete(TestCase):
    """Test run_complete_demo end-to-end with real classes + temp dirs."""

    def setUp(self):
        self.demo_mod = _get_demo_module()
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patchers = []

        def add_patcher(mod_name, attr, value):
            mod = __import__(mod_name, fromlist=[attr])
            orig = getattr(mod, attr)
            setattr(mod, attr, value)
            self._patchers.append((mod, attr, orig))

        add_patcher("vsf_rsi.rsi_metrics", "METRICS_DIR", self._tmpdir / "metrics")
        add_patcher("vsf_rsi.rsi_gap_detector", "GAPS_DIR", self._tmpdir / "gaps")
        add_patcher("vsf_rsi.rsi_pattern_detector", "PATTERNS_DIR", self._tmpdir / "patterns")
        add_patcher("vsf_rsi.rsi_tree_generator", "TREES_DIR", self._tmpdir / "trees")
        add_patcher("vsf_rsi.rsi_tree_generator", "GENERATED_DIR", self._tmpdir / "trees" / "generated")
        add_patcher("vsf_rsi.rsi_advanced_tree_generator", "TREES_DIR", self._tmpdir / "trees")
        add_patcher("vsf_rsi.rsi_advanced_tree_generator", "GENERATED_DIR", self._tmpdir / "adv_trees")
        add_patcher("vsf_rsi.rsi_predicate_generator", "GENERATED_DIR", self._tmpdir / "predicates")
        add_patcher("vsf_rsi.rsi_forest_generator", "FORESTS_DIR", self._tmpdir / "forests")
        add_patcher("vsf_rsi.rsi_genetic_algorithm", "EVOLUTION_DIR", self._tmpdir / "ga")

    def tearDown(self):
        for mod, attr, orig in self._patchers:
            setattr(mod, attr, orig)

    def test_run_complete_demo(self):
        import random
        random.seed(42)
        with mock.patch("sys.stdout", new_callable=StringIO):
            self.demo_mod.run_complete_demo()

    def test_main_function(self):
        import random
        random.seed(42)
        with mock.patch("sys.stdout", new_callable=StringIO):
            self.demo_mod.main()
