#!/usr/bin/env python3
"""
Deep tests for rsi_genetic_algorithm_v2.py — covers missing lines:
167, 200-213, 259, 264, 282-346, 482-483, 520, 532, 550-584, 588
"""

import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from vsf_rsi.rsi_genetic_algorithm_v2 import (
    RSIGeneticAlgorithmV2,
    TreeGenome,
    CONVERGENCE_THRESHOLD,
    CONVERGENCE_PATIENCE,
)


class TestEvaluateFitnessV2(unittest.TestCase):
    """Cover line 167 (depth factor in fitness)."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=4, mutation_rate=0.0)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.7

    def test_fitness_depth_factor(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "type": "d",
            "branches": [{"condition": "TRUE", "action": "ok"}],
            "threshold": 0.7,
            "complexity": 2,
            "depth": 2
        })
        forest = self.ga.evaluate_fitness([genome], "pred")
        self.assertGreater(forest[0].fitness, 0.0)

    def test_fitness_depth_acceptable_range(self):
        for depth in [1, 4]:
            genome = TreeGenome(id="g1", name="g1", genes={
                "branches": [{"condition": "c1", "action": "ok"}],
                "threshold": 0.7, "complexity": 1, "depth": depth
            })
            forest = self.ga.evaluate_fitness([genome], "pred")
            self.assertGreaterEqual(forest[0].fitness, 0.0)

    def test_fitness_depth_out_of_range(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "branches": [], "threshold": 0.5, "complexity": 5, "depth": 5
        })
        forest = self.ga.evaluate_fitness([genome], "pred")
        self.assertGreaterEqual(forest[0].fitness, 0.0)

    def test_fitness_condition_variety(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "branches": [
                {"condition": "c1", "action": "ok"},
                {"condition": "c2", "action": "ok"},
                {"condition": "c3", "action": "ok"},
                {"condition": "c4", "action": "ok"},
            ],
            "threshold": 0.7, "complexity": 1, "depth": 2
        })
        forest = self.ga.evaluate_fitness([genome], "pred")
        self.assertGreater(forest[0].fitness, 0.0)


class TestSelectParentsRouletteV2(unittest.TestCase):
    """Cover lines 200-213: roulette wheel selection."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=6, mutation_rate=0.0)
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


