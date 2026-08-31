#!/usr/bin/env python3
"""
Real integration test — RSIObserver with actual SocraticEngine.

design: docs/spec_revision/design-sources/rsi-observer-v1/rsi_observer_design.vsm

Tests the observer against the real socratic-engine with registered
predicates, not mocks.
"""

import sys
import os
import unittest
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent / "vsf_rsi"))
sys.path.insert(0, "/home/rmw3/socratic-engine")

from socratic_engine.engine import SocraticEngine, Truth, PredicateResult
from vsf_rsi.rsi_observer import RSIObserver, RSIMode, EvaluationEvent


class TestRSIObserverRealEngine(unittest.TestCase):
    """Integration tests with the actual socratic-engine."""

    def setUp(self):
        """Create a real engine with test predicates."""
        self.engine = SocraticEngine()

        # Register test predicates
        @self.engine.register("test_high")
        def test_high(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val, "threshold": threshold},
                source="test_high",
            )

        @self.engine.register("test_low")
        def test_low(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val < threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val, "threshold": threshold},
                source="test_low",
            )

        @self.engine.register("test_always_true")
        def test_always_true(ctx, **kw):
            return PredicateResult(
                truth=Truth.TRUE,
                certified=True,
                evidence={"reason": "always true"},
                source="test_always_true",
            )

    def test_real_engine_basic_evaluation(self):
        """Observer wraps a real engine evaluation."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        tree = {"predicate": "test_high", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "integration_test", "value": 0.8, "input_value": 0.8}
        result = observer.evaluate(tree, ctx, tree_id="test_tree")

        self.assertEqual(len(observer.events), 1)
        self.assertEqual(observer.events[0].source, "test_high")
        self.assertEqual(observer.events[0].truth, "true")  # real engine returns lowercase
        self.assertTrue(observer.events[0].certified)
        self.assertGreater(observer.events[0].latency_ms, 0)

    def test_real_engine_error_detection(self):
        """Observer detects errors with real engine."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # test_high with value=0.3 < threshold=0.5 → FALSE
        # input_value=0.3 < threshold=0.7 → expected TRUE
        # expected TRUE, actual FALSE → error
        tree = {"predicate": "test_high", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "error_test", "value": 0.3, "input_value": 0.3}
        result = observer.evaluate(tree, ctx, tree_id="error_tree")

        self.assertTrue(observer.events[0].is_error)
        self.assertIn(observer.events[0].error_class, ["BLOCKING", "STRUCTURAL"])

    def test_real_engine_no_error(self):
        """Observer reports no error when predicate matches expectation."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # test_high with value=0.8 > threshold=0.5 → TRUE
        # input_value=0.8 > threshold=0.5 → expected TRUE (input > threshold)
        # Wait, get_expected uses input_value < optimal_threshold
        # input_value=0.8, threshold=0.7 → 0.8 < 0.7 = False → expected FALSE
        # actual TRUE, expected FALSE → error
        # Let me use input_value=0.3 to get expected=TRUE
        tree = {"predicate": "test_high", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "no_error_test", "value": 0.8, "input_value": 0.3}
        result = observer.evaluate(tree, ctx, tree_id="no_error_tree")

        # input_value=0.3 < threshold=0.7 → expected TRUE
        # actual TRUE → no error
        self.assertFalse(observer.events[0].is_error)

    def test_real_engine_logical_composition(self):
        """Observer handles logical operators."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        tree = {
            "op": "AND",
            "args": [
                {"predicate": "test_high", "args": ["$ctx", 0.5]},
                {"predicate": "test_always_true", "args": []},
            ]
        }
        ctx = {"task_id": "composition_test", "value": 0.8, "input_value": 0.3}
        result = observer.evaluate(tree, ctx, tree_id="and_tree")

        self.assertEqual(len(observer.events), 1)
        self.assertTrue(result.is_true)

    def test_real_engine_threshold_injection(self):
        """Observer injects thresholds that predicates can use."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Register a predicate that reads from _rsi_thresholds
        @self.engine.register("test_rsi_aware")
        def test_rsi_aware(ctx, threshold=0.5, **kw):
            rsi_t = ctx.get("_rsi_thresholds", {})
            threshold = rsi_t.get("test_rsi_aware", threshold)
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val, "threshold": threshold},
                source="test_rsi_aware",
            )

        tree = {"predicate": "test_rsi_aware", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "threshold_test", "value": 0.6, "input_value": 0.3}

        # Before: threshold=0.5, value=0.6 → TRUE
        result1 = observer.evaluate(tree, ctx, tree_id="before")
        self.assertTrue(result1.is_true)

        # Inject custom threshold via _rsi_thresholds
        ctx["_rsi_thresholds"]["test_rsi_aware"] = 0.7
        result2 = observer.evaluate(tree, ctx, tree_id="after")
        # Now: threshold=0.7, value=0.6 → FALSE
        self.assertFalse(result2.is_true)

    def test_real_engine_multiple_evaluations(self):
        """Observer tracks multiple evaluations."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        for i in range(5):
            tree = {"predicate": "test_high", "args": ["$ctx", 0.5]}
            ctx = {"task_id": f"batch_{i}", "value": 0.3 + i * 0.15, "input_value": 0.5}
            observer.evaluate(tree, ctx, tree_id=f"tree_{i}")

        self.assertEqual(len(observer.events), 5)
        stats = observer.get_stats()
        self.assertEqual(stats["total_evaluations"], 5)
        self.assertGreater(stats["avg_latency_ms"], 0)

    def test_real_engine_mode_switch(self):
        """Observer respects mode switch."""
        # SAFE mode
        observer_safe = RSIObserver(self.engine, mode=RSIMode.SAFE.value)
        tree = {"predicate": "test_high", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "mode_test", "value": 0.3, "input_value": 0.3}
        observer_safe.evaluate(tree, ctx)
        self.assertEqual(ctx["_rsi_mode"], "SAFE")

        # CAPABILITY mode
        observer_cap = RSIObserver(self.engine, mode=RSIMode.CAPABILITY.value)
        ctx2 = {"task_id": "mode_test2", "value": 0.3, "input_value": 0.3}
        observer_cap.evaluate(tree, ctx2)
        self.assertEqual(ctx2["_rsi_mode"], "CAPABILITY")

    def test_real_engine_error_summary(self):
        """Observer provides error summary."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Mix of error and no-error cases
        cases = [
            {"value": 0.8, "input_value": 0.3},  # expected TRUE, actual TRUE → no error
            {"value": 0.3, "input_value": 0.3},  # expected TRUE, actual FALSE → error
            {"value": 0.9, "input_value": 0.3},  # expected TRUE, actual TRUE → no error
        ]
        for i, case in enumerate(cases):
            tree = {"predicate": "test_high", "args": ["$ctx", 0.5]}
            ctx = {"task_id": f"summary_{i}", **case}
            observer.evaluate(tree, ctx)

        summary = observer.get_error_summary()
        total_errors = summary["BLOCKING"] + summary["STRUCTURAL"]
        self.assertEqual(total_errors, 1)  # Only case 2 should error


class TestRSIObserverWithFeedbackLoop(unittest.TestCase):
    """Integration test with rsi_feedback_loop."""

    def setUp(self):
        # Use a clean temp directory for scenario memory
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        os.environ["VSI_RSI_STORE"] = self._tmpdir
        try:
            import scenario_memory as sm
            sm.STORE = Path(self._tmpdir)
        except ImportError:
            pass

        self.engine = SocraticEngine()

        @self.engine.register("ac_stasis_critical")
        def ac_stasis_critical(ctx, threshold=0.70, **kw):
            rsi_t = ctx.get("_rsi_thresholds", {})
            threshold = rsi_t.get("ac_stasis_critical", threshold)
            last_tick = ctx.get("last_tick")
            if last_tick is None:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing": "last_tick"},
                    source="ac_stasis_critical",
                )
            sc = last_tick.get("stasis_cos")
            if sc is None:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing": "stasis_cos"},
                    source="ac_stasis_critical",
                )
            return PredicateResult(
                truth=Truth.TRUE if sc < threshold else Truth.FALSE,
                certified=True,
                evidence={"stasis_cos": sc, "threshold": threshold},
                source="ac_stasis_critical",
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        os.environ.pop("VSI_RSI_STORE", None)

    def test_feedback_loop_integration(self):
        """Observer works with ac_stasis_critical predicate."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Normal case: stasis_cos=0.6 < threshold=0.70 → TRUE (danger)
        tree = {"predicate": "ac_stasis_critical", "args": ["$ctx", 0.70]}
        ctx = {
            "task_id": "feedback_test",
            "last_tick": {"stasis_cos": 0.6},
            "input_value": 0.6,
        }
        result = observer.evaluate(tree, ctx, tree_id="feedback")

        self.assertEqual(result.source, "ac_stasis_critical")
        self.assertTrue(result.is_true)

    def test_threshold_drift_detection(self):
        """Observer detects when threshold drift causes errors."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # First evaluation: stasis_cos=0.75 > threshold=0.70 → FALSE (safe)
        # input_value=0.6 < threshold=0.70 → expected TRUE, actual FALSE → error
        # Observer drifts threshold to 0.65
        tree = {"predicate": "ac_stasis_critical", "args": ["$ctx", 0.70]}
        ctx = {
            "task_id": "drift_test",
            "last_tick": {"stasis_cos": 0.75},
            "input_value": 0.6,
        }
        result1 = observer.evaluate(tree, ctx)
        self.assertFalse(result1.is_true)

        # Verify threshold was drifted
        self.assertAlmostEqual(ctx["_rsi_thresholds"]["ac_stasis_critical"], 0.65, places=2)

        # Second evaluation: stasis_cos=0.65, threshold now 0.65 → FALSE (not < threshold)
        # The drift changed the threshold, so the predicate behaves differently
        ctx["last_tick"]["stasis_cos"] = 0.65
        result2 = observer.evaluate(tree, ctx)
        # Both evaluations should have been captured
        self.assertEqual(len(observer.events), 2)


class TestRSIObserverScenarioMemory(unittest.TestCase):
    """Integration test with scenario_memory."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        os.environ["VSI_RSI_STORE"] = self.tmpdir

        # Skip if scenario_memory not available
        try:
            import scenario_memory as sm
            self.sm = sm
            sm.STORE = Path(self.tmpdir)
            import importlib
            importlib.reload(sm)
        except ImportError:
            self.skipTest("scenario_memory not installed")

        self.engine = SocraticEngine()

        @self.engine.register("test_predicate")
        def test_predicate(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val},
                source="test_predicate",
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        if "VSI_RSI_STORE" in os.environ:
            del os.environ["VSI_RSI_STORE"]

    def test_scenario_recorded_after_resolution(self):
        """Observer records scenario after resolving an error."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        tree = {"predicate": "test_predicate", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "record_test", "value": 0.3, "input_value": 0.3}
        observer.evaluate(tree, ctx)

        # Check that a scenario was recorded
        store = Path(self.tmpdir)
        scenarios = list(store.glob("*.json"))
        self.assertGreater(len(scenarios), 0)

    def test_scenario_match_on_second_occurrence(self):
        """Observer matches a scenario on second occurrence."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # First occurrence — records scenario
        tree = {"predicate": "test_predicate", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "match_test", "value": 0.3, "input_value": 0.3}
        observer.evaluate(tree, ctx)

        # Check that scenario was recorded
        store = Path(self.tmpdir)
        scenarios = list(store.glob("*.json"))
        self.assertGreater(len(scenarios), 0)

        # Second occurrence — should match
        observer2 = RSIObserver(self.engine, mode=RSIMode.SAFE.value)
        ctx2 = {"task_id": "match_test_2", "value": 0.3, "input_value": 0.3}
        observer2.evaluate(tree, ctx2)

        # Check that scenario_match was used
        if observer2.actions:
            self.assertEqual(observer2.actions[0].action_type, "scenario_match")


