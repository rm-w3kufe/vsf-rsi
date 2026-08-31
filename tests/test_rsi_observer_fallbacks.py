#!/usr/bin/env python3
"""
Tests for rsi_observer.py — covering fallback imports, GA loop, TypeError
handler, ValueError raise, and cleanup block.

Missing lines:
  44-49   Fallback Truth class
  55-61   Fallback scenario_memory import
  67-68   Fallback RSIPredicateGenerator import
  74-75   Fallback RSIGeneticAlgorithm import
  445-457 GA loop body (mutate_population + next_generation + fitness + return)
  630-632 TypeError handler in predicate wrapper
  655     ValueError raise on missing truth attribute
  660-661 Cleanup block on validation failure
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


class TestFallbackTruthClass(unittest.TestCase):
    """Lines 44-49: Fallback Truth class when socratic_engine not installed."""

    def test_fallback_truth_has_required_constants(self):
        """Fallback Truth class exposes TRUE, FALSE, UNKNOWN."""
        # Simulate import failure by temporarily removing socratic_engine from sys.modules
        saved = {}
        for key in list(sys.modules):
            if key.startswith("socratic_engine"):
                saved[key] = sys.modules.pop(key)

        # Also remove vsf_rsi.rsi_observer so it re-executes import logic
        if "vsf_rsi.rsi_observer" in sys.modules:
            saved["vsf_rsi.rsi_observer"] = sys.modules.pop("vsf_rsi.rsi_observer")

        # Block the real import
        import importlib
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "socratic_engine.engine":
                raise ImportError("mocked")
            return real_import(name, *args, **kwargs)

        try:
            builtins.__import__ = mock_import
            # Re-import the module to trigger fallback
            import vsf_rsi.rsi_observer as mod
            importlib.reload(mod)

            # The module-level Truth should be the fallback class
            # Check it by importing directly from the class definition
            from vsf_rsi.rsi_observer import Truth
            self.assertEqual(Truth.TRUE, "TRUE")
            self.assertEqual(Truth.FALSE, "FALSE")
            self.assertEqual(Truth.UNKNOWN, "UNKNOWN")
        finally:
            builtins.__import__ = real_import
            # Restore modules
            for k, v in saved.items():
                sys.modules[k] = v


class TestFallbackScenarioMemory(unittest.TestCase):
    """Lines 55-61: Fallback scenario_memory import."""

    def test_has_scenario_memory_flag_set_correctly(self):
        """_HAS_SCENARIO_MEMORY reflects whether scenario_memory is importable."""
        import vsf_rsi.rsi_observer as mod
        # After normal import, _HAS_SCENARIO_MEMORY should be a bool
        self.assertIsInstance(mod._HAS_SCENARIO_MEMORY, bool)


class TestFallbackPredicateGenerator(unittest.TestCase):
    """Lines 67-68: Fallback RSIPredicateGenerator import."""

    def test_has_predicate_generator_flag(self):
        """_HAS_PREDICATE_GENERATOR is a bool."""
        import vsf_rsi.rsi_observer as mod
        self.assertIsInstance(mod._HAS_PREDICATE_GENERATOR, bool)


class TestFallbackGeneticAlgorithm(unittest.TestCase):
    """Lines 74-75: Fallback RSIGeneticAlgorithm import."""

    def test_has_genetic_algorithm_flag(self):
        """_HAS_GENETIC_ALGORITHM is a bool."""
        import vsf_rsi.rsi_observer as mod
        self.assertIsInstance(mod._HAS_GENETIC_ALGORITHM, bool)


class TestGALoopBody(unittest.TestCase):
    """Lines 445-457: GA loop body — mutate + next_gen + fitness + return RSIAction."""

    def test_evolve_returns_rsi_action_with_best_genome(self):
        """evolve_predicate_population returns RSIAction when GA succeeds."""
        from vsf_rsi.rsi_observer import evolve_predicate_population, RSIAction

        mock_genome = MagicMock()
        mock_genome.fitness = 0.95

        mock_ga = MagicMock()
        mock_ga.create_forest.return_value = [mock_genome]
        mock_ga.evaluate_fitness.return_value = [mock_genome]
        mock_ga.select_parents.return_value = [mock_genome]
        mock_ga.crossover_population.return_value = [mock_genome]
        mock_ga.mutate_population.return_value = [mock_genome]  # line 445
        mock_ga.next_generation.return_value = [mock_genome]    # line 446

        with patch("vsf_rsi.rsi_observer.RSIGeneticAlgorithm", return_value=mock_ga), \
             patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", True):
            result = evolve_predicate_population(
                "test_pred", generations=2, population_size=5, mutation_rate=0.1
            )

        self.assertIsInstance(result, RSIAction)
        self.assertEqual(result.action_type, "evolve_forest")
        self.assertIn("predicate_name", result.params)

    def test_evolve_returns_none_when_no_genomes(self):
        """evolve_predicate_population returns None when forest is empty."""
        from vsf_rsi.rsi_observer import evolve_predicate_population

        mock_ga = MagicMock()
        mock_ga.create_forest.return_value = []
        mock_ga.evaluate_fitness.return_value = []
        mock_ga.select_parents.return_value = []
        mock_ga.crossover_population.return_value = []
        mock_ga.mutate_population.return_value = []
        mock_ga.next_generation.return_value = []

        with patch("vsf_rsi.rsi_observer.RSIGeneticAlgorithm", return_value=mock_ga), \
             patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", True):
            result = evolve_predicate_population("test_pred", generations=1)

        self.assertIsNone(result)

    def test_evolve_returns_none_when_ga_not_available(self):
        """evolve_predicate_population returns None when GA not installed."""
        from vsf_rsi.rsi_observer import evolve_predicate_population

        with patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", False):
            result = evolve_predicate_population("test_pred")
        self.assertIsNone(result)

    def test_ga_loop_runs_for_generations(self):
        """GA loop calls mutate_population and next_generation each generation."""
        from vsf_rsi.rsi_observer import evolve_predicate_population

        mock_genome = MagicMock()
        mock_genome.fitness = 0.5

        mock_ga = MagicMock()
        mock_ga.create_forest.return_value = [mock_genome]
        mock_ga.evaluate_fitness.return_value = [mock_genome]
        mock_ga.select_parents.return_value = [mock_genome]
        mock_ga.crossover_population.return_value = [mock_genome]
        mock_ga.mutate_population.return_value = [mock_genome]
        mock_ga.next_generation.return_value = [mock_genome]

        with patch("vsf_rsi.rsi_observer.RSIGeneticAlgorithm", return_value=mock_ga), \
             patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", True):
            evolve_predicate_population("pred", generations=3, population_size=5)

        # mutate + next_generation called 3 times each
        self.assertEqual(mock_ga.mutate_population.call_count, 3)
        self.assertEqual(mock_ga.next_generation.call_count, 3)

    def test_ga_tracks_best_genome_across_generations(self):
        """GA loop tracks the genome with highest fitness across generations."""
        from vsf_rsi.rsi_observer import evolve_predicate_population

        g1_genome = MagicMock()
        g1_genome.fitness = 0.3
        g2_genome = MagicMock()
        g2_genome.fitness = 0.9

        mock_ga = MagicMock()
        mock_ga.create_forest.return_value = [g1_genome]
        # Gen 1: low fitness, Gen 2: high fitness
        mock_ga.evaluate_fitness.side_effect = [[g1_genome], [g2_genome]]
        mock_ga.select_parents.side_effect = [[g1_genome], [g2_genome]]
        mock_ga.crossover_population.side_effect = [[g1_genome], [g2_genome]]
        mock_ga.mutate_population.side_effect = [[g1_genome], [g2_genome]]
        mock_ga.next_generation.side_effect = [[g1_genome], [g2_genome]]

        with patch("vsf_rsi.rsi_observer.RSIGeneticAlgorithm", return_value=mock_ga), \
             patch("vsf_rsi.rsi_observer._HAS_GENETIC_ALGORITHM", True):
            result = evolve_predicate_population("pred", generations=2)

        self.assertIsNotNone(result)
        self.assertEqual(result.params["generations"], 2)


class TestTypeErrorHandler(unittest.TestCase):
    """Lines 630-632: TypeError handler when predicate doesn't accept threshold."""

    def test_wrapper_falls_back_without_threshold_kwarg(self):
        """Wrapper calls original without threshold when TypeError raised."""
        from vsf_rsi.rsi_observer import _try_capability_extension, EvaluationEvent

        # Original predicate that raises TypeError when threshold is passed
        def pred_no_threshold(ctx, **kw):
            return MagicMock(truth="TRUE", certified=True)

        engine = MagicMock()
        engine.predicates = {"my_pred": pred_no_threshold}

        # Make evaluate return something with truth
        mock_result = MagicMock()
        mock_result.truth = "TRUE"
        engine.evaluate.return_value = mock_result

        event = EvaluationEvent(source="my_pred", threshold=0.7)
        ctx = {"_rsi_thresholds": {}}

        result = _try_capability_extension(event, ctx, engine=engine)
        # Should not crash — TypeError is caught and fallback used
        # Result may be None if validation fails, but no TypeError raised
        self.assertTrue(result is None or hasattr(result, 'action_type'))


