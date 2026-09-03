"""
Tests for rsi_scenario_bridge.py — Scenario-memory ↔ RSI gap detector bridge
"""

from unittest import TestCase, main
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import vsf_rsi.rsi_scenario_bridge as bridge


class TestImportHelpers(TestCase):
    """Test _import_scenario_memory and _import_gap_detector."""

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    def test_import_scenario_memory_missing(self, mock_import):
        """_import_scenario_memory raises ImportError when unavailable."""
        mock_import.side_effect = ImportError("scenario_memory not available")
        with self.assertRaises(ImportError):
            mock_import()

    @patch("vsf_rsi.rsi_scenario_bridge._sm")
    def test_import_scenario_memory_available(self, mock_sm):
        """_import_scenario_memory returns module when available."""
        # Reset the bridge module-level import
        import importlib
        with patch.dict("sys.modules", {"vsf_rsi.scenario_memory": mock_sm}):
            with patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory",
                       return_value=mock_sm):
                result = bridge._import_scenario_memory()
                self.assertIsNotNone(result)

    @patch("vsf_rsi.rsi_scenario_bridge._import_gap_detector")
    def test_import_gap_detector_available(self, mock_import):
        """_import_gap_detector returns RSIGapDetector instance."""
        mock_detector = MagicMock()
        mock_import.return_value = mock_detector
        result = bridge._import_gap_detector()
        self.assertEqual(result, mock_detector)


class TestFailuresToGaps(TestCase):
    """Test failures_to_gaps function."""

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    def test_failures_to_gaps_no_failures(self, mock_import):
        """failures_to_gaps returns empty when no failures."""
        mock_sm = MagicMock()
        mock_sm._load_all.return_value = [
            {"outcome": "success", "id": "s1"},
            {"outcome": "success", "id": "s2"},
        ]
        mock_import.return_value = mock_sm
        result = bridge.failures_to_gaps()
        self.assertEqual(result["total_failures"], 0)
        self.assertEqual(result["failure_gaps"], [])

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    def test_failures_to_gaps_with_failures(self, mock_import):
        """failures_to_gaps converts failures to gaps."""
        mock_sm = MagicMock()
        mock_sm._load_all.return_value = [
            {
                "outcome": "failure",
                "id": "s1",
                "fault_signature": "ac_stasis_crash",
                "decision": "wrong",
                "correction_path": "/fix/1",
            },
            {
                "outcome": "success",
                "id": "s2",
            },
            {
                "outcome": "failure",
                "id": "s3",
                "fault_signature": "ac_stasis_other",
                "decision": "bad",
                "correction_path": "/fix/2",
            },
        ]
        mock_import.return_value = mock_sm
        result = bridge.failures_to_gaps()
        self.assertEqual(result["total_failures"], 2)
        self.assertEqual(result["failure_gaps"][0]["scenario_id"], "s1")
        self.assertEqual(result["failure_gaps"][0]["type"], "scenario_failure")
        self.assertEqual(result["failure_gaps"][0]["severity"], "high")

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    def test_failures_to_gaps_with_predicate_filter(self, mock_import):
        """failures_to_gaps filters by predicate_name in fault_signature."""
        mock_sm = MagicMock()
        mock_sm._load_all.return_value = [
            {
                "outcome": "failure",
                "id": "s1",
                "fault_signature": "ac_stasis_crash",
            },
            {
                "outcome": "failure",
                "id": "s2",
                "fault_signature": "other_crash",
            },
        ]
        mock_import.return_value = mock_sm
        result = bridge.failures_to_gaps(predicate_name="ac_stasis")
        self.assertEqual(result["total_failures"], 1)
        self.assertEqual(result["failure_gaps"][0]["scenario_id"], "s1")

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    def test_failures_to_gaps_empty(self, mock_import):
        """failures_to_gaps handles empty scenario list."""
        mock_sm = MagicMock()
        mock_sm._load_all.return_value = []
        mock_import.return_value = mock_sm
        result = bridge.failures_to_gaps()
        self.assertEqual(result["total_failures"], 0)
        self.assertIn("timestamp", result)

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    def test_failures_to_gaps_result_structure(self, mock_import):
        """failures_to_gaps returns correct result structure."""
        mock_sm = MagicMock()
        mock_sm._load_all.return_value = []
        mock_import.return_value = mock_sm
        result = bridge.failures_to_gaps(predicate_name="test")
        self.assertEqual(result["predicate"], "test")
        self.assertIn("failure_gaps", result)
        self.assertIn("total_failures", result)
        self.assertIn("timestamp", result)


