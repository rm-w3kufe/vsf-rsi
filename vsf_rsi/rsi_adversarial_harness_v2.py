"""
Adversarial Harness V2 — GA with Genoma-V2 (feature construction + decision tree).

Replaces the threshold-only genome with a genome that can:
  1. Construct derived features (z = x*y, z = x²+y²)
  2. Build decision trees over those features
  3. Solve non-separable problems (XOR, circles, checkerboard)
"""

from __future__ import annotations

import copy
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .rsi_genome_v2 import (
    GenomeV2,
    create_random_genome_v2,
    genome_to_predicate_v2,
    crossover_v2,
    mutate_v2,
    genome_v2_summary,
)
from .rsi_adversarial import (
    prisoner_dilemma_scenarios,
    parabola_silenciosa_scenarios,
    xor_high_dimension_scenarios,
    signal_in_noise_scenarios,
    random_predicate,
)
from .rsi_benchmark import run_benchmark, BenchmarkReport


# ── Scenario → Feature Mapping ──────────────────────────────────────

def get_scenario_features(scenario_type: str) -> List[str]:
    """Get raw feature names for a scenario type."""
    features = {
        "prisoner": ["cooperation_ratio"],
        "parabola": ["x", "y", "distance"],
        "xor": ["x1", "x2", "x3", "x4", "x5"],
        "noise": ["snr"],
    }
    return features.get(scenario_type, [])


def extract_raw_features(scenario: Dict, scenario_type: str) -> Dict[str, float]:
    """Extract raw float features from a scenario."""
    ctx = scenario.get("context", {})
    raw = {}

    if scenario_type == "prisoner":
        raw["cooperation_ratio"] = float(ctx.get("cooperation_ratio", 0.5))
    elif scenario_type == "parabola":
        raw["x"] = float(ctx.get("x", 0))
        raw["y"] = float(ctx.get("y", 0))
        raw["distance"] = float(ctx.get("distance", 0))
    elif scenario_type == "xor":
        variables = ctx.get("variables", {})
        for k, v in variables.items():
            if isinstance(v, (int, float)):
                raw[k] = float(v)
    elif scenario_type == "noise":
        raw["snr"] = float(ctx.get("snr", 0))

    return raw


# ── V2 Fitness Function ─────────────────────────────────────────────

def adversarial_fitness_v2(
    genome: GenomeV2,
    scenarios: List[Dict],
    scenario_type: str,
) -> float:
    """Evaluate genome fitness against adversarial scenarios."""
    pred = genome_to_predicate_v2(genome)
    report = run_benchmark(f"ga_v2_{scenario_type}", pred, scenarios)
    return report.accuracy


# ── V2 GA ────────────────────────────────────────────────────────────

def evaluate_population_v2(
    population: List[GenomeV2],
    scenarios: List[Dict],
    scenario_type: str,
) -> List[GenomeV2]:
    """Evaluate fitness of entire population."""
    for genome in population:
        genome.fitness = adversarial_fitness_v2(genome, scenarios, scenario_type)
    return population


def select_parents_v2(
    population: List[GenomeV2],
    n: int = 4,
) -> List[GenomeV2]:
    """Tournament selection."""
    parents = []
    for _ in range(n):
        tournament = random.sample(population, min(3, len(population)))
        winner = max(tournament, key=lambda g: g.fitness)
        parents.append(winner)
    return parents