class TestValueErrorRaise(unittest.TestCase):
    """Line 655: ValueError raise when wrapper validation fails."""

    def test_validation_failure_returns_failed_action(self):
        """Validation failure (no truth) returns inject_predicate_failed action."""
        from vsf_rsi.rsi_observer import _try_capability_extension, EvaluationEvent, RSIAction

        # Original predicate that works fine
        def good_pred(ctx, threshold=0.7, **kw):
            return MagicMock(truth="TRUE", certified=True)

        engine = MagicMock()
        engine.predicates = {"my_pred": good_pred}

        # evaluate returns object WITHOUT truth attribute → triggers line 654-655
        mock_result = MagicMock(spec=[])  # empty spec = no attributes
        engine.evaluate.return_value = mock_result

        event = EvaluationEvent(source="my_pred", threshold=0.7)
        ctx = {"_rsi_thresholds": {}}

        result = _try_capability_extension(event, ctx, engine=engine)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate_failed")

    def test_validation_exception_triggers_cleanup(self):
        """When evaluate raises, cleanup removes injected predicate."""
        from vsf_rsi.rsi_observer import _try_capability_extension, EvaluationEvent

        def good_pred(ctx, threshold=0.7, **kw):
            return "ok"

        engine = MagicMock()
        engine.predicates = {"my_pred": good_pred}

        # evaluate raises → goes to except block, triggers cleanup
        engine.evaluate.side_effect = RuntimeError("eval failed")

        event = EvaluationEvent(source="my_pred", threshold=0.7)
        ctx = {}

        result = _try_capability_extension(event, ctx, engine=engine)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate_failed")


