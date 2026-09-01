"""
Adversarial Benchmark Scenarios — inspired by game theory and complex pattern detection.

These scenarios test whether predicates can detect patterns under adversarial
conditions: noise, deception, weak signals, and multi-variable interactions.

Inspired by:
  - Iterated Prisoner's Dilemma (cooperation detection under defection noise)
  - La Parábola Silenciosa (non-linear logic, hidden order in apparent chaos)
  - XOR de Alta Dimensión (5-variable interactions, non-separable patterns)
  - Señal en Ruido Blanco (weak signal detection, SNR < 1)
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── Scenario generators ──────────────────────────────────────────────

def prisoner_dilemma_scenarios(n: int = 50, defect_rate: float = 0.3) -> List[Dict]:
    """
    Iterated Prisoner's Dilemma: detect cooperative strategies.

    The "correct" answer: a player is cooperative if they cooperate
    when the opponent cooperated in the previous round, even when
    defection would be individually optimal.

    Noise: defect_rate fraction of cooperations are flipped to defection
    (simulating noise or bounded rationality).
    """
    rng = random.Random(42)
    scenarios = []

    for i in range(n):
        # Generate a sequence of opponent moves
        opponent_moves = [rng.choice(["C", "D"]) for _ in range(10)]

        # Player strategy: tit-for-tat with noise
        player_moves = []
        for j, opp in enumerate(opponent_moves):
            if j == 0:
                player_moves.append("C")  # always cooperate first
            else:
                # Cooperate if opponent cooperated last round
                if opponent_moves[j - 1] == "C":
                    player_moves.append("C")
                else:
                    player_moves.append("D")

            # Add noise
            if rng.random() < defect_rate:
                player_moves[-1] = "D" if player_moves[-1] == "C" else "C"

        # Determine if player is "cooperative"
        # Cooperative = cooperate more than 60% of the time when opponent cooperated
        coop_when_opp_cooperated = sum(
            1 for j in range(1, len(player_moves))
            if opponent_moves[j - 1] == "C" and player_moves[j] == "C"
        )
        opp_coop_count = sum(1 for m in opponent_moves[:-1] if m == "C")
        is_cooperative = (coop_when_opp_cooperated / max(opp_coop_count, 1)) > 0.6

        scenarios.append({
            "id": f"pd_{i:03d}",
            "decision": f"evaluate(cooperation, opponent_history={opponent_moves[:5]})",
            "outcome": "success" if is_cooperative else "failure",
            "fault_signature": f"defect_rate={defect_rate}",
            "correction_path": "iterated博弈",
            "context": {
                "opponent_moves": opponent_moves,
                "player_moves": player_moves,
                "cooperation_ratio": coop_when_opp_cooperated / max(opp_coop_count, 1),
            },
        })

    return scenarios


def parabola_silenciosa_scenarios(n: int = 50) -> List[Dict]:
    """
    La Parábola Silenciosa: detect order in apparent chaos.

    Points are generated from a hidden parabolic relationship
    y = a*x^2 + b*x + c, but with heavy noise. The "correct" answer
    is whether a point belongs to the parabola (within tolerance)
    or is an outlier.
    """
    rng = random.Random(42)
    a, b, c = 2.0, -3.0, 1.0  # hidden parameters
    noise_scale = 5.0  # heavy noise
    tolerance = 3.0

    scenarios = []
    for i in range(n):
        x = rng.uniform(-10, 10)
        y_true = a * x**2 + b * x + c
        y_noisy = y_true + rng.gauss(0, noise_scale)

        # Is this point "on" the parabola?
        distance = abs(y_noisy - y_true)
        is_on_parabola = distance < tolerance

        scenarios.append({
            "id": f"ps_{i:03d}",
            "decision": f"evaluate(on_parabola, x={x:.2f}, y={y_noisy:.2f})",
            "outcome": "success" if is_on_parabola else "failure",
            "fault_signature": f"noise_scale={noise_scale}",
            "correction_path": "nonlinear_logic",
            "context": {
                "x": x,
                "y": y_noisy,
                "y_true": y_true,
                "distance": distance,
                "hidden_params": {"a": a, "b": b, "c": c},
            },
        })

    return scenarios


def xor_high_dimension_scenarios(n: int = 50, dims: int = 5) -> List[Dict]:
    """
    XOR de Alta Dimensión: 5-variable XOR is not separable.

    The function is: result = x1 XOR x2 XOR x3 XOR x4 XOR x5
    Each variable is binary (0 or 1). The predicate must learn the
    full interaction — no single variable predicts the result.
    """
    rng = random.Random(42)
    scenarios = []

    for i in range(n):
        variables = {f"x{j+1}": rng.randint(0, 1) for j in range(dims)}
        result = 0
        for v in variables.values():
            result ^= v

        # Inject some noise: flip result for 10% of cases
        noise_flip = rng.random() < 0.1
        expected = (not noise_flip) if result else noise_flip

        scenarios.append({
            "id": f"xor_{i:03d}",
            "decision": f"evaluate(xor, variables={variables})",
            "outcome": "success" if expected else "failure",
            "fault_signature": f"dims={dims}",
            "correction_path": "high_dim_interaction",
            "context": {
                "variables": variables,
                "true_xor": result,
                "noise_flipped": noise_flip,
            },
        })

    return scenarios


def signal_in_noise_scenarios(
    n: int = 50,
    signal_strength: float = 0.3,
    noise_level: float = 1.0,
) -> List[Dict]:
    """
    Señal en Ruido Blanco: detect a weak periodic signal.

    A sine wave of given amplitude is buried in Gaussian noise.
    The "correct" answer is whether a local window shows the signal
    above noise (SNR > 1 in that window).
    """
    import math
    rng = random.Random(42)
    scenarios = []

    for i in range(n):
        # Generate a window of 20 samples
        window_size = 20
        t = [rng.uniform(0, 2 * math.pi) for _ in range(window_size)]
        signal = [signal_strength * math.sin(ti) for ti in t]
        noise = [rng.gauss(0, noise_level) for _ in range(window_size)]
        observed = [s + n for s, n in zip(signal, noise)]

        # SNR in this window
        signal_power = sum(s**2 for s in signal) / window_size
        noise_power = sum(n**2 for n in noise) / window_size
        snr = signal_power / max(noise_power, 1e-10)

        # Is signal detectable? (SNR > 1 in this window)
        signal_detected = snr > 1.0

        scenarios.append({
            "id": f"snr_{i:03d}",
            "decision": f"evaluate(signal_detected, snr={snr:.3f})",
            "outcome": "success" if signal_detected else "failure",
            "fault_signature": f"signal_strength={signal_strength},noise={noise_level}",
            "correction_path": "weak_signal",
            "context": {
                "window": observed[:5],  # truncated for brevity
                "snr": snr,
                "signal_power": signal_power,
                "noise_power": noise_power,
            },
        })

    return scenarios


# ── Benchmark predicates for comparison ──────────────────────────────

def always_true_predicate(ctx: Dict) -> bool:
    """Baseline: always says True."""
    return True


def always_false_predicate(ctx: Dict) -> bool:
    """Baseline: always says False."""
    return False


def random_predicate(ctx: Dict) -> bool:
    """Baseline: random guess."""
    return random.random() > 0.5


def snr_threshold_predicate(ctx: Dict) -> bool:
    """Simple threshold: detect signal if SNR > 1."""
    snr = ctx.get("snr", 0)
    return snr > 1.0


def cooperation_ratio_predicate(ctx: Dict) -> bool:
    """Simple threshold: cooperative if ratio > 0.6."""
    # cooperation_ratio may be at top level or in nested context
    ratio = ctx.get("cooperation_ratio")
    if ratio is None:
        nested = ctx.get("context", {})
        ratio = nested.get("cooperation_ratio", 0.5)
    return ratio > 0.6


# ── Suite runner ──────────────────────────────────────────────────────

def run_adversarial_benchmark(
    predicate_name: str,
    predicate_func: Callable[[Dict], bool],
    scenario_type: str = "all",
    n_per_type: int = 50,
) -> Dict[str, Any]:
    """Run a predicate against adversarial scenarios.

    Args:
        predicate_name: Name for the predicate
        predicate_func: The callable to test
        scenario_type: 'prisoner', 'parabola', 'xor', 'noise', or 'all'
        n_per_type: Number of scenarios per type

    Returns:
        Dict with per-type accuracy and overall accuracy.
    """
    from .rsi_benchmark import run_benchmark

    generators = {
        "prisoner": lambda: prisoner_dilemma_scenarios(n_per_type),
        "parabola": lambda: parabola_silenciosa_scenarios(n_per_type),
        "xor": lambda: xor_high_dimension_scenarios(n_per_type),
        "noise": lambda: signal_in_noise_scenarios(n_per_type),
    }

    if scenario_type == "all":
        types = list(generators.keys())
    else:
        types = [scenario_type]

    results = {}
    for stype in types:
        scenarios = generators[stype]()
        report = run_benchmark(f"{predicate_name}_{stype}", predicate_func, scenarios)
        results[stype] = {
            "accuracy": report.accuracy,
            "total": report.total,
            "correct": report.correct,
        }

    # Overall
    all_scenarios = []
    for stype in types:
        all_scenarios.extend(generators[stype]())

    overall = run_benchmark(predicate_name, predicate_func, all_scenarios)
    results["overall"] = {
        "accuracy": overall.accuracy,
        "total": overall.total,
        "correct": overall.correct,
    }

    return results


__all__ = [
    "prisoner_dilemma_scenarios",
    "parabola_silenciosa_scenarios",
    "xor_high_dimension_scenarios",
    "signal_in_noise_scenarios",
    "always_true_predicate",
    "always_false_predicate",
    "random_predicate",
    "snr_threshold_predicate",
    "cooperation_ratio_predicate",
    "run_adversarial_benchmark",
]
