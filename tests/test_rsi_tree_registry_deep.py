"""
Deep tests for rsi_tree_registry.py — covers CLI main() and validate_tree exception.
Targets lines: 170-171, 276-341, 345
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from vsf_rsi.rsi_tree_registry import RSITreeRegistry, main as cli_main


class TestValidateTreeException(TestCase):
    """Cover lines 170-171: validate_tree exception handler."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_tree_registry as mod
        self._original_dir = mod.REGISTRY_DIR
        self._original_file = mod.REGISTRY_FILE
        mod.REGISTRY_DIR = self._tmpdir
        mod.REGISTRY_FILE = self._tmpdir / "registry.json"

    def tearDown(self):
        import vsf_rsi.rsi_tree_registry as mod
        mod.REGISTRY_DIR = self._original_dir
        mod.REGISTRY_FILE = self._original_file

    def test_validate_tree_exception(self):
        """Lines 170-171: validate_tree catches general exceptions."""
        registry = RSITreeRegistry()
        with patch("os.path.exists", side_effect=OSError("permission denied")):
            result = registry.validate_tree("/some/path.vsm")
            self.assertFalse(result["valid"])
            self.assertIn("error", result)


class TestCLIMain(TestCase):
    """Cover lines 276-341, 345: CLI main() function."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_tree_registry as mod
        self._original_dir = mod.REGISTRY_DIR
        self._original_file = mod.REGISTRY_FILE
        self._original_trees_dir = mod.TREES_DIR
        mod.REGISTRY_DIR = self._tmpdir
        mod.REGISTRY_FILE = self._tmpdir / "registry.json"
        mod.TREES_DIR = self._tmpdir / "trees"

    def tearDown(self):
        import vsf_rsi.rsi_tree_registry as mod
        mod.REGISTRY_DIR = self._original_dir
        mod.REGISTRY_FILE = self._original_file
        mod.TREES_DIR = self._original_trees_dir

    def _write_valid_tree(self, name="test_tree"):
        """Helper: write a valid tree file."""
        tree_file = self._tmpdir / f"{name}.vsm"
        tree_file.write_text(
            "⟦ test | SOCRATIC-TREE-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
            "@vsm 1.2\n"
            "@status active\n"
            "test = decision(\n"
            "  TRUE → { home: \"default\", truth: \"default\", certified: TRUE }\n"
            ")\n"
            "⟦ /test ⟧\n"
        )
        return tree_file

    def test_cli_register_success(self):
        """Lines 307-312: register command."""
        tree_file = self._write_valid_tree()
        with patch("sys.argv", ["prog", "register", str(tree_file), "my_pred"]):
            cli_main()
        registry = RSITreeRegistry()
        trees = registry.get_active_trees()
        self.assertEqual(len(trees), 1)

    def test_cli_register_failure(self):
        """Lines 307-312: register with invalid tree."""
        bad_file = self._tmpdir / "bad.vsm"
        bad_file.write_text("nothing valid here")
        with patch("sys.argv", ["prog", "register", str(bad_file), "my_pred"]):
            cli_main()

    def test_cli_validate(self):
        """Lines 313-318: validate command."""
        tree_file = self._write_valid_tree()
        with patch("sys.argv", ["prog", "validate", str(tree_file)]):
            cli_main()

    def test_cli_activate(self):
        """Lines 319-323: activate command."""
        tree_file = self._write_valid_tree()
        registry = RSITreeRegistry()
        registry.register_tree(str(tree_file), "my_pred")
        with patch("sys.argv", ["prog", "activate", str(tree_file)]):
            cli_main()

    def test_cli_activate_not_found(self):
        """Lines 319-323: activate with nonexistent path."""
        with patch("sys.argv", ["prog", "activate", "/nonexistent/path"]):
            cli_main()

    def test_cli_deactivate(self):
        """Lines 324-328: deactivate command."""
        tree_file = self._write_valid_tree()
        registry = RSITreeRegistry()
        registry.register_tree(str(tree_file), "my_pred")
        with patch("sys.argv", ["prog", "deactivate", str(tree_file)]):
            cli_main()

    def test_cli_deactivate_not_found(self):
        """Lines 324-328: deactivate with nonexistent path."""
        with patch("sys.argv", ["prog", "deactivate", "/nonexistent/path"]):
            cli_main()

    def test_cli_list(self):
        """Lines 329-333: list command."""
        tree_file = self._write_valid_tree()
        registry = RSITreeRegistry()
        registry.register_tree(str(tree_file), "my_pred")
        with patch("sys.argv", ["prog", "list"]):
            cli_main()

    def test_cli_stats(self):
        """Lines 334-339: stats command."""
        with patch("sys.argv", ["prog", "stats"]):
            cli_main()

    def test_cli_no_command(self):
        """Lines 340-341: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


if __name__ == "__main__":
    main()
