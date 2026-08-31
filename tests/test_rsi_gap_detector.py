"""
Tests for rsi_gap_detector.py — Gap detection and modification suggestions

IMPORTANT: rsi_gap_detector imports `from rsi_metrics import RSIMetrics` (bare).
We add a mock `rsi_metrics` module to sys.modules before import.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, mock
from unittest.mock import patch, MagicMock

# rsi_gap_detector.py does `from rsi_metrics import RSIMetrics` (bare name).
# We inject a mock module into sys.modules BEFORE importing the module under test.
from vsf_rsi.rsi_metrics import RSIMetrics as _RealRSIMetrics

_mock_rsi_metrics = MagicMock()
_mock_rsi_metrics.RSIMetrics = _RealRSIMetrics  # Wire up real class
sys.modules.setdefault("rsi_metrics", _mock_rsi_metrics)

from vsf_rsi.rsi_gap_detector import RSIGapDetector, GAPS_DIR, GAPS_FILE


def _make_metrics_data(predicate_name="test_pred", total=100, correct=90,
                       thresholds=None, latencies=None):
    """Build a mock metrics dict for _load_metrics."""
    if thresholds is None:
        thresholds = {
            "0.5": {"correct": 45, "total": 50, "latencies": [5.0, 6.0, 4.0]},
            "0.7": {"correct": 40, "total": 50, "latencies": [3.0, 4.0, 5.0]},
        }
    if latencies is not None:
        # Overwrite all threshold latencies with provided list
        for tm in thresholds.values():
            tm["latencies"] = list(latencies)
    return {
        predicate_name: {
            "total_classifications": total,
            "correct_classifications": correct,
            "thresholds": thresholds,
        }
    }


class TestRSIGapDetectorInit(TestCase):
    """Test RSIGapDetector initialization."""

    @patch("vsf_rsi.rsi_gap_detector.RSIMetrics")
    @patch("vsf_rsi.rsi_gap_detector.GAPS_DIR")
    def test_init_default(self, mock_dir, mock_metrics_cls):
        """RSIGapDetector can be initialized."""
        detector = RSIGapDetector()
        self.assertIsNotNone(detector)
        mock_dir.mkdir.assert_called_with(parents=True, exist_ok=True)

    @patch("vsf_rsi.rsi_gap_detector.RSIMetrics")
    @patch("vsf_rsi.rsi_gap_detector.GAPS_DIR")
    def test_init_creates_metrics_instance(self, mock_dir, mock_metrics_cls):
        """__init__ creates self.metrics as RSIMetrics instance."""
        detector = RSIGapDetector()
        mock_metrics_cls.assert_called_once()
        self.assertIsNotNone(detector.metrics)


class TestDetectGaps(TestCase):
    """Test detect_gaps method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_gaps = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_DIR", self._tmpdir
        )
        self._patcher_gaps_file = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_FILE", self._tmpdir / "rsi_gaps.json"
        )
        self._mock_metrics = MagicMock()
        self._patcher_metrics = patch(
            "vsf_rsi.rsi_gap_detector.RSIMetrics", return_value=self._mock_metrics
        )
        self._patcher_gaps.start()
        self._patcher_gaps_file.start()
        self._patcher_metrics.start()
        self.detector = RSIGapDetector()

    def tearDown(self):
        self._patcher_gaps.stop()
        self._patcher_gaps_file.stop()
        self._patcher_metrics.stop()

    def test_detect_gaps_no_data_returns_empty(self):
        """detect_gaps returns empty gaps when predicate not in metrics."""
        self._mock_metrics._load_metrics.return_value = {}
        result = self.detector.detect_gaps("unknown_pred")
        self.assertEqual(result["predicate"], "unknown_pred")
        self.assertEqual(result["gaps"], [])

    def test_detect_gaps_low_accuracy(self):
        """detect_gaps detects low_accuracy gap when accuracy < 0.8."""
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            total=100, correct=65  # 0.65 < 0.8
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertIn("low_accuracy", gap_types)
        # Find the low_accuracy gap and verify fields
        low_acc = next(g for g in result["gaps"] if g["type"] == "low_accuracy")
        self.assertEqual(low_acc["severity"], "high")
        self.assertAlmostEqual(low_acc["accuracy"], 0.65)

    def test_detect_gaps_no_low_accuracy_when_above_threshold(self):
        """detect_gaps does NOT flag low_accuracy when accuracy >= 0.8."""
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            total=100, correct=90  # 0.9 >= 0.8
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertNotIn("low_accuracy", gap_types)

    def test_detect_gaps_insufficient_thresholds(self):
        """detect_gaps detects insufficient_thresholds when < 3 thresholds."""
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            thresholds={"0.5": {"correct": 10, "total": 20}}  # only 1 threshold
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertIn("insufficient_thresholds", gap_types)
        insuff = next(g for g in result["gaps"] if g["type"] == "insufficient_thresholds")
        self.assertEqual(insuff["severity"], "medium")
        self.assertEqual(insuff["tested"], 1)

    def test_detect_gaps_no_insufficient_when_enough(self):
        """detect_gaps does NOT flag insufficient_thresholds when >= 3."""
        thresholds = {
            "0.3": {"correct": 10, "total": 20},
            "0.5": {"correct": 10, "total": 20},
            "0.7": {"correct": 10, "total": 20},
        }
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            thresholds=thresholds
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertNotIn("insufficient_thresholds", gap_types)

    def test_detect_gaps_threshold_low_accuracy(self):
        """detect_gaps detects threshold_low_accuracy when accuracy < 0.7."""
        thresholds = {
            "0.5": {"correct": 5, "total": 20},   # 0.25 < 0.7
            "0.7": {"correct": 18, "total": 20},   # 0.9 >= 0.7
        }
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            thresholds=thresholds
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertIn("threshold_low_accuracy", gap_types)
        thr_gap = next(g for g in result["gaps"] if g["type"] == "threshold_low_accuracy")
        self.assertEqual(thr_gap["threshold"], 0.5)
        self.assertEqual(thr_gap["severity"], "high")

    def test_detect_gaps_high_latency(self):
        """detect_gaps detects high_latency when avg > 10ms."""
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            latencies=[8.0, 12.0, 15.0]  # avg = 11.67 > 10
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertIn("high_latency", gap_types)
        lat_gap = next(g for g in result["gaps"] if g["type"] == "high_latency")
        self.assertEqual(lat_gap["severity"], "medium")
        self.assertGreater(lat_gap["avg_latency_ms"], 10)

    def test_detect_gaps_no_high_latency_when_low(self):
        """detect_gaps does NOT flag high_latency when avg <= 10ms."""
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            latencies=[3.0, 4.0, 5.0]  # avg = 4.0
        )
        result = self.detector.detect_gaps("test_pred")
        gap_types = [g["type"] for g in result["gaps"]]
        self.assertNotIn("high_latency", gap_types)

    def test_detect_gaps_has_timestamp(self):
        """detect_gaps includes a timestamp in the result."""
        self._mock_metrics._load_metrics.return_value = {}
        result = self.detector.detect_gaps("test_pred")
        self.assertIn("timestamp", result)
        self.assertIsInstance(result["timestamp"], str)

    def test_detect_gaps_saves_to_file(self):
        """detect_gaps writes gaps to the gaps file."""
        self._mock_metrics._load_metrics.return_value = _make_metrics_data(
            total=100, correct=60
        )
        self.detector.detect_gaps("test_pred")
        gaps_file = self._tmpdir / "rsi_gaps.json"
        self.assertTrue(gaps_file.exists())
        saved = json.loads(gaps_file.read_text())
        self.assertIn("test_pred", saved)


