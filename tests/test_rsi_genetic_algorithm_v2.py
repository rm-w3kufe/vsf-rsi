"""
Tests for rsi_genetic_algorithm_v2.py — Tuned GA
"""

import os
import tempfile
from pathlib import Path
from unittest import TestCase, main

from vsf_rsi.rsi_genetic_algorithm_v2 import (
    RSIGeneticAlgorithmV2,
    TreeGenome,
    CONVERGENCE_THRESHOLD,
    CONVERGENCE_PATIENCE,
)


class TestTreeGenome(TestCase):
    """Test TreeGenome dataclass."""

    def test_tree_genome_creation(self):
        """TreeGenome can be created with required fields."""
        genome = TreeGenome(id="test_1", name="test", genes={"type": "predicate"})
        self.assertEqual(genome.id, "test_1")
        self.assertEqual(genome.name, "test")
        self.assertEqual(genome.fitness, 0.0)

    def test_tree_genome_default_values(self):
        """TreeGenome has correct default values."""
        genome = TreeGenome(id="test_1", name="test", genes={})
        self.assertEqual(genome.generation, 0)
        self.assertEqual(genome.parent_ids, [])
        self.assertNotEqual(genome.created, "")

    def test_tree_genome_with_parent(self):
        """TreeGenome can be created with parent IDs."""
        genome = TreeGenome(id="test_1", name="test", genes={}, parent_ids=["parent_1"])
        self.assertEqual(genome.parent_ids, ["parent_1"])


class TestRSIGeneticAlgorithmV2Init(TestCase):
    """Test RSIGeneticAlgorithmV2 initialization."""

    def test_init_default(self):
        """RSIGeneticAlgorithmV2 can be initialized with defaults."""
        ga = RSIGeneticAlgorithmV2()
        self.assertEqual(ga.population_size, 10)
        self.assertEqual(ga.mutation_rate, 0.2)

    def test_init_custom(self):
        """RSIGeneticAlgorithmV2 can be initialized with custom values."""
        ga = RSIGeneticAlgorithmV2(population_size=5, mutation_rate=0.3)
        self.assertEqual(ga.population_size, 5)
        self.assertEqual(ga.mutation_rate, 0.3)

    def test_convergence_constants(self):
        """Convergence constants are defined."""
        self.assertEqual(CONVERGENCE_THRESHOLD, 0.001)
        self.assertEqual(CONVERGENCE_PATIENCE, 3)


class TestRSIGeneticAlgorithmV2Forest(TestCase):
    """Test forest creation and evolution."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=5, mutation_rate=0.1)

    def test_create_forest(self):
        """create_forest returns list of TreeGenome."""
        forest = self.ga.create_forest("test_predicate")
        self.assertIsInstance(forest, list)
        self.assertEqual(len(forest), 5)

    def test_create_forest_genomes(self):
        """create_forest returns valid TreeGenome objects."""
        forest = self.ga.create_forest("test_predicate")
        for genome in forest:
            self.assertIsInstance(genome, TreeGenome)
            self.assertIn("test_predicate", genome.name)

    def test_evaluate_fitness(self):
        """evaluate_fitness assigns fitness to genomes."""
        forest = self.ga.create_forest("test_predicate")
        evaluated = self.ga.evaluate_fitness(forest, "test_predicate")
        self.assertIsInstance(evaluated, list)
        self.assertEqual(len(evaluated), 5)
        # At least some should have non-zero fitness
        fitness_values = [g.fitness for g in evaluated]
        self.assertTrue(any(f > 0 for f in fitness_values))

    def test_select_parents(self):
        """select_parents returns parent genomes."""
        forest = self.ga.create_forest("test_predicate")
        # Set some fitness values
        for i, g in enumerate(forest):
            g.fitness = i * 0.1
        parents = self.ga.select_parents(forest)
        self.assertEqual(len(parents), 2)

    def test_crossover(self):
        """crossover produces offspring."""
        forest = self.ga.create_forest("test_predicate")
        parent1 = forest[0]
        parent2 = forest[1]
        offspring1, offspring2 = self.ga.crossover(parent1, parent2)
        self.assertIsInstance(offspring1, TreeGenome)
        self.assertIsInstance(offspring2, TreeGenome)
        self.assertNotEqual(offspring1.id, parent1.id)

    def test_mutate(self):
        """mutate modifies genome genes."""
        forest = self.ga.create_forest("test_predicate")
        genome = forest[0]
        mutated = self.ga.mutate(genome)
        self.assertIsInstance(mutated, TreeGenome)

    def test_evolve_generation(self):
        """evolve_generation returns new generation."""
        forest = self.ga.create_forest("test_predicate")
        # Set fitness values
        for i, g in enumerate(forest):
            g.fitness = i * 0.1
        new_forest = self.ga.evolve_generation(forest, "test_predicate")
        self.assertIsInstance(new_forest, list)
        # May have fewer due to diversity maintenance
        self.assertGreater(len(new_forest), 0)

    def test_evolve_forest(self):
        """evolve_forest returns stats dict."""
        result = self.ga.evolve_forest("test_predicate", generations=2)
        self.assertIsInstance(result, dict)


class TestRSIGeneticAlgorithmV2Persistence(TestCase):
    """Test forest persistence."""

    def setUp(self):
        self.ga = RSIGeneticAlgorithmV2(population_size=3)
        # Use a temp directory for evolution_dir
        self.ga.evolution_dir = Path(tempfile.mkdtemp())
        # Patch FOREST_FILE and EVOLUTION_HISTORY_FILE to use temp dir
        import vsf_rsi.rsi_genetic_algorithm_v2 as module
        self._original_forest_file = module.FOREST_FILE
        self._original_history_file = module.EVOLUTION_HISTORY_FILE
        module.FOREST_FILE = self.ga.evolution_dir / "rsi_forest_v2.json"
        module.EVOLUTION_HISTORY_FILE = self.ga.evolution_dir / "rsi_evolution_history_v2.jsonl"

    def tearDown(self):
        # Restore original files
        import vsf_rsi.rsi_genetic_algorithm_v2 as module
        module.FOREST_FILE = self._original_forest_file
        module.EVOLUTION_HISTORY_FILE = self._original_history_file

    def test_save_forest(self):
        """_save_forest creates file."""
        forest = self.ga.create_forest("test_predicate")
        self.ga._save_forest("test_predicate", forest)
        forest_file = self.ga.evolution_dir / "rsi_forest_v2.json"
        self.assertTrue(forest_file.exists())

    def test_load_forest(self):
        """_load_forest loads saved forest."""
        forest = self.ga.create_forest("test_predicate")
        self.ga._save_forest("test_predicate", forest)
        loaded = self.ga._load_forest("test_predicate")
        self.assertEqual(len(loaded), 3)

    def test_append_history(self):
        """_append_history appends to file."""
        self.ga._append_history({"generation": 1, "test": True})
        history_file = self.ga.evolution_dir / "rsi_evolution_history_v2.jsonl"
        self.assertTrue(history_file.exists())


class TestRSIGeneticAlgorithmV2Stats(TestCase):
    """Test evolution stats."""

    def test_get_evolution_stats(self):
        """get_evolution_stats returns dict."""
        ga = RSIGeneticAlgorithmV2(population_size=3)
        ga.evolution_dir = Path(tempfile.mkdtemp())
        stats = ga.get_evolution_stats("test_predicate")
        self.assertIsInstance(stats, dict)


if __name__ == "__main__":
    main()
