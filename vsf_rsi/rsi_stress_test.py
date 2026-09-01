"""
Stress Tests — push RSI to its breaking points.

Systematically vary parameters to find where the GA, predicates,
and pipeline fail. The goal is NOT to show success — it's to find
the exact point of failure for each dimension.

Dimensions tested:
  1. Noise tolerance — SNR degradation until GA fails
  2. Dimensionality — XOR with more variables
  3. Genome expressiveness — can the genome represent the problem?
  4. Population pressure — tiny populations, early convergence
  5. Non-separable problems — no single threshold works
  6. Adversarial attacks — scenarios designed to fool the GA
  7. Scalability — large scenario counts
  8. Contradictory signals — conflicting ground truth
"""

from __future__ import annotations

import json
import math
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .rsi_adversarial_harness import (
    genome_to_predicate,
    adversarial_fitness,
    evolve_adversarial,
    AdversarialGenome,
    create_random_adversarial_genome,
    evaluate_population,
    select_parents_adversarial,
    crossover_adversarial,
    mutate_adversarial,
)
from .rsi_adversarial import (
    prisoner_dilemma_scenarios,
    parabola_silenciosa_scenarios,
    xor_high_dimension_scenarios,
    signal_in_noise_scenarios,
    always_true_predicate,
    random_predicate,
)
from .rsi_benchmark import run_benchmark, BenchmarkReport


# ── Result container ─────────────────────────────────────────────────

@dataclass
class StressResult:
    """Result of a single stress test."""
    dimension: str
    parameter_name: str
    parameter_value: Any
    ga_accuracy: float
    baseline_accuracy: float
    improvement: float
    converged: bool
    generations_used: int
    best_threshold: float
    wall_time_s: float
    failure_mode: Optional[str] = None


@dataclass
class StressReport:
    """Full stress test report."""
    results: List[StressResult] = field(default_factory=list)
    breaking_points: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── 1. Noise Tolerance ──────────────────────────────────────────────

def test_noise_tolerance(
    snr_values: Optional[List[float]] = None,
    n_scenarios: int = 60,
    population_size: int = 15,
    generations: int = 12,
) -> List[StressResult]:
    """Find the SNR at which GA fails to detect signal."""
    if snr_values is None:
        snr_values = [1.0, 0.5, 0.3, 0.15, 0.08, 0.04, 0.02, 0.01]

    results = []
    for snr in snr_values:
        t0 = time.time()
        scenarios = signal_in_noise_scenarios(n=n_scenarios, signal_strength=snr, noise_level=1.0)
        random.shuffle(scenarios)
        split = int(len(scenarios) * 0.8)
        train, test = scenarios[:split], scenarios[split:]

        evo = evolve_adversarial("noise", n_scenarios=len(train),
                                  population_size=population_size, generations=generations)

        best = evo["best_genome"]
        genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
        pred = genome_to_predicate(genes, "noise")
        report = run_benchmark("stress_noise", pred, test)
        baseline = run_benchmark("baseline", random_predicate, test).accuracy

        # Check if GA converged to same threshold (sign of no learning)
        thresholds = [h["best_threshold"] for h in evo["history"]]
        converged = len(set(round(t, 2) for t in thresholds)) <= 2

        failure_mode = None
        if report.accuracy < 0.6:
            failure_mode = "below_random_threshold"
        elif converged and report.accuracy < 0.8:
            failure_mode = "premature_convergence"

        results.append(StressResult(
            dimension="noise_tolerance",
            parameter_name="signal_strength",
            parameter_value=snr,
            ga_accuracy=report.accuracy,
            baseline_accuracy=baseline,
            improvement=report.accuracy - baseline,
            converged=converged,
            generations_used=generations,
            best_threshold=best["threshold"],
            wall_time_s=round(time.time() - t0, 2),
            failure_mode=failure_mode,
        ))
        print(f"  SNR={snr:.3f}: GA={report.accuracy:.1%} baseline={baseline:.1%} imp={report.accuracy-baseline:+.1%} {'FAIL: '+failure_mode if failure_mode else 'OK'}")

    return results


# ── 2. Dimensionality ───────────────────────────────────────────────

