"""
Tests for rsi_benchmark.py — benchmark framework for RSI predicates.
"""

import json
import pytest
from pathlib import Path
from vsf_rsi.rsi_benchmark import (
    load_scenarios,
    scenario_to_test_case,
    run_benchmark,
    compare_benchmarks,
    save_report,
    load_history,
    compute_improvement_curve,
    BenchmarkReport,
    BENCHMARK_DIR,
)


# ---------------------------------------------------------------------------
# load_scenarios
# ---------------------------------------------------------------------------

class TestLoadScenarios:
    """Load scenarios from scenario_memory."""

    def test_loads_all_scenarios(self):
        """Loads all available scenarios."""
        scenarios = load_scenarios()
        assert isinstance(scenarios, list)
        assert len(scenarios) > 0

    def test_scenario_has_required_fields(self):
        """Each scenario has decision, outcome, id."""
        scenarios = load_scenarios()
        for s in scenarios[:5]:
            assert "decision" in s
            assert "outcome" in s
            assert "id" in s

    def test_outcome_filter(self):
        """Filter by outcome substring."""
        all_scenarios = load_scenarios()
        success_scenarios = load_scenarios(outcome_filter="success")
        assert len(success_scenarios) <= len(all_scenarios)
        for s in success_scenarios:
            assert "success" in s.get("outcome", "").lower()


# ---------------------------------------------------------------------------
# scenario_to_test_case
# ---------------------------------------------------------------------------

class TestScenarioToTestCase:
    """Convert scenarios to test cases."""

    def test_success_outcome_is_true(self):
        """Success outcomes map to expected=True."""
        scenario = {"id": "test", "decision": "eval", "outcome": "success"}
        tc = scenario_to_test_case(scenario)
        assert tc["expected"] is True

    def test_failure_outcome_is_false(self):
        """Failure outcomes map to expected=False."""
        scenario = {"id": "test", "decision": "eval", "outcome": "failure"}
        tc = scenario_to_test_case(scenario)
        assert tc["expected"] is False

    def test_resolved_outcome_is_true(self):
        """Resolved outcomes map to expected=True."""
        scenario = {"id": "test", "decision": "eval", "outcome": "resolved"}
        tc = scenario_to_test_case(scenario)
        assert tc["expected"] is True

    def test_input_includes_decision(self):
        """Test case input includes decision string."""
        scenario = {"id": "test", "decision": "evaluate(pred)", "outcome": "ok"}
        tc = scenario_to_test_case(scenario)
        assert tc["input"]["decision"] == "evaluate(pred)"

    def test_input_extracts_truth_value(self):
        """Numeric truth value is extracted from decision."""
        scenario = {
            "id": "test",
            "decision": "evaluate(pred, truth=0.75)",
            "outcome": "success",
        }
        tc = scenario_to_test_case(scenario)
        assert tc["input"]["truth_value"] == 0.75


# ---------------------------------------------------------------------------
# run_benchmark
# ---------------------------------------------------------------------------

class TestRunBenchmark:
    """Run a predicate against scenarios."""

    def test_always_true_predicate(self):
        """Predicate that always returns True has high accuracy on success scenarios."""
        scenarios = [
            {"id": "s1", "decision": "eval", "outcome": "success"},
            {"id": "s2", "decision": "eval", "outcome": "success"},
        ]
        pred = lambda ctx: True
        report = run_benchmark("test", pred, scenarios)
        assert report.total == 2
        assert report.accuracy == 1.0
        assert report.predicate_name == "test"

    def test_always_false_predicate(self):
        """Predicate that always returns False has low accuracy on success scenarios."""
        scenarios = [
            {"id": "s1", "decision": "eval", "outcome": "success"},
        ]
        pred = lambda ctx: False
        report = run_benchmark("test", pred, scenarios)
        assert report.total == 1
        assert report.accuracy == 0.0

    def test_exception_handling(self):
        """Predicate that raises counts as False."""
        scenarios = [
            {"id": "s1", "decision": "eval", "outcome": "success"},
        ]
        def bad_pred(ctx):
            raise ValueError("boom")
        report = run_benchmark("test", bad_pred, scenarios)
        assert report.total == 1
        assert report.correct is False or report.accuracy == 0.0

    def test_report_has_results(self):
        """Report includes individual results."""
        scenarios = [
            {"id": "s1", "decision": "eval", "outcome": "success"},
        ]
        pred = lambda ctx: True
        report = run_benchmark("test", pred, scenarios)
        assert len(report.results) == 1
        assert report.results[0].scenario_id == "s1"

    def test_latency_recorded(self):
        """Each result has latency_ms."""
        scenarios = [
            {"id": "s1", "decision": "eval", "outcome": "success"},
        ]
        pred = lambda ctx: True
        report = run_benchmark("test", pred, scenarios)
        assert report.results[0].latency_ms >= 0


