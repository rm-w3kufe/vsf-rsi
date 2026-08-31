"""
Deep tests for rsi_predicate_generator.py — covers all templates, validation, CLI.
Targets lines: 56, 86-89, 100-103, 158, 194, 253, 259, 267-268, 274-305, 309
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

from vsf_rsi.rsi_predicate_generator import RSIPredicateGenerator, main as cli_main


class TestGeneratePredicateValueError(TestCase):
    """Cover line 56: ValueError when generated code is invalid."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_predicate_generator as mod
        self._original_dir = mod.GENERATED_DIR
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import vsf_rsi.rsi_predicate_generator as mod
        mod.GENERATED_DIR = self._original_dir

    def test_generate_invalid_code_raises_value_error(self):
        """Line 56: invalid generated code raises ValueError."""
        gen = RSIPredicateGenerator()
        # Force _validate_code to return invalid by patching
        with patch.object(gen, "_validate_code", return_value={"valid": False, "error": "bad code"}):
            with self.assertRaises(ValueError) as ctx:
                gen.generate_predicate({"name": "bad_pred"})
            self.assertIn("invalid", str(ctx.exception))


class TestValidateCode(TestCase):
    """Cover lines 86-89: _validate_code exception paths."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_predicate_generator as mod
        self._original_dir = mod.GENERATED_DIR
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import vsf_rsi.rsi_predicate_generator as mod
        mod.GENERATED_DIR = self._original_dir

    def test_validate_code_valid(self):
        """Valid Python code returns valid."""
        gen = RSIPredicateGenerator()
        result = gen._validate_code("def foo(): return True")
        self.assertTrue(result["valid"])
        self.assertIsNone(result["error"])

    def test_validate_code_syntax_error(self):
        """Lines 86-87: SyntaxError returns invalid."""
        gen = RSIPredicateGenerator()
        result = gen._validate_code("def foo(oops missing parens:")
        self.assertFalse(result["valid"])
        self.assertIn("Syntax error", result["error"])

    def test_validate_code_general_exception(self):
        """Lines 88-89: general exception returns invalid."""
        gen = RSIPredicateGenerator()
        with patch("ast.parse", side_effect=RuntimeError("unexpected")):
            result = gen._validate_code("anything")
            self.assertFalse(result["valid"])
            self.assertIn("Validation error", result["error"])


class TestCreatePredicateContent(TestCase):
    """Cover lines 100-103: _create_predicate_content template routing."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_predicate_generator as mod
        self._original_dir = mod.GENERATED_DIR
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import vsf_rsi.rsi_predicate_generator as mod
        mod.GENERATED_DIR = self._original_dir

    def test_edge_case_template(self):
        """Lines 98-99: edge_case_predicate template."""
        gen = RSIPredicateGenerator()
        content = gen._create_predicate_content(
            {"name": "edge_pred", "purpose": "edge test", "template": "edge_case_predicate"}, None
        )
        self.assertIn("Edge case predicate", content)
        self.assertIn("def edge_pred(", content)
        self.assertIn("PREDICATE", content)

    def test_fast_template(self):
        """Lines 100-101: fast_predicate template."""
        gen = RSIPredicateGenerator()
        content = gen._create_predicate_content(
            {"name": "fast_pred", "purpose": "fast test", "template": "fast_predicate"}, None
        )
        self.assertIn("Fast execution predicate", content)
        self.assertIn("def fast_pred(", content)

    def test_generic_template(self):
        """Lines 102-103: generic predicate template (default)."""
        gen = RSIPredicateGenerator()
        content = gen._create_predicate_content(
            {"name": "generic_pred", "purpose": "generic test"}, None
        )
        self.assertIn("Auto-generated predicate", content)
        self.assertIn("def generic_pred(", content)

    def test_no_template_defaults_to_generic(self):
        """Lines 102-103: no template key defaults to generic."""
        gen = RSIPredicateGenerator()
        content = gen._create_predicate_content(
            {"name": "no_template_pred", "purpose": "test"}, None
        )
        self.assertIn("Auto-generated predicate", content)


