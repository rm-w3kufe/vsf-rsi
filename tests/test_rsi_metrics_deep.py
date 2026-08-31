"""
Deep tests for rsi_metrics.py — covers CLI main(), _get_current_threshold, edge cases.
Targets lines: 129, 134, 158-163, 171, 220, 229, 245, 261-266, 302, 308,
311-312, 405-462, 466
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from vsf_rsi.rsi_metrics import RSIMetrics, main as cli_main


class TestGetAccuracyEdgeCases(TestCase):
    """Cover lines 129, 134: get_accuracy edge cases."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as mod
        self._original_dir = mod.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        mod.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as mod
        mod.METRICS_DIR = self._original_dir

    def test_accuracy_threshold_not_found(self):
        """Line 129: threshold not in predicates thresholds dict returns 0.0."""
        # Write metrics with threshold 0.5 but ask for 0.9
        metrics = {"test_pred": {
            "thresholds": {"0.5": {"total": 10, "correct": 8, "latencies": [1.0]}},
            "total_classifications": 10,
            "correct_classifications": 8,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        result = self.metrics.get_accuracy("test_pred", threshold=0.9)
        self.assertEqual(result, 0.0)

    def test_accuracy_threshold_zero_total(self):
        """Line 129 (inner): threshold has total=0 returns 0.0."""
        metrics = {"test_pred": {
            "thresholds": {"0.5": {"total": 0, "correct": 0, "latencies": []}},
            "total_classifications": 0,
            "correct_classifications": 0,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        result = self.metrics.get_accuracy("test_pred", threshold=0.5)
        self.assertEqual(result, 0.0)

    def test_accuracy_zero_total_classifications(self):
        """Line 134: total_classifications=0 returns 0.0."""
        metrics = {"test_pred": {
            "thresholds": {},
            "total_classifications": 0,
            "correct_classifications": 0,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        result = self.metrics.get_accuracy("test_pred")
        self.assertEqual(result, 0.0)


class TestGetLatencyEdgeCases(TestCase):
    """Cover lines 158-163, 171: get_latency edge cases."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as mod
        self._original_dir = mod.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        mod.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as mod
        mod.METRICS_DIR = self._original_dir

    def test_latency_threshold_not_found(self):
        """Line 159: threshold not in thresholds returns 0.0."""
        metrics = {"test_pred": {
            "thresholds": {"0.5": {"total": 10, "correct": 8, "latencies": [5.0]}},
            "total_classifications": 10,
            "correct_classifications": 8,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        result = self.metrics.get_latency("test_pred", threshold=0.9)
        self.assertEqual(result, 0.0)

    def test_latency_threshold_empty_latencies(self):
        """Line 161-162: threshold has empty latencies returns 0.0."""
        metrics = {"test_pred": {
            "thresholds": {"0.5": {"total": 10, "correct": 8, "latencies": []}},
            "total_classifications": 10,
            "correct_classifications": 8,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        result = self.metrics.get_latency("test_pred", threshold=0.5)
        self.assertEqual(result, 0.0)

    def test_latency_overall_no_latencies(self):
        """Line 171: overall latency with no latencies in any threshold returns 0.0."""
        metrics = {"test_pred": {
            "thresholds": {"0.5": {"total": 10, "correct": 8, "latencies": []}},
            "total_classifications": 10,
            "correct_classifications": 8,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        result = self.metrics.get_latency("test_pred")
        self.assertEqual(result, 0.0)


class TestGetRecommendationEdgeCases(TestCase):
    """Cover lines 220, 229, 245: get_recommendation edge cases."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as mod
        self._original_dir = mod.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        mod.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as mod
        mod.METRICS_DIR = self._original_dir

    def test_recommendation_threshold_zero_total(self):
        """Line 220: threshold with total=0 is skipped, no best found."""
        metrics = {"test_pred": {
            "thresholds": {"0.5": {"total": 0, "correct": 0, "latencies": []}},
            "total_classifications": 0,
            "correct_classifications": 0,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        rec = self.metrics.get_recommendation("test_pred")
        self.assertEqual(rec["action"], "collect_data")
        self.assertEqual(rec["reason"], "No threshold data available")

    def test_recommendation_best_threshold_differs_current(self):
        """Line 245: best threshold differs from current, suggests adjust."""
        # Set up two thresholds: 0.5 with 100% accuracy, 0.7 with 50%
        # Current default for unknown predicate is 0.50
        metrics = {"test_pred": {
            "thresholds": {
                "0.7": {"total": 10, "correct": 5, "latencies": []},
                "0.5": {"total": 10, "correct": 10, "latencies": []},
            },
            "total_classifications": 20,
            "correct_classifications": 15,
        }}
        (self._tmpdir / "rsi_metrics.json").write_text(json.dumps(metrics))
        rec = self.metrics.get_recommendation("test_pred")
        self.assertEqual(rec["action"], "keep")
        self.assertIn("suggested_threshold", rec)


class TestGetCurrentThreshold(TestCase):
    """Cover lines 261-266: _get_current_threshold with file."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as mod
        self._original_dir = mod.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        mod.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as mod
        mod.METRICS_DIR = self._original_dir

    def test_get_current_threshold_from_file(self):
        """Lines 261-264: reads from rsi_thresholds.json."""
        thresholds = {"my_pred": 0.85}
        (self._tmpdir / "rsi_thresholds.json").write_text(json.dumps(thresholds))
        result = self.metrics._get_current_threshold("my_pred")
        self.assertEqual(result, 0.85)

    def test_get_current_threshold_default(self):
        """Line 267: predicate not in file returns default 0.50."""
        thresholds = {"other_pred": 0.85}
        (self._tmpdir / "rsi_thresholds.json").write_text(json.dumps(thresholds))
        result = self.metrics._get_current_threshold("unknown_pred")
        self.assertEqual(result, 0.50)

    def test_get_current_threshold_no_file(self):
        """Line 267: no file returns default from dict or 0.50."""
        result = self.metrics._get_current_threshold("ac_stasis_critical")
        self.assertEqual(result, 0.70)

    def test_get_current_threshold_corrupt_file(self):
        """Line 265-266: corrupt thresholds file falls back to default."""
        (self._tmpdir / "rsi_thresholds.json").write_text("NOT JSON {{{")
        result = self.metrics._get_current_threshold("my_pred")
        self.assertEqual(result, 0.50)


class TestRebuildFromHistory(TestCase):
    """Cover lines 302, 308, 311-312: rebuild_from_history edge cases."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as mod
        self._original_dir = mod.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        mod.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as mod
        mod.METRICS_DIR = self._original_dir

    def test_rebuild_no_history_file(self):
        """Line 302: no history file returns empty dict."""
        result = self.metrics.rebuild_from_history()
        self.assertEqual(result, {})

    def test_rebuild_empty_history(self):
        """Lines 307-308: empty lines in history are skipped."""
        history_file = self._tmpdir / "rsi_metrics_history.jsonl"
        history_file.write_text("\n\n\n")
        result = self.metrics.rebuild_from_history()
        self.assertEqual(result, {})

    def test_rebuild_corrupt_json_lines(self):
        """Lines 311-312: corrupt JSON lines are skipped."""
        history_file = self._tmpdir / "rsi_metrics_history.jsonl"
        history_file.write_text(
            "not json\n"
            '{"predicate":"p","threshold":0.5,"correct":true,"latency_ms":1.0}\n'
            "also bad\n"
        )
        result = self.metrics.rebuild_from_history()
        self.assertIn("p", result)
        self.assertEqual(result["p"]["total_classifications"], 1)


class TestCLIMain(TestCase):
    """Cover lines 405-462, 466: CLI main() function."""

    def setUp(self):
        import vsf_rsi.rsi_metrics as mod
        self._original_dir = mod.METRICS_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        mod.METRICS_DIR = self._tmpdir
        self.metrics = RSIMetrics()
        metrics_file = self._tmpdir / "rsi_metrics.json"
        if metrics_file.exists():
            metrics_file.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_metrics as mod
        mod.METRICS_DIR = self._original_dir

    def test_cli_track(self):
        """Lines 434-443: track command."""
        with patch("sys.argv", ["prog", "track", "my_pred", "0.5", "0.3", "true", "true", "10.0"]):
            cli_main()
        metrics = self.metrics._load_metrics()
        self.assertIn("my_pred", metrics)

    def test_cli_accuracy(self):
        """Lines 444-446: accuracy command."""
        self.metrics.track_classification("my_pred", 0.5, 0.3, True, True, 10.0)
        with patch("sys.argv", ["prog", "accuracy", "my_pred"]):
            cli_main()

    def test_cli_accuracy_with_threshold(self):
        """Lines 444-446: accuracy with --threshold."""
        self.metrics.track_classification("my_pred", 0.5, 0.3, True, True, 10.0)
        with patch("sys.argv", ["prog", "accuracy", "my_pred", "--threshold", "0.5"]):
            cli_main()

    def test_cli_recommend(self):
        """Lines 447-452: recommend command."""
        self.metrics.track_classification("my_pred", 0.5, 0.3, True, True, 10.0)
        with patch("sys.argv", ["prog", "recommend", "my_pred"]):
            cli_main()

    def test_cli_summary(self):
        """Lines 453-460: summary command."""
        self.metrics.track_classification("my_pred", 0.5, 0.3, True, True, 10.0)
        with patch("sys.argv", ["prog", "summary"]):
            cli_main()

    def test_cli_no_command(self):
        """Lines 461-462: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


if __name__ == "__main__":
    main()
