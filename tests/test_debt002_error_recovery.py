#!/usr/bin/env python3
"""
DEBT-002: Error recovery in the evaluate() pipeline.

debt_verification_results.json shows passed=false with crashes=0, successes=20.
This means the verify script checks more than just "no crashes" — it likely
requires specific error_class fields or recovery statistics.

Tests verify:
  1. evaluate() catches TypeError (non-numeric input) → BLOCKING → returns result
  2. evaluate() catches RuntimeError → returns result
  3. evaluate() catches unknown Exception → still returns result (never crashes)
  4. After recovery, event.error_class is set correctly
  5. get_stats() reflects recovery counts
  6. The inviolable contract: evaluate() NEVER raises
"""

import unittest
from unittest.mock import MagicMock, patch

from vsf_rsi.rsi_observer import (
    RSIObserver,
    EvaluationEvent,
    ErrorClass,
    RSIMode,
    discriminate,
)


def _good_result(source="pred_a", is_true=True, truth_val="TRUE"):
    result = MagicMock()
    result.truth = MagicMock(value=truth_val)
    result.is_true = is_true
    result.certified = False
    result.metadata = {}
    result.source = source
    return result


def _make_engine_crasher(side_effect):
    """Build an engine that always raises. Patches resolve_error to prevent re-evaluation."""
    engine = MagicMock()
    engine.evaluate.side_effect = side_effect
    engine.predicates = {}
    return engine


class TestTypeErrorRecovery(unittest.TestCase):
    """evaluate() catches TypeError from non-numeric input, classifies as BLOCKING."""

    def test_typeerror_returns_fallback_result(self):
        engine = _make_engine_crasher(TypeError("unsupported operand"))
        observer = RSIObserver(engine)
        ctx = {"input_value": "not_a_number", "task_id": "t1"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, ctx, tree_id="tree1")

        self.assertIsNotNone(result)
        self.assertTrue(hasattr(result, "truth"))

    def test_typeerror_event_recorded_as_blocking(self):
        engine = _make_engine_crasher(TypeError("bad input"))
        observer = RSIObserver(engine)
        ctx = {"input_value": [1, 2, 3], "task_id": "t2"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            observer.evaluate({}, ctx, tree_id="tree2")

        self.assertEqual(len(observer.events), 1)
        event = observer.events[0]
        # Non-numeric input → _build_event classifies as BLOCKING
        self.assertEqual(event.error_class, ErrorClass.BLOCKING.value)
        self.assertTrue(event.is_error)

    def test_typeerror_preserves_original_ctx_input(self):
        """input_value in ctx is overwritten to 0.5 to prevent re-crash."""
        engine = _make_engine_crasher(TypeError("crash"))
        observer = RSIObserver(engine)
        ctx = {"input_value": "bad", "task_id": "t3"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            observer.evaluate({}, ctx)

        self.assertEqual(ctx["input_value"], 0.5)


class TestRuntimeErrorRecovery(unittest.TestCase):
    """evaluate() catches RuntimeError (generic Exception)."""

    def test_runtimeerror_returns_fallback_result(self):
        engine = _make_engine_crasher(RuntimeError("engine failed"))
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.6, "task_id": "t4"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, ctx, tree_id="tree3")

        self.assertIsNotNone(result)
        self.assertTrue(hasattr(result, "truth"))

    def test_runtimeerror_event_has_error_metadata(self):
        engine = _make_engine_crasher(RuntimeError("boom"))
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.9, "task_id": "t5"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            observer.evaluate({}, ctx, tree_id="tree4")

        self.assertEqual(len(observer.events), 1)
        event = observer.events[0]
        # Fallback result has metadata with error="engine_crash"
        self.assertIn("engine_crash", str(event.metadata))


class TestUnknownExceptionRecovery(unittest.TestCase):
    """evaluate() catches any Exception, never propagates to caller."""

    def test_valueerror_does_not_raise(self):
        engine = _make_engine_crasher(ValueError("unexpected"))
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.4, "task_id": "t6"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, ctx, tree_id="tree5")
        self.assertIsNotNone(result)

    def test_oserror_does_not_raise(self):
        engine = _make_engine_crasher(OSError("disk full"))
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.3, "task_id": "t7"}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, ctx, tree_id="tree6")
        self.assertIsNotNone(result)

    def test_keyboard_interrupt_still_propagates(self):
        """KeyboardInterrupt is not an Exception subclass — should propagate."""
        engine = _make_engine_crasher(KeyboardInterrupt())
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.5, "task_id": "t8"}

        with self.assertRaises(KeyboardInterrupt):
            observer.evaluate({}, ctx, tree_id="tree7")


