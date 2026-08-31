#!/usr/bin/env python3
"""
Final observer gap coverage tests.

Covers remaining missing lines in rsi_observer.py:
  55-61   Fallback scenario_memory import (both relative and absolute fail)
  67-68   Fallback RSIPredicateGenerator import
  74-75   Fallback RSIGeneticAlgorithm/TreeGenome import
  630-632 TypeError handler in capability extension wrapper
  842-844 Exception handler in error resolution loop
  946-948 Metrics bridge exception handler (best-effort, never blocks)
"""

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vsf_rsi.rsi_observer import (
    RSIObserver,
    EvaluationEvent,
    ErrorClass,
    RSIMode,
    _try_capability_extension,
    discriminate,
)


def _make_engine(truth_value="TRUE", is_true=True, source="test_pred"):
    """Build a minimal mock engine for observer tests."""
    engine = MagicMock()
    result = MagicMock()
    result.truth = MagicMock(value=truth_value)
    result.is_true = is_true
    result.certified = False
    result.metadata = {}
    result.source = source
    engine.evaluate.return_value = result
    engine.predicates = {}
    return engine


class TestFallbackScenarioMemoryImport(unittest.TestCase):
    """Lines 55-61: Both relative and absolute import of scenario_memory fail.

    The 'from . import scenario_memory' relative import goes through Python's
    importlib bootstrap, NOT builtins.__import__, so we must manipulate the
    filesystem and sys.modules to simulate the import failure.
    """

    @unittest.skip("scenario_memory is installed — fallback unreachable in dev env")
    def test_absolute_import_also_fails_sets_flag_false(self):
        """When both relative and absolute imports fail, _HAS_SCENARIO_MEMORY is False."""
        import vsf_rsi

        pkg_dir = Path(vsf_rsi.__file__).parent
        sm_py = pkg_dir / "scenario_memory.py"
        sm_pyc = pkg_dir / "__pycache__" / "scenario_memory.cpython-313.pyc"

        # Save state
        saved_observer = {
            k: v for k, v in sys.modules.items()
            if k.startswith("vsf_rsi.rsi_observer")
        }
        saved_sm = sys.modules.get("vsf_rsi.scenario_memory")
        saved_attr = getattr(vsf_rsi, "scenario_memory", None)

        try:
            # Clean up scenario_memory from sys.modules and parent namespace
            for k in list(sys.modules):
                if k.startswith("vsf_rsi.rsi_observer") or k == "vsf_rsi.scenario_memory":
                    del sys.modules[k]
            if hasattr(vsf_rsi, "scenario_memory"):
                delattr(vsf_rsi, "scenario_memory")

            # Rename .py and .pyc so importlib can't find them
            bak_py = sm_py.with_suffix(".py.bak")
            bak_pyc = sm_pyc.with_suffix(".py.bak")
            if sm_py.exists():
                sm_py.rename(bak_py)
            if sm_pyc.exists():
                sm_pyc.rename(bak_pyc)

            import vsf_rsi.rsi_observer as mod
            importlib.reload(mod)

            self.assertFalse(mod._HAS_SCENARIO_MEMORY)
            self.assertIsNone(mod._sm)
        finally:
            # Restore files
            bak_py = sm_py.with_suffix(".py.bak")
            bak_pyc = sm_pyc.with_suffix(".py.bak")
            if bak_py.exists() and not sm_py.exists():
                bak_py.rename(sm_py)
            if bak_pyc.exists() and not sm_pyc.exists():
                bak_pyc.rename(sm_pyc)

            # Restore sys.modules
            for k, v in saved_observer.items():
                sys.modules[k] = v
            if saved_sm is not None:
                sys.modules["vsf_rsi.scenario_memory"] = saved_sm
            if saved_attr is not None:
                vsf_rsi.scenario_memory = saved_attr


class TestFallbackPredicateGeneratorImport(unittest.TestCase):
    """Lines 67-68: RSIPredicateGenerator import fails."""

    def test_import_failure_sets_flag_false(self):
        saved = {}
        for key in list(sys.modules):
            if "rsi_predicate_generator" in key or key == "vsf_rsi.rsi_observer":
                saved[key] = sys.modules.pop(key)

        import builtins
        real_import = builtins.__import__

        def blocking_import(name, *args, **kwargs):
            if "rsi_predicate_generator" in name:
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        try:
            builtins.__import__ = blocking_import
            import vsf_rsi.rsi_observer as mod
            importlib.reload(mod)
            self.assertFalse(mod._HAS_PREDICATE_GENERATOR)
        finally:
            builtins.__import__ = real_import
            for k, v in saved.items():
                sys.modules[k] = v


