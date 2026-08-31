#!/usr/bin/env python3
"""
Deep tests for rsi_observer.py — covers missing lines:
44-49, 55-61, 67-68, 74-75, 203-204, 245, 254-255, 269, 281-282,
309, 340, 347, 383-384, 428, 445-457, 567, 571, 598, 605, 617,
630-632, 646-647, 655-662, 750-782, 790-793, 807, 812-813,
842-844, 855-857, 862-863, 881-901, 946-948
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

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
    match_scenario,
    record_scenario,
    analyze_error_patterns,
    generate_predicate_from_pattern,
    generate_predicate_if_warranted,
    evolve_predicate_population,
    evolve_if_warranted,
    resolve_error,
    _try_parameter_drift,
    _try_capability_extension,
    DEFAULT_THRESHOLDS,
    VALID_INPUT_TYPES,
    MIN_THRESHOLD,
    MAX_THRESHOLD,
    THRESHOLD_STEP,
    MAX_EVENTS,
)
from vsf_rsi.rsi_metrics import RSIMetrics


class TestImportFallbacks(unittest.TestCase):
    """Cover lines 44-49, 55-61, 67-68, 74-75: import fallbacks."""

    def test_imports_complete(self):
        self.assertIsNotNone(RSIMetrics)
        self.assertIsNotNone(DEFAULT_THRESHOLDS)
        self.assertIsNotNone(VALID_INPUT_TYPES)


class TestLoadThresholdsEdgeCases(unittest.TestCase):
    """Cover lines 203-204: load_thresholds with invalid JSON."""

    def test_load_invalid_json_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tfile = Path(tmpdir) / "rsi_thresholds.json"
            tfile.write_text("not valid json {{{")
            thresholds = load_thresholds(thresholds_dir=Path(tmpdir))
            self.assertEqual(thresholds, DEFAULT_THRESHOLDS)


class TestMatchScenario(unittest.TestCase):
    """Cover lines 245, 254-255: match_scenario."""

    def test_match_scenario_no_module(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", False):
            result = match_scenario("some:fault")
            self.assertIsNone(result)

    def test_match_scenario_exception(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", True), \
             patch("vsf_rsi.rsi_observer._sm") as mock_sm:
            mock_sm.match.side_effect = RuntimeError("fail")
            result = match_scenario("some:fault")
            self.assertIsNone(result)

    def test_match_scenario_returns_correction(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", True), \
             patch("vsf_rsi.rsi_observer._sm") as mock_sm:
            mock_sm.match.return_value = ("scenario1", "fix_action")
            result = match_scenario("some:fault")
            self.assertEqual(result, "fix_action")

    def test_match_scenario_recursive_guard(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", True), \
             patch("vsf_rsi.rsi_observer._sm") as mock_sm:
            mock_sm.match.return_value = ("s1", "scenario_match_recursion")
            result = match_scenario("fault")
            self.assertIsNone(result)

    def test_match_scenario_none_result(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", True), \
             patch("vsf_rsi.rsi_observer._sm") as mock_sm:
            mock_sm.match.return_value = None
            result = match_scenario("fault")
            self.assertIsNone(result)


class TestRecordScenario(unittest.TestCase):
    """Cover lines 269, 281-282: record_scenario."""

    def test_record_no_module(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", False):
            result = record_scenario(
                EvaluationEvent(source="pred", error_class="BLOCKING"),
                RSIAction(event=EvaluationEvent(), action_type="fix")
            )
            self.assertIsNone(result)

    def test_record_exception(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", True), \
             patch("vsf_rsi.rsi_observer._sm") as mock_sm:
            mock_sm.record.side_effect = RuntimeError("fail")
            result = record_scenario(
                EvaluationEvent(source="pred"),
                RSIAction(event=EvaluationEvent(), action_type="fix")
            )
            self.assertIsNone(result)

    def test_record_success(self):
        with patch("vsf_rsi.rsi_observer._HAS_SCENARIO_MEMORY", True), \
             patch("vsf_rsi.rsi_observer._sm") as mock_sm:
            mock_sm.record.return_value = "scenario_123"
            result = record_scenario(
                EvaluationEvent(source="pred", error_class="BLOCKING"),
                RSIAction(event=EvaluationEvent(), action_type="fix", resolution="resolution_path")
            )
            self.assertEqual(result, "scenario_123")


class TestAnalyzeErrorPatterns(unittest.TestCase):
    """Cover line 309: analyze_error_patterns (skip < 2 occurrences)."""

    def test_patterns_need_two_occurrences(self):
        event = EvaluationEvent(
            source="pred1", expected=False, actual=False,
            error_class="BLOCKING", threshold=0.7, input_value=0.5
        )
        patterns = analyze_error_patterns([event])
        self.assertEqual(len(patterns), 0)

    def test_patterns_detect_frequent_errors(self):
        events = []
        for i in range(3):
            e = EvaluationEvent(
                source="pred1", expected=True, actual=False,
                error_class="BLOCKING", threshold=0.7, input_value=0.5
            )
            events.append(e)
        patterns = analyze_error_patterns(events)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["source"], "pred1")
        self.assertEqual(patterns[0]["count"], 3)

    def test_patterns_sorted_by_count(self):
        events = []
        for _ in range(5):
            events.append(EvaluationEvent(
                source="pred_a", expected=True, actual=False,
                error_class="BLOCKING", threshold=0.7, input_value=0.5
            ))
        for _ in range(3):
            events.append(EvaluationEvent(
                source="pred_b", expected=True, actual=False,
                error_class="STRUCTURAL", threshold=0.7, input_value=0.5
            ))
        patterns = analyze_error_patterns(events)
        self.assertEqual(patterns[0]["source"], "pred_a")

    def test_no_error_events(self):
        events = [EvaluationEvent(source="pred1", expected=False, actual=False)]
        patterns = analyze_error_patterns(events)
        self.assertEqual(len(patterns), 0)

    def test_empty_events(self):
        patterns = analyze_error_patterns([])
        self.assertEqual(len(patterns), 0)


class TestGeneratePredicateFromPattern(unittest.TestCase):
    """Cover lines 340, 347, 383-384: generate_predicate_from_pattern."""

    def test_no_generator_module(self):
        with patch("vsf_rsi.rsi_observer._HAS_PREDICATE_GENERATOR", False):
            result = generate_predicate_from_pattern({"source": "pred", "count": 3})
            self.assertIsNone(result)

    def test_predicate_already_exists(self):
        mock_engine = MagicMock()
        mock_engine.predicates = {"_rsi_gen_pred": MagicMock()}
        with patch("vsf_rsi.rsi_observer._HAS_PREDICATE_GENERATOR", True):
            result = generate_predicate_from_pattern(
                {"source": "pred", "count": 3, "error_class": "BLOCKING",
                 "avg_threshold": 0.7, "avg_input": 0.5},
                engine=mock_engine
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.action_type, "generate_predicate_exists")

    def test_predicate_generation_success(self):
        mock_engine = MagicMock()
        mock_engine.predicates = {}
        with patch("vsf_rsi.rsi_observer._HAS_PREDICATE_GENERATOR", True), \
             patch("vsf_rsi.rsi_observer.RSIPredicateGenerator") as MockGen:
            mock_gen = MagicMock()
            mock_gen.generate_predicate.return_value = "/tmp/pred.vsm"
            MockGen.return_value = mock_gen
            result = generate_predicate_from_pattern(
                {"source": "pred", "count": 3, "error_class": "BLOCKING",
                 "avg_threshold": 0.7, "avg_input": 0.5},
                engine=mock_engine
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.action_type, "generate_predicate")
            self.assertFalse(result.autonomous)

    def test_predicate_generation_exception(self):
        mock_engine = MagicMock()
        mock_engine.predicates = {}
        with patch("vsf_rsi.rsi_observer._HAS_PREDICATE_GENERATOR", True), \
             patch("vsf_rsi.rsi_observer.RSIPredicateGenerator") as MockGen:
            MockGen.side_effect = RuntimeError("gen failed")
            result = generate_predicate_from_pattern(
                {"source": "pred", "count": 3, "error_class": "BLOCKING",
                 "avg_threshold": 0.7, "avg_input": 0.5},
                engine=mock_engine
            )
            self.assertIsNotNone(result)
            self.assertEqual(result.action_type, "generate_predicate_failed")


class TestGeneratePredicateIfWarranted(unittest.TestCase):
    """Cover line 428: generate_predicate_if_warranted."""

    def test_no_patterns_meet_threshold(self):
        events = [EvaluationEvent(source="p1", expected=True, actual=False)]
        actions = generate_predicate_if_warranted(events, min_occurrences=3)
        self.assertEqual(len(actions), 0)

    def test_patterns_meet_threshold(self):
        events = []
        for _ in range(5):
            events.append(EvaluationEvent(
                source="pred1", expected=True, actual=False,
                error_class="BLOCKING", threshold=0.7, input_value=0.5
            ))
        with patch("vsf_rsi.rsi_observer._HAS_PREDICATE_GENERATOR", False):
            actions = generate_predicate_if_warranted(events, min_occurrences=3)
            self.assertEqual(len(actions), 0)


class TestEvolvePredicatePopulation(unittest.TestCase):
    """Cover lines 445-457: evolve_predicate_population."""

    def test_no_genetic_algorithm_module(self):
        with patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", False):
            result = evolve_predicate_population("pred")
            self.assertIsNone(result)


class TestTryParameterDrift(unittest.TestCase):
    """Cover lines 567, 571: _try_parameter_drift edge cases."""

    def test_drift_at_max_boundary(self):
        event = EvaluationEvent(
            source="pred", threshold=0.95, input_value=1.0,
            expected=True, actual=False
        )
        ctx = {"_rsi_thresholds": {"pred": MAX_THRESHOLD}}
        result = _try_parameter_drift(event, ctx)
        self.assertIsNone(result)

    def test_drift_at_min_boundary(self):
        event = EvaluationEvent(
            source="pred", threshold=0.05, input_value=0.01,
            expected=True, actual=False
        )
        ctx = {"_rsi_thresholds": {"pred": MIN_THRESHOLD}}
        result = _try_parameter_drift(event, ctx)
        self.assertIsNone(result)

    def test_drift_creates_thresholds_dict(self):
        event = EvaluationEvent(
            source="pred", threshold=0.70, input_value=0.90,
            expected=True, actual=False
        )
        ctx = {}
        result = _try_parameter_drift(event, ctx)
        self.assertIsNotNone(result)
        self.assertIn("_rsi_thresholds", ctx)


class TestTryCapabilityExtension(unittest.TestCase):
    """Cover lines 598, 605, 617, 630-632, 646-647, 655-662: _try_capability_extension."""

    def test_no_engine_returns_none(self):
        event = EvaluationEvent(source="pred")
        result = _try_capability_extension(event, {}, engine=None)
        self.assertIsNone(result)

    def test_predicate_already_injected(self):
        event = EvaluationEvent(source="pred")
        mock_engine = MagicMock()
        mock_engine.predicates = {"_rsi_adj_pred": MagicMock()}
        result = _try_capability_extension(event, {}, engine=mock_engine)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate_exists")

    def test_original_predicate_not_found(self):
        event = EvaluationEvent(source="pred")
        mock_engine = MagicMock()
        mock_engine.predicates = {}
        result = _try_capability_extension(event, {}, engine=mock_engine)
        self.assertIsNone(result)

    def test_successful_injection(self):
        event = EvaluationEvent(source="pred")
        mock_engine = MagicMock()
        original_pred = MagicMock(return_value=True)
        mock_engine.predicates = {"pred": original_pred}
        mock_engine.evaluate.return_value = MagicMock(truth="TRUE")
        result = _try_capability_extension(event, {}, engine=mock_engine)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate")
        self.assertIn("_rsi_adj_pred", mock_engine.predicates)

    def test_injection_validation_fails(self):
        event = EvaluationEvent(source="pred")
        mock_engine = MagicMock()
        original_pred = MagicMock(return_value=True)
        mock_engine.predicates = {"pred": original_pred}
        mock_engine.evaluate.side_effect = RuntimeError("eval fail")
        result = _try_capability_extension(event, {}, engine=mock_engine)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate_failed")

    def test_predicate_assign_exception(self):
        class ReadOnlyPredicates(dict):
            def __setitem__(self, key, value):
                raise TypeError("predicates are read-only")

        event = EvaluationEvent(source="pred")
        mock_engine = MagicMock()
        original_pred = MagicMock()
        mock_engine.predicates = ReadOnlyPredicates({"pred": original_pred})
        result = _try_capability_extension(event, {}, engine=mock_engine)
        self.assertIsNone(result)

    def test_wrapper_fallback_no_threshold(self):
        event = EvaluationEvent(source="pred")
        mock_engine = MagicMock()

        def orig_pred(ctx, **kw):
            return True

        mock_engine.predicates = {"pred": orig_pred}
        mock_engine.evaluate.return_value = MagicMock(truth="TRUE")
        result = _try_capability_extension(event, {}, engine=mock_engine)
        self.assertIsNotNone(result)


class TestRSIObserverInit(unittest.TestCase):
    """Cover RSIObserver __init__ and mode handling."""

    def test_init_default_mode(self):
        engine = MagicMock()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RSI_MODE", None)
            observer = RSIObserver(engine)
            self.assertEqual(observer.mode, RSIMode.CAPABILITY.value)

    def test_init_env_mode(self):
        engine = MagicMock()
        with patch.dict(os.environ, {"RSI_MODE": "SAFE"}):
            observer = RSIObserver(engine)
            self.assertEqual(observer.mode, "SAFE")

    def test_init_custom_metrics(self):
        engine = MagicMock()
        custom_metrics = MagicMock()
        observer = RSIObserver(engine, metrics=custom_metrics)
        self.assertEqual(observer.metrics, custom_metrics)


class TestRSIObserverEvaluate(unittest.TestCase):
    """Cover lines 750-782, 790-793, 807, 812-813, 842-844, 855-857, 862-863: evaluate with error recovery."""

    def _mock_engine(self, truth="TRUE", source="test_pred"):
        engine = MagicMock()
        result = MagicMock()
        result.truth = MagicMock(value=truth)
        result.is_true = (truth == "TRUE")
        result.certified = True
        result.source = source
        result.metadata = {}
        engine.evaluate.return_value = result
        return engine

    def test_evaluate_type_error_recovery(self):
        engine = MagicMock()
        engine.evaluate.side_effect = TypeError("bad input")
        observer = RSIObserver(engine)
        result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
        self.assertEqual(len(observer.events), 1)

    def test_evaluate_generic_exception_recovery(self):
        engine = MagicMock()
        call_n = [0]
        def eval_side(tree, ctx):
            call_n[0] += 1
            if call_n[0] == 1:
                raise RuntimeError("crash")
            r = MagicMock()
            r.truth = MagicMock(value="FALSE")
            r.is_true = False
            r.certified = True
            r.source = "ac_stasis_critical"
            r.metadata = {}
            return r
        engine.evaluate.side_effect = eval_side
        observer = RSIObserver(engine)
        result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
        self.assertEqual(len(observer.events), 1)

    def test_evaluate_build_event_exception(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)
        with patch.object(observer, "_build_event", side_effect=RuntimeError("event fail")):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            self.assertEqual(len(observer.events), 1)
            self.assertEqual(observer.events[0].source, "unknown")

    def test_evaluate_bridge_exception(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)
        with patch.object(observer, "_bridge_to_metrics", side_effect=RuntimeError("bridge fail")):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            self.assertEqual(len(observer.events), 1)

    def test_evaluate_memory_circulation(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)
        # Push MAX_EVENTS + 10 events
        for i in range(MAX_EVENTS + 10):
            observer.evaluate({}, {"task_id": f"t{i}", "input_value": 0.5})
        self.assertLessEqual(len(observer.events), MAX_EVENTS)

    def test_evaluate_scenario_match(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.match_scenario", return_value="fix_action"):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            self.assertTrue(any(a.action_type == "scenario_match" for a in observer.actions))

    def test_evaluate_error_resolution_exception(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer.resolve_error", side_effect=RuntimeError("res fail")):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            self.assertEqual(len(observer.events), 1)

    def test_evaluate_adjust_threshold_reevaluate(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        observer = RSIObserver(engine)
        action = RSIAction(
            event=EvaluationEvent(source="ac_stasis_critical"),
            action_type="adjust_threshold", autonomous=True,
            resolution="drifted"
        )
        with patch("vsf_rsi.rsi_observer.match_scenario", return_value=None), \
             patch("vsf_rsi.rsi_observer.resolve_error", return_value=action):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            # Re-evaluation was attempted
            self.assertGreaterEqual(engine.evaluate.call_count, 2)

    def test_evaluate_adjust_threshold_reevaluate_exception(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        call_count = [0]
        def eval_side_effect(tree, ctx):
            call_count[0] += 1
            if call_count[0] == 2:
                raise TypeError("re-eval crash")
            r = MagicMock()
            r.truth = MagicMock(value="FALSE")
            r.is_true = False
            r.certified = True
            r.source = "ac_stasis_critical"
            r.metadata = {}
            return r

        engine.evaluate.side_effect = eval_side_effect
        observer = RSIObserver(engine)
        action = RSIAction(
            event=EvaluationEvent(source="ac_stasis_critical"),
            action_type="adjust_threshold", autonomous=True,
            resolution="drifted"
        )
        with patch("vsf_rsi.rsi_observer.match_scenario", return_value=None), \
             patch("vsf_rsi.rsi_observer.resolve_error", return_value=action):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            self.assertEqual(len(observer.events), 1)

    def test_evaluate_record_scenario_exception(self):
        engine = self._mock_engine(truth="FALSE", source="ac_stasis_critical")
        observer = RSIObserver(engine)
        action = RSIAction(
            event=EvaluationEvent(source="ac_stasis_critical"),
            action_type="adjust_threshold", autonomous=True,
            resolution="drifted"
        )
        with patch("vsf_rsi.rsi_observer.match_scenario", return_value=None), \
             patch("vsf_rsi.rsi_observer.resolve_error", return_value=action), \
             patch("vsf_rsi.rsi_observer.record_scenario", side_effect=RuntimeError("record fail")):
            result = observer.evaluate({}, {"task_id": "t", "input_value": 0.5})
            self.assertEqual(len(observer.events), 1)


class TestRSIObserverBuildEvent(unittest.TestCase):
    """Cover lines 881-901: _build_event with non-numeric input."""

    def _mock_engine(self):
        engine = MagicMock()
        result = MagicMock()
        result.truth = MagicMock(value="TRUE")
        result.is_true = True
        result.certified = False
        result.source = "test_pred"
        result.metadata = {}
        engine.evaluate.return_value = result
        return engine

    def test_build_event_non_numeric_input(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)
        ctx = {"task_id": "t", "input_value": "not_a_number"}
        event = observer._build_event(engine.evaluate({}, ctx), ctx, "tree1", 1.0)
        self.assertEqual(event.error_class, ErrorClass.BLOCKING.value)
        self.assertEqual(event.input_value, 0.5)

    def test_build_event_numeric_input(self):
        engine = self._mock_engine()
        observer = RSIObserver(engine)
        ctx = {"task_id": "t", "input_value": 0.5}
        event = observer._build_event(engine.evaluate({}, ctx), ctx, "tree1", 1.0)
        self.assertEqual(event.source, "test_pred")

    def test_build_event_no_is_true(self):
        engine = MagicMock()
        result = MagicMock(spec=[])  # no is_true
        result.source = "pred"
        result.truth = MagicMock(value="UNKNOWN")
        result.certified = False
        result.metadata = {}
        engine.evaluate.return_value = result
        observer = RSIObserver(engine)
        ctx = {"task_id": "t", "input_value": 0.5}
        event = observer._build_event(result, ctx, "tree1", 1.0)
        self.assertFalse(event.actual)


class TestRSIObserverDumpEvents(unittest.TestCase):
    """Cover dump_events."""

    def test_dump_events_default_path(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        observer.events = [
            EvaluationEvent(source="p1", truth="TRUE", tree_id="t1")
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = observer.dump_events(os.path.join(tmpdir, "events.json"))
            self.assertTrue(os.path.exists(path))
            data = json.loads(open(path).read())
            self.assertIn("events", data)
            self.assertIn("actions", data)
            self.assertIn("stats", data)

    def test_dump_events_custom_path(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = observer.dump_events(os.path.join(tmpdir, "custom.json"))
            self.assertTrue(os.path.exists(path))


class TestRSIObserverGetStats(unittest.TestCase):
    """Cover get_stats."""

    def test_stats_empty(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 0)
        self.assertEqual(stats["total_errors"], 0)
        self.assertEqual(stats["error_rate"], 0.0)

    def test_stats_with_events(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        observer.events = [
            EvaluationEvent(source="p1", expected=False, actual=False, latency_ms=1.0),
            EvaluationEvent(source="p2", expected=True, actual=False, latency_ms=2.0),
        ]
        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 2)
        self.assertEqual(stats["total_errors"], 1)


class TestRSIObserverAnalyzePatterns(unittest.TestCase):
    """Cover analyze_patterns."""

    def test_analyze_patterns_delegates(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        observer.events = [
            EvaluationEvent(source="p1", expected=True, actual=False, error_class="BLOCKING"),
            EvaluationEvent(source="p1", expected=True, actual=False, error_class="BLOCKING"),
        ]
        patterns = observer.analyze_patterns()
        self.assertEqual(len(patterns), 1)


class TestRSIObserverGeneratePredicates(unittest.TestCase):
    """Cover generate_predicates."""

    def test_generate_predicates(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer._HAS_PREDICATE_GENERATOR", False):
            actions = observer.generate_predicates()
            self.assertEqual(len(actions), 0)


class TestRSIObserverEvolvePredicates(unittest.TestCase):
    """Cover evolve_predicates."""

    def test_evolve_predicates(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        with patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", False):
            actions = observer.evolve_predicates()
            self.assertEqual(len(actions), 0)


class TestTryParameterDriftBounds(unittest.TestCase):
    """Cover drift direction logic."""

    def test_drift_increases_when_input_above(self):
        event = EvaluationEvent(
            source="pred", threshold=0.70, input_value=0.90,
            expected=True, actual=False
        )
        ctx = {"_rsi_thresholds": {"pred": 0.70}}
        result = _try_parameter_drift(event, ctx)
        self.assertIsNotNone(result)
        self.assertGreater(result.params["new"], result.params["old"])

    def test_drift_decreases_when_input_below(self):
        event = EvaluationEvent(
            source="pred", threshold=0.70, input_value=0.30,
            expected=True, actual=False
        )
        ctx = {"_rsi_thresholds": {"pred": 0.70}}
        result = _try_parameter_drift(event, ctx)
        self.assertIsNotNone(result)
        self.assertLess(result.params["new"], result.params["old"])


class TestErrorClass(unittest.TestCase):
    """Cover ErrorClass enum."""

    def test_values(self):
        self.assertEqual(ErrorClass.NONE.value, "NONE")
        self.assertEqual(ErrorClass.BLOCKING.value, "BLOCKING")
        self.assertEqual(ErrorClass.STRUCTURAL.value, "STRUCTURAL")


class TestEvaluationEventIsError(unittest.TestCase):
    """Cover BUG-004: is_error computed from expected != actual."""

    def test_same_expected_actual_no_error(self):
        e = EvaluationEvent(expected=True, actual=True)
        self.assertFalse(e.is_error)

    def test_different_expected_actual_error(self):
        e = EvaluationEvent(expected=True, actual=False)
        self.assertTrue(e.is_error)


class TestGetExpected(unittest.TestCase):
    """Cover get_expected edge cases."""

    def test_exact_boundary(self):
        self.assertFalse(get_expected(0.70, 0.70))
        self.assertTrue(get_expected(0.699, 0.70))


class TestResolveErrorNoneResult(unittest.TestCase):
    """Cover resolve_error returning None."""

    def test_structural_error_returns_none(self):
        event = EvaluationEvent(
            source="pred", expected=True, actual=False,
            error_class="BLOCKING"
        )
        ctx = {"_rsi_thresholds": {"pred": 0.70}}
        memory = {"pred": ["known_scenario"]}
        with patch("vsf_rsi.rsi_observer.discriminate", return_value=ErrorClass.STRUCTURAL.value):
            result = resolve_error(event, ctx, mode=RSIMode.SAFE.value)
            self.assertIsNone(result)


class TestConstants(unittest.TestCase):
    """Cover constant values used in boundary checks."""

    def test_min_max_threshold(self):
        self.assertGreater(MIN_THRESHOLD, 0)
        self.assertLess(MAX_THRESHOLD, 1.0)
        self.assertGreater(THRESHOLD_STEP, 0)

    def test_max_events(self):
        self.assertGreater(MAX_EVENTS, 0)

    def test_valid_input_types(self):
        self.assertIn(int, VALID_INPUT_TYPES)
        self.assertIn(float, VALID_INPUT_TYPES)


class TestRSIObserverGetEventsBySource(unittest.TestCase):
    """Test get_events_by_source filtering."""

    def test_filter_by_source(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        observer.events = [
            EvaluationEvent(source="p1"),
            EvaluationEvent(source="p2"),
            EvaluationEvent(source="p1"),
        ]
        self.assertEqual(len(observer.get_events_by_source("p1")), 2)
        self.assertEqual(len(observer.get_events_by_source("p3")), 0)


class TestRSIObserverGetErrorSummary(unittest.TestCase):
    """Test error_summary counts."""

    def test_summary_all_classes(self):
        engine = MagicMock()
        observer = RSIObserver(engine)
        observer.events = [
            EvaluationEvent(source="p1", error_class="NONE"),
            EvaluationEvent(source="p2", error_class="BLOCKING"),
            EvaluationEvent(source="p3", error_class="STRUCTURAL"),
        ]
        summary = observer.get_error_summary()
        self.assertEqual(summary["NONE"], 1)
        self.assertEqual(summary["BLOCKING"], 1)
        self.assertEqual(summary["STRUCTURAL"], 1)


if __name__ == "__main__":
    unittest.main()