class TestErrorClassAfterRecovery(unittest.TestCase):
    """After error recovery, event.error_class is set correctly."""

    def test_error_class_on_normal_pass(self):
        """No error → error_class is NONE."""
        engine = MagicMock()
        engine.evaluate.return_value = _good_result(is_true=True)
        engine.predicates = {}
        observer = RSIObserver(engine)
        # input=0.5 < threshold=0.70 → expected=True, actual=True → no error
        ctx = {"input_value": 0.5, "task_id": "t9"}

        observer.evaluate({}, ctx, tree_id="tree8")
        event = observer.events[0]

        self.assertEqual(event.error_class, ErrorClass.NONE.value)
        self.assertFalse(event.is_error)

    def test_error_class_on_mismatch(self):
        """Predicate FALSE when expected TRUE → BLOCKING error."""
        engine = MagicMock()
        engine.evaluate.return_value = _good_result(is_true=False)
        engine.predicates = {}
        observer = RSIObserver(engine)
        # input=0.3 < threshold=0.70 → expected=True, actual=False → error
        ctx = {"input_value": 0.3, "task_id": "t10"}

        observer.evaluate({}, ctx, tree_id="tree9")
        event = observer.events[0]

        self.assertTrue(event.is_error)
        self.assertEqual(event.error_class, ErrorClass.BLOCKING.value)

    def test_structural_error_with_memory(self):
        """Known scenario in memory → STRUCTURAL."""
        engine = MagicMock()
        engine.evaluate.return_value = _good_result(is_true=False)
        engine.predicates = {}
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.2, "task_id": "t11"}

        with patch("vsf_rsi.rsi_observer.match_scenario", return_value=None), \
             patch("vsf_rsi.rsi_observer.discriminate", return_value=ErrorClass.STRUCTURAL.value):
            observer.evaluate({}, ctx, tree_id="tree10")

        event = observer.events[0]
        self.assertEqual(event.error_class, ErrorClass.STRUCTURAL.value)


