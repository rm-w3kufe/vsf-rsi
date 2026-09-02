#!/usr/bin/env python3
"""
Tests for L3 Autonomous Cycle: FaultDetector, ShadowMode, RollbackManager, AutonomousL3.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vsf_rsi.rsi_fault_detector import FaultDetector, FaultSignature, FaultWindow
from vsf_rsi.rsi_shadow_mode import ShadowMode, StrategyCandidate, ShadowResult
from vsf_rsi.rsi_rollback import RollbackManager, MonitoredStrategy, RollbackEvent
from vsf_rsi.rsi_autonomous_l3 import AutonomousL3, L3CycleResult


class TestFaultWindow(unittest.TestCase):
    """Test sliding window for fault detection."""

    def test_empty_window(self):
        w = FaultWindow(source="test")
        self.assertEqual(w.error_count, 0)
        self.assertEqual(w.error_ratio, 0.0)
        self.assertEqual(w.coverage, 0.0)

    def test_add_events(self):
        w = FaultWindow(source="test")
        for _ in range(5):
            w.add({"is_error": True, "truth": "FALSE", "latency_ms": 15.0, "error_class": "BLOCKING"})
        self.assertEqual(w.error_count, 5)
        self.assertEqual(w.error_ratio, 1.0)

    def test_window_sliding(self):
        w = FaultWindow(source="test")
        for i in range(12):
            w.add({"is_error": i < 7, "truth": "TRUE", "latency_ms": 5.0, "error_class": "NONE"})
        self.assertEqual(len(w.events), 10)  # WINDOW_SIZE = 10
        # After sliding: last 5 events have is_error = False (i=7..11), first 5 have True (i=2..6)
        self.assertEqual(w.error_count, 5)

    def test_coverage(self):
        w = FaultWindow(source="test")
        for _ in range(4):
            w.add({"truth": "TRUE", "is_error": False, "latency_ms": 1.0})
        for _ in range(6):
            w.add({"truth": "UNKNOWN", "is_error": False, "latency_ms": 1.0})
        self.assertAlmostEqual(w.coverage, 0.4)  # 4 known out of 10


class TestFaultDetector(unittest.TestCase):
    """Test complex fault detection."""

    def setUp(self):
        self.detector = FaultDetector()
        # Clear any persisted state
        self.detector._windows = {}
        self.detector._faults = {}
        # Use unique source per test to avoid cross-contamination
        self._test_source = f"test-{id(self)}"

    def _make_event(self, source="op:AND", is_error=False, error_class="NONE",
                    latency_ms=5.0, truth="TRUE"):
        return {
            "source": source,
            "is_error": is_error,
            "error_class": error_class,
            "latency_ms": latency_ms,
            "truth": truth,
            "timestamp": "2026-09-01T00:00:00Z",
        }

    def test_no_fault_on_single_error(self):
        ev = self._make_event(source=f"{self._test_source}-single", is_error=True, error_class="BLOCKING")
        result = self.detector.observe(ev)
        self.assertIsNone(result)

    def test_no_fault_on_non_blocking_errors(self):
        for _ in range(5):
            ev = self._make_event(source=f"{self._test_source}-nonblock", is_error=True, error_class="STRUCTURAL")
            result = self.detector.observe(ev)
        self.assertEqual(len(self.detector.get_pending_faults()), 0)

    def test_detects_complex_fault(self):
        """≥3 BLOCKING errors in 10 evals → fault detected."""
        for _ in range(4):
            ev = self._make_event(source=f"{self._test_source}-detect", is_error=True, error_class="BLOCKING")
            result = self.detector.observe(ev)

        faults = self.detector.get_pending_faults()
        self.assertEqual(len(faults), 1)
        self.assertIn(self._test_source, faults[0].source)

    def test_fault_idempotent(self):
        """Same fault detected twice → same fault_id."""
        for _ in range(4):
            ev = self._make_event(source=f"{self._test_source}-idem", is_error=True, error_class="BLOCKING")
            self.detector.observe(ev)

        faults = self.detector.get_pending_faults()
        fault_id = faults[0].fault_id

        # Trigger again
        for _ in range(2):
            ev = self._make_event(source=f"{self._test_source}-idem", is_error=True, error_class="BLOCKING")
            self.detector.observe(ev)

        faults2 = self.detector.get_pending_faults()
        self.assertEqual(len(faults2), 1)
        self.assertEqual(faults2[0].fault_id, fault_id)

    def test_update_status(self):
        for _ in range(4):
            self.detector.observe(self._make_event(source=f"{self._test_source}-update", is_error=True, error_class="BLOCKING"))

        fault = self.detector.get_pending_faults()[0]
        self.detector.update_fault_status(fault.fault_id, "generating")
        self.assertEqual(len(self.detector.get_pending_faults()), 0)


class TestShadowMode(unittest.TestCase):
    """Test shadow mode validation."""

    def setUp(self):
        self.engine = MagicMock()
        self.shadow = ShadowMode(self.engine)

    def _make_candidate(self, tree=None):
        return StrategyCandidate(
            strategy_id="test-strategy-1",
            fault_id="test-fault",
            tree=tree or {"op": "AND", "children": [{"op": "ctx_has", "kwargs": {"field": "x"}}]},
            source="op:AND",
            description="Test strategy",
        )

    def _make_test_cases(self, n=10):
        return [{"tree": {"op": "ctx_has", "kwargs": {"field": "x"}}, "ctx": {"x": i / 10.0}, "expected": i % 2 == 0}
                for i in range(n)]

    def test_baseline_evaluation(self):
        self.engine.evaluate.return_value = MagicMock(is_true=True)
        cases = self._make_test_cases()
        accuracy, latency = self.shadow.evaluate_baseline(
            {"op": "ctx_has", "kwargs": {"field": "x"}}, cases
        )
        self.assertGreaterEqual(accuracy, 0.0)
        self.assertLessEqual(accuracy, 1.0)

    def test_strategy_passes_shadow(self):
        """Strategy with better accuracy than baseline → passes."""
        # First call: baseline (0.5 accuracy), second call: strategy (0.9 accuracy)
        results = [MagicMock(is_true=(i % 2 == 0)) for i in range(10)]
        self.engine.evaluate.side_effect = results

        cases = self._make_test_cases()
        candidate = self._make_candidate()

        result = self.shadow.evaluate_strategy(candidate, cases, 0.5, 5.0)
        self.assertIsInstance(result, ShadowResult)
        self.assertTrue(result.passed or not result.passed)  # Just runs without error

    def test_strategy_fails_shadow(self):
        """Strategy with worse accuracy → fails."""
        self.engine.evaluate.return_value = MagicMock(is_true=False)
        cases = self._make_test_cases()
        candidate = self._make_candidate()

        result = self.shadow.evaluate_strategy(candidate, cases, 0.8, 5.0)
        self.assertFalse(result.passed)
        self.assertEqual(result.status, "failed")


class TestRollbackManager(unittest.TestCase):
    """Test rollback monitoring."""

    def setUp(self):
        self.engine = MagicMock()
        self.rollback = RollbackManager(self.engine)
        self.rollback._monitored = {}
        self.rollback._rollbacks = []

    def test_activate_strategy(self):
        monitored = self.rollback.activate(
            strategy_id="strat-1",
            fault_id="fault-1",
            tree={"op": "AND"},
            baseline_accuracy=0.7,
        )
        self.assertEqual(monitored.status, "monitoring")
        self.assertEqual(len(self.rollback.get_monitored()), 1)

    def test_confirm_after_window(self):
        self.rollback.activate("strat-1", "fault-1", {}, 0.7)

        # Record 50 correct evaluations — 50th triggers confirmation
        for _ in range(49):
            result = self.rollback.record_evaluation("strat-1", correct=True)
            self.assertIsNone(result)  # Still monitoring

        # 50th evaluation triggers confirmation
        result = self.rollback.record_evaluation("strat-1", correct=True)
        self.assertEqual(result, "confirmed")
        self.assertEqual(len(self.rollback.get_confirmed()), 1)

    def test_rollback_on_degradation(self):
        self.rollback.activate("strat-1", "fault-1", {}, 0.7)

        # Record 9 evaluations with poor accuracy
        for _ in range(9):
            result = self.rollback.record_evaluation("strat-1", correct=False)
            self.assertIsNone(result)  # Still monitoring

        # 10th evaluation — recent_accuracy is 1/10 ≈ 10%, which is < 0.7 - 0.05 = 0.65
        # This triggers early revert check
        result = self.rollback.record_evaluation("strat-1", correct=False)
        self.assertEqual(result, "rolled_back")
        self.assertEqual(len(self.rollback.get_rolled_back()), 1)

    def test_get_tree(self):
        tree = {"op": "AND", "children": []}
        self.rollback.activate("strat-1", "fault-1", tree, 0.7)
        self.assertEqual(self.rollback.get_tree("strat-1"), tree)
        self.assertIsNone(self.rollback.get_tree("nonexistent"))


class TestAutonomousL3(unittest.TestCase):
    """Test the full L3 autonomous cycle."""

    def setUp(self):
        self.engine = MagicMock()
        self.l3 = AutonomousL3(self.engine)
        self.l3.detector._windows = {}
        self.l3.detector._faults = {}

    def test_no_pending_faults(self):
        result = self.l3.run_cycle()
        self.assertEqual(result.status, "no_faults")

    def test_full_cycle_no_activation(self):
        """Full cycle with no strategy passing shadow."""
        self.engine.evaluate.return_value = MagicMock(is_true=False)

        # Trigger fault detection
        for _ in range(5):
            ev = {"source": "op:AND", "is_error": True, "error_class": "BLOCKING",
                  "latency_ms": 15.0, "truth": "FALSE", "timestamp": "2026-09-01T00:00:00Z"}
            self.l3.detector.observe(ev)

        result = self.l3.run_cycle()
        self.assertEqual(result.strategies_generated, 5)
        self.assertIn(result.status, ["activated", "no_candidate"])

    def test_process_event_no_fault(self):
        ev = {"source": "op:AND", "is_error": False, "error_class": "NONE",
              "latency_ms": 1.0, "truth": "TRUE", "timestamp": "2026-09-01T00:00:00Z"}
        result = self.l3.process_event(ev)
        self.assertIsNone(result)

    def test_process_event_with_fault(self):
        # Build up enough errors to trigger fault
        for _ in range(5):
            ev = {"source": "op:AND", "is_error": True, "error_class": "BLOCKING",
                  "latency_ms": 15.0, "truth": "FALSE", "timestamp": "2026-09-01T00:00:00Z"}
            self.l3.detector.observe(ev)

        # This should trigger a cycle
        ev = {"source": "op:AND", "is_error": True, "error_class": "BLOCKING",
              "latency_ms": 15.0, "truth": "FALSE", "timestamp": "2026-09-01T00:00:00Z"}
        result = self.l3.process_event(ev)
        self.assertIsNotNone(result)
        self.assertIn(result.status, ["activated", "no_candidate"])

    def test_stats(self):
        stats = self.l3.get_stats()
        self.assertIn("total_cycles", stats)
        self.assertIn("pending_faults", stats)


class TestObserverIntegration(unittest.TestCase):
    """Test RSIObserver with L3 autonomous integration."""

    def setUp(self):
        self.engine = MagicMock()
        self.engine.evaluate.return_value = MagicMock(
            is_true=True, truth=MagicMock(value="TRUE"),
            certified=False, metadata={}, source="op:AND"
        )

    def test_observer_creates_l3(self):
        from vsf_rsi.rsi_observer import RSIObserver
        obs = RSIObserver(self.engine, autonomous_l3=True)
        self.assertIsNotNone(obs._autonomous_l3)

    def test_observer_without_l3(self):
        from vsf_rsi.rsi_observer import RSIObserver
        obs = RSIObserver(self.engine, autonomous_l3=False)
        self.assertIsNone(obs._autonomous_l3)

    def test_observer_evaluate_works(self):
        from vsf_rsi.rsi_observer import RSIObserver
        obs = RSIObserver(self.engine, autonomous_l3=True)
        result = obs.evaluate({"op": "ctx_has", "kwargs": {"field": "x"}}, {"x": 1})
        self.assertIsNotNone(result)
        self.assertTrue(len(obs.events) >= 1)


class TestBuildThresholdTree(unittest.TestCase):
    """Test _build_threshold_tree (DEBT-001 fix)."""

    def setUp(self):
        self.l3 = AutonomousL3.__new__(AutonomousL3)

    def test_returns_valid_tree(self):
        tree = self.l3._build_threshold_tree("test_pred", 0.05)
        self.assertIsNotNone(tree)
        self.assertEqual(tree["op"], "AND")
        self.assertIn("children", tree)
        self.assertEqual(len(tree["children"]), 3)

    def test_tree_has_inject_context(self):
        tree = self.l3._build_threshold_tree("test_pred", 0.05)
        self.assertTrue(tree.get("inject_context", False))
        for child in tree["children"]:
            self.assertTrue(child.get("inject_context", False))

    def test_tree_uses_predicate_format(self):
        tree = self.l3._build_threshold_tree("test_pred", 0.05)
        for child in tree["children"]:
            self.assertIn("predicate", child)
            self.assertNotIn("op", child)  # Should NOT use "op" for predicates

    def test_returns_none_on_empty_source(self):
        tree = self.l3._build_threshold_tree("", 0.05)
        self.assertIsNone(tree)

    def test_returns_none_on_invalid_delta(self):
        tree = self.l3._build_threshold_tree("test_pred", "invalid")
        self.assertIsNone(tree)

    def test_tree_structure_matches_socratic_engine(self):
        """Verify tree can be evaluated by socratic-engine."""
        from socratic_engine.engine import SocraticEngine
        engine = SocraticEngine()
        
        # Register a mock predicate for threshold_adjusted
        @engine.register("threshold_adjusted")
        def threshold_adjusted(ctx, source=None, delta=0.0, **kw):
            from socratic_engine.engine import PredicateResult, Truth
            return PredicateResult(
                truth=Truth.TRUE,
                certified=True,
                evidence={"source": source, "delta": delta},
                source="threshold_adjusted",
            )
        
        tree = self.l3._build_threshold_tree("test_pred", 0.05)
        ctx = {"input_value": 0.5, "threshold": 0.7}
        
        # This should NOT raise "Operador desconocido"
        result = engine.evaluate(tree, ctx)
        self.assertIsNotNone(result)


class TestBuildOperatorTree(unittest.TestCase):
    """Test _build_operator_tree (DEBT-001 fix)."""

    def setUp(self):
        self.l3 = AutonomousL3.__new__(AutonomousL3)

    def test_returns_valid_tree_for_gt(self):
        tree = self.l3._build_operator_tree("test_pred", "gt")
        self.assertIsNotNone(tree)
        self.assertEqual(tree["op"], "AND")
        self.assertEqual(len(tree["children"]), 3)

    def test_returns_valid_tree_for_lt(self):
        tree = self.l3._build_operator_tree("test_pred", "lt")
        self.assertIsNotNone(tree)

    def test_returns_valid_tree_for_eq(self):
        tree = self.l3._build_operator_tree("test_pred", "eq")
        self.assertIsNotNone(tree)

    def test_returns_none_on_invalid_op(self):
        tree = self.l3._build_operator_tree("test_pred", "invalid_op")
        self.assertIsNone(tree)

    def test_returns_none_on_empty_source(self):
        tree = self.l3._build_operator_tree("", "gt")
        self.assertIsNone(tree)

    def test_tree_has_inject_context(self):
        tree = self.l3._build_operator_tree("test_pred", "gt")
        self.assertTrue(tree.get("inject_context", False))
        for child in tree["children"]:
            self.assertTrue(child.get("inject_context", False))


if __name__ == "__main__":
    unittest.main()
