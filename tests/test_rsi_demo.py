"""
Tests for rsi_demo.py — Print helper functions only.

The run_complete_demo / main functions import from scripts.vsl.classifier.rsi_*
which may not exist in the test environment, so we only test the pure
print helpers which are self-contained.
"""

import io
import sys
import types
from unittest import TestCase, main


def _import_print_helpers():
    """Import only the print helpers from rsi_demo without triggering
    the scripts.vsl.classifier imports at module level."""
    # Create a stub for the missing scripts.vsl.classifier package
    stub = types.ModuleType("scripts")
    stub.vsl = types.ModuleType("scripts.vsl")
    stub.vsl.classifier = types.ModuleType("scripts.vsl.classifier")
    # Provide minimal stubs for every rsi_* import the demo makes
    for name in (
        "rsi_metrics", "rsi_feedback_loop", "rsi_gap_detector",
        "rsi_tree_generator", "rsi_pattern_detector",
        "rsi_predicate_generator", "rsi_advanced_tree_generator",
        "rsi_genetic_algorithm", "rsi_forest_generator",
    ):
        mod = types.ModuleType(f"scripts.vsl.classifier.{name}")
        mod.RSIMetrics = type("RSIMetrics", (), {"__init__": lambda s: None})
        mod.RSIFeedbackLoop = type("RSIFeedbackLoop", (), {"__init__": lambda s: None})
        mod.RSIGapDetector = type("RSIGapDetector", (), {"__init__": lambda s: None})
        mod.RSITreeGenerator = type("RSITreeGenerator", (), {"__init__": lambda s: None})
        mod.RSIPatternDetector = type("RSIPatternDetector", (), {"__init__": lambda s: None})
        mod.RSIPredicateGenerator = type("RSIPredicateGenerator", (), {"__init__": lambda s: None})
        mod.RSIAdvancedTreeGenerator = type("RSIAdvancedTreeGenerator", (), {"__init__": lambda s: None})
        mod.RSIGeneticAlgorithm = type("RSIGeneticAlgorithm", (), {"__init__": lambda s: None})
        mod.RSIForestGenerator = type("RSIForestGenerator", (), {"__init__": lambda s: None})
        setattr(stub.vsl.classifier, name, mod)
    sys.modules["scripts"] = stub
    sys.modules["scripts.vsl"] = stub.vsl
    sys.modules["scripts.vsl.classifier"] = stub.vsl.classifier
    for name in (
        "rsi_metrics", "rsi_feedback_loop", "rsi_gap_detector",
        "rsi_tree_generator", "rsi_pattern_detector",
        "rsi_predicate_generator", "rsi_advanced_tree_generator",
        "rsi_genetic_algorithm", "rsi_forest_generator",
    ):
        full = f"scripts.vsl.classifier.{name}"
        sys.modules[full] = getattr(stub.vsl.classifier, name)
    from vsf_rsi.rsi_demo import print_header, print_step, print_result, print_footer
    return print_header, print_step, print_result, print_footer


print_header, print_step, print_result, print_footer = _import_print_helpers()


class TestPrintHeader(TestCase):
    """Test print_header function."""

    def test_print_header_no_raise(self):
        """print_header does not raise."""
        try:
            print_header("Test Title")
        except Exception as e:
            self.fail(f"print_header raised: {e}")

    def test_print_header_output(self):
        """print_header outputs title with decorations."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_header("My Title")
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("My Title", output)
        self.assertIn("═", output)


class TestPrintStep(TestCase):
    """Test print_step function."""

    def test_print_step_no_raise(self):
        """print_step does not raise."""
        try:
            print_step(1, "Step Title")
        except Exception as e:
            self.fail(f"print_step raised: {e}")

    def test_print_step_output(self):
        """print_step outputs step number and title."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_step(3, "Build Tree")
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("Step 3", output)
        self.assertIn("Build Tree", output)
        self.assertIn("┌─", output)


class TestPrintResult(TestCase):
    """Test print_result function."""

    def test_print_result_no_raise(self):
        """print_result does not raise with string value."""
        try:
            print_result("label", "value")
        except Exception as e:
            self.fail(f"print_result raised: {e}")

    def test_print_result_float_formatting(self):
        """print_result formats floats with 4 decimals."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_result("Accuracy", 0.12345678)
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("0.1235", output)

    def test_print_result_non_float(self):
        """print_result prints non-float values directly."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_result("Count", 42)
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("42", output)

    def test_print_result_string_value(self):
        """print_result prints string values."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_result("Status", "ok")
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("ok", output)


class TestPrintFooter(TestCase):
    """Test print_footer function."""

    def test_print_footer_no_raise(self):
        """print_footer does not raise."""
        try:
            print_footer()
        except Exception as e:
            self.fail(f"print_footer raised: {e}")

    def test_print_footer_output(self):
        """print_footer outputs footer decoration."""
        captured = io.StringIO()
        sys.stdout = captured
        try:
            print_footer()
        finally:
            sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("└", output)
        self.assertIn("─", output)


if __name__ == "__main__":
    main()
