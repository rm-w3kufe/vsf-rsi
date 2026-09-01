"""
Adversarial Benchmark Harness — challenge RSI with known-answer problems.

Runs the GA against adversarial scenarios and measures whether evolved
predicados actually improve over baselines.

This is the test: can RSI produce a predicate that beats random chance
on problems with known ground truth?
"""

from __future__ import annotations

import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .rsi_adversarial import (
    prisoner_dilemma_scenarios,
    parabola_silenciosa_scenarios,
    xor_high_dimension_scenarios,
    signal_in_noise_scenarios,
    always_true_predicate,
    always_false_predicate,
    random_predicate,
)
from .rsi_benchmark import (
    run_benchmark,
    compare_benchmarks,
    save_report,
    BenchmarkReport,
)


# ── Genome → Predicate bridge ────────────────────────────────────────

def genome_to_predicate(genome: Dict, scenario_type: str) -> Callable[[Dict], bool]:
    """Convert a GA genome into a callable predicate.

    The genome has:
        - threshold: float (0.0–1.0)
        - branches: list of {condition, action} dicts
        - complexity: int

    The predicate applies the threshold to scenario-specific numeric values.
    """
    threshold = genome.get("threshold", 0.7)
    branch_count = len(genome.get("branches", []))

    if scenario_type == "prisoner":
        # Cooperative if cooperation_ratio > threshold
        def pred(ctx: Dict) -> bool:
            nested = ctx.get("context", {})
            ratio = nested.get("cooperation_ratio", ctx.get("cooperation_ratio", 0.5))
            return ratio > threshold
        return pred

    elif scenario_type == "parabola":
        # On parabola if distance < threshold * max_distance
        max_dist = 5.0  # noise_scale
        def pred(ctx: Dict) -> bool:
            nested = ctx.get("context", {})
            dist = nested.get("distance", ctx.get("distance", 0))
            return dist < threshold * max_dist
        return pred

    elif scenario_type == "xor":
        # XOR of all variables, with threshold on count
        def pred(ctx: Dict) -> bool:
            nested = ctx.get("context", {})
            variables = nested.get("variables", {})
            if not variables:
                return False
            result = 0
            for v in variables.values():
                result ^= v
            # Use threshold to decide: if result == 1, return True
            # But also consider branch count as a "confidence" modifier
            if result == 1:
                return True
            # Some genomes might return True even for result == 0
            # if they have enough branches (overfitting check)
            return branch_count > 3 and threshold > 0.8
        return pred

    elif scenario_type == "noise":
        # Signal detected if SNR > threshold
        def pred(ctx: Dict) -> bool:
            nested = ctx.get("context", {})
            snr = nested.get("snr", ctx.get("snr", 0))
            return snr > threshold
        return pred

    else:
        # Generic: use threshold on any available numeric value
        def pred(ctx: Dict) -> bool:
            nested = ctx.get("context", {})
            for v in nested.values():
                if isinstance(v, (int, float)):
                    return v > threshold
            return False
        return pred


# ── Adversarial Fitness Function ─────────────────────────────────────

def adversarial_fitness(
    genome: Dict,
    scenarios: List[Dict],
    scenario_type: str,
) -> float:
    """Evaluate a genome's fitness against adversarial scenarios.

    Returns accuracy (0.0–1.0) as fitness score.
    """
    pred = genome_to_predicate(genome, scenario_type)
    report = run_benchmark(f"ga_{scenario_type}", pred, scenarios)
    return report.accuracy


# ── GA with Adversarial Fitness ──────────────────────────────────────

@dataclass
class AdversarialGenome:
    """Genome for adversarial evolution."""
    id: str
    threshold: float
    branch_count: int
    scenario_type: str
    fitness: float = 0.0
    generation: int = 0
    parent_ids: List[str] = field(default_factory=list)


def create_random_adversarial_genome(
    scenario_type: str,
    gen: int = 0,
    idx: int = 0,
) -> AdversarialGenome:
    """Create a random genome for adversarial evolution."""
    return AdversarialGenome(
        id=f"{scenario_type}_g{gen}_{idx}",
        threshold=random.uniform(0.1, 0.95),
        branch_count=random.randint(1, 6),
        scenario_type=scenario_type,
        generation=gen,
    )


def evaluate_population(
    population: List[AdversarialGenome],
    scenarios: List[Dict],
    scenario_type: str,
) -> List[AdversarialGenome]:
    """Evaluate fitness of entire population."""
    for genome in population:
        genes = {
            "threshold": genome.threshold,
            "branches": [{"condition": "true", "action": "ok"}] * genome.branch_count,
        }
        genome.fitness = adversarial_fitness(genes, scenarios, scenario_type)
    return population