def evolve_adversarial_v2(
    scenario_type: str,
    n_scenarios: int = 60,
    population_size: int = 20,
    generations: int = 15,
    mutation_rate: float = 0.2,
    n_derived_features: int = 2,
    tree_depth: int = 2,
) -> Dict[str, Any]:
    """Run GA evolution with Genoma-V2."""
    # Generate scenarios
    generators = {
        "prisoner": lambda: prisoner_dilemma_scenarios(n_scenarios),
        "parabola": lambda: parabola_silenciosa_scenarios(n_scenarios),
        "xor": lambda: xor_high_dimension_scenarios(n_scenarios),
        "noise": lambda: signal_in_noise_scenarios(n_scenarios),
    }
    scenarios = generators[scenario_type]()

    # Split into train/test
    split = int(len(scenarios) * 0.8)
    train, test = scenarios[:split], scenarios[split:]

    # Get available features
    available = get_scenario_features(scenario_type)

    # Create initial population
    population = [
        create_random_genome_v2(
            genome_id=f"{scenario_type}_g0_{i}",
            available_features=available,
            n_derived=n_derived_features,
            tree_depth=tree_depth,
            gen=0,
        )
        for i in range(population_size)
    ]

    history = []
    best_overall = None
    best_overall_fitness = 0.0

    for gen in range(generations):
        # Evaluate on TRAIN
        population = evaluate_population_v2(population, train, scenario_type)

        # Track best
        best = max(population, key=lambda g: g.fitness)
        avg = statistics.mean(g.fitness for g in population)

        if best.fitness > best_overall_fitness:
            best_overall_fitness = best.fitness
            best_overall = copy.deepcopy(best)

        history.append({
            "generation": gen,
            "best_fitness": best.fitness,
            "avg_fitness": avg,
        })

        # Select parents
        parents = select_parents_v2(population, n=4)

        # Create offspring
        offspring = []
        for i in range(0, len(parents) - 1, 2):
            c1, c2 = crossover_v2(parents[i], parents[i + 1])
            offspring.extend([mutate_v2(c1, rate=mutation_rate),
                            mutate_v2(c2, rate=mutation_rate)])

        # Elitism
        elite_count = max(2, population_size // 5)
        elite = sorted(population, key=lambda g: g.fitness, reverse=True)[:elite_count]

        # Next generation
        population = elite + offspring[:population_size - elite_count]
        while len(population) < population_size:
            population.append(create_random_genome_v2(
                genome_id=f"{scenario_type}_g{gen+1}_{len(population)}",
                available_features=available,
                n_derived=n_derived_features,
                tree_depth=tree_depth,
                gen=gen + 1,
            ))

    # Final evaluation on TEST
    test_genomes = sorted(population, key=lambda g: g.fitness, reverse=True)[:5]
    test_results = []
    for g in test_genomes:
        pred = genome_to_predicate_v2(g)
        report = run_benchmark(f"ga_v2_{scenario_type}_test", pred, test)
        test_results.append({
            "id": g.id,
            "train_fitness": g.fitness,
            "test_accuracy": report.accuracy,
            "features": [(f.output_name, f.op, f.args) for f in g.features],
        })

    return {
        "scenario_type": scenario_type,
        "generations": generations,
        "population_size": population_size,
        "train_scenarios": len(train),
        "test_scenarios": len(test),
        "history": history,
        "best_genome_summary": genome_v2_summary(best_overall) if best_overall else "None",
        "test_results": test_results,
    }


def run_full_challenge_v2(
    n_scenarios: int = 60,
    population_size: int = 20,
    generations: int = 15,
) -> Dict[str, Any]:
    """Run full adversarial challenge with Genoma-V2."""
    results = {}
    types = ["prisoner", "parabola", "xor", "noise"]

    for stype in types:
        print(f"\n{'='*50}")
        print(f"  V2 Evolving for: {stype}")
        print(f"{'='*50}")

        t_start = time.time()
        evo = evolve_adversarial_v2(
            scenario_type=stype,
            n_scenarios=n_scenarios,
            population_size=population_size,
            generations=generations,
        )
        t_evo = time.time() - t_start

        # Baselines
        generators = {
            "prisoner": lambda: prisoner_dilemma_scenarios(n_scenarios),
            "parabola": lambda: parabola_silenciosa_scenarios(n_scenarios),
            "xor": lambda: xor_high_dimension_scenarios(n_scenarios),
            "noise": lambda: signal_in_noise_scenarios(n_scenarios),
        }
        all_scenarios = generators[stype]()
        split = int(len(all_scenarios) * 0.8)
        test = all_scenarios[split:]

        baselines = {
            "always_true": run_benchmark("always_true", lambda ctx: True, test).accuracy,
            "always_false": run_benchmark("always_false", lambda ctx: False, test).accuracy,
            "random": run_benchmark("random", random_predicate, test).accuracy,
        }

        best_test = max(evo["test_results"], key=lambda r: r["test_accuracy"]) if evo["test_results"] else None

        results[stype] = {
            "evolution": evo,
            "baselines": baselines,
            "best_ga_test_accuracy": best_test["test_accuracy"] if best_test else 0,
            "improvement_over_random": (best_test["test_accuracy"] - baselines["random"]) if best_test else 0,
            "evolution_time_s": round(t_evo, 1),
        }

        print(f"  Best V2 test accuracy: {best_test['test_accuracy']:.1%}" if best_test else "  No results")
        print(f"  Baselines: {baselines}")
        print(f"  Best genome:\n{evo['best_genome_summary'][:200]}")

    # Summary
    all_improvements = [r["improvement_over_random"] for r in results.values()]
    overall = {
        "results": results,
        "summary": {
            "mean_improvement_over_random": statistics.mean(all_improvements) if all_improvements else 0,
            "scenarios_tested": len(types),
            "total_test_scenarios": sum(r["evolution"]["test_scenarios"] for r in results.values()),
        },
    }

    return overall


__all__ = [
    "get_scenario_features",
    "extract_raw_features",
    "adversarial_fitness_v2",
    "evolve_adversarial_v2",
    "run_full_challenge_v2",
]