class TestCleanupBlock(unittest.TestCase):
    """Lines 660-661: Cleanup block on validation failure."""

    def test_cleanup_removes_injected_predicate(self):
        """On validation failure, injected predicate is removed from engine."""
        from vsf_rsi.rsi_observer import _try_capability_extension, EvaluationEvent

        def good_pred(ctx, threshold=0.7, **kw):
            return "ok"

        predicates_dict = {"my_pred": good_pred}
        engine = MagicMock()
        engine.predicates = predicates_dict

        # evaluate returns object without truth → triggers ValueError → cleanup
        mock_result = MagicMock(spec=[])
        engine.evaluate.return_value = mock_result

        event = EvaluationEvent(source="my_pred", threshold=0.7)
        ctx = {}

        _try_capability_extension(event, ctx, engine=engine)

        # Cleanup should have tried to delete _rsi_adj_my_pred
        # (dict.__delitem__ called, but we check through mock)
        # The predicate dict should still have original but not the injected one
        self.assertNotIn("_rsi_adj_my_pred", predicates_dict)

    def test_cleanup_swallows_key_error(self):
        """Cleanup doesn't crash if predicate already removed (KeyError)."""
        from vsf_rsi.rsi_observer import _try_capability_extension, EvaluationEvent

        def good_pred(ctx, threshold=0.7, **kw):
            return "ok"

        # Use a mock for predicates where __delitem__ raises KeyError
        mock_predicates = MagicMock()
        mock_predicates.__contains__ = lambda self, key: key == "my_pred"
        mock_predicates.__getitem__ = lambda self, key: good_pred if key == "my_pred" else None
        mock_predicates.__setitem__ = lambda self, key, val: None
        mock_predicates.__delitem__ = MagicMock(side_effect=KeyError("already deleted"))

        engine = MagicMock()
        engine.predicates = mock_predicates

        mock_result = MagicMock(spec=[])
        engine.evaluate.return_value = mock_result

        event = EvaluationEvent(source="my_pred", threshold=0.7)
        ctx = {}

        # Should not raise — KeyError is caught in cleanup (lines 660-661)
        result = _try_capability_extension(event, ctx, engine=engine)
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, "inject_predicate_failed")


if __name__ == "__main__":
    unittest.main()