class TestDetectAllGaps(TestCase):
    """Test detect_all_gaps method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_gaps = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_DIR", self._tmpdir
        )
        self._patcher_gaps_file = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_FILE", self._tmpdir / "rsi_gaps.json"
        )
        self._mock_metrics = MagicMock()
        self._patcher_metrics = patch(
            "vsf_rsi.rsi_gap_detector.RSIMetrics", return_value=self._mock_metrics
        )
        self._patcher_gaps.start()
        self._patcher_gaps_file.start()
        self._patcher_metrics.start()
        self.detector = RSIGapDetector()

    def tearDown(self):
        self._patcher_gaps.stop()
        self._patcher_gaps_file.stop()
        self._patcher_metrics.stop()

    def test_detect_all_gaps_empty_metrics(self):
        """detect_all_gaps returns empty predicates when no metrics."""
        self._mock_metrics._load_metrics.return_value = {}
        result = self.detector.detect_all_gaps()
        self.assertEqual(result["predicates"], {})
        self.assertIn("timestamp", result)

    def test_detect_all_gaps_multiple_predicates(self):
        """detect_all_gaps detects gaps for multiple predicates."""
        metrics_data = {
            "pred_a": {
                "total_classifications": 100,
                "correct_classifications": 60,  # 0.6 < 0.8
                "thresholds": {"0.5": {"correct": 10, "total": 20, "latencies": [5.0]}},
            },
            "pred_b": {
                "total_classifications": 100,
                "correct_classifications": 95,  # 0.95 >= 0.8
                "thresholds": {
                    "0.3": {"correct": 18, "total": 20, "latencies": [3.0]},
                    "0.5": {"correct": 17, "total": 20, "latencies": [3.0]},
                    "0.7": {"correct": 19, "total": 20, "latencies": [3.0]},
                },
            },
        }
        self._mock_metrics._load_metrics.return_value = metrics_data
        result = self.detector.detect_all_gaps()
        self.assertEqual(len(result["predicates"]), 2)
        # pred_a should have low_accuracy + insufficient_thresholds
        a_types = [g["type"] for g in result["predicates"]["pred_a"]["gaps"]]
        self.assertIn("low_accuracy", a_types)
        self.assertIn("insufficient_thresholds", a_types)
        # pred_b should have no gaps (accuracy >= 0.8, 3 thresholds, each >= 0.7, latency < 10)
        self.assertEqual(result["predicates"]["pred_b"]["gaps"], [])


class TestSuggestModification(TestCase):
    """Test suggest_modification method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_gaps = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_DIR", self._tmpdir
        )
        self._mock_metrics = MagicMock()
        self._patcher_metrics = patch(
            "vsf_rsi.rsi_gap_detector.RSIMetrics", return_value=self._mock_metrics
        )
        self._patcher_gaps.start()
        self._patcher_metrics.start()
        self.detector = RSIGapDetector()

    def tearDown(self):
        self._patcher_gaps.stop()
        self._patcher_metrics.stop()

    def test_suggest_low_accuracy(self):
        """suggest_modification returns threshold adjustment for low_accuracy."""
        gap = {"type": "low_accuracy", "accuracy": 0.65, "predicate": "p1"}
        result = self.detector.suggest_modification(gap)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "adjust_threshold")
        self.assertEqual(result["predicate"], "p1")
        self.assertIn("65.00%", result["reason"])

    def test_suggest_threshold_low_accuracy(self):
        """suggest_modification returns add_branch for threshold_low_accuracy."""
        gap = {"type": "threshold_low_accuracy", "threshold": 0.8,
               "accuracy": 0.55, "predicate": "p1"}
        result = self.detector.suggest_modification(gap)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "add_branch")
        self.assertEqual(result["threshold"], 0.8)

    def test_suggest_insufficient_thresholds(self):
        """suggest_modification returns test_thresholds for insufficient_thresholds."""
        gap = {"type": "insufficient_thresholds", "tested": 1, "predicate": "p1"}
        result = self.detector.suggest_modification(gap)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "test_thresholds")
        self.assertIn("1", result["reason"])

    def test_suggest_high_latency(self):
        """suggest_modification returns optimize for high_latency."""
        gap = {"type": "high_latency", "avg_latency_ms": 15.5, "predicate": "p1"}
        result = self.detector.suggest_modification(gap)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "optimize")
        self.assertIn("15.50", result["reason"])

    def test_suggest_unknown_type_returns_none(self):
        """suggest_modification returns None for unknown gap type."""
        gap = {"type": "unknown_type", "predicate": "p1"}
        result = self.detector.suggest_modification(gap)
        self.assertIsNone(result)

    def test_suggest_missing_predicate_defaults_to_unknown(self):
        """suggest_modification uses 'unknown' when predicate is missing."""
        gap = {"type": "low_accuracy", "accuracy": 0.5}
        result = self.detector.suggest_modification(gap)
        self.assertIsNotNone(result)
        self.assertEqual(result["predicate"], "unknown")