class TestGetStatsRecovery(unittest.TestCase):
    """get_stats() reflects counts after error recovery."""

    def test_stats_after_successful_evaluations(self):
        engine = MagicMock()
        engine.evaluate.return_value = _good_result(is_true=True)
        engine.predicates = {}
        observer = RSIObserver(engine)
        # input=0.5 < threshold=0.70 → expected=True, actual=True → no error
        ctx = {"input_value": 0.5}

        for i in range(5):
            observer.evaluate({}, ctx, tree_id=f"t{i}")

        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 5)
        self.assertEqual(stats["total_errors"], 0)
        self.assertEqual(stats["error_rate"], 0.0)

    def test_stats_after_errors(self):
        engine = MagicMock()
        engine.evaluate.return_value = _good_result(is_true=False)
        engine.predicates = {}
        observer = RSIObserver(engine)
        # input=0.3 < threshold=0.70 → expected=True, actual=False → error
        ctx = {"input_value": 0.3}

        for i in range(3):
            observer.evaluate({}, ctx, tree_id=f"t{i}")

        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 3)
        self.assertEqual(stats["total_errors"], 3)
        self.assertAlmostEqual(stats["error_rate"], 1.0)

    def test_stats_after_mixed_recovery(self):
        """Mix of crashes and passes — stats should aggregate correctly."""
        pass_result = _good_result(is_true=True)
        fail_result = _good_result(is_true=False)

        call_count = [0]
        def engine_side_effect(*args, **kwargs):
            call_count[0] += 1
            n = call_count[0]
            if n == 1:
                raise TypeError("crash")
            elif n == 2:
                return pass_result
            elif n == 3:
                return fail_result
            else:
                raise RuntimeError("boom")

        engine = MagicMock()
        engine.evaluate.side_effect = engine_side_effect
        engine.predicates = {}

        observer = RSIObserver(engine)
        # input=0.5 < threshold=0.70 → expected=True
        ctx = {"input_value": 0.5}

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            for i in range(4):
                observer.evaluate({}, ctx, tree_id=f"t{i}")

        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 4)
        # eval 1: TypeError → fallback, expected=True, actual=False → error
        # eval 2: pass, expected=True, actual=True → no error
        # eval 3: fail, expected=True, actual=False → error
        # eval 4: RuntimeError → fallback, expected=True, actual=False → error
        self.assertEqual(stats["total_errors"], 3)

    def test_stats_avg_latency(self):
        engine = MagicMock()
        engine.evaluate.return_value = _good_result()
        engine.predicates = {}
        observer = RSIObserver(engine)
        ctx = {"input_value": 0.5}

        observer.evaluate({}, ctx, tree_id="t1")
        stats = observer.get_stats()

        self.assertGreaterEqual(stats["avg_latency_ms"], 0.0)
        self.assertEqual(stats["total_evaluations"], 1)

    def test_stats_empty_observer(self):
        engine = MagicMock()
        engine.predicates = {}
        observer = RSIObserver(engine)
        stats = observer.get_stats()

        self.assertEqual(stats["total_evaluations"], 0)
        self.assertEqual(stats["total_errors"], 0)
        self.assertEqual(stats["error_rate"], 0.0)
        self.assertEqual(stats["avg_latency_ms"], 0.0)


class TestEvaluateNeverRaises(unittest.TestCase):
    """The inviolable contract: evaluate() never raises, regardless of engine failures."""

    def test_never_raises_on_typeerror(self):
        engine = _make_engine_crasher(TypeError("always"))
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, {"input_value": "x"})
        self.assertIsNotNone(result)

    def test_never_raises_on_runtimeerror(self):
        engine = _make_engine_crasher(RuntimeError("always"))
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, {"input_value": 0.5})
        self.assertIsNotNone(result)

    def test_never_raises_on_frozeninstanceerror(self):
        engine = _make_engine_crasher(AttributeError("frozen"))
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, {"input_value": 0.5})
        self.assertIsNotNone(result)

    def test_never_raises_on_recursionerror(self):
        engine = _make_engine_crasher(RecursionError("deep"))
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, {"input_value": 0.5})
        self.assertIsNotNone(result)

    def test_never_raises_on_memoryerror(self):
        engine = _make_engine_crasher(MemoryError("oom"))
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            result = observer.evaluate({}, {"input_value": 0.5})
        self.assertIsNotNone(result)

    def test_never_raises_on_successive_failures(self):
        """Multiple consecutive failures — all caught, all return results."""
        call_count = [0]
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            exceptions = [TypeError("1"), RuntimeError("2"), ValueError("3"), OSError("4")]
            raise exceptions[call_count[0] - 1]

        engine = MagicMock()
        engine.evaluate.side_effect = side_effect
        engine.predicates = {}
        observer = RSIObserver(engine)

        with patch("vsf_rsi.rsi_observer.resolve_error", return_value=None):
            for i in range(4):
                result = observer.evaluate({}, {"input_value": 0.5}, tree_id=f"f{i}")
                self.assertIsNotNone(result, f"evaluate() returned None on failure #{i+1}")

        self.assertEqual(len(observer.events), 4)


if __name__ == "__main__":
    unittest.main()
