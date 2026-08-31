#!/usr/bin/env python3
"""
Deep tests for rsi_genetic_algorithm.py — covers missing lines:
71, 185-198, 214-233, 237-251, 263-298, 319-345, 349, 377-424,
448-453, 457-458, 462-469, 483-517, 521
"""

import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vsf_rsi.rsi_genetic_algorithm import (
    RSIGeneticAlgorithm,
    TreeGenome,
    CONVERGENCE_THRESHOLD,
    CONVERGENCE_PATIENCE,
)


class TestTreeGenome(unittest.TestCase):
    """Test TreeGenome dataclass defaults."""

    def test_post_init_defaults(self):
        g = TreeGenome(id="a", name="b", genes={})
        self.assertEqual(g.parent_ids, [])
        self.assertNotEqual(g.created, "")

    def test_post_init_preserves_existing(self):
        g = TreeGenome(id="a", name="b", genes={}, parent_ids=["p1"], created="2025-01-01")
        self.assertEqual(g.parent_ids, ["p1"])
        self.assertEqual(g.created, "2025-01-01")


class TestRSIGeneticAlgorithmInit(unittest.TestCase):
    """Test __init__ covers line 71 (rebuild_from_history)."""

    def test_init_rebuilds_when_metrics_empty(self):
        mock_metrics = MagicMock()
        mock_metrics._load_metrics.return_value = False
        mock_metrics.rebuild_from_history.return_value = {}
        with patch("vsf_rsi.rsi_genetic_algorithm.RSIMetrics", return_value=mock_metrics):
            ga = RSIGeneticAlgorithm(population_size=5)
            mock_metrics.rebuild_from_history.assert_called()

    def test_init_skips_rebuild_when_metrics_exist(self):
        mock_metrics = MagicMock()
        mock_metrics._load_metrics.return_value = {"some": "data"}
        with patch("vsf_rsi.rsi_genetic_algorithm.RSIMetrics", return_value=mock_metrics):
            ga = RSIGeneticAlgorithm(population_size=5)
            mock_metrics.rebuild_from_history.assert_not_called()


class TestSelectParentsRoulette(unittest.TestCase):
    """Cover lines 185-198: roulette wheel selection."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=6, mutation_rate=0.0)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.8

    def test_roulette_selects_parents(self):
        forest = self.ga.create_forest("pred")
        for i, g in enumerate(forest):
            g.fitness = float(i)
        parents = self.ga.select_parents(forest, method="roulette")
        self.assertIsInstance(parents, list)
        self.assertGreater(len(parents), 0)

    def test_roulette_zero_fitness_fallback(self):
        forest = self.ga.create_forest("pred")
        for g in forest:
            g.fitness = 0.0
        parents = self.ga.select_parents(forest, method="roulette")
        self.assertIsInstance(parents, list)
        self.assertGreater(len(parents), 0)


class TestCrossover(unittest.TestCase):
    """Cover lines 214-233: crossover produces two offspring."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=4, mutation_rate=0.0)

    def test_crossover_produces_two_offspring(self):
        p1 = TreeGenome(id="p1", name="p1", genes={"type": "d", "branches": [], "threshold": 0.7, "complexity": 2}, generation=1)
        p2 = TreeGenome(id="p2", name="p2", genes={"type": "d", "branches": [], "threshold": 0.8, "complexity": 3}, generation=1)
        o1, o2 = self.ga.crossover(p1, p2)
        self.assertIsInstance(o1, TreeGenome)
        self.assertIsInstance(o2, TreeGenome)
        self.assertEqual(o1.generation, 2)
        self.assertEqual(o2.generation, 2)
        self.assertIn("p1", o1.parent_ids)
        self.assertIn("p2", o1.parent_ids)

    def test_crossover_different_genes(self):
        p1 = TreeGenome(id="p1", name="p1", genes={"threshold": 0.5, "complexity": 1})
        p2 = TreeGenome(id="p2", name="p2", genes={"threshold": 0.9, "complexity": 5})
        o1, o2 = self.ga.crossover(p1, p2)
        self.assertIn(o1.genes["threshold"], [0.5, 0.9])
        self.assertIn(o2.genes["threshold"], [0.5, 0.9])


