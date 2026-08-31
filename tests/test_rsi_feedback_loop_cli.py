"""
Tests for rsi_feedback_loop.py — covers line 79 (clamp logic)
and CLI main() lines 231-232, 240, 252-254, 263.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_feedback_loop import (
    main,
    RSIFeedbackLoop,
    ADJUSTMENT_STEP,
    DEFAULT_THRESHOLDS,
)


class TestThresholdClampLogic(unittest.TestCase):
    """Test line 79: downward clamp in adjust_thresholds."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self._tmpdir)),
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE",
                  Path(self._tmpdir) / "rsi_thresholds.json"),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE",
                  Path(self._tmpdir) / "rsi_adjustments.jsonl"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_downward_clamp(self):
        """Line 79: max(suggested, current - ADJUSTMENT_STEP) when suggested < current."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()

        # Set current threshold high, suggest much lower
        current_thresholds = {"test_pred": 0.90}
        thresholds_file = Path(self._tmpdir) / "rsi_thresholds.json"
        thresholds_file.write_text(json.dumps(current_thresholds))

        # Suggest 0.50 (diff = 0.40 > ADJUSTMENT_STEP)
        feedback.metrics.get_recommendation.return_value = {
            "action": "adjust",
            "suggested_threshold": 0.50,
            "reason": "low accuracy"
        }
        feedback.metrics._load_metrics.return_value = {
            "test_pred": {
                "thresholds": {
                    str(0.85): {"total": 50, "correct": 40},
                    str(0.90): {"total": 50, "correct": 35},
                }
            }
        }
        feedback.metrics.get_accuracy.return_value = 0.80

        result = feedback.adjust_thresholds()

        # new_threshold = max(0.50, 0.90 - 0.05) = max(0.50, 0.85) = 0.85
        adj = result["adjustments"][0]
        self.assertAlmostEqual(adj["new"], 0.85)

    def test_upward_clamp(self):
        """Line 77: min(suggested, current + ADJUSTMENT_STEP) when suggested > current."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()

        current_thresholds = {"test_pred": 0.50}
        thresholds_file = Path(self._tmpdir) / "rsi_thresholds.json"
        thresholds_file.write_text(json.dumps(current_thresholds))

        # Suggest 0.90 (diff = 0.40 > ADJUSTMENT_STEP)
        feedback.metrics.get_recommendation.return_value = {
            "action": "adjust",
            "suggested_threshold": 0.90,
            "reason": "improve accuracy"
        }
        feedback.metrics._load_metrics.return_value = {
            "test_pred": {
                "thresholds": {
                    str(0.55): {"total": 50, "correct": 45},
                    str(0.50): {"total": 50, "correct": 40},
                }
            }
        }
        feedback.metrics.get_accuracy.return_value = 0.85

        result = feedback.adjust_thresholds()

        # new_threshold = min(0.90, 0.50 + 0.05) = min(0.90, 0.55) = 0.55
        adj = result["adjustments"][0]
        self.assertAlmostEqual(adj["new"], 0.55)


class TestFeedbackLoopCLIAdjust(unittest.TestCase):
    """Test the 'adjust' subcommand (lines 228-232)."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self._tmpdir)),
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE",
                  Path(self._tmpdir) / "rsi_thresholds.json"),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE",
                  Path(self._tmpdir) / "rsi_adjustments.jsonl"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-feedback-loop", "adjust"])
    def test_adjust(self):
        """adjust prints adjustment count and details."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        feedback.metrics.get_recommendation.return_value = {
            "action": "keep", "suggested_threshold": None, "reason": "ok"
        }
        feedback.metrics._load_metrics.return_value = {}
        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print") as mock_print:
                main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Adjustments made: 0" in c for c in calls))