def select_parents_adversarial(
    population: List[AdversarialGenome],
    n: int = 4,
) -> List[AdversarialGenome]:
    """Tournament selection."""
    parents = []
    for _ in range(n):
        tournament = random.sample(population, min(3, len(population)))
        winner = max(tournament, key=lambda g: g.fitness)
        parents.append(winner)
    return parents


def crossover_adversarial(
    p1: AdversarialGenome,
    p2: AdversarialGenome,
) -> Tuple[AdversarialGenome, AdversarialGenome]:
    """Single-point crossover on threshold + branch_count."""
    t1 = p1.threshold * 0.5 + p2.threshold * 0.5
    t2 = p2.threshold * 0.5 + p1.threshold * 0.5
    b1 = (p1.branch_count + p2.branch_count) // 2
    b2 = max(1, abs(p1.branch_count - p2.branch_count))

    c1 = AdversarialGenome(
        id=f"{p1.scenario_type}_cross_{random.randint(0,9999)}",
        threshold=t1,
        branch_count=b1,
        scenario_type=p1.scenario_type,
        generation=max(p1.generation, p2.generation) + 1,
        parent_ids=[p1.id, p2.id],
    )
    c2 = AdversarialGenome(
        id=f"{p1.scenario_type}_cross_{random.randint(0,9999)}",
        threshold=t2,
        branch_count=b2,
        scenario_type=p1.scenario_type,
        generation=max(p1.generation, p2.generation) + 1,
        parent_ids=[p1.id, p2.id],
    )
    return c1, c2


def mutate_adversarial(
    genome: AdversarialGenome,
    rate: float = 0.2,
) -> AdversarialGenome:
    """Mutate threshold and branch_count."""
    t = genome.threshold
    b = genome.branch_count

    if random.random() < rate:
        t = t + random.gauss(0, 0.1)
        t = max(0.05, min(0.95, t))
    if random.random() < rate:
        b = b + random.choice([-1, 0, 0, 1])
        b = max(1, min(8, b))

    return AdversarialGenome(
        id=f"{genome.scenario_type}_mut_{random.randint(0,9999)}",
        threshold=t,
        branch_count=b,
        scenario_type=genome.scenario_type,
        generation=genome.generation,
        parent_ids=[genome.id],
    )


