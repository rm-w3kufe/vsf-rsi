"""
Tests for rsi_demo.py — Print helper functions.
"""

import io
import sys
from unittest import TestCase, main

from vsf_rsi.rsi_demo import print_header, print_step, print_result, print_footer


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