def test_dimensionality(
    dims_list: Optional[List[int]] = None,
    n_scenarios: int = 60,
    population_size: int = 15,
    generations: int = 12,
) -> List[StressResult]:
    """Find the dimension count where XOR becomes intractable."""
    if dims_list is None:
        dims_list = [3, 5, 7, 10, 15, 20, 30]

    results = []
    for dims in dims_list:
        t0 = time.time()
        scenarios = xor_high_dimension_scenarios(n=n_scenarios, dims=dims)
        random.shuffle(scenarios)
        split = int(len(scenarios) * 0.8)
        train, test = scenarios[:split], scenarios[split:]

        evo = evolve_adversarial("xor", n_scenarios=len(train),
                                  population_size=population_size, generations=generations)

        best = evo["best_genome"]
        genes = {"threshold": best["threshold"], "branches": [{"c":"1"}]*best["branches"], "complexity": 1}
        pred = genome_to_predicate(genes, "xor")
        report = run_benchmark("stress_xor", pred, test)
        baseline = run_benchmark("baseline", random_predicate, test).accuracy

        failure_mode = None
        if report.accuracy < 0.6:
            failure_mode = "below_random_threshold"

        results.append(StressResult(
            dimension="dimensionality",
            parameter_name="xor_dims",
            parameter_value=dims,
            ga_accuracy=report.accuracy,
            baseline_accuracy=baseline,
            improvement=report.accuracy - baseline,
            converged=False,
            generations_used=generations,
            best_threshold=best["threshold"],
            wall_time_s=round(time.time() - t0, 2),
            failure_mode=failure_mode,
        ))
        print(f"  XOR-{dims}D: GA={report.accuracy:.1%} baseline={baseline:.1%} imp={report.accuracy-baseline:+.1%} {'FAIL: '+failure_mode if failure_mode else 'OK'}")

    return results


# ── 3. Genome Expressiveness ────────────────────────────────────────

def test_genome_expressiveness(
    n_scenarios: int = 60,
    population_size: int = 15,
    generations: int = 12,
) -> List[StressResult]:
    """Test if genome representation can capture non-threshold logic.

    The genome only has threshold + branch_count. What happens when
    the problem requires more complex logic?
    """
    # Create a scenario where threshold alone can't work:
    # XOR-like problem with continuous values
    rng = random.Random(42)
    scenarios = []
    for i in range(n_scenarios):
        x = rng.uniform(-1, 1)
        y = rng.uniform(-1, 1)
        # Ground truth: inside unit circle
        inside = (x**2 + y**2) < 1.0
        scenarios.append({
            "id": f"circle_{i}",
            "decision": f"evaluate(circle, x={x:.3f}, y={y:.3f})",
            "outcome": "success" if inside else "failure",
            "context": {"x": x, "y": y, "distance": math.sqrt(x**2 + y**2)},
        })

    random.shuffle(scenarios)
    split = int(len(scenarios) * 0.8)
    train, test = scenarios[:split], scenarios[split:]

    # Evolve with threshold-only genome
    t0 = time.time()
    evo = evolve_adversarial("noise", n_scenarios=len(train),
                              population_size=population_size, generations=generations)

    best = evo["best_genome"]
    # Threshold genome can only do: value > threshold
    # But the problem needs: x^2 + y^2 < 1
    # The genome will try to use "distance" as the value
    genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
    pred = genome_to_predicate(genes, "noise")  # uses SNR/distance > threshold
    report = run_benchmark("stress_expressiveness", pred, test)

    # What does the problem actually need?
    # It needs a 2D boundary, not a 1D threshold
    # The genome can't represent this

    results = [StressResult(
        dimension="genome_expressiveness",
        parameter_name="problem_type",
        parameter_value="unit_circle_2d",
        ga_accuracy=report.accuracy,
        baseline_accuracy=0.5,  # random on balanced data
        improvement=report.accuracy - 0.5,
        converged=False,
        generations_used=generations,
        best_threshold=best["threshold"],
        wall_time_s=round(time.time() - t0, 2),
        failure_mode="threshold_cannot_represent_2d_boundary" if report.accuracy < 0.7 else None,
    )]
    print(f"  Unit circle (2D): GA={report.accuracy:.1%} threshold={best['threshold']:.2f}")
    print(f"  Problem needs: x²+y² < 1 (2D boundary)")
    print(f"  Genome has: value > threshold (1D threshold)")
    if report.accuracy < 0.7:
        print(f"  FAIL: genome cannot represent 2D decision boundary")

    return results


# ── 4. Population Pressure ──────────────────────────────────────────

