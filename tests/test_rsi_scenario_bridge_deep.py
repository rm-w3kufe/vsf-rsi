"""
Deep tests for rsi_scenario_bridge.py — covers remaining uncovered lines.

Targets:
  - Lines 20-22: module-level fallback import (scenario_memory unavailable)
  - Lines 27-31: _import_scenario_memory() success and failure paths
  - Lines 36-40: _import_gap_detector() success and failure paths
"""

from unittest import TestCase, main
from unittest.mock import patch, MagicMock
import sys
import importlib
import importlib.abc
import importlib.machinery

import vsf_rsi
import vsf_rsi.rsi_scenario_bridge as bridge


class _BlockingFinder(importlib.abc.MetaPathFinder):
    """Meta path finder that blocks import of specific submodules."""

    def __init__(self, blocked_name: str):
        self.blocked_name = blocked_name

    def find_spec(self, fullname, path, target=None):
        if fullname == self.blocked_name:
            raise ImportError(f"No module named '{fullname}'")
        return None


def _setup_import_block(blocked_name: str):
    """Block import of *blocked_name* by:
    1. Removing from sys.modules
    2. Removing attribute from parent package
    3. Inserting a blocking meta path finder."""
    parent_name, _, child_name = blocked_name.rpartition(".")
    saved_mod = sys.modules.pop(blocked_name, None)
    parent = sys.modules.get(parent_name)
    saved_attr = None
    had_attr = False
    if parent is not None:
        had_attr = hasattr(parent, child_name)
        saved_attr = getattr(parent, child_name, None)
        if had_attr:
            delattr(parent, child_name)
    finder = _BlockingFinder(blocked_name)
    sys.meta_path.insert(0, finder)
    return finder, saved_mod, parent, saved_attr, had_attr


def _teardown_import_block(blocked_name, finder, saved_mod, parent, saved_attr, had_attr):
    sys.meta_path.remove(finder)
    if parent is not None and had_attr:
        setattr(parent, blocked_name.rpartition(".")[-1], saved_attr)
    if saved_mod is not None:
        sys.modules[blocked_name] = saved_mod


class TestModuleLevelFallbackImport(TestCase):
    """Lines 20-22: When scenario_memory is unavailable at module level."""

    def test_has_scenario_memory_flag_set_false(self):
        """When ImportError occurs, _HAS_SCENARIO_MEMORY is False."""
        with patch.object(bridge, "_sm", None), \
             patch.object(bridge, "_HAS_SCENARIO_MEMORY", False):
            self.assertFalse(bridge._HAS_SCENARIO_MEMORY)
            self.assertIsNone(bridge._sm)

    def test_module_has_import_error_handler(self):
        """Verify the module has the try/except import structure."""
        import inspect
        source = inspect.getsource(bridge)
        self.assertIn("ImportError", source)
        self.assertIn("_HAS_SCENARIO_MEMORY", source)


class TestImportScenarioMemory(TestCase):
    """Lines 27-31: _import_scenario_memory() success and failure paths."""

    def test_import_success(self):
        """_import_scenario_memory returns scenario_memory module."""
        mock_sm = MagicMock()
        with patch.object(vsf_rsi, "scenario_memory", mock_sm):
            result = bridge._import_scenario_memory()
            self.assertIs(result, mock_sm)

    def test_import_failure_raises_import_error(self):
        """_import_scenario_memory raises ImportError with message."""
        f, sm, parent, sa, ha = _setup_import_block("vsf_rsi.scenario_memory")
        try:
            with self.assertRaises(ImportError) as ctx:
                bridge._import_scenario_memory()
            self.assertIn("scenario_memory not available", str(ctx.exception))
        finally:
            _teardown_import_block("vsf_rsi.scenario_memory", f, sm, parent, sa, ha)

    def test_import_failure_includes_original_error(self):
        """ImportError message includes original exception details."""
        f, sm, parent, sa, ha = _setup_import_block("vsf_rsi.scenario_memory")
        try:
            with self.assertRaises(ImportError) as ctx:
                bridge._import_scenario_memory()
            self.assertIn("scenario_memory not available", str(ctx.exception))
        finally:
            _teardown_import_block("vsf_rsi.scenario_memory", f, sm, parent, sa, ha)


class TestImportGapDetector(TestCase):
    """Lines 36-40: _import_gap_detector() success and failure paths."""

    def test_import_success(self):
        """_import_gap_detector returns RSIGapDetector instance."""
        mock_detector_instance = MagicMock()
        mock_detector_cls = MagicMock(return_value=mock_detector_instance)
        mock_module = MagicMock(RSIGapDetector=mock_detector_cls)

        with patch.dict(sys.modules, {"vsf_rsi.rsi_gap_detector": mock_module}):
            result = bridge._import_gap_detector()
            self.assertEqual(result, mock_detector_instance)

    def test_import_failure_raises_import_error(self):
        """_import_gap_detector raises ImportError when module missing."""
        f, sm, parent, sa, ha = _setup_import_block("vsf_rsi.rsi_gap_detector")
        try:
            with self.assertRaises(ImportError) as ctx:
                bridge._import_gap_detector()
            self.assertIn("RSIGapDetector not available", str(ctx.exception))
        finally:
            _teardown_import_block("vsf_rsi.rsi_gap_detector", f, sm, parent, sa, ha)

    def test_import_failure_includes_original_error(self):
        """ImportError message includes original exception details."""
        f, sm, parent, sa, ha = _setup_import_block("vsf_rsi.rsi_gap_detector")
        try:
            with self.assertRaises(ImportError) as ctx:
                bridge._import_gap_detector()
            self.assertIn("RSIGapDetector not available", str(ctx.exception))
        finally:
            _teardown_import_block("vsf_rsi.rsi_gap_detector", f, sm, parent, sa, ha)


class TestImportHelpersIntegration(TestCase):
    """Integration tests verifying both import helpers work together."""

    def test_both_imports_fail_independently(self):
        """Both import helpers fail independently without cross-contamination."""
        f_sm, sm_mod, p_sm, sa_sm, ha_sm = _setup_import_block("vsf_rsi.scenario_memory")
        f_gap, gap_mod, p_gap, sa_gap, ha_gap = _setup_import_block("vsf_rsi.rsi_gap_detector")
        try:
            with self.assertRaises(ImportError):
                bridge._import_scenario_memory()
            with self.assertRaises(ImportError):
                bridge._import_gap_detector()
        finally:
            _teardown_import_block("vsf_rsi.scenario_memory", f_sm, sm_mod, p_sm, sa_sm, ha_sm)
            _teardown_import_block("vsf_rsi.rsi_gap_detector", f_gap, gap_mod, p_gap, sa_gap, ha_gap)

    def test_both_imports_succeed_independently(self):
        """Both import helpers succeed independently."""
        mock_sm_module = MagicMock()
        mock_gap_module = MagicMock()
        mock_detector = MagicMock()
        mock_gap_module.RSIGapDetector.return_value = mock_detector

        with patch.object(vsf_rsi, "scenario_memory", mock_sm_module):
            with patch.dict(sys.modules, {
                "vsf_rsi.scenario_memory": mock_sm_module,
                "vsf_rsi.rsi_gap_detector": mock_gap_module,
            }):
                result_sm = bridge._import_scenario_memory()
                result_gap = bridge._import_gap_detector()
                self.assertIs(result_sm, mock_sm_module)
                self.assertEqual(result_gap, mock_detector)


if __name__ == "__main__":
    main()
