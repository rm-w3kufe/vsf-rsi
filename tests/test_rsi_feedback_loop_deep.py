#!/usr/bin/env python3
"""
Deep tests for rsi_feedback_loop.py — covers missing lines:
44-46, 56-99, 113-132, 136-139, 143-144, 148-149, 161-162, 166-175,
179-200, 206-259, 263
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vsf_rsi.rsi_feedback_loop import (
    RSIFeedbackLoop,
    CONFIG_DIR,
    THRESHOLDS_FILE,
    ADJUSTMENTS_FILE,
    DEFAULT_THRESHOLDS,
    MIN_SAMPLES,
    ACCURACY_THRESHOLD,
    ADJUSTMENT_STEP,
)


class TestRSIFeedbackLoopInit(unittest.TestCase):
    """Cover lines 44-46: __init__ creates config_dir."""

    def test_init_creates_config_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(tmpdir)):
                feedback = RSIFeedbackLoop()
                self.assertTrue(Path(tmpdir).exists())


class TestAdjustThresholds(unittest.TestCase):
    """Cover lines 56-99: adjust_thresholds full flow."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.thresholds_file = Path(self.tmpdir) / "rsi_thresholds.json"
        self.adjustments_file = Path(self.tmpdir) / "rsi_adjustments.jsonl"
        self._patches = [
            patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", self.thresholds_file),
            patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", self.adjustments_file),
            patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(self.tmpdir)),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_feedback(self):
        feedback = RSIFeedbackLoop()
        feedback.metrics = MagicMock()
        return feedback

    def test_adjust_no_change_when_same_threshold(self):
        feedback = self._make_feedback()
        self.thresholds_file.write_text(json.dumps({"pred": 0.70}))
        feedback.metrics.get_recommendation.return_value = {
            "action": "adjust",
            "suggested_threshold": 0.72,
            "reason": "test"
        }
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {"0.71": {"total": 15, "correct": 13, "latencies": []}}}
        }
        result = feedback.adjust_thresholds()
        self.assertEqual(len(result["adjustments"]), 0)

    def test_adjust_applies_when_significant(self):
        feedback = self._make_feedback()
        self.thresholds_file.write_text(json.dumps({"pred": 0.50}))
        feedback.metrics.get_recommendation.return_value = {
            "action": "adjust",
            "suggested_threshold": 0.80,
            "reason": "accuracy low"
        }
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {"0.55": {"total": 20, "correct": 18, "latencies": []}}}
        }
        result = feedback.adjust_thresholds()
        self.assertGreater(len(result["adjustments"]), 0)
        adj = result["adjustments"][0]
        self.assertEqual(adj["old"], 0.50)
        self.assertGreater(adj["new"], 0.50)

    def test_adjust_limit_step_size(self):
        feedback = self._make_feedback()
        self.thresholds_file.write_text(json.dumps({"pred": 0.50}))
        feedback.metrics.get_recommendation.return_value = {
            "action": "adjust",
            "suggested_threshold": 0.95,
            "reason": "way off"
        }
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {"0.55": {"total": 20, "correct": 18, "latencies": []}}}
        }
        result = feedback.adjust_thresholds()
        if result["adjustments"]:
            adj = result["adjustments"][0]
            self.assertLessEqual(adj["new"] - adj["old"], ADJUSTMENT_STEP + 0.001)

    def test_adjust_no_action_when_keep(self):
        feedback = self._make_feedback()
        self.thresholds_file.write_text(json.dumps({"pred": 0.70}))
        feedback.metrics.get_recommendation.return_value = {
            "action": "keep",
            "suggested_threshold": 0.70,
            "reason": "optimal"
        }
        result = feedback.adjust_thresholds()
        self.assertEqual(len(result["adjustments"]), 0)

    def test_adjust_no_action_when_collect_data(self):
        feedback = self._make_feedback()
        self.thresholds_file.write_text(json.dumps({"pred": 0.70}))
        feedback.metrics.get_recommendation.return_value = {
            "action": "collect_data",
            "suggested_threshold": None,
            "reason": "no data"
        }
        result = feedback.adjust_thresholds()
        self.assertEqual(len(result["adjustments"]), 0)

    def test_adjust_saves_new_thresholds(self):
        feedback = self._make_feedback()
        self.thresholds_file.write_text(json.dumps({"pred": 0.50}))
        feedback.metrics.get_recommendation.return_value = {
            "action": "adjust",
            "suggested_threshold": 0.80,
            "reason": "low accuracy"
        }
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {"0.60": {"total": 20, "correct": 18, "latencies": []}}}
        }
        feedback.adjust_thresholds()
        saved = json.loads(self.thresholds_file.read_text())
        self.assertIn("pred", saved)


