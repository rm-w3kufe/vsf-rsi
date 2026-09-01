"""
RSI Benchmark Framework — Record and evaluate real agent sessions.

Loads scenarios from scenario_memory, creates test cases, and measures
whether predicates improve decision quality over time.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import scenario_memory


# ── Configuration ────────────────────────────────────────────────────

BENCHMARK_DIR = Path(__file__).parent.parent / "state" / "benchmarks"
BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    """Result of evaluating a predicate against one scenario."""
    scenario_id: str
    predicate_name: str
    input_data: Dict[str, Any]
    expected: bool
    got: bool
    correct: bool
    latency_ms: float = 0.0


@dataclass
class BenchmarkReport:
    """Aggregated results from a benchmark run."""
    predicate_name: str
    total: int
    correct: int
    accuracy: float
    results: List[BenchmarkResult] = field(default_factory=list)
    timestamp: str = ""
    improvement_delta: Optional[float] = None  # vs previous run

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ── Core functions ───────────────────────────────────────────────────

def load_scenarios(
    min_quality: Optional[float] = None,
    outcome_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load scenarios from scenario_memory.

    Args:
        min_quality: Only include scenarios with quality >= this value.
        outcome_filter: Only include scenarios matching this outcome pattern.

    Returns:
        List of scenario dicts.
    """
    store = scenario_memory._get_store()
    scenarios = []

    for p in store.glob("*.json"):
        try:
            rec = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(rec, dict):
            continue

        # Apply filters
        if min_quality is not None:
            quality = rec.get("quality", 0.5)  # default 0.5 if not set
            if quality < min_quality:
                continue

        if outcome_filter is not None:
            outcome = rec.get("outcome", "")
            if outcome_filter not in outcome:
                continue

        scenarios.append(rec)

    return scenarios