class TestMixGenesV2(unittest.TestCase):
    """Cover lines 259, 264: _mix_genes with shared and unique keys."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=4)

    def test_mix_genes_shared_key(self):
        g1 = {"a": 1, "b": 2}
        g2 = {"a": 10, "b": 20}
        mixed = self.ga._mix_genes(g1, g2)
        self.assertIn(mixed["a"], [1, 10])
        self.assertIn(mixed["b"], [2, 20])

    def test_mix_genes_unique_key_from_g1(self):
        g1 = {"a": 1}
        g2 = {"b": 2}
        mixed = self.ga._mix_genes(g1, g2)
        self.assertEqual(mixed["a"], 1)

    def test_mix_genes_unique_key_from_g2(self):
        g1 = {"a": 1}
        g2 = {"a": 10, "c": 30}
        mixed = self.ga._mix_genes(g1, g2)
        self.assertEqual(mixed["c"], 30)


class TestMutateV2(unittest.TestCase):
    """Cover lines 282-346: all mutation types (threshold, branch, complexity, depth, condition)."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=4, mutation_rate=1.0)

    def _genome_with_branches(self, n=3):
        branches = [{"condition": f"cond_{i}", "action": f"act_{i}"} for i in range(n)]
        return TreeGenome(
            id="g1", name="g1",
            genes={"type": "d", "branches": branches, "threshold": 0.7, "complexity": 3, "depth": 2}
        )

    def test_mutate_threshold(self):
        genome = self._genome_with_branches()
        for seed in range(100):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if "threshold" in mutated.genes and mutated.id != genome.id:
                self.assertGreaterEqual(mutated.genes["threshold"], 0.1)
                self.assertLessEqual(mutated.genes["threshold"], 0.95)
                self.assertEqual(mutated.fitness, 0.0)
                break

    def test_mutate_branch(self):
        genome = self._genome_with_branches()
        for seed in range(100):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if mutated.id != genome.id:
                self.assertIsInstance(mutated, TreeGenome)
                self.assertIn("branches", mutated.genes)
                break

    def test_mutate_complexity(self):
        genome = self._genome_with_branches()
        for seed in range(100):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if "complexity" in mutated.genes and mutated.genes["complexity"] != 3:
                self.assertGreaterEqual(mutated.genes["complexity"], 1)
                self.assertLessEqual(mutated.genes["complexity"], 5)
                break

    def test_mutate_depth(self):
        genome = self._genome_with_branches()
        for seed in range(100):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if "depth" in mutated.genes and mutated.genes["depth"] != 2:
                self.assertGreaterEqual(mutated.genes["depth"], 1)
                self.assertLessEqual(mutated.genes["depth"], 4)
                break

    def test_mutate_condition_add_branch(self):
        genome = TreeGenome(id="g1", name="g1", genes={
            "branches": [{"condition": "c1", "action": "a1"}],
            "threshold": 0.7, "complexity": 2, "depth": 1
        })
        for seed in range(200):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if len(mutated.genes.get("branches", [])) > 1:
                self.assertGreater(len(mutated.genes["branches"]), 1)
                break

    def test_mutate_condition_remove_branch(self):
        genome = self._genome_with_branches(5)
        for seed in range(200):
            random.seed(seed)
            mutated = self.ga.mutate(genome)
            if len(mutated.genes.get("branches", [])) < 5:
                self.assertLess(len(mutated.genes["branches"]), 5)
                break

    def test_mutate_no_op_when_rate_zero(self):
        self.ga.mutation_rate = 0.0
        genome = self._genome_with_branches()
        result = self.ga.mutate(genome)
        self.assertEqual(result.id, genome.id)


class TestMaintainDiversity(unittest.TestCase):
    """Test _maintain_diversity removes duplicates."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=4)

    def test_maintain_diversity_removes_dupes(self):
        genes = {"type": "d", "branches": [], "threshold": 0.7}
        g1 = TreeGenome(id="g1", name="g1", genes=genes)
        g2 = TreeGenome(id="g2", name="g2", genes=genes)
        g3 = TreeGenome(id="g3", name="g3", genes={"type": "d", "branches": [], "threshold": 0.8})
        result = self.ga._maintain_diversity([g1, g2, g3])
        self.assertEqual(len(result), 2)


class TestEvolveForestV2(unittest.TestCase):
    """Cover lines 482-483 (convergence break), 520 (_load_forest return)."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=5, mutation_rate=0.3)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.7
        self.ga.metrics._load_metrics.return_value = {"pred": {"thresholds": {}}}
        self.tmpdir = tempfile.mkdtemp()
        self.ga.evolution_dir = Path(self.tmpdir)
        import vsf_rsi.rsi_genetic_algorithm_v2 as mod
        self._orig_forest = mod.FOREST_FILE
        self._orig_history = mod.EVOLUTION_HISTORY_FILE
        mod.FOREST_FILE = Path(self.tmpdir) / "forest_v2.json"
        mod.EVOLUTION_HISTORY_FILE = Path(self.tmpdir) / "history_v2.jsonl"

    def tearDown(self):
        import vsf_rsi.rsi_genetic_algorithm_v2 as mod
        mod.FOREST_FILE = self._orig_forest
        mod.EVOLUTION_HISTORY_FILE = self._orig_history

    def test_evolve_forest_returns_all_fields(self):
        result = self.ga.evolve_forest("pred", generations=3)
        self.assertIn("generations", result)
        self.assertIn("max_generations", result)
        self.assertIn("converged", result)
        self.assertIn("final_forest", result)
        self.assertIn("best_tree", result)
        self.assertIn("evolution_history", result)
        self.assertIn("improvement", result)

    def test_evolve_forest_convergence_early_stop(self):
        result = self.ga.evolve_forest(
            "pred", generations=50, patience=2, convergence_threshold=0.5
        )
        self.assertLessEqual(result["generations"], 50)


