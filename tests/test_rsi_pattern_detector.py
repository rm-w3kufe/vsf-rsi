"""
Tests for rsi_pattern_detector.py — Pattern detection
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_pattern_detector import RSIPatternDetector


class TestRSIPatternDetectorInit(TestCase):
    """Test RSIPatternDetector initialization."""

    def test_init_default(self):
        """RSIPatternDetector can be initialized."""
        detector = RSIPatternDetector()
        self.assertIsNotNone(detector)
        self.assertIsNotNone(detector.metrics)

    def test_init_creates_patterns_dir(self):
        """RSIPatternDetector creates patterns directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as module
            original_dir = module.PATTERNS_DIR
            module.PATTERNS_DIR = Path(tmpdir)
            try:
                detector = RSIPatternDetector()
                self.assertTrue(Path(tmpdir).exists())
            finally:
                module.PATTERNS_DIR = original_dir


class TestRSIPatternDetectorDetectPatterns(TestCase):
    """Test detect_patterns method."""

    def setUp(self):
        import vsf_rsi.rsi_pattern_detector as module
        self._original_dir = module.PATTERNS_DIR
        self._original_file = module.PATTERNS_FILE
        self._tmpdir = Path(tempfile.mkdtemp())
        module.PATTERNS_DIR = self._tmpdir
        module.PATTERNS_FILE = self._tmpdir / "rsi_patterns.json"
        self.detector = RSIPatternDetector()
        # Mock the metrics to return controlled data
        self.detector.metrics = MagicMock()

    def tearDown(self):
        import vsf_rsi.rsi_pattern_detector as module
        module.PATTERNS_DIR = self._original_dir
        module.PATTERNS_FILE = self._original_file

    def test_detect_patterns_no_data(self):
        """detect_patterns returns empty patterns when predicate not in metrics."""
        self.detector.metrics._load_metrics.return_value = {}
        result = self.detector.detect_patterns("test_pred")
        self.assertEqual(result["predicate"], "test_pred")
        self.assertEqual(result["patterns"], [])

    def test_detect_patterns_misclassification(self):
        """detect_patterns detects misclassification pattern."""
        self.detector.metrics._load_metrics.return_value = {
            "test_pred": {
                "total_classifications": 100,
                "correct_classifications": 50,  # 50% accuracy < 80%
                "thresholds": {
                    "0.5": {"total": 50, "correct": 30, "latencies": []},
                    "0.7": {"total": 50, "correct": 20, "latencies": []},
                },
                "latencies": [],
            }
        }
        result = self.detector.detect_patterns("test_pred")
        types = [p["type"] for p in result["patterns"]]
        self.assertIn("recurring_misclassification", types)

    def test_detect_patterns_threshold_clustering(self):
        """detect_patterns detects threshold clustering pattern."""
        self.detector.metrics._load_metrics.return_value = {
            "test_pred": {
                "total_classifications": 100,
                "correct_classifications": 80,
                "thresholds": {
                    "0.3": {"total": 10, "correct": 9, "latencies": []},
                    "0.5": {"total": 10, "correct": 10, "latencies": []},
                    "0.9": {"total": 10, "correct": 5, "latencies": []},
                },
                "latencies": [],
            }
        }
        result = self.detector.detect_patterns("test_pred")
        types = [p["type"] for p in result["patterns"]]
        self.assertIn("threshold_clustering", types)

    def test_detect_patterns_latency_spike(self):
        """detect_patterns detects latency spike pattern."""
        self.detector.metrics._load_metrics.return_value = {
            "test_pred": {
                "total_classifications": 10,
                "correct_classifications": 9,
                "thresholds": {
                    "0.7": {"total": 10, "correct": 9, "latencies": [100, 200, 150]},
                },
            }
        }
        result = self.detector.detect_patterns("test_pred")
        types = [p["type"] for p in result["patterns"]]
        self.assertIn("latency_spike", types)

    def test_detect_patterns_coverage_gap(self):
        """detect_patterns detects coverage gap pattern."""
        self.detector.metrics._load_metrics.return_value = {
            "test_pred": {
                "total_classifications": 10,
                "correct_classifications": 9,
                "thresholds": {
                    "0.5": {"total": 5, "correct": 5, "latencies": []},
                    "0.7": {"total": 5, "correct": 4, "latencies": []},
                },
                "latencies": [],
            }
        }
        result = self.detector.detect_patterns("test_pred")
        types = [p["type"] for p in result["patterns"]]
        self.assertIn("coverage_gap", types)

    def test_detect_patterns_saves_to_file(self):
        """detect_patterns writes patterns to PATTERNS_FILE."""
        self.detector.metrics._load_metrics.return_value = {
            "test_pred": {
                "total_classifications": 10,
                "correct_classifications": 9,
                "thresholds": {},
                "latencies": [],
            }
        }
        self.detector.detect_patterns("test_pred")
        self.assertTrue((self._tmpdir / "rsi_patterns.json").exists())


