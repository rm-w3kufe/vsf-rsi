#!/usr/bin/env python3
"""
Tests for RSI supporting modules — metrics, feedback loop, gap detector, pattern detector.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestRSIMetrics(unittest.TestCase):
    """Test rsi_metrics module."""

    def test_import(self):
        from vsf_rsi.rsi_metrics import RSIMetrics
        self.assertTrue(hasattr(RSIMetrics, 'track_classification'))

    def test_track_classification_runs(self):
        from vsf_rsi.rsi_metrics import RSIMetrics
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch METRICS_DIR and METRICS_FILE to use temp dir
            with patch('vsf_rsi.rsi_metrics.METRICS_DIR', Path(tmpdir)), \
                 patch('vsf_rsi.rsi_metrics.METRICS_FILE', Path(tmpdir) / "rsi_metrics.json"):
                metrics = RSIMetrics()
                # Track an event - should not crash
                metrics.track_classification(
                    predicate_name="test_pred",
                    threshold=0.7,
                    input_value=0.3,
                    expected=True,
                    actual=False,
                    latency_ms=0.1,
                )
                # Verify file was created
                self.assertTrue((Path(tmpdir) / "rsi_metrics.json").exists())

    def test_rebuild_from_history(self):
        from vsf_rsi.rsi_metrics import RSIMetrics
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["VSI_RSI_STORE"] = tmpdir
            try:
                metrics = RSIMetrics()
                # Rebuild should not crash on empty store
                metrics.rebuild_from_history()
            finally:
                os.environ.pop("VSI_RSI_STORE", None)


class TestRSIFeedbackLoop(unittest.TestCase):
    """Test rsi_feedback_loop module."""

    def test_import(self):
        from vsf_rsi.rsi_feedback_loop import RSIFeedbackLoop
        self.assertTrue(hasattr(RSIFeedbackLoop, 'adjust_thresholds'))


class TestRSIGapDetector(unittest.TestCase):
    """Test rsi_gap_detector module."""

    def test_import(self):
        from vsf_rsi.rsi_gap_detector import RSIGapDetector
        self.assertTrue(hasattr(RSIGapDetector, 'detect_gaps'))


class TestRSIPatternDetector(unittest.TestCase):
    """Test rsi_pattern_detector module."""

    def test_import(self):
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector
        self.assertTrue(hasattr(RSIPatternDetector, 'detect_patterns'))


class TestRSITreeGenerator(unittest.TestCase):
    """Test rsi_tree_generator module."""

    def test_import(self):
        from vsf_rsi.rsi_tree_generator import RSITreeGenerator
        self.assertTrue(hasattr(RSITreeGenerator, 'generate_tree'))


class TestRSIForestGenerator(unittest.TestCase):
    """Test rsi_forest_generator module."""

    def test_import(self):
        from vsf_rsi.rsi_forest_generator import RSIForestGenerator
        self.assertTrue(hasattr(RSIForestGenerator, 'generate_forest'))


class TestRSIManifestParser(unittest.TestCase):
    """Test rsi_manifest_parser module."""

    def test_import(self):
        from vsf_rsi.rsi_manifest_parser import load_manifest, save_manifest
        self.assertTrue(callable(load_manifest))
        self.assertTrue(callable(save_manifest))

    def test_save_and_load(self):
        from vsf_rsi.rsi_manifest_parser import save_manifest, load_manifest
        with tempfile.NamedTemporaryFile(suffix=".vsm", mode='w', delete=False) as f:
            f.write("test")
            path = f.name
        try:
            save_manifest(
                Path(path),
                "predicates",
                [{"name": "test"}],
                "test_manifest",
                "2026-01-01T00:00:00Z"
            )
            manifest = load_manifest(Path(path))
            self.assertIn("predicates", manifest)
        finally:
            os.unlink(path)


class TestRSIComponentRegistry(unittest.TestCase):
    """Test rsi_component_registry module."""

    def test_import(self):
        from vsf_rsi.rsi_component_registry import RSIComponentRegistry
        self.assertTrue(hasattr(RSIComponentRegistry, 'register_component'))


class TestRSITreeRegistry(unittest.TestCase):
    """Test rsi_tree_registry module."""

    def test_import(self):
        from vsf_rsi.rsi_tree_registry import RSITreeRegistry
        self.assertTrue(hasattr(RSITreeRegistry, 'register_tree'))


class TestRSIScenarioBridge(unittest.TestCase):
    """Test rsi_scenario_bridge module."""

    def test_import(self):
        from vsf_rsi import rsi_scenario_bridge
        self.assertTrue(hasattr(rsi_scenario_bridge, 'failures_to_gaps'))
        self.assertTrue(hasattr(rsi_scenario_bridge, 'gaps_to_corrections'))


if __name__ == "__main__":
    unittest.main()