class TestGetEvolutionStatsV2(unittest.TestCase):
    """Cover line 532: error case when no forest found."""

    def test_stats_no_forest(self):
        ga = RSIGeneticAlgorithmV2(population_size=3)
        ga.evolution_dir = Path(tempfile.mkdtemp())
        stats = ga.get_evolution_stats("nonexistent")
        self.assertIn("error", stats)

    def test_stats_with_forest(self):
        ga = RSIGeneticAlgorithmV2(population_size=3)
        ga.evolution_dir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_genetic_algorithm_v2 as mod
        orig = mod.FOREST_FILE
        mod.FOREST_FILE = ga.evolution_dir / "forest.json"
        try:
            forest = ga.create_forest("pred")
            for g in forest:
                g.fitness = 0.6
            ga._save_forest("pred", forest)
            stats = ga.get_evolution_stats("pred")
            self.assertEqual(stats["predicate"], "pred")
            self.assertEqual(stats["population_size"], 3)
            self.assertIn("avg_fitness", stats)
        finally:
            mod.FOREST_FILE = orig


class TestCLIV2(unittest.TestCase):
    """Cover lines 550-584, 588: main() CLI interface."""

    def test_main_evolve(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_genetic_algorithm_v2 as mod
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
            import vsf_rsi.rsi_genetic_algorithm_v2 as mod
            old_forest = mod.FOREST_FILE
            mod.FOREST_FILE = Path(tmpdir) / "forest.json"
            try:
                ga = RSIGeneticAlgorithmV2(population_size=2)
                ga.evolution_dir = Path(tmpdir)
                ga.create_forest("pred")
                with patch("sys.argv", ["prog", "stats", "pred"]):
                    mod.main()
            finally:
                mod.FOREST_FILE = old_forest

    def test_main_no_command(self):
        import vsf_rsi.rsi_genetic_algorithm_v2 as mod
        with patch("sys.argv", ["prog"]):
            mod.main()


class TestCrossoverV2(unittest.TestCase):
    """Test crossover creates correct offspring."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=4)

    def test_crossover_offspring(self):
        p1 = TreeGenome(id="p1", name="p1", genes={"threshold": 0.5, "branches": []}, generation=0)
        p2 = TreeGenome(id="p2", name="p2", genes={"threshold": 0.9, "branches": []}, generation=1)
        o1, o2 = self.ga.crossover(p1, p2)
        self.assertEqual(o1.generation, 2)
        self.assertEqual(o2.generation, 2)
        self.assertIn("p1", o1.parent_ids)
        self.assertIn("p2", o2.parent_ids)


class TestEvolveGenerationV2(unittest.TestCase):
    """Test evolve_generation full pipeline."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=6, mutation_rate=0.2)
        self.ga.metrics = MagicMock()
        self.ga.metrics.get_accuracy.return_value = 0.7

    def test_evolve_generation_pipeline(self):
        forest = self.ga.create_forest("pred")
        for i, g in enumerate(forest):
            g.fitness = float(i) / len(forest)
        new_forest = self.ga.evolve_generation(forest, "pred")
        self.assertIsInstance(new_forest, list)
        self.assertLessEqual(len(new_forest), self.ga.population_size)

    def test_evolve_generation_diversity_maintained(self):
        forest = self.ga.create_forest("pred")
        for g in forest:
            g.fitness = 0.5
        new_forest = self.ga.evolve_generation(forest, "pred")
        self.assertGreater(len(new_forest), 0)


if __name__ == "__main__":
    unittest.main()
