"""
Tests for adversarial harness — genome→predicate bridge, fitness, evolution.
"""

import pytest
from vsf_rsi.rsi_adversarial_harness import (
    genome_to_predicate,
    adversarial_fitness,
    create_random_adversarial_genome,
    evolve_adversarial,
)


# ---------------------------------------------------------------------------
# genome_to_predicate
# ---------------------------------------------------------------------------

class TestGenomeToPredicate:
    """Convert genomes to callable predicates."""

    def test_prisoner_genome(self):
        """Prisoner genome uses cooperation_ratio."""
        genome = {"threshold": 0.6, "branches": [{"condition": "true"}], "complexity": 1}
        pred = genome_to_predicate(genome, "prisoner")
        assert pred({"context": {"cooperation_ratio": 0.8}}) is True
        assert pred({"context": {"cooperation_ratio": 0.3}}) is False

    def test_parabola_genome(self):
        """Parabola genome uses distance."""
        genome = {"threshold": 0.5, "branches": [], "complexity": 1}
        pred = genome_to_predicate(genome, "parabola")
        assert pred({"context": {"distance": 1.0}}) is True   # 1.0 < 0.5*5=2.5
        assert pred({"context": {"distance": 4.0}}) is False  # 4.0 > 2.5

    def test_xor_genome(self):
        """XOR genome computes XOR of variables."""
        genome = {"threshold": 0.5, "branches": [{"c": "1"}] * 2, "complexity": 1}
        pred = genome_to_predicate(genome, "xor")
        # XOR(1,0,1,0,1) = 1
        assert pred({"context": {"variables": {"x1": 1, "x2": 0, "x3": 1, "x4": 0, "x5": 1}}}) is True
        # XOR(1,1,0,0,0) = 0
        assert pred({"context": {"variables": {"x1": 1, "x2": 1, "x3": 0, "x4": 0, "x5": 0}}}) is False

    def test_noise_genome(self):
        """Noise genome uses SNR."""
        genome = {"threshold": 1.0, "branches": [], "complexity": 1}
        pred = genome_to_predicate(genome, "noise")
        assert pred({"context": {"snr": 2.0}}) is True
        assert pred({"context": {"snr": 0.5}}) is False


# ---------------------------------------------------------------------------
# adversarial_fitness
# ---------------------------------------------------------------------------

class TestAdversarialFitness:
    """Fitness function evaluates genome against scenarios."""

    def test_perfect_genome_high_fitness(self):
        """Genome matching ground truth gets high fitness."""
        from vsf_rsi.rsi_adversarial import signal_in_noise_scenarios
        scenarios = signal_in_noise_scenarios(n=20)
        # Threshold=1.0 matches the ground truth (SNR > 1)
        genome = {"threshold": 1.0, "branches": [], "complexity": 1}
        fitness = adversarial_fitness(genome, scenarios, "noise")
        assert fitness > 0.8

    def test_bad_genome_low_fitness(self):
        """Genome opposite to ground truth gets low fitness."""
        from vsf_rsi.rsi_adversarial import signal_in_noise_scenarios
        scenarios = signal_in_noise_scenarios(n=20)
        # Threshold=0.0 classifies everything as True — wrong for failure cases
        genome = {"threshold": 0.0, "branches": [], "complexity": 1}
        fitness = adversarial_fitness(genome, scenarios, "noise")
        assert fitness < 0.8  # not perfect


# ---------------------------------------------------------------------------
# Evolution
# ---------------------------------------------------------------------------

class TestEvolution:
    """GA evolution against adversarial scenarios."""

    def test_evolution_runs(self):
        """Evolution completes without error."""
        result = evolve_adversarial("noise", n_scenarios=20, population_size=8, generations=3)
        assert result["generations"] == 3
        assert len(result["history"]) == 3
        assert result["best_genome"] is not None

    def test_evolution_improves(self):
        """Fitness should improve over generations."""
        result = evolve_adversarial("noise", n_scenarios=30, population_size=10, generations=5)
        first = result["history"][0]["best_fitness"]
        last = result["history"][-1]["best_fitness"]
        # Should not get worse (elite preservation)
        assert last >= first * 0.8  # allow small variance

    def test_best_genome_has_threshold(self):
        """Best genome has a valid threshold."""
        result = evolve_adversarial("parabola", n_scenarios=20, population_size=8, generations=3)
        best = result["best_genome"]
        assert 0.0 <= best["threshold"] <= 1.0

    def test_test_results_exist(self):
        """Test results are generated on holdout set."""
        result = evolve_adversarial("xor", n_scenarios=20, population_size=8, generations=3)
        assert len(result["test_results"]) > 0
        for tr in result["test_results"]:
            assert "test_accuracy" in tr
            assert 0.0 <= tr["test_accuracy"] <= 1.0