class TestManifestIO(TestCase):
    """Cover lines 253, 259: manifest load/save edge cases."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_load_manifest_with_file(self):
        """Line 253: _load_manifest reads from existing file."""
        import vsf_rsi.rsi_predicate_generator as mod
        original_manifest = mod.MANIFEST_FILE
        manifest_file = self._tmpdir / "rsi_generated_predicates.vsm"
        mod.MANIFEST_FILE = manifest_file
        try:
            gen = RSIPredicateGenerator()
            manifest_file.write_text(
                "⟦ rsi_generated_predicates | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
                "@vsm 1.2\n"
                "@status active\n"
                "predicates = [\n"
                '  { name: "test", path: "/tmp/test.py" },\n'
                "]\n"
                "⟦ /rsi_generated_predicates ⟧\n"
            )
            result = gen._load_manifest()
            self.assertIn("predicates", result)
        finally:
            mod.MANIFEST_FILE = original_manifest

    def test_save_manifest_dir_missing(self):
        """Line 259: _save_manifest skips when parent dir doesn't exist."""
        import vsf_rsi.rsi_predicate_generator as mod
        original_manifest = mod.MANIFEST_FILE
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent_dir" / "file.vsm"
        try:
            gen = RSIPredicateGenerator()
            # Should not raise, just silently skip
            gen._save_manifest({"predicates": []})
        finally:
            mod.MANIFEST_FILE = original_manifest


class TestGetGeneratedPredicates(TestCase):
    """Cover lines 267-268: get_generated_predicates."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())

    def test_get_generated_predicates(self):
        """Lines 267-268: returns predicates from manifest."""
        import vsf_rsi.rsi_predicate_generator as mod
        original_manifest = mod.MANIFEST_FILE
        manifest_file = self._tmpdir / "rsi_generated_predicates.vsm"
        mod.MANIFEST_FILE = manifest_file
        try:
            manifest_file.write_text(
                "⟦ rsi_generated_predicates | MANIFEST-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
                "@vsm 1.2\n"
                "@status active\n"
                "predicates = [\n"
                '  { name: "p1", path: "/tmp/p1.py" },\n'
                '  { name: "p2", path: "/tmp/p2.py" },\n'
                "]\n"
                "⟦ /rsi_generated_predicates ⟧\n"
            )
            gen = RSIPredicateGenerator()
            result = gen.get_generated_predicates()
            self.assertEqual(len(result), 2)
        finally:
            mod.MANIFEST_FILE = original_manifest

    def test_get_generated_predicates_empty(self):
        """Lines 267-268: empty manifest returns empty list."""
        import vsf_rsi.rsi_predicate_generator as mod
        original_manifest = mod.MANIFEST_FILE
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"
        try:
            gen = RSIPredicateGenerator()
            result = gen.get_generated_predicates()
            self.assertEqual(result, [])
        finally:
            mod.MANIFEST_FILE = original_manifest


class TestCLIMain(TestCase):
    """Cover lines 274-305, 309: CLI main() function."""

    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp())
        import vsf_rsi.rsi_predicate_generator as mod
        self._original_dir = mod.GENERATED_DIR
        self._original_manifest = mod.MANIFEST_FILE
        mod.GENERATED_DIR = self._tmpdir / "generated"
        mod.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        mod.MANIFEST_FILE = self._tmpdir / "nonexistent.vsm"

    def tearDown(self):
        import vsf_rsi.rsi_predicate_generator as mod
        mod.GENERATED_DIR = self._original_dir
        mod.MANIFEST_FILE = self._original_manifest

    def test_cli_generate_generic(self):
        """Lines 291-298: generate with generic template."""
        with patch("sys.argv", ["prog", "generate", "my_pred", "--template", "generic"]):
            cli_main()
        gen = RSIPredicateGenerator()
        predicates = gen.get_generated_predicates()
        self.assertEqual(len(predicates), 1)

    def test_cli_generate_edge_case(self):
        """Lines 291-298: generate with edge_case template."""
        with patch("sys.argv", ["prog", "generate", "edge_pred", "--template", "edge_case"]):
            cli_main()

    def test_cli_generate_fast(self):
        """Lines 291-298: generate with fast template."""
        with patch("sys.argv", ["prog", "generate", "fast_pred", "--template", "fast"]):
            cli_main()

    def test_cli_list(self):
        """Lines 299-303: list command."""
        with patch("sys.argv", ["prog", "list"]):
            cli_main()

    def test_cli_no_command(self):
        """Lines 304-305: no command prints help."""
        with patch("sys.argv", ["prog"]):
            cli_main()


if __name__ == "__main__":
    main()