def evolve_adversarial(
    scenario_type: str,
    n_scenarios: int = 60,
    population_size: int = 20,
    generations: int = 15,
    mutation_rate: float = 0.2,
) -> Dict[str, Any]:
    """Run GA evolution against adversarial scenarios.

    Returns evolution history and best genome.
    """
    # Generate scenarios
    generators = {
        "prisoner": lambda: prisoner_dilemma_scenarios(n_scenarios),
        "parabola": lambda: parabola_silenciosa_scenarios(n_scenarios),
        "xor": lambda: xor_high_dimension_scenarios(n_scenarios),
        "noise": lambda: signal_in_noise_scenarios(n_scenarios),
    }
    scenarios = generators[scenario_type]()

    # Split into train/test (80/20)
    split = int(len(scenarios) * 0.8)
    train = scenarios[:split]
    test = scenarios[split:]

    # Create initial population
    population = [
        create_random_adversarial_genome(scenario_type, gen=0, idx=i)
        for i in range(population_size)
    ]

    history = []
    best_overall = None
    best_overall_fitness = 0.0

    for gen in range(generations):
        # Evaluate on TRAIN set
        population = evaluate_population(population, train, scenario_type)

        # Track best
        best = max(population, key=lambda g: g.fitness)
        avg = statistics.mean(g.fitness for g in population)

        if best.fitness > best_overall_fitness:
            best_overall_fitness = best.fitness
            best_overall = best

        history.append({
            "generation": gen,
            "best_fitness": best.fitness,
            "avg_fitness": avg,
            "best_threshold": best.threshold,
            "best_branches": best.branch_count,
        })

        # Select parents
        parents = select_parents_adversarial(population, n=4)

        # Create offspring
        offspring = []
        for i in range(0, len(parents) - 1, 2):
            c1, c2 = crossover_adversarial(parents[i], parents[i + 1])
            offspring.extend([mutate_adversarial(c1, rate=mutation_rate),
                            mutate_adversarial(c2, rate=mutation_rate)])

        # Elitism: keep top 20%
        elite_count = max(2, population_size // 5)
        elite = sorted(population, key=lambda g: g.fitness, reverse=True)[:elite_count]

        # Next generation
        population = elite + offspring[:population_size - elite_count]
        while len(population) < population_size:
            population.append(create_random_adversarial_genome(scenario_type, gen + 1, len(population)))

    # Final evaluation on TEST set (holdout)
    test_genomes = population[:5]  # top 5 from final generation
    test_results = []
    for g in test_genomes:
        genes = {"threshold": g.threshold, "branches": [{"condition": "true", "action": "ok"}] * g.branch_count}
        pred = genome_to_predicate(genes, scenario_type)
        report = run_benchmark(f"ga_{scenario_type}_test", pred, test)
        test_results.append({
            "id": g.id,
            "threshold": g.threshold,
            "branches": g.branch_count,
            "train_fitness": g.fitness,
            "test_accuracy": report.accuracy,
        })

    return {
        "scenario_type": scenario_type,
        "generations": generations,
        "population_size": population_size,
        "train_scenarios": len(train),
        "test_scenarios": len(test),
        "history": history,
        "best_genome": {
            "id": best_overall.id,
            "threshold": best_overall.threshold,
            "branches": best_overall.branch_count,
            "fitness": best_overall.fitness,
        } if best_overall else None,
        "test_results": test_results,
    }


# ── Full Adversarial Challenge ───────────────────────────────────────

def run_full_challenge(
    n_scenarios: int = 60,
    population_size: int = 20,
    generations: int = 15,
) -> Dict[str, Any]:
    """Run the full adversarial challenge across all scenario types.

    Returns comprehensive results comparing GA-evolved predicates
    against baselines.
    """
    results = {}
    types = ["prisoner", "parabola", "xor", "noise"]

    for stype in types:
        print(f"\n{'='*50}")
        print(f"  Evolving for: {stype}")
        print(f"{'='*50}")

        t_start = time.time()
        evo = evolve_adversarial(
            scenario_type=stype,
            n_scenarios=n_scenarios,
            population_size=population_size,
            generations=generations,
        )
        t_evo = time.time() - t_start

        # Benchmark baselines on same test set
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
            "always_true": run_benchmark("always_true", always_true_predicate, test).accuracy,
            "always_false": run_benchmark("always_false", always_false_predicate, test).accuracy,
            "random": run_benchmark("random", random_predicate, test).accuracy,
        }

        # Best GA result on test
        best_test = max(evo["test_results"], key=lambda r: r["test_accuracy"]) if evo["test_results"] else None

        results[stype] = {
            "evolution": evo,
            "baselines": baselines,
            "best_ga_test_accuracy": best_test["test_accuracy"] if best_test else 0,
            "best_ga_threshold": best_test["threshold"] if best_test else 0,
            "improvement_over_random": (best_test["test_accuracy"] - baselines["random"]) if best_test else 0,
            "evolution_time_s": round(t_evo, 1),
        }

        print(f"  Best GA test accuracy: {best_test['test_accuracy']:.1%}" if best_test else "  No results")
        print(f"  Baselines: {baselines}")
        print(f"  Improvement over random: {results[stype]['improvement_over_random']:+.1%}")

    # Overall summary
    all_improvements = [r["improvement_over_random"] for r in results.values()]
    overall = {
        "results": results,
        "summary": {
            "mean_improvement_over_random": statistics.mean(all_improvements) if all_improvements else 0,
            "scenarios_tested": len(types),
            "total_test_scenarios": sum(r["evolution"]["test_scenarios"] for r in results.values()),
            "conclusion": _draw_conclusion(all_improvements),
        },
    }

    return overall


def _draw_conclusion(improvements: List[float]) -> str:
    """Draw a conclusion from the improvement data."""
    if not improvements:
        return "No data"

    mean_imp = statistics.mean(improvements)
    positive = sum(1 for i in improvements if i > 0)
    total = len(improvements)

    if mean_imp > 0.1:
        return f"STRONG: GA improves over random by {mean_imp:.1%} on average ({positive}/{total} scenarios)"
    elif mean_imp > 0.02:
        return f"MARGINAL: GA shows slight improvement ({mean_imp:.1%}) — needs more generations or larger population"
    elif mean_imp > -0.02:
        return f"NEUTRAL: GA performs similar to random — predicate templates may not match scenario structure"
    else:
        return f"NEGATIVE: GA performs worse than random ({mean_imp:.1%}) — overfitting or wrong genome representation"


__all__ = [
    "genome_to_predicate",
    "adversarial_fitness",
    "evolve_adversarial",
    "run_full_challenge",
    "AdversarialGenome",
]
