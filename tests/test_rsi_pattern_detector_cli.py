"""
Tests for rsi_pattern_detector.py CLI main() — covers lines 338-366, 370.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_pattern_detector import main, RSIPatternDetector


class TestPatternDetectorCLIDetect(unittest.TestCase):
    """Test the 'detect' subcommand."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_patterns_dir = patch(
            "vsf_rsi.rsi_pattern_detector.PATTERNS_DIR", self._tmpdir
        )
        self._patcher_rs = patch("vsf_rsi.rsi_pattern_detector.RSIMetrics")
        self._mock_rs_cls = self._patcher_rs.start()
        self._patcher_patterns_dir.start()
        self._mock_metrics = MagicMock()
        self._mock_rs_cls.return_value = self._mock_metrics

    def tearDown(self):
        self._patcher_patterns_dir.stop()
        self._patcher_rs.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-pattern-detector", "detect", "--predicate", "test_pred"])
    def test_detect_with_predicate(self, ):
        """detect --predicate prints pattern list."""
        self._mock_metrics._load_metrics.return_value = {
            "test_pred": {
                "total": 100,
                "correct": 80,
                "incorrect": 20,
                "thresholds": {}
            }
        }
        with patch.object(RSIPatternDetector, "detect_patterns") as mock_detect:
            mock_detect.return_value = {
                "predicate": "test_pred",
                "patterns": [
                    {"type": "low_accuracy", "severity": "high"},
                    {"type": "threshold_drift", "severity": "medium"},
                ]
            }
            with patch("builtins.print") as mock_print:
                main()
            calls = [c[0][0] for c in mock_print.call_args_list]
            self.assertTrue(any("Patterns for test_pred: 2" in c for c in calls))
            self.assertTrue(any("low_accuracy" in c for c in calls))
            self.assertTrue(any("threshold_drift" in c for c in calls))

    @patch("sys.argv", ["rsi-pattern-detector", "detect"])
    def test_detect_no_predicate_prints_message(self):
        """detect without --predicate prints 'Please specify'."""
        with patch("builtins.print") as mock_print:
            main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Please specify --predicate" in c for c in calls))


class TestPatternDetectorCLISummary(unittest.TestCase):
    """Test the 'summary' subcommand."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_patterns_dir = patch(
            "vsf_rsi.rsi_pattern_detector.PATTERNS_DIR", self._tmpdir
        )
        self._patcher_rs = patch("vsf_rsi.rsi_pattern_detector.RSIMetrics")
        self._mock_rs_cls = self._patcher_rs.start()
        self._patcher_patterns_dir.start()
        self._mock_metrics = MagicMock()
        self._mock_rs_cls.return_value = self._mock_metrics

    def tearDown(self):
        self._patcher_patterns_dir.stop()
        self._patcher_rs.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-pattern-detector", "summary"])
    def test_summary(self):
        """summary prints total patterns and by-type."""
        with patch.object(RSIPatternDetector, "get_patterns_summary") as mock_summary:
            mock_summary.return_value = {
                "total_patterns": 5,
                "by_type": {"low_accuracy": 3, "drift": 2},
                "predicates": {}
            }
            with patch("builtins.print") as mock_print:
                main()
            calls = [c[0][0] for c in mock_print.call_args_list]
            self.assertTrue(any("Total patterns: 5" in c for c in calls))
            self.assertTrue(any("low_accuracy" in c for c in calls))


class TestPatternDetectorCLIHelp(unittest.TestCase):
    """Test no-subcommand prints help."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patcher_patterns_dir = patch(
            "vsf_rsi.rsi_pattern_detector.PATTERNS_DIR", self._tmpdir
        )
        self._patcher_rs = patch("vsf_rsi.rsi_pattern_detector.RSIMetrics")
        self._mock_rs_cls = self._patcher_rs.start()
        self._patcher_patterns_dir.start()
        self._mock_metrics = MagicMock()
        self._mock_rs_cls.return_value = self._mock_metrics

    def tearDown(self):
        self._patcher_patterns_dir.stop()
        self._patcher_rs.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-pattern-detector"])
    def test_no_command_prints_help(self):
        """No subcommand prints help (line 366)."""
        with patch.object(RSIPatternDetector, "detect_patterns") as mock_dp, \
             patch.object(RSIPatternDetector, "get_patterns_summary") as mock_gs, \
             patch("builtins.print") as mock_print:
            main()
        # No crash, no detect/summary calls
        mock_dp.assert_not_called()
        mock_gs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
