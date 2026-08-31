"""
Tests for rsi_component_registry.py — Component registry
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase, main

from vsf_rsi.rsi_component_registry import RSIComponentRegistry


class TestRSIComponentRegistryInit(TestCase):
    """Test RSIComponentRegistry initialization."""

    def test_init_default(self):
        """RSIComponentRegistry can be initialized."""
        registry = RSIComponentRegistry()
        self.assertIsNotNone(registry)

    def test_init_creates_registry_dir(self):
        """RSIComponentRegistry creates registry directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_component_registry as module
            original_dir = module.REGISTRY_DIR
            module.REGISTRY_DIR = Path(tmpdir)
            try:
                registry = RSIComponentRegistry()
                self.assertTrue(Path(tmpdir).exists())
            finally:
                module.REGISTRY_DIR = original_dir


class TestRSIComponentRegistryRegister(TestCase):
    """Test register_component method."""

    def setUp(self):
        import vsf_rsi.rsi_component_registry as module
        self._original_dir = module.REGISTRY_DIR
        self._original_file = module.REGISTRY_FILE
        self._tmpdir = Path(tempfile.mkdtemp())
        module.REGISTRY_DIR = self._tmpdir
        module.REGISTRY_FILE = self._tmpdir / "rsi_component_registry.json"
        self.registry = RSIComponentRegistry()
        # Clear any existing registry
        if module.REGISTRY_FILE.exists():
            module.REGISTRY_FILE.unlink()

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as module
        module.REGISTRY_DIR = self._original_dir
        module.REGISTRY_FILE = self._original_file

    def test_register_component_predicate(self):
        """register_component registers a predicate."""
        # Create a valid predicate file
        predicate_file = self._tmpdir / "test_pred.py"
        predicate_file.write_text(
            "def test_predicate():\n"
            "    return True\n"
            "PREDICATE = {}\n"
        )
        result = self.registry.register_component(
            "predicate", str(predicate_file), "test_pred"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["component"]["name"], "test_pred")
        self.assertEqual(result["component"]["type"], "predicate")

    def test_register_component_tree(self):
        """register_component registers a tree."""
        tree_file = self._tmpdir / "test_tree.vsm"
        tree_file.write_text(
            "⟦ test_tree | TREE-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
            "@vsm 1.2\n"
            "@status active\n"
            "decision(test) = {}\n"
            "⟦ /test_tree | TREE-v1 | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
        )
        result = self.registry.register_component(
            "tree", str(tree_file), "test_tree"
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["component"]["name"], "test_tree")

    def test_register_component_with_metadata(self):
        """register_component stores metadata."""
        predicate_file = self._tmpdir / "test_pred.py"
        predicate_file.write_text(
            "def test():\n    return True\nPREDICATE = {}\n"
        )
        metadata = {"source": "auto", "version": 1}
        result = self.registry.register_component(
            "predicate", str(predicate_file), "test_pred", metadata
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["component"]["metadata"]["source"], "auto")

    def test_register_component_validation_fails(self):
        """register_component returns error on invalid component."""
        predicate_file = self._tmpdir / "bad_pred.py"
        predicate_file.write_text("x = 1\n")
        result = self.registry.register_component(
            "predicate", str(predicate_file), "bad_pred"
        )
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    def test_register_component_duplicate(self):
        """register_component rejects duplicate registration."""
        predicate_file = self._tmpdir / "test_pred.py"
        predicate_file.write_text(
            "def test():\n    return True\nPREDICATE = {}\n"
        )
        result1 = self.registry.register_component(
            "predicate", str(predicate_file), "test_pred"
        )
        self.assertTrue(result1["success"])
        result2 = self.registry.register_component(
            "predicate", str(predicate_file), "test_pred"
        )
        self.assertFalse(result2["success"])
        self.assertIn("already registered", result2["error"])


