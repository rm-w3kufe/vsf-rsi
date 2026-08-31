"""
Deep tests for rsi_component_registry.py — covers CLI main(), exception handlers, validation.
Targets lines: 122-123, 174, 295-363, 367
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from vsf_rsi.rsi_component_registry import RSIComponentRegistry, main as cli_main


class TestValidateComponentException(TestCase):
    """Cover lines 122-123: validate_component exception handler."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_component_registry as mod
        self._original_dir = mod.REGISTRY_DIR
        self._original_file = mod.REGISTRY_FILE
        mod.REGISTRY_DIR = self._tmpdir
        mod.REGISTRY_FILE = self._tmpdir / "registry.json"

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as mod
        mod.REGISTRY_DIR = self._original_dir
        mod.REGISTRY_FILE = self._original_file

    def test_validate_component_exception(self):
        """Lines 122-123: validate_component catches general exceptions."""
        registry = RSIComponentRegistry()
        # Pass a path that will cause an error (e.g., permission issue simulated)
        with patch("os.path.exists", side_effect=OSError("permission denied")):
            result = registry.validate_component("predicate", "/some/path.py")
            self.assertFalse(result["valid"])
            self.assertIn("error", result)


class TestValidateTreeMissingStatus(TestCase):
    """Cover line 174: _validate_tree missing @status branch."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_component_registry as mod
        self._original_dir = mod.REGISTRY_DIR
        self._original_file = mod.REGISTRY_FILE
        mod.REGISTRY_DIR = self._tmpdir
        mod.REGISTRY_FILE = self._tmpdir / "registry.json"

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as mod
        mod.REGISTRY_DIR = self._original_dir
        mod.REGISTRY_FILE = self._original_file

    def test_validate_tree_missing_status(self):
        """Line 174: tree missing @status returns invalid."""
        registry = RSIComponentRegistry()
        tree_file = self._tmpdir / "bad_tree.vsm"
        tree_file.write_text("⟦ test | TREE-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n@vsm 1.2\ndecision()\n⟦ /test ⟧")
        result = registry.validate_component("tree", str(tree_file))
        self.assertFalse(result["valid"])
        self.assertIn("@status", result["error"])


class TestCLIMain(TestCase):
    """Cover lines 295-363, 367: CLI main() function."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_component_registry as mod
        self._original_dir = mod.REGISTRY_DIR
        self._original_file = mod.REGISTRY_FILE
        mod.REGISTRY_DIR = self._tmpdir
        mod.REGISTRY_FILE = self._tmpdir / "registry.json"

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as mod
        mod.REGISTRY_DIR = self._original_dir
        mod.REGISTRY_FILE = self._original_file

    def _write_valid_predicate(self, name="test_pred"):
        """Helper: write a valid predicate file."""
        pred_file = self._tmpdir / f"{name}.py"
        pred_file.write_text(
            "def my_pred(ctx):\n"
            "    return True\n"
            "\n"
            "PREDICATE = {}\n"
        )
        return pred_file

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
        """Lines 329-334: register command with valid component."""
        pred_file = self._write_valid_predicate()
        with patch("sys.argv", ["prog", "register", "predicate", str(pred_file), "my_pred"]):
            cli_main()
        # Verify component was registered
        registry = RSIComponentRegistry()
        components = registry.get_active_components("predicate")
        self.assertEqual(len(components), 1)

    def test_cli_register_failure(self):
        """Lines 329-334: register command with invalid component."""
        bad_file = self._tmpdir / "bad.py"
        bad_file.write_text("nothing valid here")
        with patch("sys.argv", ["prog", "register", "predicate", str(bad_file), "bad"]):
            cli_main()

    def test_cli_validate(self):
        """Lines 335-340: validate command."""
        pred_file = self._write_valid_predicate()
        with patch("sys.argv", ["prog", "validate", "predicate", str(pred_file)]):
            cli_main()

    def test_cli_activate(self):
        """Lines 341-345: activate command."""
        pred_file = self._write_valid_predicate()
        registry = RSIComponentRegistry()
        registry.register_component("predicate", str(pred_file), "my_pred")
        with patch("sys.argv", ["prog", "activate", str(pred_file)]):
            cli_main()

    def test_cli_activate_not_found(self):
        """Lines 341-345: activate with nonexistent path."""
        with patch("sys.argv", ["prog", "activate", "/nonexistent/path"]):
            cli_main()

    def test_cli_deactivate(self):
        """Lines 346-350: deactivate command."""
        pred_file = self._write_valid_predicate()
        registry = RSIComponentRegistry()
        registry.register_component("predicate", str(pred_file), "my_pred")
        with patch("sys.argv", ["prog", "deactivate", str(pred_file)]):
            cli_main()

    def test_cli_deactivate_not_found(self):
        """Lines 346-350: deactivate with nonexistent path."""
        with patch("sys.argv", ["prog", "deactivate", "/nonexistent/path"]):
            cli_main()

    def test_cli_list(self):
        """Lines 351-355: list command."""
        pred_file = self._write_valid_predicate()
        registry = RSIComponentRegistry()
        registry.register_component("predicate", str(pred_file), "my_pred")
        with patch("sys.argv", ["prog", "list"]):
            cli_main()

    def test_cli_list_with_type(self):
        """Lines 351-355: list command with type filter."""
        with patch("sys.argv", ["prog", "list", "--type", "predicate"]):
            cli_main()

    def test_cli_stats(self):
        """Lines 356-361: stats command."""
        with patch("sys.argv", ["prog", "stats"]):
            cli_main()

    def test_cli_no_command(self):
        """Lines 362-363: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


if __name__ == "__main__":
    main()