class TestFeedbackLoopCLIStatus(unittest.TestCase):
    """Test the 'status' subcommand (lines 233-247)."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self._tmpdir)),
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE",
                  Path(self._tmpdir) / "rsi_thresholds.json"),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE",
                  Path(self._tmpdir) / "rsi_adjustments.jsonl"),
        ]
        for p in self._patches:
            p.start()
        # Write thresholds file
        (Path(self._tmpdir) / "rsi_thresholds.json").write_text(
            json.dumps(DEFAULT_THRESHOLDS)
        )

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-feedback-loop", "status"])
    def test_status(self):
        """status prints thresholds and predicates."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        feedback.metrics.get_accuracy.return_value = 0.75
        feedback.metrics.get_recommendation.return_value = {
            "action": "keep", "reason": "within range"
        }
        # No history file means empty history
        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print") as mock_print:
                main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Current thresholds:" in c for c in calls))
        self.assertTrue(any("ac_stasis_critical" in c for c in calls))
        self.assertTrue(any("Per predicate:" in c for c in calls))
        self.assertTrue(any("75.00%" in c or "0.75" in c for c in calls))

    @patch("sys.argv", ["rsi-feedback-loop", "status"])
    def test_status_with_last_adjustment(self, ):
        """status prints last_adjustment timestamp when present (line 240)."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        feedback.metrics.get_accuracy.return_value = 0.80
        feedback.metrics.get_recommendation.return_value = {
            "action": "keep", "reason": "ok"
        }
        # Write an adjustment history entry
        adj_file = Path(self._tmpdir) / "rsi_adjustments.jsonl"
        entry = {"timestamp": "2026-01-01T00:00:00Z", "adjustments": []}
        adj_file.write_text(json.dumps(entry) + "\n")

        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print") as mock_print:
                main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Last adjustment: 2026-01-01" in c for c in calls))


class TestFeedbackLoopCLIHistory(unittest.TestCase):
    """Test the 'history' subcommand (lines 248-254)."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self._tmpdir)),
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE",
                  Path(self._tmpdir) / "rsi_thresholds.json"),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE",
                  Path(self._tmpdir) / "rsi_adjustments.jsonl"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-feedback-loop", "history"])
    def test_history_with_entries(self):
        """history prints timestamped adjustment entries."""
        adj_file = Path(self._tmpdir) / "rsi_adjustments.jsonl"
        entry = {
            "timestamp": "2026-06-01T12:00:00Z",
            "adjustments": [
                {"predicate": "pred_a", "old": 0.70, "new": 0.75}
            ]
        }
        adj_file.write_text(json.dumps(entry) + "\n")

        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print") as mock_print:
                main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Adjustment history: 1 entries" in c for c in calls))
        self.assertTrue(any("pred_a" in c for c in calls))
        self.assertTrue(any("pred_a" in c and "->" in c for c in calls))

    @patch("sys.argv", ["rsi-feedback-loop", "history"])
    def test_history_empty(self):
        """history with no file prints 0 entries."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print") as mock_print:
                main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Adjustment history: 0 entries" in c for c in calls))


class TestFeedbackLoopCLIThreshold(unittest.TestCase):
    """Test the 'threshold' subcommand (lines 255-257)."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self._tmpdir)),
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE",
                  Path(self._tmpdir) / "rsi_thresholds.json"),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE",
                  Path(self._tmpdir) / "rsi_adjustments.jsonl"),
        ]
        for p in self._patches:
            p.start()
        (Path(self._tmpdir) / "rsi_thresholds.json").write_text(
            json.dumps({"ac_stasis_critical": 0.70})
        )

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-feedback-loop", "threshold", "ac_stasis_critical"])
    def test_threshold(self):
        """threshold prints current value."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print") as mock_print:
                main()
        calls = [c[0][0] for c in mock_print.call_args_list]
        self.assertTrue(any("Current threshold for ac_stasis_critical" in c for c in calls))


class TestFeedbackLoopCLIHelp(unittest.TestCase):
    """Test no-subcommand prints help."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self._tmpdir)),
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE",
                  Path(self._tmpdir) / "rsi_thresholds.json"),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE",
                  Path(self._tmpdir) / "rsi_adjustments.jsonl"),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @patch("sys.argv", ["rsi-feedback-loop"])
    def test_no_command_prints_help(self):
        """No subcommand prints help (line 263)."""
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        with patch("vsf_rsi.rsi_feedback_loop.RSIFeedbackLoop", return_value=feedback):
            with patch("builtins.print"):
                main()
        # No crash, no adjust/status/history/threshold calls


if __name__ == "__main__":
    unittest.main()