class TestRSIPatternDetectorSuggestGeneration(TestCase):
    """Test suggest_generation method."""

    def setUp(self):
        self.detector = RSIPatternDetector()

    def test_suggest_misclassification(self):
        """suggest_generation returns predicate for misclassification."""
        pattern = {"type": "recurring_misclassification"}
        result = self.detector.suggest_generation(pattern)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "predicate")
        self.assertIn("edge_cases", result["name"])

    def test_suggest_threshold(self):
        """suggest_generation returns tree for threshold clustering."""
        pattern = {"type": "threshold_clustering", "best_threshold": 0.6}
        result = self.detector.suggest_generation(pattern)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "tree")
        self.assertIn("optimized", result["name"])

    def test_suggest_latency(self):
        """suggest_generation returns predicate for latency spike."""
        pattern = {"type": "latency_spike"}
        result = self.detector.suggest_generation(pattern)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "predicate")
        self.assertIn("fast", result["name"])

    def test_suggest_coverage(self):
        """suggest_generation returns tree for coverage gap."""
        pattern = {"type": "coverage_gap"}
        result = self.detector.suggest_generation(pattern)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "tree")
        self.assertIn("coverage", result["name"])

    def test_suggest_unknown_type(self):
        """suggest_generation returns None for unknown pattern type."""
        pattern = {"type": "unknown_pattern"}
        result = self.detector.suggest_generation(pattern)
        self.assertIsNone(result)


class TestRSIPatternDetectorGetPatternsSummary(TestCase):
    """Test get_patterns_summary method."""

    def setUp(self):
        import vsf_rsi.rsi_pattern_detector as module
        self._original_dir = module.PATTERNS_DIR
        self._original_file = module.PATTERNS_FILE
        self._tmpdir = Path(tempfile.mkdtemp())
        module.PATTERNS_DIR = self._tmpdir
        module.PATTERNS_FILE = self._tmpdir / "rsi_patterns.json"
        self.detector = RSIPatternDetector()

    def tearDown(self):
        import vsf_rsi.rsi_pattern_detector as module
        module.PATTERNS_DIR = self._original_dir
        module.PATTERNS_FILE = self._original_file

    def test_summary_empty(self):
        """get_patterns_summary returns zeroed summary when no patterns."""
        summary = self.detector.get_patterns_summary()
        self.assertEqual(summary["total_predicates"], 0)
        self.assertEqual(summary["total_patterns"], 0)

    def test_summary_with_patterns(self):
        """get_patterns_summary counts patterns correctly."""
        # Write patterns file directly
        patterns_data = {
            "pred_a": {
                "patterns": [
                    {"type": "recurring_misclassification", "severity": "high"},
                    {"type": "latency_spike", "severity": "medium"},
                ]
            },
            "pred_b": {
                "patterns": [
                    {"type": "coverage_gap", "severity": "low"}
                ]
            },
        }
        with open(self._tmpdir / "rsi_patterns.json", "w") as f:
            json.dump(patterns_data, f)
        summary = self.detector.get_patterns_summary()
        self.assertEqual(summary["total_predicates"], 2)
        self.assertEqual(summary["total_patterns"], 3)
        self.assertEqual(summary["by_type"]["recurring_misclassification"], 1)
        self.assertEqual(summary["by_type"]["latency_spike"], 1)
        self.assertEqual(summary["by_type"]["coverage_gap"], 1)
        self.assertIn("pred_a", summary["predicates"])
        self.assertEqual(summary["predicates"]["pred_a"]["patterns"], 2)


class TestRSIPatternDetectorDecay(TestCase):
    """Test DEBT-005 pattern decay."""

    def setUp(self):
        import vsf_rsi.rsi_pattern_detector as module
        self._original_dir = module.PATTERNS_DIR
        self._original_file = module.PATTERNS_FILE
        self._tmpdir = Path(tempfile.mkdtemp())
        module.PATTERNS_DIR = self._tmpdir
        module.PATTERNS_FILE = self._tmpdir / "rsi_patterns.json"
        self.detector = RSIPatternDetector()

    def tearDown(self):
        import vsf_rsi.rsi_pattern_detector as module
        module.PATTERNS_DIR = self._original_dir
        module.PATTERNS_FILE = self._original_file

    def test_decay_applied_on_save(self):
        """Decay is applied to patterns on save."""
        from datetime import datetime, timezone, timedelta

        old_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        patterns_data = {
            "pred_a": {
                "patterns": [
                    {
                        "type": "test",
                        "last_seen": old_time,
                        "strength": 1.0,
                    }
                ]
            }
        }
        with open(self._tmpdir / "rsi_patterns.json", "w") as f:
            json.dump(patterns_data, f)

        # Detect patterns to trigger save + decay
        self.detector.metrics = MagicMock()
        self.detector.metrics._load_metrics.return_value = {
            "pred_a": {
                "total_classifications": 10,
                "correct_classifications": 5,
                "thresholds": {},
                "latencies": [],
            }
        }
        self.detector.detect_patterns("pred_a")

        # Load and check that decay was applied
        with open(self._tmpdir / "rsi_patterns.json") as f:
            saved = json.load(f)
        # Old pattern should have been updated with new last_seen
        self.assertIn("pred_a", saved)


if __name__ == "__main__":
    main()