class TestValidateThreshold(unittest.TestCase):
    """Cover lines 113-132: _validate_threshold."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_feedback(self):
        feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
        feedback.metrics = MagicMock()
        return feedback

    def test_validate_rejects_low_accuracy(self):
        feedback = self._make_feedback()
        feedback.metrics.get_accuracy.return_value = 0.5
        self.assertFalse(feedback._validate_threshold("pred", 0.7))

    def test_validate_rejects_missing_predicate(self):
        feedback = self._make_feedback()
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {}
        self.assertFalse(feedback._validate_threshold("pred", 0.7))

    def test_validate_rejects_missing_threshold(self):
        feedback = self._make_feedback()
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {}}
        }
        self.assertFalse(feedback._validate_threshold("pred", 0.7))

    def test_validate_rejects_insufficient_samples(self):
        feedback = self._make_feedback()
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {"0.7": {"total": 5, "correct": 4, "latencies": []}}}
        }
        self.assertFalse(feedback._validate_threshold("pred", 0.7))

    def test_validate_accepts_valid_threshold(self):
        feedback = self._make_feedback()
        feedback.metrics.get_accuracy.return_value = 0.9
        feedback.metrics._load_metrics.return_value = {
            "pred": {"thresholds": {"0.7": {"total": 15, "correct": 13, "latencies": []}}}
        }
        self.assertTrue(feedback._validate_threshold("pred", 0.7))


class TestLoadThresholds(unittest.TestCase):
    """Cover lines 136-139: _load_thresholds."""

    def test_load_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tfile = Path(tmpdir) / "rsi_thresholds.json"
            tfile.write_text(json.dumps({"custom": 0.55}))
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", tfile):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                result = feedback._load_thresholds()
                self.assertEqual(result["custom"], 0.55)

    def test_load_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "no_file.json"
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", nonexistent):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                result = feedback._load_thresholds()
                self.assertEqual(result, DEFAULT_THRESHOLDS)


class TestSaveThresholds(unittest.TestCase):
    """Cover lines 143-144: _save_thresholds."""

    def test_save_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tfile = Path(tmpdir) / "out.json"
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", tfile):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                feedback._save_thresholds({"pred": 0.80})
                self.assertTrue(tfile.exists())
                saved = json.loads(tfile.read_text())
                self.assertEqual(saved["pred"], 0.80)


class TestRecordAdjustment(unittest.TestCase):
    """Cover lines 148-149: _record_adjustment."""

    def test_record_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            afile = Path(tmpdir) / "adjustments.jsonl"
            with patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", afile):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                feedback._record_adjustment({"timestamp": "now", "adjustments": []})
                self.assertTrue(afile.exists())
                lines = afile.read_text().strip().split("\n")
                self.assertEqual(len(lines), 1)


class TestGetCurrentThreshold(unittest.TestCase):
    """Cover lines 161-162: get_current_threshold."""

    def test_get_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tfile = Path(tmpdir) / "rsi_thresholds.json"
            tfile.write_text(json.dumps({"pred": 0.65}))
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", tfile):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                feedback.metrics = MagicMock()
                val = feedback.get_current_threshold("pred")
                self.assertEqual(val, 0.65)

    def test_get_default_known_predicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "no.json"
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", nonexistent):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                feedback.metrics = MagicMock()
                val = feedback.get_current_threshold("ac_stasis_critical")
                self.assertEqual(val, 0.70)

    def test_get_default_unknown_predicate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "no.json"
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", nonexistent):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                feedback.metrics = MagicMock()
                val = feedback.get_current_threshold("unknown_pred")
                self.assertEqual(val, 0.50)


class TestGetAdjustmentHistory(unittest.TestCase):
    """Cover lines 166-175: get_adjustment_history."""

    def test_history_empty_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            afile = Path(tmpdir) / "no.jsonl"
            with patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", afile):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                history = feedback.get_adjustment_history()
                self.assertEqual(history, [])

    def test_history_reads_entries(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            afile = Path(tmpdir) / "adjustments.jsonl"
            entry = {"timestamp": "2025-01-01", "adjustments": [{"pred": 0.5}]}
            afile.write_text(json.dumps(entry) + "\n")
            with patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", afile):
                feedback = RSIFeedbackLoop.__new__(RSIFeedbackLoop)
                history = feedback.get_adjustment_history()
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["timestamp"], "2025-01-01")


class TestGetStatus(unittest.TestCase):
    """Cover lines 179-200: get_status."""

    def test_status_returns_all_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tfile = Path(tmpdir) / "rsi_thresholds.json"
            tfile.write_text(json.dumps({"pred": 0.70}))
            afile = Path(tmpdir) / "adjustments.jsonl"
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", tfile), \
                 patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", afile), \
                 patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(tmpdir)):
                feedback = RSIFeedbackLoop()
                feedback.metrics = MagicMock()
                feedback.metrics.get_accuracy.return_value = 0.85
                feedback.metrics.get_recommendation.return_value = {
                    "action": "keep",
                    "reason": "optimal"
                }
                status = feedback.get_status()
                self.assertIn("current_thresholds", status)
                self.assertIn("total_adjustments", status)
                self.assertIn("last_adjustment", status)
                self.assertIn("predicates", status)
                self.assertIn("pred", status["predicates"])
                self.assertEqual(status["predicates"]["pred"]["threshold"], 0.70)
                self.assertEqual(status["predicates"]["pred"]["accuracy"], 0.85)

    def test_status_no_adjustments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tfile = Path(tmpdir) / "rsi_thresholds.json"
            tfile.write_text(json.dumps({"pred": 0.70}))
            afile = Path(tmpdir) / "no.jsonl"
            with patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", tfile), \
                 patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", afile), \
                 patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(tmpdir)):
                feedback = RSIFeedbackLoop()
                feedback.metrics = MagicMock()
                feedback.metrics.get_accuracy.return_value = 0.0
                feedback.metrics.get_recommendation.return_value = {
                    "action": "collect_data",
                    "reason": "none",
                    "suggested_threshold": None
                }
                status = feedback.get_status()
                self.assertIsNone(status["last_adjustment"])


class TestCLI(unittest.TestCase):
    """Cover lines 206-259, 263: main() CLI."""

    def _patch_all(self, tmpdir):
        return patch("vsf_rsi.rsi_feedback_loop.THRESHOLDS_FILE", Path(tmpdir) / "t.json"), \
               patch("vsf_rsi.rsi_feedback_loop.ADJUSTMENTS_FILE", Path(tmpdir) / "a.jsonl"), \
               patch("vsf_rsi.rsi_feedback_loop.CONFIG_DIR", Path(tmpdir))

    def test_main_adjust(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "rsi_thresholds.json").write_text(json.dumps({"pred": 0.70}))
            p1, p2, p3 = self._patch_all(tmpdir)
            with p1, p2, p3:
                with patch("sys.argv", ["prog", "adjust"]):
                    from vsf_rsi.rsi_feedback_loop import main
                    main()

    def test_main_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "rsi_thresholds.json").write_text(json.dumps({"pred": 0.70}))
            p1, p2, p3 = self._patch_all(tmpdir)
            with p1, p2, p3:
                with patch("sys.argv", ["prog", "status"]):
                    from vsf_rsi.rsi_feedback_loop import main
                    main()

    def test_main_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1, p2, p3 = self._patch_all(tmpdir)
            with p1, p2, p3:
                with patch("sys.argv", ["prog", "history"]):
                    from vsf_rsi.rsi_feedback_loop import main
                    main()

    def test_main_threshold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "rsi_thresholds.json").write_text(json.dumps({"pred": 0.70}))
            p1, p2, p3 = self._patch_all(tmpdir)
            with p1, p2, p3:
                with patch("sys.argv", ["prog", "threshold", "pred"]):
                    from vsf_rsi.rsi_feedback_loop import main
                    main()

    def test_main_no_command(self):
        with patch("sys.argv", ["prog"]):
            from vsf_rsi.rsi_feedback_loop import main
            main()


if __name__ == "__main__":
    unittest.main()