class TestRSIComponentRegistryValidate(TestCase):
    """Test validate_component method."""

    def setUp(self):
        import vsf_rsi.rsi_component_registry as module
        self._original_dir = module.REGISTRY_DIR
        self._tmpdir = Path(tempfile.mkdtemp())
        module.REGISTRY_DIR = self._tmpdir
        self.registry = RSIComponentRegistry()

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as module
        module.REGISTRY_DIR = self._original_dir

    def test_validate_predicate_valid(self):
        """validate_component accepts valid predicate."""
        f = self._tmpdir / "good.py"
        f.write_text("def test():\n    return True\nPREDICATE = {}\n")
        result = self.registry.validate_component("predicate", str(f))
        self.assertTrue(result["valid"])

    def test_validate_predicate_missing_def(self):
        """validate_component rejects predicate without def."""
        f = self._tmpdir / "bad.py"
        f.write_text("return True\nPREDICATE = {}\n")
        result = self.registry.validate_component("predicate", str(f))
        self.assertFalse(result["valid"])
        self.assertIn("function definition", result["error"])

    def test_validate_predicate_missing_return(self):
        """validate_component rejects predicate without return."""
        f = self._tmpdir / "bad.py"
        f.write_text("def test():\n    x = 1\nPREDICATE = {}\n")
        result = self.registry.validate_component("predicate", str(f))
        self.assertFalse(result["valid"])
        self.assertIn("return statement", result["error"])

    def test_validate_predicate_missing_predicate_reg(self):
        """validate_component rejects predicate without PREDICATE."""
        f = self._tmpdir / "bad.py"
        f.write_text("def test():\n    return True\n")
        result = self.registry.validate_component("predicate", str(f))
        self.assertFalse(result["valid"])
        self.assertIn("PREDICATE", result["error"])

    def test_validate_tree_valid(self):
        """validate_component accepts valid tree."""
        f = self._tmpdir / "good.vsm"
        f.write_text(
            "⟦ t | TREE | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
            "@vsm 1.2\n@status active\ndecision(x) = {}\n"
            "⟦ /t | TREE | vsm-1.2 | 2026-01-01T00:00:00Z ⟧\n"
        )
        result = self.registry.validate_component("tree", str(f))
        self.assertTrue(result["valid"])

    def test_validate_tree_missing_vsm_header(self):
        """validate_component rejects tree without VSM brackets."""
        f = self._tmpdir / "bad.vsm"
        f.write_text("@vsm 1.2\n@status active\ndecision(x) = {}\n")
        result = self.registry.validate_component("tree", str(f))
        self.assertFalse(result["valid"])
        self.assertIn("VSM header/footer", result["error"])

    def test_validate_tree_missing_vsm_version(self):
        """validate_component rejects tree without @vsm 1.2."""
        f = self._tmpdir / "bad.vsm"
        f.write_text("⟦ t ⟧\n@status active\ndecision(x) = {}\n⟦ /t ⟧\n")
        result = self.registry.validate_component("tree", str(f))
        self.assertFalse(result["valid"])
        self.assertIn("@vsm 1.2", result["error"])

    def test_validate_tree_missing_decision(self):
        """validate_component rejects tree without decision()."""
        f = self._tmpdir / "bad.vsm"
        f.write_text("⟦ t ⟧\n@vsm 1.2\n@status active\n⟦ /t ⟧\n")
        result = self.registry.validate_component("tree", str(f))
        self.assertFalse(result["valid"])
        self.assertIn("decision()", result["error"])

    def test_validate_file_not_found(self):
        """validate_component returns error for missing file."""
        result = self.registry.validate_component("predicate", "/no/such/file")
        self.assertFalse(result["valid"])
        self.assertIn("not found", result["error"])

    def test_validate_unknown_type(self):
        """validate_component accepts unknown type."""
        f = self._tmpdir / "x.py"
        f.write_text("x = 1\n")
        result = self.registry.validate_component("unknown", str(f))
        self.assertTrue(result["valid"])


