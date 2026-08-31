"""
Tests for rsi_bridge.py — state-canon-mcp integration
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main

from vsf_rsi.rsi_bridge import (
    query_canon,
    get_rsi_rules,
    get_rsi_focus,
    feed_metrics_to_canon,
    get_metrics_history,
    _query_local,
)


class TestRSIBridgeQueryCanon(TestCase):
    """Test query_canon function."""

    def test_query_canon_returns_dict(self):
        """query_canon returns a dictionary."""
        result = query_canon("services")
        self.assertIsInstance(result, dict)

    def test_query_canon_has_domain(self):
        """query_canon includes domain in result."""
        result = query_canon("services")
        self.assertEqual(result["domain"], "services")

    def test_query_canon_with_filter(self):
        """query_canon accepts filter parameter."""
        result = query_canon("services", {"name": "test"})
        self.assertIsInstance(result, dict)

    def test_query_canon_fallback_to_local(self):
        """query_canon falls back to local state when MCP unavailable."""
        result = query_canon("nonexistent_domain")
        self.assertEqual(result["source"], "local")

    def test_query_canon_local_with_data(self):
        """query_canon returns data from local file if exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a local state file
            state_file = Path(tmpdir) / "test_domain.json"
            state_file.write_text(json.dumps([{"id": 1, "name": "test"}]))
            
            # Patch LOCAL_STATE_DIR temporarily
            import vsf_rsi.rsi_bridge as bridge
            original_dir = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            
            try:
                result = _query_local("test_domain")
                self.assertEqual(result["source"], "local")
                self.assertEqual(len(result["data"]), 1)
            finally:
                bridge.LOCAL_STATE_DIR = original_dir


class TestRSIBridgeGetRules(TestCase):
    """Test get_rsi_rules function."""

    def test_get_rsi_rules_returns_dict(self):
        """get_rsi_rules returns a dictionary."""
        rules = get_rsi_rules()
        self.assertIsInstance(rules, dict)

    def test_get_rsi_rules_has_required_keys(self):
        """get_rsi_rules contains required rule IDs."""
        rules = get_rsi_rules()
        required_keys = ["A0", "A5", "D4-L2", "D4-L3", "R17", "R16"]
        for key in required_keys:
            self.assertIn(key, rules)

    def test_get_rsi_rules_values_are_strings(self):
        """get_rsi_rules values are strings."""
        rules = get_rsi_rules()
        for key, value in rules.items():
            self.assertIsInstance(value, str)


class TestRSIBridgeGetFocus(TestCase):
    """Test get_rsi_focus function."""

    def test_get_rsi_focus_returns_dict(self):
        """get_rsi_focus returns a dictionary."""
        focus = get_rsi_focus()
        self.assertIsInstance(focus, dict)

    def test_get_rsi_focus_has_entries(self):
        """get_rsi_focus has entries key."""
        focus = get_rsi_focus()
        self.assertIn("entries", focus)


class TestRSIBridgeFeedMetrics(TestCase):
    """Test feed_metrics_to_canon function."""

    def test_feed_metrics_returns_dict(self):
        """feed_metrics_to_canon returns a dictionary."""
        metrics = {"evaluations": 100, "errors": 5}
        result = feed_metrics_to_canon(metrics)
        self.assertIsInstance(result, dict)

    def test_feed_metrics_has_status(self):
        """feed_metrics_to_canon includes status."""
        metrics = {"evaluations": 100}
        result = feed_metrics_to_canon(metrics)
        self.assertEqual(result["status"], "recorded")

    def test_feed_metrics_saves_locally(self):
        """feed_metrics_to_canon saves metrics locally."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original_dir = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            
            try:
                metrics = {"evaluations": 100, "errors": 5}
                result = feed_metrics_to_canon(metrics)
                
                # Check that file was created
                metrics_file = Path(tmpdir) / "rsi_metrics_history.json"
                self.assertTrue(metrics_file.exists())
                
                # Check content
                with open(metrics_file) as f:
                    history = json.load(f)
                self.assertEqual(len(history), 1)
                self.assertEqual(history[0]["evaluations"], 100)
            finally:
                bridge.LOCAL_STATE_DIR = original_dir

    def test_feed_metrics_appends_to_history(self):
        """feed_metrics_to_canon appends to existing history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original_dir = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            
            try:
                # Feed first metric
                feed_metrics_to_canon({"evaluations": 100})
                
                # Feed second metric
                feed_metrics_to_canon({"evaluations": 200})
                
                # Check history
                metrics_file = Path(tmpdir) / "rsi_metrics_history.json"
                with open(metrics_file) as f:
                    history = json.load(f)
                self.assertEqual(len(history), 2)
            finally:
                bridge.LOCAL_STATE_DIR = original_dir


class TestRSIBridgeGetHistory(TestCase):
    """Test get_metrics_history function."""

    def test_get_metrics_history_returns_list(self):
        """get_metrics_history returns a list."""
        history = get_metrics_history()
        self.assertIsInstance(history, list)

    def test_get_metrics_history_with_limit(self):
        """get_metrics_history respects limit parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original_dir = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            
            try:
                # Create some metrics
                for i in range(5):
                    feed_metrics_to_canon({"evaluations": i * 100})
                
                # Get with limit
                history = get_metrics_history(limit=2)
                self.assertEqual(len(history), 2)
            finally:
                bridge.LOCAL_STATE_DIR = original_dir

    def test_get_metrics_history_empty(self):
        """get_metrics_history returns empty list when no history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original_dir = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            
            try:
                history = get_metrics_history()
                self.assertEqual(len(history), 0)
            finally:
                bridge.LOCAL_STATE_DIR = original_dir


if __name__ == "__main__":
    main()