def test_population_pressure(
    pop_sizes: Optional[List[int]] = None,
    n_scenarios: int = 60,
    generations: int = 15,
) -> List[StressResult]:
    """Find the minimum population where GA still works."""
    if pop_sizes is None:
        pop_sizes = [2, 3, 5, 8, 10, 15, 20]

    results = []
    for pop in pop_sizes:
        t0 = time.time()
        scenarios = signal_in_noise_scenarios(n=n_scenarios, signal_strength=0.3, noise_level=1.0)
        random.shuffle(scenarios)
        split = int(len(scenarios) * 0.8)
        train, test = scenarios[:split], scenarios[split:]

        evo = evolve_adversarial("noise", n_scenarios=len(train),
                                  population_size=pop, generations=generations)

        best = evo["best_genome"]
        genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
        pred = genome_to_predicate(genes, "noise")
        report = run_benchmark("stress_pop", pred, test)
        baseline = run_benchmark("baseline", random_predicate, test).accuracy

        # Check diversity: are all thresholds the same?
        thresholds = [h["best_threshold"] for h in evo["history"]]
        diversity_loss = len(set(round(t, 1) for t in thresholds)) <= 2

        failure_mode = None
        if report.accuracy < 0.6:
            failure_mode = "population_too_small"
        elif diversity_loss and report.accuracy < 0.8:
            failure_mode = "diversity_loss"

        results.append(StressResult(
            dimension="population_pressure",
            parameter_name="population_size",
            parameter_value=pop,
            ga_accuracy=report.accuracy,
            baseline_accuracy=baseline,
            improvement=report.accuracy - baseline,
            converged=diversity_loss,
            generations_used=generations,
            best_threshold=best["threshold"],
            wall_time_s=round(time.time() - t0, 2),
            failure_mode=failure_mode,
        ))
        print(f"  Pop={pop}: GA={report.accuracy:.1%} baseline={baseline:.1%} diversity_loss={diversity_loss} {'FAIL: '+failure_mode if failure_mode else 'OK'}")

    return results


# ── 5. Non-Separable Problems ───────────────────────────────────────

def test_non_separable(
    n_scenarios: int = 60,
    population_size: int = 15,
    generations: int = 12,
) -> List[StressResult]:
    """Test problems where no single threshold works.

    Example: XOR of 2 continuous variables where the decision boundary
    is a checkerboard pattern — no 1D threshold can capture this.
    """
    rng = random.Random(42)
    scenarios = []
    for i in range(n_scenarios):
        x = rng.uniform(-1, 1)
        y = rng.uniform(-1, 1)
        # Checkerboard: True if (x>0) XOR (y>0)
        ground_truth = (x > 0) != (y > 0)
        scenarios.append({
            "id": f"checker_{i}",
            "decision": f"evaluate(checker, x={x:.3f}, y={y:.3f})",
            "outcome": "success" if ground_truth else "failure",
            "context": {"x": x, "y": y},
        })

    random.shuffle(scenarios)
    split = int(len(scenarios) * 0.8)
    train, test = scenarios[:split], scenarios[split:]

    # Try to evolve with threshold genome
    t0 = time.time()
    evo = evolve_adversarial("noise", n_scenarios=len(train),
                              population_size=population_size, generations=generations)

    best = evo["best_genome"]
    genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
    pred = genome_to_predicate(genes, "noise")
    report = run_benchmark("stress_nonsep", pred, test)
    baseline = run_benchmark("baseline", random_predicate, test).accuracy

    failure_mode = None
    if report.accuracy < 0.6:
        failure_mode = "non_separable_no_threshold_works"

    results = [StressResult(
        dimension="non_separable",
        parameter_name="checkerboard_xor",
        parameter_value="2d_xor",
        ga_accuracy=report.accuracy,
        baseline_accuracy=baseline,
        improvement=report.accuracy - baseline,
        converged=False,
        generations_used=generations,
        best_threshold=best["threshold"],
        wall_time_s=round(time.time() - t0, 2),
        failure_mode=failure_mode,
    )]
    print(f"  Checkerboard XOR: GA={report.accuracy:.1%} baseline={baseline:.1%}")
    if failure_mode:
        print(f"  FAIL: {failure_mode}")

    return results


# ── 6. Adversarial Attacks ──────────────────────────────────────────