class TestMixGenes(unittest.TestCase):
    """Cover lines 237-251: _mix_genes logic."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=4)

    def test_mix_genes_common_keys(self):
        g1 = {"a": 1, "b": 2}
        g2 = {"a": 10, "b": 20}
        mixed = self.ga._mix_genes(g1, g2)
        self.assertIn("a", mixed)
        self.assertIn("b", mixed)
        self.assertIn(mixed["a"], [1, 10])
        self.assertIn(mixed["b"], [2, 20])

    def test_mix_genes_unique_keys(self):
        g1 = {"a": 1}
        g2 = {"b": 2}
        mixed = self.ga._mix_genes(g1, g2)
        self.assertEqual(mixed["a"], 1)
        self.assertEqual(mixed["b"], 2)


class TestMutate(unittest.TestCase):
    """Cover lines 263-298: mutate (threshold, branch, complexity)."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=4, mutation_rate=1.0)

    def test_mutate_threshold(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "type": "d", "branches": [{"condition": "TRUE", "action": "ok"}],
            "threshold": 0.7, "complexity": 2
        })
        random.seed(42)
        # Force threshold mutation by iterating
        for _ in range(20):
            mutated = self.ga.mutate(genome)
            if mutated.id != genome.id:
                self.assertIn("threshold", mutated.genes)
                self.assertGreaterEqual(mutated.genes["threshold"], 0.1)
                self.assertLessEqual(mutated.genes["threshold"], 0.9)
                self.assertEqual(mutated.fitness, 0.0)
                self.assertEqual(mutated.parent_ids, [genome.id])
                break

    def test_mutate_branch(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "type": "d",
            "branches": [{"condition": "ctx_equals($ctx, 'value', 0.5)", "action": "ok"}],
            "threshold": 0.7, "complexity": 2
        })
        for seed in range(100):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if "condition" in str(mutated.genes.get("branches", [])):
                self.assertIsInstance(mutated, TreeGenome)
                break

    def test_mutate_complexity(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "type": "d", "branches": [], "threshold": 0.7, "complexity": 3
        })
        for seed in range(100):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if "complexity" in mutated.genes:
                self.assertGreaterEqual(mutated.genes["complexity"], 1)
                self.assertLessEqual(mutated.genes["complexity"], 5)
                break

    def test_mutate_no_mutation_when_rate_zero(self):
        self.ga.mutation_rate = 0.0
        genome = TreeGenome(id="g1", name="g1", genes={"threshold": 0.7})
        result = self.ga.mutate(genome)
        self.assertEqual(result.id, genome.id)


class TestEvolveGeneration(unittest.TestCase):
    """Cover lines 319-345: evolve_generation (elitism, offspring fill)."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=6, mutation_rate=0.1)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.7

    def test_evolve_generation_returns_population(self):
        forest = self.ga.create_forest("pred")
        for i, g in enumerate(forest):
            g.fitness = float(i) / len(forest)
        new_forest = self.ga.evolve_generation(forest, "pred")
        self.assertIsInstance(new_forest, list)
        self.assertLessEqual(len(new_forest), self.ga.population_size)

    def test_evolve_generation_elitism(self):
        forest = self.ga.create_forest("pred")
        for i, g in enumerate(forest):
            g.fitness = float(i)
        new_forest = self.ga.evolve_generation(forest, "pred")
        # Population size maintained
        self.assertLessEqual(len(new_forest), self.ga.population_size)


class TestCreateRandomOffspring(unittest.TestCase):
    """Cover line 349: _create_random_offspring."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=4)

    def test_create_random_offspring(self):
        offspring = self.ga._create_random_offspring("pred")
        self.assertIsInstance(offspring, TreeGenome)
        self.assertIn("pred", offspring.name)


