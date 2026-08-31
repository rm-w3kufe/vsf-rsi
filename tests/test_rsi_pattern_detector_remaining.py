#!/usr/bin/env python3
"""
Tests for rsi_pattern_detector.py — covering remaining missing lines.

Missing lines:
  85      accuracy_degradation pattern append
  100     early return None when total_classifications == 0
  132     early return None when no best threshold
  146     early return None when threshold within 0.1 of current
  188     early return None when coverage gap not detected (>= 5 thresholds)
  275-278 days_since fallback when last_seen missing/unparseable in _apply_decay
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestMisclassificationZeroClassifications(unittest.TestCase):
    """Line 100: early return None when total_classifications == 0."""

    def test_returns_none_when_no_classifications(self):
        """_detect_misclassification_pattern returns None when count is 0."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            pm = {
                "total_classifications": 0,
                "correct_classifications": 0,
                "thresholds": {},
            }
            result = detector._detect_misclassification_pattern(pm)
            self.assertIsNone(result)


class TestThresholdPatternNoBestThreshold(unittest.TestCase):
    """Line 132: early return None when no best threshold found."""

    def test_returns_none_when_all_thresholds_zero_total(self):
        """_detect_threshold_pattern returns None when no threshold has data."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            pm = {
                "thresholds": {
                    "0.5": {"total": 0, "correct": 0},
                    "0.6": {"total": 0, "correct": 0},
                    "0.7": {"total": 0, "correct": 0},
                }
            }
            result = detector._detect_threshold_pattern(pm)
            self.assertIsNone(result)

    def test_returns_none_when_fewer_than_3_thresholds(self):
        """_detect_threshold_pattern returns None when < 3 thresholds."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            pm = {
                "thresholds": {
                    "0.5": {"total": 10, "correct": 9},
                }
            }
            result = detector._detect_threshold_pattern(pm)
            self.assertIsNone(result)


class TestThresholdNearCurrent(unittest.TestCase):
    """Line 146: early return None when threshold within 0.1 of current (0.7)."""

    def test_returns_none_when_best_near_current_threshold(self):
        """_detect_threshold_pattern returns None when best ≈ 0.7."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            # best threshold = 0.72, current = 0.7, diff = 0.02 < 0.1
            pm = {
                "thresholds": {
                    "0.5": {"total": 10, "correct": 5},
                    "0.6": {"total": 10, "correct": 6},
                    "0.72": {"total": 100, "correct": 95},
                }
            }
            result = detector._detect_threshold_pattern(pm)
            self.assertIsNone(result)


class TestCoverageGapNotDetected(unittest.TestCase):
    """Line 188: early return None when >= 5 thresholds tested."""

    def test_returns_none_when_enough_thresholds(self):
        """_detect_coverage_pattern returns None when >= 5 thresholds."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            pm = {
                "thresholds": {
                    "0.3": {}, "0.4": {}, "0.5": {}, "0.6": {}, "0.7": {},
                }
            }
            result = detector._detect_coverage_pattern(pm)
            self.assertIsNone(result)

    def test_returns_pattern_when_few_thresholds(self):
        """_detect_coverage_pattern returns pattern when < 5 thresholds."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            pm = {"thresholds": {"0.5": {}, "0.6": {}}}
            result = detector._detect_coverage_pattern(pm)
            self.assertIsNotNone(result)
            self.assertEqual(result["type"], "coverage_gap")


class TestApplyDecayDaysSinceFallback(unittest.TestCase):
    """Lines 275-278: days_since fallback when last_seen missing/unparseable."""

    def test_days_since_zero_when_no_last_seen(self):
        """_apply_decay uses days_since=0 when last_seen is missing."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            patterns = {
                "pred1": {
                    "predicate": "pred1",
                    "patterns": [
                        {"type": "test", "strength": 1.0}  # no last_seen
                    ],
                }
            }
            result = detector._apply_decay(patterns)
            # Should still have the pattern (strength ≈ 1.0 * 1.0^0 = 1.0)
            self.assertIn("pred1", result)
            self.assertAlmostEqual(result["pred1"]["patterns"][0]["strength"], 1.0, places=2)

    def test_days_since_zero_when_last_seen_unparseable(self):
        """_apply_decay uses days_since=0 when last_seen is garbage."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            patterns = {
                "pred1": {
                    "predicate": "pred1",
                    "patterns": [
                        {"type": "test", "strength": 0.8, "last_seen": "not-a-date"}
                    ],
                }
            }
            result = detector._apply_decay(patterns)
            self.assertIn("pred1", result)
            # strength should remain ~0.8 since days_since=0
            self.assertAlmostEqual(
                result["pred1"]["patterns"][0]["strength"], 0.8, places=2
            )

    def test_days_since_zero_when_last_seen_none(self):
        """_apply_decay uses days_since=0 when last_seen is None."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            patterns = {
                "pred1": {
                    "predicate": "pred1",
                    "patterns": [
                        {"type": "test", "strength": 0.5, "last_seen": None}
                    ],
                }
            }
            result = detector._apply_decay(patterns)
            self.assertIn("pred1", result)

    def test_valid_last_seen_applies_decay(self):
        """_apply_decay applies proper decay with valid last_seen."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            old_date = "2020-01-01T00:00:00+00:00"
            patterns = {
                "pred1": {
                    "predicate": "pred1",
                    "patterns": [
                        {"type": "test", "strength": 1.0, "last_seen": old_date}
                    ],
                }
            }
            result = detector._apply_decay(patterns)
            # Very old date → strength should be decayed significantly
            if "pred1" in result:
                strength = result["pred1"]["patterns"][0]["strength"]
                self.assertLess(strength, 1.0)


class TestAccuracyDegradationPattern(unittest.TestCase):
    """Line 85: accuracy_degradation pattern append in detect_patterns."""

    def test_degradation_pattern_appended(self):
        """detect_patterns appends degradation pattern when detected."""
        from vsf_rsi.rsi_pattern_detector import RSIPatternDetector

        # _detect_degradation_pattern currently always returns None (line 176),
        # so we patch it to return a pattern to test the append path
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_pattern_detector as mod
            mod.PATTERNS_DIR = Path(tmpdir)
            mod.PATTERNS_FILE = Path(tmpdir) / "patterns.json"

            detector = RSIPatternDetector()
            degradation_pattern = {
                "type": "accuracy_degradation",
                "severity": "high",
            }

            pm = {
                "total_classifications": 100,
                "correct_classifications": 50,
                "thresholds": {
                    "0.5": {"total": 50, "correct": 25},
                    "0.6": {"total": 50, "correct": 25},
                },
            }

            metrics = {"test_pred": pm}
            with patch.object(detector.metrics, "_load_metrics", return_value=metrics), \
                 patch.object(detector, "_detect_misclassification_pattern", return_value=None), \
                 patch.object(detector, "_detect_threshold_pattern", return_value=None), \
                 patch.object(detector, "_detect_latency_pattern", return_value=None), \
                 patch.object(detector, "_detect_degradation_pattern", return_value=degradation_pattern), \
                 patch.object(detector, "_detect_coverage_pattern", return_value=None), \
                 patch.object(detector, "_save_patterns"):
                result = detector.detect_patterns("test_pred")

            self.assertEqual(len(result["patterns"]), 1)
            self.assertEqual(result["patterns"][0]["type"], "accuracy_degradation")


if __name__ == "__main__":
    unittest.main()