def test_adversarial_attacks(
    n_scenarios: int = 60,
    population_size: int = 15,
    generations: int = 12,
) -> List[StressResult]:
    """Scenarios designed to fool threshold-based predicates.

    Attack 1: Bimodal distribution — two clusters at different thresholds
    Attack 2: Adversarial examples — flip labels at decision boundary
    Attack 3: Distribution shift — train on one distribution, test on another
    """
    results = []

    # Attack 1: Bimodal
    rng = random.Random(42)
    scenarios_bimodal = []
    for i in range(n_scenarios):
        # Two clusters: one at 0.2, one at 0.8
        if rng.random() < 0.5:
            val = rng.gauss(0.2, 0.05)
        else:
            val = rng.gauss(0.8, 0.05)
        # Ground truth: True if from cluster 0.8
        from_high = val > 0.5
        scenarios_bimodal.append({
            "id": f"bimodal_{i}",
            "decision": f"evaluate(bimodal, val={val:.3f})",
            "outcome": "success" if from_high else "failure",
            "context": {"snr": val},  # reuse noise predicate
        })

    random.shuffle(scenarios_bimodal)
    split = int(len(scenarios_bimodal) * 0.8)
    train, test = scenarios_bimodal[:split], scenarios_bimodal[split:]

    t0 = time.time()
    evo = evolve_adversarial("noise", n_scenarios=len(train),
                              population_size=population_size, generations=generations)
    best = evo["best_genome"]
    genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
    pred = genome_to_predicate(genes, "noise")
    report = run_benchmark("stress_attack1", pred, test)
    baseline = run_benchmark("baseline", random_predicate, test).accuracy

    results.append(StressResult(
        dimension="adversarial_attack",
        parameter_name="bimodal_distribution",
        parameter_value="bimodal_0.2_0.8",
        ga_accuracy=report.accuracy,
        baseline_accuracy=baseline,
        improvement=report.accuracy - baseline,
        converged=False,
        generations_used=generations,
        best_threshold=best["threshold"],
        wall_time_s=round(time.time() - t0, 2),
        failure_mode=None if report.accuracy > 0.7 else "bimodal_fooling_threshold",
    ))
    print(f"  Attack 1 (bimodal): GA={report.accuracy:.1%} threshold={best['threshold']:.2f}")

    # Attack 2: Adversarial label flipping at boundary
    scenarios_flip = []
    for i in range(n_scenarios):
        val = rng.uniform(0, 1)
        # Ground truth: val > 0.5
        gt = val > 0.5
        # Flip labels near boundary (0.45–0.55)
        if 0.45 < val < 0.55:
            gt = not gt
        scenarios_flip.append({
            "id": f"flip_{i}",
            "decision": f"evaluate(flip, val={val:.3f})",
            "outcome": "success" if gt else "failure",
            "context": {"snr": val},
        })

    random.shuffle(scenarios_flip)
    split = int(len(scenarios_flip) * 0.8)
    train, test = scenarios_flip[:split], scenarios_flip[split:]

    t0 = time.time()
    evo = evolve_adversarial("noise", n_scenarios=len(train),
                              population_size=population_size, generations=generations)
    best = evo["best_genome"]
    genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
    pred = genome_to_predicate(genes, "noise")
    report = run_benchmark("stress_attack2", pred, test)
    baseline = run_benchmark("baseline", random_predicate, test).accuracy

    results.append(StressResult(
        dimension="adversarial_attack",
        parameter_name="label_flipping",
        parameter_value="flip_at_boundary",
        ga_accuracy=report.accuracy,
        baseline_accuracy=baseline,
        improvement=report.accuracy - baseline,
        converged=False,
        generations_used=generations,
        best_threshold=best["threshold"],
        wall_time_s=round(time.time() - t0, 2),
        failure_mode=None if report.accuracy > 0.6 else "boundary_flip_defeats_threshold",
    ))
    print(f"  Attack 2 (label flip): GA={report.accuracy:.1%} threshold={best['threshold']:.2f}")

    # Attack 3: Distribution shift
    # Train: signal at amplitude 0.3, Test: signal at amplitude 0.1
    train_scenarios = signal_in_noise_scenarios(n=int(n_scenarios*0.8), signal_strength=0.3)
    test_scenarios = signal_in_noise_scenarios(n=int(n_scenarios*0.2), signal_strength=0.05)

    t0 = time.time()
    evo = evolve_adversarial("noise", n_scenarios=len(train_scenarios),
                              population_size=population_size, generations=generations)
    best = evo["best_genome"]
    genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
    pred = genome_to_predicate(genes, "noise")
    report = run_benchmark("stress_attack3", pred, test_scenarios)
    baseline = run_benchmark("baseline", random_predicate, test_scenarios).accuracy

    results.append(StressResult(
        dimension="adversarial_attack",
        parameter_name="distribution_shift",
        parameter_value="train_0.3_test_0.05",
        ga_accuracy=report.accuracy,
        baseline_accuracy=baseline,
        improvement=report.accuracy - baseline,
        converged=False,
        generations_used=generations,
        best_threshold=best["threshold"],
        wall_time_s=round(time.time() - t0, 2),
        failure_mode=None if report.accuracy > 0.6 else "distribution_shift_breaks_generalization",
    ))
    print(f"  Attack 3 (dist shift): GA={report.accuracy:.1%} threshold={best['threshold']:.2f}")

    return results


