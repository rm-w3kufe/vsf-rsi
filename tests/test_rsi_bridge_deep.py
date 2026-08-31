"""
Deep tests for rsi_bridge.py — covers MCP fallback, filter logic, focus, metrics history.
Targets lines: 44-46, 51-53, 65, 68-69, 83-85, 107-108, 111-112, 117-121,
144-145, 151, 156-157, 162-168, 171-172, 193-194
"""

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch, MagicMock

from vsf_rsi.rsi_bridge import (
    query_canon,
    get_rsi_rules,
    get_rsi_focus,
    feed_metrics_to_canon,
    get_metrics_history,
    _query_local,
)


class TestQueryCanonMCPImport(TestCase):
    """Cover lines 44-46, 51-53: MCP import success and exception paths."""

    def test_query_canon_mcp_success(self):
        """Lines 44-46: MCP import succeeds and returns result."""
        mock_result = {"data": [{"id": 1}], "source": "mcp"}
        mock_state_query = MagicMock(return_value=mock_result)

        with patch.dict("sys.modules", {"state_canon_mcp": MagicMock(state_query=mock_state_query)}):
            result = query_canon("services", {"name": "foo"})
            self.assertEqual(result, mock_result)
            mock_state_query.assert_called_once_with(domain="services", filter={"name": "foo"})

    def test_query_canon_mcp_import_error(self):
        """Lines 51-53: MCP import raises ImportError, falls back to local."""
        with patch.dict("sys.modules", {"state_canon_mcp": None}):
            result = query_canon("services")
            self.assertEqual(result["source"], "local")

    def test_query_canon_mcp_runtime_error(self):
        """Lines 51-53: MCP raises a runtime exception, falls back to local."""
        mock_state_query = MagicMock(side_effect=RuntimeError("MCP down"))
        with patch.dict("sys.modules", {"state_canon_mcp": MagicMock(state_query=mock_state_query)}):
            result = query_canon("services")
            self.assertEqual(result["source"], "local")


class TestQueryLocalFilter(TestCase):
    """Cover lines 65, 68-69: filter logic and error handler in _query_local."""

    def test_query_local_with_list_data_and_filter(self):
        """Line 65: filter applied to list data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_domain.json"
            state_file.write_text(json.dumps([
                {"id": 1, "name": "alpha"},
                {"id": 2, "name": "beta"},
                {"id": 3, "name": "alpha"},
            ]))
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = _query_local("test_domain", {"name": "alpha"})
                self.assertEqual(len(result["data"]), 2)
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_query_local_with_dict_data_and_filter(self):
        """Line 65: filter applied when data is a dict (wrapped in list)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_domain.json"
            state_file.write_text(json.dumps({"id": 1, "name": "alpha"}))
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = _query_local("test_domain", {"name": "alpha"})
                self.assertEqual(len(result["data"]), 1)
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_query_local_filter_no_match(self):
        """Line 65: filter matches nothing returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "test_domain.json"
            state_file.write_text(json.dumps([{"id": 1, "name": "alpha"}]))
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = _query_local("test_domain", {"name": "nope"})
                self.assertEqual(result["data"], [])
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_query_local_corrupt_json(self):
        """Lines 68-69: corrupt JSON triggers error handler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "bad.json"
            state_file.write_text("NOT JSON {{{")
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = _query_local("bad")
                self.assertEqual(result["data"], [])
                self.assertEqual(result["status"], "not_found")
            finally:
                bridge.LOCAL_STATE_DIR = original


class TestGetRSIRulesCanon(TestCase):
    """Cover lines 83-85: get_rsi_rules when canon returns data."""

    def test_get_rsi_rules_from_canon(self):
        """Lines 83-85: rules returned from canon query."""
        mock_result = {"data": {"A0": "custom rule"}}
        with patch("vsf_rsi.rsi_bridge.query_canon", return_value=mock_result):
            rules = get_rsi_rules()
            self.assertEqual(rules, {"A0": "custom rule"})

    def test_get_rsi_rules_canon_empty(self):
        """Lines 83-85: canon returns empty data, falls back to defaults."""
        mock_result = {"data": []}
        with patch("vsf_rsi.rsi_bridge.query_canon", return_value=mock_result):
            rules = get_rsi_rules()
            self.assertIn("A0", rules)

    def test_get_rsi_rules_canon_exception(self):
        """Lines 83-85: canon query raises exception, falls back."""
        with patch("vsf_rsi.rsi_bridge.query_canon", side_effect=Exception("boom")):
            rules = get_rsi_rules()
            self.assertIn("A0", rules)


