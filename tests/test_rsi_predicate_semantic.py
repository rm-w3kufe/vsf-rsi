"""
Tests for context-aware predicate generation (RSI-L3-SEMANTIC).

Verifies that the generator uses pattern data (avg_threshold, avg_input,
error_class) to create predicates with dynamic thresholds instead of
hardcoded values.
"""

import pytest
from vsf_rsi.rsi_predicate_generator import RSIPredicateGenerator


# ---------------------------------------------------------------------------
# Context-aware generation
# ---------------------------------------------------------------------------

class TestContextAwareGeneration:
    """Generator should use pattern data when available."""

    def test_uses_avg_threshold_and_avg_input(self):
        """Pattern with avg_threshold + avg_input produces context-aware predicate."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "test_pred",
            "purpose": "Test predicate",
            "avg_threshold": 0.7,
            "avg_input": 0.65,
            "error_class": "false_negative",
        }
        content = gen._create_predicate_content(pattern, base_predicate="original")
        assert "context_aware" in content
        assert "avg_threshold=0.700" in content
        assert "avg_input=0.650" in content

    def test_false_positive_strategy(self):
        """false_positive error class uses conservative strategy."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "fp_pred",
            "purpose": "False positive recovery",
            "avg_threshold": 0.5,
            "avg_input": 0.6,
            "error_class": "false_positive",
        }
        content = gen._create_predicate_content(pattern, None)
        assert "false_positive recovery" in content
        assert "Clearly above threshold" in content

    def test_false_negative_strategy(self):
        """false_negative error class uses aggressive strategy."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "fn_pred",
            "purpose": "False negative recovery",
            "avg_threshold": 0.5,
            "avg_input": 0.4,
            "error_class": "false_negative",
        }
        content = gen._create_predicate_content(pattern, None)
        assert "false_negative recovery" in content
        assert "Borderline zone" in content

    def test_unknown_error_class_uses_generic(self):
        """Unknown error class uses generic boundary detection."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "unk_pred",
            "purpose": "Unknown error",
            "avg_threshold": 0.5,
            "avg_input": 0.5,
            "error_class": "unknown",
        }
        content = gen._create_predicate_content(pattern, None)
        assert "generic boundary detection" in content

    def test_fallback_to_static_without_pattern_data(self):
        """Pattern without avg_threshold falls back to static template."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "static_pred",
            "purpose": "Static fallback",
            "template": "edge_case_predicate",
        }
        content = gen._create_predicate_content(pattern, None)
        assert "Edge case predicate" in content
        assert "context_aware" not in content

    def test_safety_margin_calculation(self):
        """Thresholds are derived with 10% safety margin."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "margin_pred",
            "purpose": "Margin test",
            "avg_threshold": 0.6,
            "avg_input": 0.55,
            "error_class": "false_negative",
        }
        content = gen._create_predicate_content(pattern, None)
        # low_bound = 0.6 - 0.1 = 0.5, high_bound = 0.6 + 0.1 = 0.7
        assert "0.500" in content  # low_bound
        assert "0.700" in content  # high_bound


# ---------------------------------------------------------------------------
# Edge values
# ---------------------------------------------------------------------------

class TestEdgeValues:
    """Handle boundary conditions in threshold calculation."""

    def test_threshold_at_zero(self):
        """Threshold at 0.0 — low_bound clamped to 0."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "zero_thresh",
            "purpose": "Zero threshold",
            "avg_threshold": 0.0,
            "avg_input": 0.1,
            "error_class": "false_negative",
        }
        content = gen._create_predicate_content(pattern, None)
        assert "0.000" in content  # low_bound clamped

    def test_threshold_at_one(self):
        """Threshold at 1.0 — high_bound clamped to 1."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "one_thresh",
            "purpose": "One threshold",
            "avg_threshold": 1.0,
            "avg_input": 0.9,
            "error_class": "false_positive",
        }
        content = gen._create_predicate_content(pattern, None)
        assert "1.000" in content  # high_bound clamped

    def test_no_value_in_context(self):
        """Generated predicate handles missing 'value' key."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "no_val",
            "purpose": "No value test",
            "avg_threshold": 0.5,
            "avg_input": 0.5,
            "error_class": "unknown",
        }
        content = gen._create_predicate_content(pattern, None)
        assert '"value" not in ctx' in content
        assert "return False" in content


# ---------------------------------------------------------------------------
# Integration with generate_predicate
# ---------------------------------------------------------------------------

class TestGeneratePredicateIntegration:
    """Context-aware generation works through the full pipeline."""

    def test_generate_creates_file(self):
        """generate_predicate creates a context-aware file when pattern has data."""
        gen = RSIPredicateGenerator()
        pattern = {
            "name": "integration_test",
            "purpose": "Integration test",
            "avg_threshold": 0.8,
            "avg_input": 0.75,
            "error_class": "false_negative",
            "template": "edge_case_predicate",  # should be ignored
        }
        filepath = gen.generate_predicate(pattern, base_predicate="test")
        assert filepath.endswith("integration_test.py")

        # Read and verify it's context-aware
        with open(filepath) as f:
            content = f.read()
        assert "context_aware" in content
        assert "avg_threshold=0.800" in content