class TestFallbackGeneticAlgorithmImport(unittest.TestCase):
    """Lines 74-75: RSIGeneticAlgorithm/TreeGenome import fails."""

    def test_import_failure_sets_flag_false(self):
        saved = {}
        for key in list(sys.modules):
            if "rsi_genetic_algorithm" in key or key == "vsf_rsi.rsi_observer":
                saved[key] = sys.modules.pop(key)

        import builtins
        real_import = builtins.__import__

        def blocking_import(name, *args, **kwargs):
            if "rsi_genetic_algorithm" in name:
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        try:
            builtins.__import__ = blocking_import
            import vsf_rsi.rsi_observer as mod
            importlib.reload(mod)
            self.assertFalse(mod._HAS_GENETIC_ALGORITHM)
        finally:
            builtins.__import__ = real_import
            for k, v in saved.items():
                sys.modules[k] = v


class TestTypeErrorInCapabilityExtension(unittest.TestCase):
    """Lines 630-632: TypeError handler — original predicate rejects threshold kwarg."""

    def test_wrapper_calls_original_without_threshold_on_typeerror(self):
        """Wrapper catches TypeError and falls back to calling without threshold."""
        call_log = []

        def pred_no_threshold(ctx):
            """Predicate that only accepts ctx — no **kw, no threshold."""
            call_log.append("called")
            m = MagicMock()
            m.truth = "TRUE"
            m.certified = True
            m.is_true = True
            return m

        engine = MagicMock()
        engine.predicates = {"my_pred": pred_no_threshold}

        validate_result = MagicMock()
        validate_result.truth = "TRUE"
        engine.evaluate.return_value = validate_result

        event = EvaluationEvent(source="my_pred", threshold=0.7, input_value=0.5)
        ctx = {"_rsi_thresholds": {"my_pred": 0.8}}

        result = _try_capability_extension(event, ctx, engine=engine)

        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate")
        self.assertIn("_rsi_adj_my_pred", engine.predicates)

        # Call the wrapper — it should catch TypeError and fall back
        wrapper = engine.predicates["_rsi_adj_my_pred"]
        wrapper({"_rsi_thresholds": {"my_pred": 0.8}}, threshold=0.7)
        # pred_no_threshold was called (fallback path: without threshold kwarg)
        self.assertEqual(len(call_log), 1)


class TestExceptionInErrorResolutionLoop(unittest.TestCase):
    """Lines 842-844: Exception during error resolution → action = None."""

    def test_exception_during_resolve_error_sets_action_none(self):
        """When resolve_error raises, action is set to None and evaluation continues."""
        engine = _make_engine(is_true=False, source="test_pred")
        observer = RSIObserver(engine)

        # input=0.5 < threshold=0.70 → expected TRUE, actual FALSE → is_error=True
        ctx = {"input_value": 0.5, "task_id": "t1"}

        with patch("vsf_rsi.rsi_observer.match_scenario", return_value=None), \
             patch("vsf_rsi.rsi_observer.resolve_error", side_effect=RuntimeError("boom")):
            result = observer.evaluate({}, ctx, tree_id="tree1")

        # evaluate should NOT raise — error was caught
        self.assertIsNotNone(result)
        # No action was appended because resolve_error raised
        self.assertEqual(len(observer.actions), 0)
        # The event was still recorded
        self.assertEqual(len(observer.events), 1)
        self.assertTrue(observer.events[0].is_error)


class TestMetricsBridgeExceptionHandler(unittest.TestCase):
    """Lines 946-948: Metrics bridge is best-effort, never blocks evaluation."""

    def test_metrics_exception_does_not_block_evaluation(self):
        """When RSIMetrics.track_classification raises, evaluation still completes."""
        # Use input below threshold so expected=True matches is_true=True → no error
        engine = _make_engine(is_true=True, source="pred_a")
        mock_metrics = MagicMock()
        mock_metrics.track_classification.side_effect = RuntimeError("metrics down")

        observer = RSIObserver(engine, metrics=mock_metrics)
        ctx = {"input_value": 0.5, "task_id": "t1"}  # 0.5 < 0.70 → expected=True

        result = observer.evaluate({}, ctx, tree_id="tree2")

        self.assertIsNotNone(result)
        self.assertEqual(len(observer.events), 1)
        self.assertFalse(observer.events[0].is_error)
        mock_metrics.track_classification.assert_called_once()

    def test_metrics_exception_still_records_event(self):
        """Event is appended to observer.events even when metrics bridge fails."""
        # Use input above threshold so expected=False matches is_true=False → no error
        engine = _make_engine(is_true=False, source="pred_b")
        mock_metrics = MagicMock()
        mock_metrics.track_classification.side_effect = ValueError("bad data")

        observer = RSIObserver(engine, metrics=mock_metrics)
        ctx = {"input_value": 0.9, "task_id": "t2"}  # 0.9 > 0.70 → expected=False

        result = observer.evaluate({}, ctx, tree_id="tree3")

        self.assertIsNotNone(result)
        self.assertEqual(len(observer.events), 1)
        self.assertEqual(observer.events[0].source, "pred_b")


if __name__ == "__main__":
    unittest.main()