def scenario_to_test_case(scenario: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a scenario to a test case for predicate evaluation.

    A test case has:
    - 'input': context dict for the predicate
    - 'expected': bool — True if outcome was success/resolved
    """
    outcome = scenario.get("outcome", "")
    decision = scenario.get("decision", "")

    # Determine expected result from outcome
    # Success outcomes → predicate should return True (triggered)
    # Failure outcomes → predicate should return False (not triggered)
    success_keywords = ["success", "resolved", "done", "pass"]
    expected = any(kw in outcome.lower() for kw in success_keywords)

    # Build input from decision context
    # Extract the predicate name and args from the decision string
    input_data = {
        "decision": decision,
        "outcome": outcome,
        "fault_signature": scenario.get("fault_signature", ""),
        "correction_path": scenario.get("correction_path", ""),
    }

    # Pass through nested context if available (for rich predicates)
    if "context" in scenario:
        input_data["context"] = scenario["context"]

    # Try to extract numeric values from decision for threshold-based predicates
    if "truth=" in decision:
        truth_str = decision.split("truth=")[-1].split(")")[0]
        try:
            input_data["truth_value"] = float(truth_str)
        except ValueError:
            pass

    return {
        "input": input_data,
        "expected": expected,
        "scenario_id": scenario.get("id", "unknown"),
    }


def run_benchmark(
    predicate_name: str,
    predicate_func: Callable[[Dict], bool],
    scenarios: Optional[List[Dict]] = None,
    min_accuracy: float = 0.0,
) -> BenchmarkReport:
    """Run a predicate against scenarios and measure accuracy.

    Args:
        predicate_name: Name of the predicate being tested
        predicate_func: The callable to evaluate
        scenarios: Scenarios to test against. If None, loads all.
        min_accuracy: Not used for filtering, just for reporting.

    Returns:
        BenchmarkReport with results and accuracy.
    """
    if scenarios is None:
        scenarios = load_scenarios()

    results = []
    for scenario in scenarios:
        tc = scenario_to_test_case(scenario)
        if tc is None:
            continue

        # Evaluate
        t_start = _now_ms()
        try:
            got = predicate_func(tc["input"])
            # Normalize
            if hasattr(got, "is_true"):
                got = got.is_true
            else:
                got = bool(got)
        except Exception:
            got = False
        t_end = _now_ms()

        correct = got == tc["expected"]
        results.append(BenchmarkResult(
            scenario_id=tc["scenario_id"],
            predicate_name=predicate_name,
            input_data=tc["input"],
            expected=tc["expected"],
            got=got,
            correct=correct,
            latency_ms=(t_end - t_start),
        ))

    total = len(results)
    correct_count = sum(1 for r in results if r.correct)
    accuracy = correct_count / total if total > 0 else 0.0

    report = BenchmarkReport(
        predicate_name=predicate_name,
        total=total,
        correct=correct_count,
        accuracy=accuracy,
        results=results,
    )

    return report


def compare_benchmarks(
    current: BenchmarkReport,
    previous: Optional[BenchmarkReport] = None,
) -> BenchmarkReport:
    """Add improvement delta to current report by comparing with previous."""
    if previous is not None and previous.total > 0:
        current.improvement_delta = current.accuracy - previous.accuracy
    return current


def save_report(report: BenchmarkReport) -> Path:
    """Persist a benchmark report to disk."""
    filename = f"{report.predicate_name}_{report.timestamp[:10]}.json"
    filepath = BENCHMARK_DIR / filename

    data = {
        "predicate_name": report.predicate_name,
        "total": report.total,
        "correct": report.correct,
        "accuracy": report.accuracy,
        "timestamp": report.timestamp,
        "improvement_delta": report.improvement_delta,
        "results": [
            {
                "scenario_id": r.scenario_id,
                "expected": r.expected,
                "got": r.got,
                "correct": r.correct,
                "latency_ms": r.latency_ms,
            }
            for r in report.results
        ],
    }

    filepath.write_text(json.dumps(data, indent=2))
    return filepath


def load_history(predicate_name: str) -> List[BenchmarkReport]:
    """Load all benchmark reports for a predicate, sorted by timestamp."""
    reports = []
    for p in BENCHMARK_DIR.glob(f"{predicate_name}_*.json"):
        try:
            data = json.loads(p.read_text())
            results = [
                BenchmarkResult(
                    scenario_id=r["scenario_id"],
                    predicate_name=predicate_name,
                    input_data={},
                    expected=r["expected"],
                    got=r["got"],
                    correct=r["correct"],
                    latency_ms=r.get("latency_ms", 0),
                )
                for r in data.get("results", [])
            ]
            report = BenchmarkReport(
                predicate_name=predicate_name,
                total=data["total"],
                correct=data["correct"],
                accuracy=data["accuracy"],
                results=results,
                timestamp=data.get("timestamp", ""),
                improvement_delta=data.get("improvement_delta"),
            )
            reports.append(report)
        except (json.JSONDecodeError, KeyError, OSError):
            continue

    reports.sort(key=lambda r: r.timestamp)
    return reports


def compute_improvement_curve(reports: List[BenchmarkReport]) -> Dict[str, Any]:
    """Compute improvement metrics across multiple benchmark runs.

    Returns:
        Dict with:
            - 'accuracy_trend': list of accuracy values over time
            - 'mean_accuracy': average accuracy across all runs
            - 'std_accuracy': standard deviation of accuracy
            - 'total_runs': number of benchmark runs
            - 'improving': True if latest > first
    """
    if not reports:
        return {
            "accuracy_trend": [],
            "mean_accuracy": 0.0,
            "std_accuracy": 0.0,
            "total_runs": 0,
            "improving": False,
        }

    accuracies = [r.accuracy for r in reports]
    mean_acc = statistics.mean(accuracies)
    std_acc = statistics.stdev(accuracies) if len(accuracies) > 1 else 0.0
    improving = accuracies[-1] > accuracies[0] if len(accuracies) >= 2 else False

    return {
        "accuracy_trend": accuracies,
        "mean_accuracy": mean_acc,
        "std_accuracy": std_acc,
        "total_runs": len(reports),
        "improving": improving,
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _now_ms() -> float:
    import time
    return time.monotonic() * 1000.0


__all__ = [
    "load_scenarios",
    "scenario_to_test_case",
    "run_benchmark",
    "compare_benchmarks",
    "save_report",
    "load_history",
    "compute_improvement_curve",
    "BenchmarkResult",
    "BenchmarkReport",
    "BENCHMARK_DIR",
]