class TestRSIComponentRegistryActivateDeactivate(TestCase):
    """Test activate_component and deactivate_component methods."""

    def setUp(self):
        import vsf_rsi.rsi_component_registry as module
        self._original_dir = module.REGISTRY_DIR
        self._original_file = module.REGISTRY_FILE
        self._tmpdir = Path(tempfile.mkdtemp())
        module.REGISTRY_DIR = self._tmpdir
        module.REGISTRY_FILE = self._tmpdir / "rsi_component_registry.json"
        self.registry = RSIComponentRegistry()
        if module.REGISTRY_FILE.exists():
            module.REGISTRY_FILE.unlink()
        # Register a valid component
        f = self._tmpdir / "pred.py"
        f.write_text("def test():\n    return True\nPREDICATE = {}\n")
        self.registry.register_component("predicate", str(f), "test_pred")
        self.component_path = str(f)

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as module
        module.REGISTRY_DIR = self._original_dir
        module.REGISTRY_FILE = self._original_file

    def test_activate_component(self):
        """activate_component sets status to active."""
        # Deactivate first
        self.registry.deactivate_component(self.component_path)
        result = self.registry.activate_component(self.component_path)
        self.assertTrue(result)
        components = self.registry.get_active_components()
        self.assertEqual(len(components), 1)

    def test_deactivate_component(self):
        """deactivate_component sets status to inactive."""
        result = self.registry.deactivate_component(self.component_path)
        self.assertTrue(result)
        components = self.registry.get_active_components()
        self.assertEqual(len(components), 0)

    def test_activate_nonexistent(self):
        """activate_component returns False for unknown path."""
        result = self.registry.activate_component("/no/such/path")
        self.assertFalse(result)

    def test_deactivate_nonexistent(self):
        """deactivate_component returns False for unknown path."""
        result = self.registry.deactivate_component("/no/such/path")
        self.assertFalse(result)


class TestRSIComponentRegistryQueries(TestCase):
    """Test get_active_components, get_components_by_name, get_registry_stats."""

    def setUp(self):
        import vsf_rsi.rsi_component_registry as module
        self._original_dir = module.REGISTRY_DIR
        self._original_file = module.REGISTRY_FILE
        self._tmpdir = Path(tempfile.mkdtemp())
        module.REGISTRY_DIR = self._tmpdir
        module.REGISTRY_FILE = self._tmpdir / "rsi_component_registry.json"
        self.registry = RSIComponentRegistry()
        if module.REGISTRY_FILE.exists():
            module.REGISTRY_FILE.unlink()
        # Register two components
        f1 = self._tmpdir / "a.py"
        f1.write_text("def a():\n    return True\nPREDICATE = {}\n")
        f2 = self._tmpdir / "a.vsm"
        f2.write_text(
            "⟦ t ⟧\n@vsm 1.2\n@status active\ndecision(x) = {}\n⟦ /t ⟧\n"
        )
        self.registry.register_component("predicate", str(f1), "alpha")
        self.registry.register_component("tree", str(f2), "alpha")
        self._path_a = str(f1)
        self._path_b = str(f2)

    def tearDown(self):
        import vsf_rsi.rsi_component_registry as module
        module.REGISTRY_DIR = self._original_dir
        module.REGISTRY_FILE = self._original_file

    def test_get_active_components_all(self):
        """get_active_components returns all active."""
        active = self.registry.get_active_components()
        self.assertEqual(len(active), 2)

    def test_get_active_components_by_type(self):
        """get_active_components filters by type."""
        preds = self.registry.get_active_components("predicate")
        self.assertEqual(len(preds), 1)
        self.assertEqual(preds[0]["type"], "predicate")

    def test_get_active_components_after_deactivate(self):
        """get_active_components excludes inactive."""
        self.registry.deactivate_component(self._path_a)
        active = self.registry.get_active_components()
        self.assertEqual(len(active), 1)

    def test_get_components_by_name(self):
        """get_components_by_name returns matching components."""
        results = self.registry.get_components_by_name("alpha")
        self.assertEqual(len(results), 2)

    def test_get_components_by_name_no_match(self):
        """get_components_by_name returns empty list for no match."""
        results = self.registry.get_components_by_name("nonexistent")
        self.assertEqual(len(results), 0)

    def test_get_registry_stats(self):
        """get_registry_stats returns correct counts."""
        stats = self.registry.get_registry_stats()
        self.assertEqual(stats["total_components"], 2)
        self.assertEqual(stats["active_components"], 2)
        self.assertEqual(stats["inactive_components"], 0)
        self.assertIn("predicate", stats["by_type"])
        self.assertEqual(stats["by_type"]["predicate"], 1)
        self.assertEqual(stats["by_type"]["tree"], 1)

    def test_get_registry_stats_after_deactivate(self):
        """get_registry_stats counts inactive correctly."""
        self.registry.deactivate_component(self._path_a)
        stats = self.registry.get_registry_stats()
        self.assertEqual(stats["active_components"], 1)
        self.assertEqual(stats["inactive_components"], 1)

    def test_get_registry_stats_recent(self):
        """get_registry_stats includes recent registrations."""
        stats = self.registry.get_registry_stats()
        self.assertLessEqual(len(stats["recent_registrations"]), 5)


if __name__ == "__main__":
    main()