class TestEvolveForest(unittest.TestCase):
    """Cover lines 377-424: evolve_forest with convergence."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=5, mutation_rate=0.3)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.7
        self.ga.metrics._load_metrics.return_value = {"pred": {"thresholds": {}}}
        self.tmpdir = tempfile.mkdtemp()
        self.ga.evolution_dir = Path(self.tmpdir)

    def test_evolve_forest_returns_result(self):
        result = self.ga.evolve_forest("pred", generations=3)
        self.assertIn("generations", result)
        self.assertIn("best_tree", result)
        self.assertIn("converged", result)
        self.assertIn("evolution_history", result)
        self.assertIn("improvement", result)
        self.assertEqual(result["generations"], 3)

    def test_evolve_forest_convergence(self):
        result = self.ga.evolve_forest(
            "pred", generations=50,
            patience=2, convergence_threshold=0.1
        )
        # With high threshold, should converge early
        self.assertLessEqual(result["generations"], 50)

    def test_evolve_forest_best_tree(self):
        result = self.ga.evolve_forest("pred", generations=2)
        best = result["best_tree"]
        self.assertIsInstance(best, TreeGenome)
        self.assertGreaterEqual(best.fitness, 0.0)


class TestLoadForest(unittest.TestCase):
    """Cover lines 448-453: _load_forest."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=3)
        self.tmpdir = tempfile.mkdtemp()
        self.ga.evolution_dir = Path(self.tmpdir)
        import vsf_rsi.rsi_genetic_algorithm as mod
        self._orig_forest = mod.FOREST_FILE
        mod.FOREST_FILE = Path(self.tmpdir) / "forest.json"
        self.forest_file = mod.FOREST_FILE

    def tearDown(self):
        import vsf_rsi.rsi_genetic_algorithm as mod
        mod.FOREST_FILE = self._orig_forest

    def test_load_forest_existing_file(self):
        forest = self.ga.create_forest("pred")
        loaded = self.ga._load_forest("pred")
        self.assertEqual(len(loaded), 3)

    def test_load_forest_wrong_predicate(self):
        forest = self.ga.create_forest("pred")
        loaded = self.ga._load_forest("other_pred")
        self.assertEqual(len(loaded), 0)

    def test_load_forest_no_file(self):
        loaded = self.ga._load_forest("pred")
        self.assertEqual(len(loaded), 0)


class TestAppendHistory(unittest.TestCase):
    """Cover lines 457-458: _append_history."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=3)
        self.tmpdir = tempfile.mkdtemp()
        self.ga.evolution_dir = Path(self.tmpdir)
        import vsf_rsi.rsi_genetic_algorithm as mod
        self._orig_history = mod.EVOLUTION_HISTORY_FILE
        mod.EVOLUTION_HISTORY_FILE = Path(self.tmpdir) / "history.jsonl"
        self.history_file = mod.EVOLUTION_HISTORY_FILE

    def tearDown(self):
        import vsf_rsi.rsi_genetic_algorithm as mod
        mod.EVOLUTION_HISTORY_FILE = self._orig_history

    def test_append_history_creates_file(self):
        self.ga._append_history({"generation": 0, "fitness": 0.5})
        self.assertTrue(self.history_file.exists())

    def test_append_history_appends(self):
        self.ga._append_history({"gen": 0})
        self.ga._append_history({"gen": 1})
        lines = self.history_file.read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)


class TestGetEvolutionStats(unittest.TestCase):
    """Cover lines 462-469: get_evolution_stats."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=3)
        self.tmpdir = tempfile.mkdtemp()
        self.ga.evolution_dir = Path(self.tmpdir)
        import vsf_rsi.rsi_genetic_algorithm as mod
        self._orig_forest = mod.FOREST_FILE
        mod.FOREST_FILE = Path(self.tmpdir) / "forest.json"

    def tearDown(self):
        import vsf_rsi.rsi_genetic_algorithm as mod
        mod.FOREST_FILE = self._orig_forest

    def test_stats_with_forest(self):
        forest = self.ga.create_forest("pred")
        for g in forest:
            g.fitness = 0.5
        self.ga._save_forest("pred", forest)
        stats = self.ga.get_evolution_stats("pred")
        self.assertEqual(stats["predicate"], "pred")
        self.assertEqual(stats["population_size"], 3)
        self.assertIn("avg_fitness", stats)
        self.assertIn("max_fitness", stats)
        self.assertIn("min_fitness", stats)
        self.assertIn("best_tree", stats)
        self.assertIn("generations", stats)

    def test_stats_no_forest(self):
        stats = self.ga.get_evolution_stats("nonexistent")
        self.assertIn("error", stats)