class TestGetRSIFocus(TestCase):
    """Cover lines 107-108, 111-112, 117-121: MCP focus and local fallback."""

    def test_get_focus_mcp_success(self):
        """Lines 107-108: MCP import succeeds."""
        mock_history = [{"id": 1, "ref": "test"}]
        mock_mod = MagicMock()
        mock_mod.state_journal_history.return_value = mock_history
        with patch.dict("sys.modules", {"state_canon_mcp": mock_mod}):
            result = get_rsi_focus()
            self.assertEqual(result["entries"], mock_history)
            self.assertEqual(result["source"], "state-canon-mcp")

    def test_get_focus_mcp_import_error(self):
        """Lines 111-112: MCP import fails, falls back to local."""
        with patch.dict("sys.modules", {"state_canon_mcp": None}):
            result = get_rsi_focus()
            self.assertIn("entries", result)
            self.assertEqual(result["source"], "local")

    def test_get_focus_mcp_runtime_error(self):
        """Lines 111-112: MCP raises runtime error."""
        mock_mod = MagicMock()
        mock_mod.state_journal_history.side_effect = RuntimeError("down")
        with patch.dict("sys.modules", {"state_canon_mcp": mock_mod}):
            result = get_rsi_focus()
            self.assertEqual(result["source"], "local")

    def test_get_focus_local_file(self):
        """Lines 117-121: reads from local focus file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            focus_file = Path(tmpdir) / "rsi_focus.json"
            focus_file.write_text(json.dumps({"entries": [{"ref": "x"}], "source": "local"}))
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                with patch.dict("sys.modules", {"state_canon_mcp": None}):
                    result = get_rsi_focus()
                    self.assertEqual(len(result["entries"]), 1)
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_get_focus_local_file_corrupt(self):
        """Lines 117-121: corrupt focus file falls through to default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            focus_file = Path(tmpdir) / "rsi_focus.json"
            focus_file.write_text("NOT JSON")
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                with patch.dict("sys.modules", {"state_canon_mcp": None}):
                    result = get_rsi_focus()
                    self.assertEqual(result["entries"], [])
            finally:
                bridge.LOCAL_STATE_DIR = original


class TestFeedMetricsToCanon(TestCase):
    """Cover lines 144-145, 151, 156-157, 162-168, 171-172: history load, trim, write, MCP."""

    def test_feed_metrics_load_existing_corrupt(self):
        """Lines 144-145: corrupt existing history file is handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_file = Path(tmpdir) / "rsi_metrics_history.json"
            metrics_file.write_text("BAD JSON {{{")
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = feed_metrics_to_canon({"key": "val"})
                self.assertEqual(result["status"], "recorded")
                self.assertEqual(result["entry_count"], 1)
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_feed_metrics_trims_history(self):
        """Line 151: history trimmed to 100 entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                # Pre-populate with 101 entries
                metrics_file = Path(tmpdir) / "rsi_metrics_history.json"
                history = [{"i": i} for i in range(101)]
                metrics_file.write_text(json.dumps(history))

                result = feed_metrics_to_canon({"key": "new"})
                self.assertEqual(result["entry_count"], 100)
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_feed_metrics_write_error(self):
        """Lines 156-157: write failure is caught."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                with patch("builtins.open", side_effect=OSError("disk full")):
                    # The function should still return status recorded
                    # because the MCP fallback is tried after the write error
                    # But the write error is caught internally
                    result = feed_metrics_to_canon({"key": "val"})
                    self.assertIn("status", result)
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_feed_metrics_mcp_success(self):
        """Lines 162-168: MCP state_focus_mark succeeds."""
        mock_mod = MagicMock()
        mock_mod.state_focus_mark.return_value = None
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                with patch.dict("sys.modules", {"state_canon_mcp": mock_mod}):
                    result = feed_metrics_to_canon({"key": "val"})
                    self.assertEqual(result["source"], "state-canon-mcp")
                    mock_mod.state_focus_mark.assert_called_once()
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_feed_metrics_mcp_import_error(self):
        """Lines 171-172: MCP import fails, local only."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                with patch.dict("sys.modules", {"state_canon_mcp": None}):
                    result = feed_metrics_to_canon({"key": "val"})
                    self.assertEqual(result["source"], "local")
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_feed_metrics_mcp_runtime_error(self):
        """Lines 171-172: MCP raises runtime error, local fallback."""
        mock_mod = MagicMock()
        mock_mod.state_focus_mark.side_effect = RuntimeError("boom")
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                with patch.dict("sys.modules", {"state_canon_mcp": mock_mod}):
                    result = feed_metrics_to_canon({"key": "val"})
                    self.assertEqual(result["source"], "local")
            finally:
                bridge.LOCAL_STATE_DIR = original


class TestGetMetricsHistory(TestCase):
    """Cover lines 193-194: get_metrics_history exception handling."""

    def test_get_metrics_history_corrupt_file(self):
        """Lines 193-194: corrupt metrics history file returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics_file = Path(tmpdir) / "rsi_metrics_history.json"
            metrics_file.write_text("NOT JSON {{{")
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = get_metrics_history()
                self.assertEqual(result, [])
            finally:
                bridge.LOCAL_STATE_DIR = original

    def test_get_metrics_history_file_not_found(self):
        """Lines 193-194: no file returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import vsf_rsi.rsi_bridge as bridge
            original = bridge.LOCAL_STATE_DIR
            bridge.LOCAL_STATE_DIR = Path(tmpdir)
            try:
                result = get_metrics_history()
                self.assertEqual(result, [])
            finally:
                bridge.LOCAL_STATE_DIR = original


if __name__ == "__main__":
    main()
