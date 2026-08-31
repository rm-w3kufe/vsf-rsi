#!/usr/bin/env python3
"""
Tests for RSI Observer — integration bridge between socratic-engine and rsi_metrics.

design: docs/spec_revision/design-sources/rsi-observer-v1/rsi_observer_design.vsm

Tests:
  1. EvaluationEvent construction
  2. Discrimination (BLOCKING/STRUCTURAL/NONE)
  3. Parameter drift resolution
  4. Observer evaluate() with mock engine
  5. Threshold injection via context
  6. Mode switching (SAFE/CAPABILITY)
  7. Stats and summary
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import asdict

# Add package dir to path
_package_dir = Path(__file__).parent.parent / "vsf_rsi"
sys.path.insert(0, str(_package_dir))

from vsf_rsi.rsi_observer import (
    RSIObserver,
    RSIMode,
    ErrorClass,
    ActionLevel,
    EvaluationEvent,
    RSIAction,
    get_expected,
    load_thresholds,
    discriminate,
    resolve_error,
    DEFAULT_THRESHOLDS,
)


class TestGetExpected(unittest.TestCase):
    """Test ground truth derivation."""

    def test_below_threshold_is_true(self):
        # input=0.50 < threshold=0.70 → expected TRUE (danger zone)
        self.assertTrue(get_expected(0.50, 0.70))

    def test_above_threshold_is_false(self):
        # input=0.80 > threshold=0.70 → expected FALSE (safe zone)
        self.assertFalse(get_expected(0.80, 0.70))

    def test_at_threshold_is_false(self):
        # input=0.70 == threshold=0.70 → not below, expected FALSE
        self.assertFalse(get_expected(0.70, 0.70))

    def test_boundary_values(self):
        self.assertTrue(get_expected(0.01, 0.99))   # 0.01 < 0.99 → TRUE
        self.assertFalse(get_expected(0.99, 0.01))  # 0.99 < 0.01 → FALSE


class TestLoadThresholds(unittest.TestCase):
    """Test threshold loading from file."""

    def test_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("vsf_rsi.rsi_observer.Path") as mock_path:
                mock_path.return_value.parent.parent.parent = Path(tmpdir)
                thresholds = load_thresholds()
                self.assertEqual(thresholds, DEFAULT_THRESHOLDS)

    def test_loads_from_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            thresholds_file = Path(tmpdir) / "rsi_thresholds.json"
            thresholds_file.write_text(json.dumps({
                "ac_stasis_critical": 0.85,
                "ac_stasis_warning": 0.90,
            }))
            # BUG-005: Use new path parameter
            thresholds = load_thresholds(thresholds_dir=Path(tmpdir))
            self.assertEqual(thresholds["ac_stasis_critical"], 0.85)
            self.assertEqual(thresholds["ac_stasis_warning"], 0.90)
            # Default preserved for missing key
            self.assertEqual(thresholds["ac_viable_false"], 0.50)


class TestDiscriminate(unittest.TestCase):
    """Test error discrimination."""

    def _make_event(self, is_error=True, certified=False, source="test_pred"):
        # BUG-004: is_error is computed from expected != actual
        # To get is_error=True: expected=True, actual=False
        # To get is_error=False: expected=False, actual=False (or same)
        expected = is_error  # If we want error, expected=True
        actual = False       # actual=False always for simplicity
        return EvaluationEvent(
            source=source,
            truth="FALSE",
            certified=certified,
            expected=expected,
            actual=actual,
            error_class="NONE",
        )

    def test_no_error_returns_none(self):
        event = self._make_event(is_error=False)
        self.assertEqual(discriminate(event), ErrorClass.NONE.value)

    def test_certified_error_is_blocking(self):
        event = self._make_event(certified=True)
        self.assertEqual(discriminate(event), ErrorClass.BLOCKING.value)

    def test_unknown_scenario_is_blocking(self):
        event = self._make_event()
        memory = {}
        self.assertEqual(discriminate(event, memory), ErrorClass.BLOCKING.value)

    def test_known_scenario_is_structural(self):
        event = self._make_event(source="known_pred")
        memory = {"known_pred": ["scenario1"]}
        self.assertEqual(discriminate(event, memory), ErrorClass.STRUCTURAL.value)

    def test_non_certified_no_memory_is_blocking(self):
        event = self._make_event()
        # No memory → default is BLOCKING (conservative)
        self.assertEqual(discriminate(event, {}), ErrorClass.BLOCKING.value)


class TestResolveError(unittest.TestCase):
    """Test error resolution."""

    def _make_event(self, source="ac_stasis_critical", threshold=0.70,
                    input_value=0.80, actual=False, expected=True):
        # BUG-004: is_error is computed from expected != actual
        return EvaluationEvent(
            source=source,
            truth="FALSE",
            error_class="BLOCKING",
            threshold=threshold,
            input_value=input_value,
            actual=actual,
            expected=expected,
        )

    def test_parameter_drift_increases_threshold(self):
        event = self._make_event(input_value=0.80, threshold=0.70)
        ctx = {"_rsi_thresholds": {"ac_stasis_critical": 0.70}}
        action = resolve_error(event, ctx, mode=RSIMode.SAFE.value)
        self.assertIsNotNone(action)
        self.assertEqual(action.action_type, "adjust_threshold")
        self.assertTrue(action.autonomous)
        self.assertIn("old", action.params)
        self.assertIn("new", action.params)

    def test_parameter_drift_decreases_threshold(self):
        event = self._make_event(input_value=0.40, threshold=0.70)
        ctx = {"_rsi_thresholds": {"ac_stasis_critical": 0.70}}
        action = resolve_error(event, ctx, mode=RSIMode.SAFE.value)
        self.assertIsNotNone(action)
        self.assertLess(action.params["new"], action.params["old"])

    def test_safe_mode_no_capability_extension(self):
        event = self._make_event()
        ctx = {"_rsi_thresholds": {"ac_stasis_critical": 0.70}}
        # Patch parameter_drift to return None (simulates drift failure)
        with patch("vsf_rsi.rsi_observer._try_parameter_drift", return_value=None):
            action = resolve_error(event, ctx, mode=RSIMode.SAFE.value)
            # In SAFE mode, capability_extension is blocked
            self.assertIsNotNone(action)
            self.assertEqual(action.resolution, "error_unresolvable")

    def test_capability_mode_proposes_extension(self):
        event = self._make_event()
        ctx = {"_rsi_thresholds": {"ac_stasis_critical": 0.70}}
        # Patch parameter_drift to return None (simulates drift failure)
        # Patch capability_extension to return a specific action
        mock_action = RSIAction(
            event=event,
            level="L2",
            action_type="inject_predicate",
            params={"name": "_rsi_adj_test"},
            autonomous=True,
            resolution="predicate_injected",
        )
        with patch("vsf_rsi.rsi_observer._try_parameter_drift", return_value=None), \
             patch("vsf_rsi.rsi_observer._try_capability_extension", return_value=mock_action):
            action = resolve_error(event, ctx, mode=RSIMode.CAPABILITY.value)
            self.assertIsNotNone(action)
            self.assertEqual(action.action_type, "inject_predicate")
            self.assertEqual(action.level, "L2")

    def test_non_blocking_returns_none(self):
        event = self._make_event()
        event.error_class = "STRUCTURAL"
        event.is_error = False
        ctx = {}
        action = resolve_error(event, ctx)
        self.assertIsNone(action)


class TestEvaluationEvent(unittest.TestCase):
    """Test EvaluationEvent data class."""

    def test_default_values(self):
        event = EvaluationEvent()
        self.assertEqual(event.source, "")
        self.assertEqual(event.truth, "UNKNOWN")
        self.assertFalse(event.certified)
        self.assertEqual(event.latency_ms, 0.0)
        self.assertFalse(event.is_error)
        self.assertEqual(event.error_class, "NONE")

    def test_serialization(self):
        # BUG-004: is_error is now computed from expected != actual
        event = EvaluationEvent(
            source="test",
            truth="TRUE",
            expected=True,
            actual=False,  # Different from expected → is_error=True
            error_class="BLOCKING",
        )
        d = asdict(event)
        self.assertEqual(d["source"], "test")
        self.assertTrue(d["is_error"])


class TestRSIObserver(unittest.TestCase):
    """Test observer with mock engine."""

    def _mock_engine(self, truth="TRUE", source="test_pred", certified=True):
        """Create a mock engine that returns a fixed Evaluation."""
        engine = MagicMock()
        result = MagicMock()
        result.truth = MagicMock(value=truth)
        result.is_true = (truth == "TRUE")
        result.certified = certified
        result.source = source
        result.metadata = {}
        engine.evaluate.return_value = result
        return engine

    def test_basic_evaluation(self):
        engine = self._mock_engine(truth="TRUE")
        observer = RSIObserver(engine, mode=RSIMode.SAFE.value)

        tree = {"predicate": "test", "args": []}
        ctx = {"task_id": "test_task", "input_value": 0.80}
        result = observer.evaluate(tree, ctx, tree_id="test_tree")

        self.assertEqual(len(observer.events), 1)
        self.assertEqual(observer.events[0].source, "test_pred")
        self.assertEqual(observer.events[0].truth, "TRUE")
        self.assertEqual(observer.events[0].tree_id, "test_tree")

    def test_threshold_injection(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)

        ctx = {"task_id": "test"}
        observer.evaluate({}, ctx)

        # Thresholds should be injected with defaults
        self.assertIn("_rsi_thresholds", ctx)
        self.assertEqual(ctx["_rsi_thresholds"]["ac_stasis_critical"], 0.70)
        self.assertEqual(ctx["_rsi_thresholds"]["ac_stasis_warning"], 0.80)
        self.assertEqual(ctx["_rsi_thresholds"]["ac_viable_false"], 0.50)

    def test_existing_thresholds_preserved(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)

        ctx = {
            "task_id": "test",
            "_rsi_thresholds": {"ac_stasis_critical": 0.90},
        }
        observer.evaluate({}, ctx)

        # Existing thresholds preserved
        self.assertEqual(ctx["_rsi_thresholds"]["ac_stasis_critical"], 0.90)

    def test_error_detection(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        observer = RSIObserver(engine)

        # input=0.50 < threshold=0.70 → expected TRUE, predicate returns FALSE → error
        ctx = {"task_id": "test", "input_value": 0.50}
        observer.evaluate({}, ctx)

        self.assertTrue(observer.events[0].is_error)

    def test_no_error_when_correct(self):
        engine = self._mock_engine(truth="TRUE", source="ac_stasis_critical")
        observer = RSIObserver(engine)

        # input=0.60 < threshold=0.70 → expected TRUE, predicate returns TRUE → no error
        ctx = {"task_id": "test", "input_value": 0.60}
        observer.evaluate({}, ctx)

        self.assertFalse(observer.events[0].is_error)

    def test_mode_injection(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine, mode=RSIMode.SAFE.value)

        ctx = {"task_id": "test"}
        observer.evaluate({}, ctx)

        self.assertEqual(ctx["_rsi_mode"], "SAFE")

    def test_stats(self):
        engine = self._mock_engine(truth="TRUE")
        observer = RSIObserver(engine)

        for i in range(5):
            observer.evaluate({}, {"task_id": f"task_{i}", "input_value": 0.5})

        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 5)
        self.assertEqual(stats["mode"], RSIMode.CAPABILITY.value)

    def test_error_summary(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        observer = RSIObserver(engine)

        # input=0.50 < threshold=0.70 → expected TRUE, predicate returns FALSE → error
        ctx = {"task_id": "test", "input_value": 0.50}
        observer.evaluate({}, ctx)

        summary = observer.get_error_summary()
        self.assertEqual(summary["BLOCKING"] + summary["STRUCTURAL"], 1)

    def test_get_events_by_source(self):
        engine = self._mock_engine(source="ac_stasis_critical")
        observer = RSIObserver(engine)

        observer.evaluate({}, {"task_id": "t1", "input_value": 0.5})
        observer.evaluate({}, {"task_id": "t2", "input_value": 0.5})

        events = observer.get_events_by_source("ac_stasis_critical")
        self.assertEqual(len(events), 2)

        events = observer.get_events_by_source("other")
        self.assertEqual(len(events), 0)


class TestRSIMode(unittest.TestCase):
    """Test mode enum."""

    def test_capability_value(self):
        self.assertEqual(RSIMode.CAPABILITY.value, "CAPABILITY")

    def test_safe_value(self):
        self.assertEqual(RSIMode.SAFE.value, "SAFE")


class TestActionLevel(unittest.TestCase):
    """Test action level enum."""

    def test_levels(self):
        self.assertEqual(ActionLevel.L1.value, "L1")
        self.assertEqual(ActionLevel.L2.value, "L2")
        self.assertEqual(ActionLevel.L3.value, "L3")
        self.assertEqual(ActionLevel.L4.value, "L4")


if __name__ == "__main__":
    unittest.main()