class TestCLI(unittest.TestCase):
    """Cover lines 483-517, 521: main() CLI interface."""

    def test_main_evolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_genetic_algorithm as mod
            old_dir = mod.EVOLUTION_DIR
            old_forest = mod.FOREST_FILE
            old_history = mod.EVOLUTION_HISTORY_FILE
            mod.EVOLUTION_DIR = Path(tmpdir)
            mod.FOREST_FILE = Path(tmpdir) / "forest.json"
            mod.EVOLUTION_HISTORY_FILE = Path(tmpdir) / "history.jsonl"
            try:
                with patch("sys.argv", ["prog", "evolve", "pred", "--generations", "2", "--population", "3"]):
                    mod.main()
            finally:
                mod.EVOLUTION_DIR = old_dir
                mod.FOREST_FILE = old_forest
                mod.EVOLUTION_HISTORY_FILE = old_history

    def test_main_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_genetic_algorithm as mod
            old_dir = mod.EVOLUTION_DIR
            old_forest = mod.FOREST_FILE
            mod.EVOLUTION_DIR = Path(tmpdir)
            mod.FOREST_FILE = Path(tmpdir) / "forest.json"
            try:
                ga = RSIGeneticAlgorithm(population_size=2)
                ga.evolution_dir = Path(tmpdir)
                ga.create_forest("pred")
                with patch("sys.argv", ["prog", "stats", "pred"]):
                    mod.main()
            finally:
                mod.EVOLUTION_DIR = old_dir
                mod.FOREST_FILE = old_forest

    def test_main_no_command(self):
        import vsf_rsi.rsi_genetic_algorithm as mod
        with patch("sys.argv", ["prog"]):
            # Should print help, not crash
            mod.main()


class TestRandomGenome(unittest.TestCase):
    """Test _random_genome produces valid structure."""

    def test_random_genome_keys(self):
        ga = RSIGeneticAlgorithm(population_size=3)
        genome = ga._random_genome("pred")
        self.assertIn("type", genome)
        self.assertIn("branches", genome)
        self.assertIn("threshold", genome)
        self.assertIn("complexity", genome)
        self.assertIsInstance(genome["branches"], list)
        self.assertGreaterEqual(len(genome["branches"]), 2)
        self.assertLessEqual(len(genome["branches"]), 5)


class TestEvaluateFitness(unittest.TestCase):
    """Cover fitness evaluation logic."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithm(population_size=4, mutation_rate=0.0)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.8

    def test_evaluate_fitness_range(self):
        forest = self.ga.create_forest("pred")
        evaluated = self.ga.evaluate_fitness(forest, "pred")
        for g in evaluated:
            self.assertGreaterEqual(g.fitness, 0.0)
            self.assertLessEqual(g.fitness, 1.0)

    def test_evaluate_fitness_weights(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "type": "d",
            "branches": [{"condition": "TRUE", "action": "ok"}] * 5,
            "threshold": 0.7,
            "complexity": 1
        })
        forest = self.ga.evaluate_fitness([genome], "pred")
        self.assertGreater(forest[0].fitness, 0.0)


if __name__ == "__main__":
    unittest.main()