class TestGapsToCorrections(TestCase):
    """Test gaps_to_corrections function."""

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    @patch("vsf_rsi.rsi_scenario_bridge._import_gap_detector")
    def test_gaps_to_corrections_with_match(self, mock_det_import, mock_sm_import):
        """gaps_to_corrections enriches gaps with scenario corrections."""
        mock_detector = MagicMock()
        mock_detector.detect_gaps.return_value = {
            "gaps": [
                {"type": "accuracy_gap", "severity": "high"},
            ]
        }
        mock_det_import.return_value = mock_detector

        mock_sm = MagicMock()
        mock_sm.match.return_value = ("s1", "/fix/1")
        mock_sm_import.return_value = mock_sm

        result = bridge.gaps_to_corrections("test_pred")
        self.assertEqual(result["total_gaps"], 1)
        self.assertEqual(result["with_corrections"], 1)
        self.assertTrue(result["enriched_gaps"][0]["has_scenario_correction"])

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    @patch("vsf_rsi.rsi_scenario_bridge._import_gap_detector")
    def test_gaps_to_corrections_no_match(self, mock_det_import, mock_sm_import):
        """gaps_to_corrections marks gaps without corrections."""
        mock_detector = MagicMock()
        mock_detector.detect_gaps.return_value = {
            "gaps": [
                {"type": "latency_gap", "severity": "medium"},
            ]
        }
        mock_det_import.return_value = mock_detector

        mock_sm = MagicMock()
        mock_sm.match.return_value = None
        mock_sm_import.return_value = mock_sm

        result = bridge.gaps_to_corrections("test_pred")
        self.assertEqual(result["total_gaps"], 1)
        self.assertEqual(result["with_corrections"], 0)
        self.assertFalse(result["enriched_gaps"][0]["has_scenario_correction"])

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    @patch("vsf_rsi.rsi_scenario_bridge._import_gap_detector")
    def test_gaps_to_corrections_no_gaps(self, mock_det_import, mock_sm_import):
        """gaps_to_corrections handles empty gap list."""
        mock_detector = MagicMock()
        mock_detector.detect_gaps.return_value = {"gaps": []}
        mock_det_import.return_value = mock_detector

        mock_sm = MagicMock()
        mock_sm_import.return_value = mock_sm

        result = bridge.gaps_to_corrections("test_pred")
        self.assertEqual(result["total_gaps"], 0)
        self.assertEqual(result["with_corrections"], 0)

    @patch("vsf_rsi.rsi_scenario_bridge._import_scenario_memory")
    @patch("vsf_rsi.rsi_scenario_bridge._import_gap_detector")
    def test_gaps_to_corrections_result_structure(self, mock_det_import, mock_sm_import):
        """gaps_to_corrections returns correct result structure."""
        mock_detector = MagicMock()
        mock_detector.detect_gaps.return_value = {"gaps": []}
        mock_det_import.return_value = mock_detector
        mock_sm = MagicMock()
        mock_sm_import.return_value = mock_sm

        result = bridge.gaps_to_corrections("test_pred")
        self.assertIn("predicate", result)
        self.assertIn("enriched_gaps", result)
        self.assertIn("total_gaps", result)
        self.assertIn("with_corrections", result)
        self.assertIn("timestamp", result)


class TestFullBridge(TestCase):
    """Test full_bridge function."""

    @patch("vsf_rsi.rsi_scenario_bridge.gaps_to_corrections")
    @patch("vsf_rsi.rsi_scenario_bridge.failures_to_gaps")
    def test_full_bridge_with_predicate(self, mock_f2g, mock_g2c):
        """full_bridge runs both flows for specific predicate."""
        mock_f2g.return_value = {
            "predicate": "test_pred",
            "failure_gaps": [],
            "total_failures": 0,
        }
        mock_g2c.return_value = {
            "predicate": "test_pred",
            "enriched_gaps": [],
            "total_gaps": 0,
            "with_corrections": 0,
        }
        result = bridge.full_bridge(predicate_name="test_pred")
        self.assertIn("failures_to_gaps", result)
        self.assertIn("gaps_to_corrections", result)
        self.assertIn("bridge_timestamp", result)
        mock_f2g.assert_called_once_with("test_pred")
        mock_g2c.assert_called_once_with("test_pred")

    @patch("vsf_rsi.rsi_scenario_bridge._import_gap_detector")
    @patch("vsf_rsi.rsi_scenario_bridge.gaps_to_corrections")
    @patch("vsf_rsi.rsi_scenario_bridge.failures_to_gaps")
    def test_full_bridge_no_predicate(self, mock_f2g, mock_g2c, mock_det_import):
        """full_bridge iterates all predicates when no filter."""
        mock_f2g.return_value = {
            "predicate": "all",
            "failure_gaps": [],
            "total_failures": 0,
        }
        mock_detector = MagicMock()
        mock_detector.detect_all_gaps.return_value = {
            "predicates": {"pred_a": {}, "pred_b": {}}
        }
        mock_det_import.return_value = mock_detector
        mock_g2c.return_value = {
            "enriched_gaps": [],
            "total_gaps": 0,
            "with_corrections": 0,
        }
        result = bridge.full_bridge()
        self.assertIn("failures_to_gaps", result)
        self.assertIn("gaps_to_corrections", result)
        self.assertEqual(mock_g2c.call_count, 2)


if __name__ == "__main__":
    main()