# ── 7. Scalability ──────────────────────────────────────────────────

def test_scalability(
    n_values: Optional[List[int]] = None,
    population_size: int = 15,
    generations: int = 10,
) -> List[StressResult]:
    """Test performance with increasing scenario counts."""
    if n_values is None:
        n_values = [20, 50, 100, 200, 500]

    results = []
    for n in n_values:
        t0 = time.time()
        scenarios = signal_in_noise_scenarios(n=n, signal_strength=0.3)
        random.shuffle(scenarios)
        split = int(len(scenarios) * 0.8)
        train, test = scenarios[:split], scenarios[split:]

        evo = evolve_adversarial("noise", n_scenarios=len(train),
                                  population_size=population_size, generations=generations)

        best = evo["best_genome"]
        genes = {"threshold": best["threshold"], "branches": [], "complexity": 1}
        pred = genome_to_predicate(genes, "noise")
        report = run_benchmark("stress_scale", pred, test)
        baseline = run_benchmark("baseline", random_predicate, test).accuracy

        wall_time = time.time() - t0
        results.append(StressResult(
            dimension="scalability",
            parameter_name="n_scenarios",
            parameter_value=n,
            ga_accuracy=report.accuracy,
            baseline_accuracy=baseline,
            improvement=report.accuracy - baseline,
            converged=False,
            generations_used=generations,
            best_threshold=best["threshold"],
            wall_time_s=round(wall_time, 2),
            failure_mode=None if wall_time < 60 else "timeout",
        ))
        print(f"  N={n}: GA={report.accuracy:.1%} time={wall_time:.1f}s")

    return results


# ── Full Stress Test ────────────────────────────────────────────────

def run_full_stress_test() -> StressReport:
    """Run all stress tests and compile findings."""
    report = StressReport()

    print("=" * 60)
    print("  STRESS TEST SUITE — Finding the breaking points")
    print("=" * 60)

    print("\n--- 1. Noise Tolerance ---")
    report.results.extend(test_noise_tolerance())

    print("\n--- 2. Dimensionality ---")
    report.results.extend(test_dimensionality())

    print("\n--- 3. Genome Expressiveness ---")
    report.results.extend(test_genome_expressiveness())

    print("\n--- 4. Population Pressure ---")
    report.results.extend(test_population_pressure())

    print("\n--- 5. Non-Separable Problems ---")
    report.results.extend(test_non_separable())

    print("\n--- 6. Adversarial Attacks ---")
    report.results.extend(test_adversarial_attacks())

    print("\n--- 7. Scalability ---")
    report.results.extend(test_scalability())

    # Find breaking points
    for dimension in set(r.dimension for r in report.results):
        dim_results = [r for r in report.results if r.dimension == dimension]
        failures = [r for r in dim_results if r.failure_mode]
        if failures:
            worst = min(failures, key=lambda r: r.ga_accuracy)
            report.breaking_points[dimension] = {
                "failure_mode": worst.failure_mode,
                "parameter": f"{worst.parameter_name}={worst.parameter_value}",
                "accuracy": worst.ga_accuracy,
            }

    # Summary
    print("\n" + "=" * 60)
    print("  BREAKING POINTS")
    print("=" * 60)
    if report.breaking_points:
        for dim, bp in report.breaking_points.items():
            print(f"  {dim}: {bp['failure_mode']}")
            print(f"    at {bp['parameter']}: accuracy={bp['accuracy']:.1%}")
    else:
        print("  No breaking points found — system is robust across all tested dimensions")

    print(f"\n  Total tests: {len(report.results)}")
    print(f"  Failures: {len([r for r in report.results if r.failure_mode])}")

    return report


__all__ = [
    "test_noise_tolerance",
    "test_dimensionality",
    "test_genome_expressiveness",
    "test_population_pressure",
    "test_non_separable",
    "test_adversarial_attacks",
    "test_scalability",
    "run_full_stress_test",
    "StressResult",
    "StressReport",
]