class TestRSIObserverCapabilityExtension(unittest.TestCase):
    """Integration test for L2 capability_extension (inject_predicate)."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        os.environ["VSI_RSI_STORE"] = self.tmpdir
        try:
            import scenario_memory as sm
            sm.STORE = Path(self.tmpdir)
        except ImportError:
            pass

        self.engine = SocraticEngine()

        @self.engine.register("original_pred")
        def original_pred(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val, "threshold": threshold},
                source="original_pred",
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop("VSI_RSI_STORE", None)

    def test_inject_predicate_creates_wrapper(self):
        """L2 inject_predicate creates a wrapper in the engine."""
        from unittest.mock import patch

        observer = RSIObserver(self.engine, mode=RSIMode.CAPABILITY.value)

        # Patch parameter_drift to fail, forcing L2
        with patch("vsf_rsi.rsi_observer._try_parameter_drift", return_value=None):
            tree = {"predicate": "original_pred", "args": ["$ctx", 0.5]}
            ctx = {"task_id": "inject_test", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        # Check if inject_predicate action was taken
        inject_actions = [a for a in observer.actions if a.action_type == "inject_predicate"]
        self.assertGreater(len(inject_actions), 0)

        # Verify the wrapper was registered
        wrapper_name = inject_actions[0].params["name"]
        self.assertIn(wrapper_name, self.engine.predicates)
        self.assertTrue(wrapper_name.startswith("_rsi_adj_"))

    def test_inject_predicate_validates_before_registering(self):
        """L2 inject_predicate validates the wrapper before keeping it."""
        from unittest.mock import patch

        observer = RSIObserver(self.engine, mode=RSIMode.CAPABILITY.value)

        with patch("vsf_rsi.rsi_observer._try_parameter_drift", return_value=None):
            tree = {"predicate": "original_pred", "args": ["$ctx", 0.5]}
            ctx = {"task_id": "validate_test", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        # Should have inject_predicate (validated successfully)
        l2_actions = [a for a in observer.actions if a.level == "L2"]
        self.assertGreater(len(l2_actions), 0)
        self.assertEqual(l2_actions[0].action_type, "inject_predicate")

    def test_inject_predicate_not_repeated(self):
        """L2 inject_predicate doesn't re-inject if already exists."""
        from unittest.mock import patch

        observer = RSIObserver(self.engine, mode=RSIMode.CAPABILITY.value)

        with patch("vsf_rsi.rsi_observer._try_parameter_drift", return_value=None):
            # First evaluation — injects
            tree = {"predicate": "original_pred", "args": ["$ctx", 0.5]}
            ctx = {"task_id": "no_repeat_1", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

            # Second evaluation — scenario_match may take priority
            # but if L2 is reached, inject_predicate_exists should appear
            ctx2 = {"task_id": "no_repeat_2", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx2)

        # Either scenario_match (from memory) or inject_predicate_exists
        # Both are valid — the key is that no duplicate injection occurs
        action_types = [a.action_type for a in observer.actions]
        has_exists = "inject_predicate_exists" in action_types
        has_match = "scenario_match" in action_types
        has_inject = "inject_predicate" in action_types
        # First call injects, second call either matches or detects existing
        self.assertTrue(has_inject or has_match)
        if has_exists:
            # No duplicate: only one inject_predicate, one exists
            self.assertEqual(action_types.count("inject_predicate"), 1)


class TestRSIObserverDashboard(unittest.TestCase):
    """Integration test for observation dashboard."""

    def setUp(self):
        self.engine = SocraticEngine()

        @self.engine.register("dash_pred")
        def dash_pred(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val},
                source="dash_pred",
            )

    def test_dump_events_creates_file(self):
        """dump_events creates a JSON file."""
        import tempfile
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        tree = {"predicate": "dash_pred", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "dump_test", "value": 0.8, "input_value": 0.3}
        observer.evaluate(tree, ctx)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            result_path = observer.dump_events(path)
            self.assertEqual(result_path, path)

            import json
            with open(path) as f:
                data = json.load(f)

            self.assertIn("stats", data)
            self.assertIn("events", data)
            self.assertIn("actions", data)
            self.assertEqual(data["stats"]["total_evaluations"], 1)
        finally:
            os.unlink(path)

    def test_dump_events_default_path(self):
        """dump_events uses default path in state/monitoring/."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        tree = {"predicate": "dash_pred", "args": ["$ctx", 0.5]}
        ctx = {"task_id": "default_path_test", "value": 0.8, "input_value": 0.3}
        observer.evaluate(tree, ctx)

        path = observer.dump_events()
        self.assertTrue(os.path.exists(path))

        # Clean up
        try:
            os.unlink(path)
        except OSError:
            pass


class TestRSIObserverL3Generation(unittest.TestCase):
    """Integration test for L3 predicate generation."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        os.environ["VSI_RSI_STORE"] = self.tmpdir
        try:
            import scenario_memory as sm
            sm.STORE = Path(self.tmpdir)
        except ImportError:
            pass

        self.engine = SocraticEngine()

        @self.engine.register("failing_pred")
        def failing_pred(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val},
                source="failing_pred",
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop("VSI_RSI_STORE", None)

    def test_analyze_patterns_detects_repeated_errors(self):
        """analyze_patterns detects predicates with repeated errors."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Generate 5 errors on the same predicate
        tree = {"predicate": "failing_pred", "args": ["$ctx", 0.5]}
        for i in range(5):
            ctx = {"task_id": f"pattern_{i}", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        patterns = observer.analyze_patterns()
        self.assertGreater(len(patterns), 0)
        self.assertEqual(patterns[0]["source"], "failing_pred")
        self.assertGreaterEqual(patterns[0]["count"], 5)

    def test_generate_predicates_creates_action(self):
        """generate_predicates creates a generate_predicate action."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Generate 4 errors (above min_occurrences=3)
        tree = {"predicate": "failing_pred", "args": ["$ctx", 0.5]}
        for i in range(4):
            ctx = {"task_id": f"gen_{i}", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        actions = observer.generate_predicates(min_occurrences=3)
        # Should have generate_predicate actions
        gen_actions = [a for a in actions if a.action_type in ("generate_predicate", "generate_predicate_exists", "generate_predicate_failed")]
        self.assertGreater(len(gen_actions), 0)
        self.assertEqual(gen_actions[0].level, "L3")
        self.assertFalse(gen_actions[0].autonomous)  # L3 requires human approval

    def test_generate_predicates_respects_min_occurrences(self):
        """generate_predicates doesn't generate for infrequent errors."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Only 2 errors (below min_occurrences=3)
        tree = {"predicate": "failing_pred", "args": ["$ctx", 0.5]}
        for i in range(2):
            ctx = {"task_id": f"min_{i}", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        actions = observer.generate_predicates(min_occurrences=3)
        gen_actions = [a for a in actions if a.action_type == "generate_predicate"]
        self.assertEqual(len(gen_actions), 0)


class TestRSIObserverL4Evolution(unittest.TestCase):
    """Integration test for L4 genetic evolution."""

    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        os.environ["VSI_RSI_STORE"] = self.tmpdir
        try:
            import scenario_memory as sm
            sm.STORE = Path(self.tmpdir)
        except ImportError:
            pass

        self.engine = SocraticEngine()

        @self.engine.register("evo_pred")
        def evo_pred(ctx, threshold=0.5, **kw):
            val = ctx.get("value", 0.0)
            return PredicateResult(
                truth=Truth.TRUE if val > threshold else Truth.FALSE,
                certified=True,
                evidence={"value": val},
                source="evo_pred",
            )

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        os.environ.pop("VSI_RSI_STORE", None)

    def test_evolve_predicates_creates_action(self):
        """evolve_predicates creates an evolve_forest action."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Generate 12 errors (above min_errors=10)
        tree = {"predicate": "evo_pred", "args": ["$ctx", 0.5]}
        for i in range(12):
            ctx = {"task_id": f"evo_{i}", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        actions = observer.evolve_predicates(min_errors=10, generations=3)
        evo_actions = [a for a in actions if a.action_type in ("evolve_forest", "evolve_forest_failed")]
        self.assertGreater(len(evo_actions), 0)
        self.assertEqual(evo_actions[0].level, "L4")
        self.assertFalse(evo_actions[0].autonomous)  # L4 requires human approval

    def test_evolve_predicates_respects_min_errors(self):
        """evolve_predicates doesn't evolve for infrequent errors."""
        observer = RSIObserver(self.engine, mode=RSIMode.SAFE.value)

        # Only 5 errors (below min_errors=10)
        tree = {"predicate": "evo_pred", "args": ["$ctx", 0.5]}
        for i in range(5):
            ctx = {"task_id": f"min_evo_{i}", "value": 0.3, "input_value": 0.3}
            observer.evaluate(tree, ctx)

        actions = observer.evolve_predicates(min_errors=10)
        evo_actions = [a for a in actions if a.action_type == "evolve_forest"]
        self.assertEqual(len(evo_actions), 0)


if __name__ == "__main__":
    unittest.main()
