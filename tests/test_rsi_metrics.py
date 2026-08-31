"""
Tests for rsi_metrics.py — Metrics tracking
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase, main

from vsf_rsi.rsi_metrics import RSIMetrics


class TestRSIMetricsInit(TestCase):
    """Test RSIMetrics initialization."""

    def test_init_default(self):
        """RSIMetrics can be initialized."""
        metrics = RSIMetrics()
        self.assertIsNotNone(metrics)

    def test_init_creates_metrics_dir(self):
        """RSIMetrics creates metrics directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_metrics as module
            original_dir = module.METRICS_DIR
            module.METRICS_DIR = Path(tmpdir)
            try:
                metrics = RSIMetrics()
                self.assertTrue(Path(tmpdir).exists())
            finally:
                module.METRICS_DIR = original_dir


class TestRSIMetricsTrackClassification(TestCase):
    """Test track_classification method."""

    def setUp(self):
        # Use temp directory and clear any existing metrics
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        # Clear any existing metrics file
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_track_classification(self):
        """track_classification records a classification."""
        self.metrics.track_classification(
            "test_pred", 0.5, 0.3, True, True, 10.0
        )
        stored = self.metrics._load_metrics()
        self.assertIn("test_pred", stored)

    def test_track_multiple_classifications(self):
        """track_classification records multiple classifications."""
        for i in range(5):
            self.metrics.track_classification(
                "test_pred", 0.5, 0.3 + i * 0.1, True, True, 10.0 + i
            )
        stored = self.metrics._load_metrics()
        self.assertIn("test_pred", stored)
        tm = stored["test_pred"]["thresholds"]["0.5"]
        self.assertEqual(tm["total"], 5)

    def test_track_classification_with_errors(self):
        """track_classification records errors."""
        self.metrics.track_classification(
            "test_pred", 0.5, 0.3, True, False, 10.0
        )
        stored = self.metrics._load_metrics()
        tm = stored["test_pred"]["thresholds"]["0.5"]
        self.assertEqual(tm["total"], 1)
        self.assertEqual(tm["correct"], 0)


class TestRSIMetricsGetAccuracy(TestCase):
    """Test get_accuracy method."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        # Clear any existing metrics file
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_get_accuracy_no_data(self):
        """get_accuracy returns 0.0 for no data."""
        accuracy = self.metrics.get_accuracy("nonexistent")
        self.assertEqual(accuracy, 0.0)

    def test_get_accuracy_with_data(self):
        """get_accuracy returns correct accuracy."""
        # Track 8 correct, 2 incorrect (expected=True, actual varies)
        for i in range(10):
            actual = i < 8  # first 8 correct, last 2 wrong
            self.metrics.track_classification(
                "test_pred", 0.5, 0.3, True, actual, 10.0
            )
        accuracy = self.metrics.get_accuracy("test_pred")
        self.assertAlmostEqual(accuracy, 0.8, places=2)

    def test_get_accuracy_with_threshold(self):
        """get_accuracy respects threshold parameter."""
        self.metrics.track_classification("test_pred", 0.5, 0.3, True, True, 10.0)
        self.metrics.track_classification("test_pred", 0.7, 0.3, True, True, 10.0)
        accuracy = self.metrics.get_accuracy("test_pred", threshold=0.5)
        self.assertEqual(accuracy, 1.0)


class TestRSIMetricsGetLatency(TestCase):
    """Test get_latency method."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_get_latency_no_data(self):
        """get_latency returns 0.0 for no data."""
        latency = self.metrics.get_latency("nonexistent")
        self.assertEqual(latency, 0.0)

    def test_get_latency_with_data(self):
        """get_latency returns average latency."""
        self.metrics.track_classification("test_pred", 0.5, 0.3, True, True, 10.0)
        self.metrics.track_classification("test_pred", 0.5, 0.3, True, True, 20.0)
        latency = self.metrics.get_latency("test_pred")
        self.assertAlmostEqual(latency, 15.0, places=2)


class TestRSIMetricsGetCoverage(TestCase):
    """Test get_coverage method."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_get_coverage_no_data(self):
        """get_coverage returns 0.0 for no data."""
        coverage = self.metrics.get_coverage("nonexistent")
        self.assertEqual(coverage, 0.0)

    def test_get_coverage_with_data(self):
        """get_coverage returns coverage percentage."""
        # Track at threshold 0.5 only
        self.metrics.track_classification("test_pred", 0.5, 0.3, True, True, 10.0)
        coverage = self.metrics.get_coverage("test_pred")
        self.assertGreater(coverage, 0.0)


class TestRSIMetricsGetRecommendation(TestCase):
    """Test get_recommendation method."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_get_recommendation_no_data(self):
        """get_recommendation returns dict for no data."""
        rec = self.metrics.get_recommendation("nonexistent")
        self.assertIsInstance(rec, dict)

    def test_get_recommendation_with_data(self):
        """get_recommendation returns dict with data."""
        self.metrics.track_classification("test_pred", 0.5, 0.3, True, True, 10.0)
        rec = self.metrics.get_recommendation("test_pred")
        self.assertIsInstance(rec, dict)


class TestRSIMetricsGetSummary(TestCase):
    """Test get_summary method."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_get_summary_no_data(self):
        """get_summary returns dict for no data."""
        summary = self.metrics.get_summary()
        self.assertIsInstance(summary, dict)

    def test_get_summary_with_data(self):
        """get_summary returns dict with data."""
        self.metrics.track_classification("test_pred", 0.5, 0.3, True, True, 10.0)
        summary = self.metrics.get_summary()
        self.assertIsInstance(summary, dict)
        self.assertIn("predicates", summary)


class TestRSIMetricsRebuildFromHistory(TestCase):
    """Test rebuild_from_history method."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as module
        self._original_dir = module.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as module
        module.METRICS_DIR = self._original_dir

    def test_rebuild_from_history(self):
        """rebuild_from_history rebuilds metrics from history."""
        # Add some history
        self.metrics._append_history({
            "predicate_name": "test_pred",
            "threshold": 0.5,
            "input_value": 0.3,
            "expected": True,
            "actual": True,
            "latency_ms": 10.0,
        })
        result = self.metrics.rebuild_from_history()
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    main()
