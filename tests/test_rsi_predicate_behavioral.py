"""
Tests for behavioral predicate validation (RSI-L3-BEHAVIORAL-VALIDATION).

Verifies that validate_predicate_behavior() runs predicates against test
cases and rejects those that produce wrong results.
"""

import pytest
from vsf_rsi.rsi_predicate_generator import RSIPredicateGenerator


# ---------------------------------------------------------------------------
# Basic validation
# ---------------------------------------------------------------------------

class TestBasicValidation:
    """validate_predicate_behavior runs test cases and checks results."""

    def test_all_pass(self):
        """Predicate that matches all expectations passes."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("value", 0) > 0.5
        test_cases = [
            {"input": {"value": 0.8}, "expected": True},
            {"input": {"value": 0.2}, "expected": False},
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        assert result["valid"] is True
        assert result["accuracy"] == 1.0
        assert result["passed"] == 2
        assert result["total"] == 2
        assert result["failures"] == []

    def test_some_fail(self):
        """Predicate that misses some cases has reduced accuracy."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("value", 0) > 0.5
        test_cases = [
            {"input": {"value": 0.8}, "expected": True},   # pass
            {"input": {"value": 0.2}, "expected": False},  # pass
            {"input": {"value": 0.6}, "expected": True},   # pass
            {"input": {"value": 0.4}, "expected": False},  # pass
            {"input": {"value": 0.51}, "expected": True},  # pass
            {"input": {"value": 0.49}, "expected": False}, # pass
            {"input": {"value": 0.7}, "expected": False},  # FAIL
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        assert result["valid"] is True  # 6/7 = 85.7% > 50%
        assert result["accuracy"] == pytest.approx(6 / 7, abs=0.01)
        assert result["passed"] == 6
        assert len(result["failures"]) == 1

    def test_below_threshold_rejected(self):
        """Predicate with accuracy below min_accuracy is rejected."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("value", 0) > 0.5
        test_cases = [
            {"input": {"value": 0.8}, "expected": False},  # FAIL
            {"input": {"value": 0.2}, "expected": False},  # pass
            {"input": {"value": 0.6}, "expected": False},  # FAIL
            {"input": {"value": 0.4}, "expected": False},  # pass
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases, min_accuracy=0.6)
        assert result["valid"] is False
        assert result["accuracy"] == 0.5
        assert "50.0%" in result["warning"]

    def test_no_test_cases_passes_with_warning(self):
        """No test cases = pass with warning (not blocking)."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: True
        result = gen.validate_predicate_behavior("test", pred, None)
        assert result["valid"] is True
        assert result["total"] == 0
        assert "skipped" in result["warning"].lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Handle boundary conditions."""

    def test_exception_in_predicate(self):
        """Predicate that raises exception counts as failure."""
        gen = RSIPredicateGenerator()
        def bad_pred(ctx):
            raise ValueError("boom")
        test_cases = [
            {"input": {"value": 1}, "expected": True},
        ]
        result = gen.validate_predicate_behavior("test", bad_pred, test_cases)
        assert result["valid"] is False
        assert result["passed"] == 0
        assert "EXCEPTION" in str(result["failures"][0]["got"])

    def test_predicate_returns_non_bool(self):
        """Predicate returning non-bool is normalized to bool."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: 1  # truthy
        test_cases = [
            {"input": {}, "expected": True},
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        assert result["valid"] is True
        assert result["passed"] == 1

    def test_predicate_returns_predicate_result(self):
        """PredicateResult is normalized via is_true."""
        from socratic_engine.engine import PredicateResult, Truth
        gen = RSIPredicateGenerator()
        pred = lambda ctx: PredicateResult(truth=Truth.TRUE, certified=True)
        test_cases = [
            {"input": {}, "expected": True},
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        assert result["valid"] is True

    def test_empty_test_list(self):
        """Empty list of test cases passes with warning."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: True
        result = gen.validate_predicate_behavior("test", pred, [])
        assert result["valid"] is True
        assert result["total"] == 0

    def test_min_accuracy_exactly_met(self):
        """Accuracy exactly at threshold passes."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("v", 0) > 0.5
        test_cases = [
            {"input": {"v": 0.8}, "expected": True},
            {"input": {"v": 0.2}, "expected": False},
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases, min_accuracy=1.0)
        assert result["valid"] is True
        assert result["accuracy"] == 1.0

    def test_min_accuracy_exactly_missed(self):
        """Accuracy just below threshold is rejected."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("v", 0) > 0.5
        test_cases = [
            {"input": {"v": 0.8}, "expected": True},   # pass
            {"input": {"v": 0.2}, "expected": False},  # pass
            {"input": {"v": 0.6}, "expected": False},  # FAIL
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases, min_accuracy=0.7)
        assert result["valid"] is False
        assert result["accuracy"] == pytest.approx(2 / 3, abs=0.01)


# ---------------------------------------------------------------------------
# Failure reporting
# ---------------------------------------------------------------------------

class TestFailureReporting:
    """Failures include enough detail for debugging."""

    def test_failure_includes_input(self):
        """Each failure records the input that caused it."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("x") == "wrong"
        test_cases = [
            {"input": {"x": "right"}, "expected": True},
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        assert result["failures"][0]["input"] == {"x": "right"}

    def test_failure_includes_expected_and_got(self):
        """Each failure records expected vs actual."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: False
        test_cases = [
            {"input": {}, "expected": True},
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        f = result["failures"][0]
        assert f["expected"] is True
        assert f["got"] is False

    def test_failure_includes_index(self):
        """Each failure records its position in the test list."""
        gen = RSIPredicateGenerator()
        pred = lambda ctx: ctx.get("pass", False)
        test_cases = [
            {"input": {"pass": True}, "expected": True},   # pass (0)
            {"input": {"pass": False}, "expected": True},   # FAIL (1)
            {"input": {"pass": False}, "expected": True},   # FAIL (2)
        ]
        result = gen.validate_predicate_behavior("test", pred, test_cases)
        indices = [f["index"] for f in result["failures"]]
        assert indices == [1, 2]
