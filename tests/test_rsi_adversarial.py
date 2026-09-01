"""
Tests for adversarial benchmark scenarios.

Validates that the scenario generators produce correct ground truth
and that the benchmark framework can evaluate predicates against them.
"""

import pytest
from vsf_rsi.rsi_adversarial import (
    prisoner_dilemma_scenarios,
    parabola_silenciosa_scenarios,
    xor_high_dimension_scenarios,
    signal_in_noise_scenarios,
    always_true_predicate,
    snr_threshold_predicate,
    cooperation_ratio_predicate,
    run_adversarial_benchmark,
)


# ---------------------------------------------------------------------------
# Scenario generators — ground truth correctness
# ---------------------------------------------------------------------------

class TestPrisonerDilemma:
    """Prisoner's Dilemma scenarios have valid structure."""

    def test_generates_correct_count(self):
        scenarios = prisoner_dilemma_scenarios(n=10)
        assert len(scenarios) == 10

    def test_all_have_required_fields(self):
        scenarios = prisoner_dilemma_scenarios(n=5)
        for s in scenarios:
            assert "id" in s
            assert "decision" in s
            assert "outcome" in s
            assert "context" in s
            assert "opponent_moves" in s["context"]
            assert "player_moves" in s["context"]

    def test_outcomes_are_valid(self):
        scenarios = prisoner_dilemma_scenarios(n=20)
        for s in scenarios:
            assert s["outcome"] in ("success", "failure")

    def test_cooperation_ratio_in_context(self):
        scenarios = prisoner_dilemma_scenarios(n=5)
        for s in scenarios:
            ratio = s["context"]["cooperation_ratio"]
            assert 0.0 <= ratio <= 1.0


class TestParabolaSilenciosa:
    """La Parábola Silenciosa scenarios have valid structure."""

    def test_generates_correct_count(self):
        scenarios = parabola_silenciosa_scenarios(n=10)
        assert len(scenarios) == 10

    def test_all_have_required_fields(self):
        scenarios = parabola_silenciosa_scenarios(n=5)
        for s in scenarios:
            assert "id" in s
            assert "context" in s
            assert "x" in s["context"]
            assert "y" in s["context"]
            assert "distance" in s["context"]

    def test_distance_calculation(self):
        """Distance should be non-negative."""
        scenarios = parabola_silenciosa_scenarios(n=10)
        for s in scenarios:
            assert s["context"]["distance"] >= 0

    def test_hidden_params_present(self):
        scenarios = parabola_silenciosa_scenarios(n=3)
        for s in scenarios:
            hp = s["context"]["hidden_params"]
            assert "a" in hp and "b" in hp and "c" in hp


class TestXORHighDimension:
    """XOR de Alta Dimensión scenarios have valid structure."""

    def test_generates_correct_count(self):
        scenarios = xor_high_dimension_scenarios(n=10)
        assert len(scenarios) == 10

    def test_all_have_required_fields(self):
        scenarios = xor_high_dimension_scenarios(n=5)
        for s in scenarios:
            assert "id" in s
            assert "context" in s
            assert "variables" in s["context"]
            assert "true_xor" in s["context"]

    def test_xor_correctness(self):
        """True XOR should match manual calculation."""
        scenarios = xor_high_dimension_scenarios(n=20)
        for s in scenarios:
            variables = s["context"]["variables"]
            expected_xor = 0
            for v in variables.values():
                expected_xor ^= v
            assert s["context"]["true_xor"] == expected_xor

    def test_variables_are_binary(self):
        scenarios = xor_high_dimension_scenarios(n=10)
        for s in scenarios:
            for k, v in s["context"]["variables"].items():
                assert v in (0, 1), f"{k}={v} is not binary"


class TestSignalInNoise:
    """Signal in Noise scenarios have valid structure."""

    def test_generates_correct_count(self):
        scenarios = signal_in_noise_scenarios(n=10)
        assert len(scenarios) == 10

    def test_snr_in_context(self):
        scenarios = signal_in_noise_scenarios(n=5)
        for s in scenarios:
            assert "snr" in s["context"]
            assert s["context"]["snr"] >= 0

    def test_signal_detection_matches_snr(self):
        """Outcome matches SNR > 1 threshold."""
        scenarios = signal_in_noise_scenarios(n=20)
        for s in scenarios:
            snr = s["context"]["snr"]
            if snr > 1.0:
                assert s["outcome"] == "success", f"SNR={snr} should be success"
            else:
                assert s["outcome"] == "failure", f"SNR={snr} should be failure"


# ---------------------------------------------------------------------------
# Predicates against adversarial scenarios
# ---------------------------------------------------------------------------

class TestPredicatesAgainstAdversarial:
    """Evaluate predicates against adversarial scenarios."""

    def test_always_true_on_prisoner(self):
        """Always-True gets ~50% on prisoner (depends on distribution)."""
        from vsf_rsi.rsi_benchmark import run_benchmark
        scenarios = prisoner_dilemma_scenarios(n=20)
        report = run_benchmark("always_true", always_true_predicate, scenarios)
        # Always True should get some right (the success ones)
        assert 0.0 <= report.accuracy <= 1.0

    def test_snr_predicate_on_noise(self):
        """SNR threshold predicate should do well on noise scenarios."""
        from vsf_rsi.rsi_benchmark import run_benchmark
        scenarios = signal_in_noise_scenarios(n=30)
        report = run_benchmark("snr_threshold", snr_threshold_predicate, scenarios)
        # Should be reasonably accurate
        assert report.accuracy > 0.5

    def test_cooperation_predicate_on_prisoner(self):
        """Cooperation ratio predicate should do well on prisoner."""
        from vsf_rsi.rsi_benchmark import run_benchmark
        scenarios = prisoner_dilemma_scenarios(n=30)
        report = run_benchmark("coop_ratio", cooperation_ratio_predicate, scenarios)
        assert report.accuracy > 0.5


# ---------------------------------------------------------------------------
# Full adversarial benchmark suite
# ---------------------------------------------------------------------------

class TestAdversarialBenchmarkSuite:
    """Run the full adversarial benchmark suite."""

    def test_run_all_types(self):
        """Can run all scenario types."""
        results = run_adversarial_benchmark(
            "test_pred", always_true_predicate, scenario_type="all", n_per_type=10
        )
        assert "prisoner" in results
        assert "parabola" in results
        assert "xor" in results
        assert "noise" in results
        assert "overall" in results

    def test_run_single_type(self):
        """Can run a single scenario type."""
        results = run_adversarial_benchmark(
            "test_pred", always_true_predicate, scenario_type="xor", n_per_type=10
        )
        assert "xor" in results
        assert "overall" in results
        assert len(results) == 2  # only xor + overall

    def test_overall_is_aggregate(self):
        """Overall accuracy is aggregate of all types."""
        results = run_adversarial_benchmark(
            "test_pred", always_true_predicate, scenario_type="all", n_per_type=10
        )
        total_correct = sum(
            results[t]["correct"] for t in ["prisoner", "parabola", "xor", "noise"]
        )
        total_all = sum(
            results[t]["total"] for t in ["prisoner", "parabola", "xor", "noise"]
        )
        assert results["overall"]["total"] == total_all
        assert results["overall"]["correct"] == total_correct
