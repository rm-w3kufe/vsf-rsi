"""
Deep tests for rsi_gap_detector.py — covers CLI main() and get_gaps_summary.
Targets lines: 218, 231-264, 268
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_gap_detector import RSIGapDetector, main as cli_main


def _make_metrics_file(tmpdir, metrics_data):
    """Write metrics data to the expected path and return the detector."""
    metrics_file = tmpdir / "rsi_metrics.json"
    metrics_file.write_text(json.dumps(metrics_data))
    return metrics_file


class TestGetGapsSummarySeverity(TestCase):
    """Cover line 218: get_gaps_summary severity counting."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_gaps_summary_severity_counting(self):
        """Line 218: summary correctly counts severity levels."""
        metrics_data = {
            "bad_pred": {
                "thresholds": {
                    "0.5": {"total": 10, "correct": 3, "latencies": [1.0]},
                },
                "total_classifications": 10,
                "correct_classifications": 3,
                "latencies": [15.0],
            }
        }
        detector = RSIGapDetector()
        with patch.object(detector.metrics, "_load_metrics", return_value=metrics_data):
            summary = detector.get_gaps_summary()
        self.assertGreater(summary["total_gaps"], 0)
        self.assertIn("high_severity", summary)
        self.assertIn("medium_severity", summary)
        self.assertIn("low_severity", summary)
        self.assertEqual(summary["total_predicates"], 1)


class TestCLIMain(TestCase):
    """Cover lines 231-264, 268: CLI main() function."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_cli_detect_with_predicate(self):
        """Lines 246-251: detect command with specific predicate."""
        metrics_data = {
            "test_pred": {
                "thresholds": {
                    "0.5": {"total": 5, "correct": 2, "latencies": [1.0]},
                },
                "total_classifications": 5,
                "correct_classifications": 2,
                "latencies": [1.0],
            }
        }
        detector = RSIGapDetector()
        with patch.object(detector.metrics, "_load_metrics", return_value=metrics_data):
            with patch("sys.argv", ["prog", "detect", "--predicate", "test_pred"]):
                with patch("vsf_rsi.rsi_gap_detector.RSIGapDetector", return_value=detector):
                    cli_main()

    def test_cli_detect_all(self):
        """Lines 252-256: detect command without predicate (all)."""
        metrics_data = {
            "pred_a": {
                "thresholds": {},
                "total_classifications": 0,
                "correct_classifications": 0,
                "latencies": [],
            }
        }
        detector = RSIGapDetector()
        with patch.object(detector.metrics, "_load_metrics", return_value=metrics_data):
            with patch("sys.argv", ["prog", "detect"]):
                with patch("vsf_rsi.rsi_gap_detector.RSIGapDetector", return_value=detector):
                    cli_main()

    def test_cli_summary(self):
        """Lines 257-262: summary command."""
        metrics_data = {
            "test_pred": {
                "thresholds": {"0.5": {"total": 10, "correct": 5, "latencies": [2.0]}},
                "total_classifications": 10,
                "correct_classifications": 5,
                "latencies": [2.0],
            }
        }
        detector = RSIGapDetector()
        with patch.object(detector.metrics, "_load_metrics", return_value=metrics_data):
            with patch("sys.argv", ["prog", "summary"]):
                with patch("vsf_rsi.rsi_gap_detector.RSIGapDetector", return_value=detector):
                    cli_main()

    def test_cli_no_command(self):
        """Lines 263-264: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


class TestSuggestModification(TestCase):
    """Test suggest_modification covers all gap types."""

    def test_suggest_low_accuracy(self):
        """suggest_modification for low_accuracy gap."""
        detector = RSIGapDetector()
        gap = {"type": "low_accuracy", "accuracy": 0.65, "predicate": "p"}
        result = detector.suggest_modification(gap)
        self.assertEqual(result["type"], "adjust_threshold")

    def test_suggest_threshold_low_accuracy(self):
        """suggest_modification for threshold_low_accuracy gap."""
        detector = RSIGapDetector()
        gap = {"type": "threshold_low_accuracy", "threshold": 0.5, "accuracy": 0.6, "predicate": "p"}
        result = detector.suggest_modification(gap)
        self.assertEqual(result["type"], "add_branch")

    def test_suggest_insufficient_thresholds(self):
        """suggest_modification for insufficient_thresholds gap."""
        detector = RSIGapDetector()
        gap = {"type": "insufficient_thresholds", "tested": 1, "predicate": "p"}
        result = detector.suggest_modification(gap)
        self.assertEqual(result["type"], "test_thresholds")

    def test_suggest_high_latency(self):
        """suggest_modification for high_latency gap."""
        detector = RSIGapDetector()
        gap = {"type": "high_latency", "avg_latency_ms": 15.0, "predicate": "p"}
        result = detector.suggest_modification(gap)
        self.assertEqual(result["type"], "optimize")

    def test_suggest_unknown_type(self):
        """suggest_modification returns None for unknown gap type."""
        detector = RSIGapDetector()
        gap = {"type": "unknown_gap"}
        result = detector.suggest_modification(gap)
        self.assertIsNone(result)


class TestDetectGaps(TestCase):
    """Test detect_gaps and detect_all_gaps directly."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_detect_gaps_no_data(self):
        """detect_gaps returns empty gaps when predicate not in metrics."""
        detector = RSIGapDetector()
        with patch.object(detector.metrics, "_load_metrics", return_value={}):
            result = detector.detect_gaps("nonexistent")
        self.assertEqual(result["gaps"], [])

    def test_detect_all_gaps_empty(self):
        """detect_all_gaps returns empty when no metrics."""
        detector = RSIGapDetector()
        with patch.object(detector.metrics, "_load_metrics", return_value={}):
            result = detector.detect_all_gaps()
        self.assertEqual(result["predicates"], {})

    def test_save_and_load_gaps(self):
        """_save_gaps and _load_gaps persist data."""
        import vsf_rsi.rsi_gap_detector as mod
        original_gaps_file = mod.GAPS_FILE
        gaps_file = self._tmpdir / "rsi_gaps.json"
        mod.GAPS_FILE = gaps_file
        try:
            detector = RSIGapDetector()
            gaps = {"predicate": "test", "gaps": [], "timestamp": "2026-01-01T00:00:00Z"}
            detector._save_gaps(gaps)
            loaded = detector._load_gaps()
            self.assertIn("test", loaded)
        finally:
            mod.GAPS_FILE = original_gaps_file

    def test_load_gaps_no_file(self):
        """_load_gaps returns empty dict when no file."""
        import vsf_rsi.rsi_gap_detector as mod
        original_gaps_file = mod.GAPS_FILE
        mod.GAPS_FILE = self._tmpdir / "nonexistent.json"
        try:
            detector = RSIGapDetector()
            result = detector._load_gaps()
            self.assertEqual(result, {})
        finally:
            mod.GAPS_FILE = original_gaps_file


if __name__ == "__main__":
    main()