class TestGetGapsSummary(TestCase):
    """Test get_gaps_summary method."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_gaps = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_DIR", self._tmpdir
        )
        self._patcher_gaps_file = patch(
            "vsf_rsi.rsi_gap_detector.GAPS_FILE", self._tmpdir / "rsi_gaps.json"
        )
        self._mock_metrics = MagicMock()
        self._patcher_metrics = patch(
            "vsf_rsi.rsi_gap_detector.RSIMetrics", return_value=self._mock_metrics
        )
        self._patcher_gaps.start()
        self._patcher_gaps_file.start()
        self._patcher_metrics.start()
        self.detector = RSIGapDetector()

    def tearDown(self):
        self._patcher_gaps.stop()
        self._patcher_gaps_file.stop()
        self._patcher_metrics.stop()

    def test_summary_no_metrics(self):
        """get_gaps_summary returns zeroed counts when no metrics."""
        self._mock_metrics._load_metrics.return_value = {}
        result = self.detector.get_gaps_summary()
        self.assertEqual(result["total_predicates"], 0)
        self.assertEqual(result["total_gaps"], 0)
        self.assertEqual(result["high_severity"], 0)
        self.assertEqual(result["medium_severity"], 0)
        self.assertEqual(result["low_severity"], 0)

    def test_summary_counts_gaps_by_severity(self):
        """get_gaps_summary correctly counts high/medium/low severity."""
        metrics_data = {
            "pred_a": {
                "total_classifications": 100,
                "correct_classifications": 60,  # low_accuracy (high)
                "thresholds": {"0.5": {"correct": 5, "total": 20, "latencies": [12.0]}},  # insufficient (medium) + threshold_low (high)
            }
        }
        self._mock_metrics._load_metrics.return_value = metrics_data
        result = self.detector.get_gaps_summary()
        self.assertEqual(result["total_predicates"], 1)
        self.assertGreater(result["total_gaps"], 0)
        self.assertGreaterEqual(result["high_severity"], 1)
        self.assertGreaterEqual(result["medium_severity"], 1)

    def test_summary_includes_per_predicate_details(self):
        """get_gaps_summary includes per-predicate gap details."""
        metrics_data = {
            "pred_a": {
                "total_classifications": 100,
                "correct_classifications": 60,
                "thresholds": {},
            }
        }
        self._mock_metrics._load_metrics.return_value = metrics_data
        result = self.detector.get_gaps_summary()
        self.assertIn("pred_a", result["predicates"])
        self.assertIn("gaps", result["predicates"]["pred_a"])
        self.assertIn("details", result["predicates"]["pred_a"])

    def test_summary_multiple_predicates(self):
        """get_gaps_summary handles multiple predicates."""
        metrics_data = {
            "a": {
                "total_classifications": 100, "correct_classifications": 50,
                "thresholds": {},
            },
            "b": {
                "total_classifications": 100, "correct_classifications": 95,
                "thresholds": {
                    "0.3": {"correct": 10, "total": 20, "latencies": [2.0]},
                    "0.5": {"correct": 10, "total": 20, "latencies": [2.0]},
                    "0.7": {"correct": 10, "total": 20, "latencies": [2.0]},
                },
            },
        }
        self._mock_metrics._load_metrics.return_value = metrics_data
        result = self.detector.get_gaps_summary()
        self.assertEqual(result["total_predicates"], 2)
        self.assertIn("a", result["predicates"])
        self.assertIn("b", result["predicates"])