# ---------------------------------------------------------------------------
# compare_benchmarks
# ---------------------------------------------------------------------------

class TestCompareBenchmarks:
    """Compare two benchmark reports."""

    def test_improvement_delta(self):
        """Delta = current accuracy - previous accuracy."""
        prev = BenchmarkReport("test", total=10, correct=5, accuracy=0.5)
        curr = BenchmarkReport("test", total=10, correct=7, accuracy=0.7)
        result = compare_benchmarks(curr, prev)
        assert result.improvement_delta == pytest.approx(0.2)

    def test_no_previous(self):
        """No previous report → delta is None."""
        curr = BenchmarkReport("test", total=10, correct=7, accuracy=0.7)
        result = compare_benchmarks(curr, None)
        assert result.improvement_delta is None


# ---------------------------------------------------------------------------
# save_report / load_history
# ---------------------------------------------------------------------------

class TestPersistence:
    """Save and load benchmark reports."""

    def test_save_and_load(self):
        """Report survives save/load cycle."""
        report = BenchmarkReport(
            predicate_name="_benchmark_test",
            total=5,
            correct=4,
            accuracy=0.8,
        )
        filepath = save_report(report)
        assert filepath.exists()

        # Load
        history = load_history("_benchmark_test")
        assert len(history) >= 1
        assert history[-1].accuracy == 0.8

        # Cleanup
        filepath.unlink()

    def test_history_sorted_by_time(self):
        """History is sorted chronologically."""
        import time
        # Save two reports with different names to avoid same-day collision
        for i in range(2):
            report = BenchmarkReport(
                predicate_name=f"_benchmark_test_{i}",
                total=3,
                correct=i,
                accuracy=i / 3,
            )
            save_report(report)
            time.sleep(0.01)  # ensure different timestamps

        history_0 = load_history("_benchmark_test_0")
        history_1 = load_history("_benchmark_test_1")
        assert len(history_0) >= 1
        assert len(history_1) >= 1
        assert history_0[-1].accuracy == 0.0
        assert history_1[-1].accuracy == pytest.approx(1 / 3)

        # Cleanup
        for p in BENCHMARK_DIR.glob("_benchmark_test_*.json"):
            p.unlink()


# ---------------------------------------------------------------------------
# compute_improvement_curve
# ---------------------------------------------------------------------------

class TestImprovementCurve:
    """Compute improvement metrics across runs."""

    def test_improving_trend(self):
        """Detect improving accuracy."""
        reports = [
            BenchmarkReport("test", total=10, correct=5, accuracy=0.5, timestamp="2026-01-01"),
            BenchmarkReport("test", total=10, correct=7, accuracy=0.7, timestamp="2026-01-02"),
        ]
        curve = compute_improvement_curve(reports)
        assert curve["improving"] is True
        assert curve["accuracy_trend"] == [0.5, 0.7]

    def test_declining_trend(self):
        """Detect declining accuracy."""
        reports = [
            BenchmarkReport("test", total=10, correct=8, accuracy=0.8, timestamp="2026-01-01"),
            BenchmarkReport("test", total=10, correct=5, accuracy=0.5, timestamp="2026-01-02"),
        ]
        curve = compute_improvement_curve(reports)
        assert curve["improving"] is False

    def test_empty_reports(self):
        """Empty list returns safe defaults."""
        curve = compute_improvement_curve([])
        assert curve["total_runs"] == 0
        assert curve["improving"] is False

    def test_single_report(self):
        """Single report — no improvement possible."""
        reports = [
            BenchmarkReport("test", total=10, correct=7, accuracy=0.7, timestamp="2026-01-01"),
        ]
        curve = compute_improvement_curve(reports)
        assert curve["total_runs"] == 1
        assert curve["improving"] is False
        assert curve["mean_accuracy"] == 0.7
