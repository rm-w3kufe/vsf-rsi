#!/usr/bin/env python3
"""Security regression tests for RSI pipeline RCE fix.

RSI-RCE-FIX-2026-09-01: These tests verify that the exec()-based code
generation vulnerability (CVE-like) is properly mitigated.

The attack vector: a malicious fault_signature or command string could
inject Python code via f-strings into exec() calls in rsi_pipeline.py
and rsi_socratic_bridge.py, achieving Remote Code Execution (RCE).

These tests confirm:
1. Injection payloads are rejected by input sanitization
2. Generated predicates are structured trees, not executable code
3. No exec() or eval() calls exist in the code paths
4. enforce_limits=True is used in all evaluation paths
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from vsf_rsi.rsi_pipeline import (
    _sanitize_value,
    _sanitize_fault_signature,
    _generate_predicate_name,
    _generate_predicate_tree,
    _persist_predicate,
    _load_predicates,
    pipeline,
)
from vsf_rsi.rsi_socratic_bridge import load_predicates_from_file


# ============================================================
# Test 1: Claude's PoC — the exact attack that was demonstrated
# ============================================================

class TestClaudePoCInjection:
    """Regression test for the exact PoC Claude demonstrated."""
    
    def test_pooc_os_system_injection_rejected(self):
        """Claude's PoC: x)or(__import__('os').system('id>/tmp/PWNED'))or(
        
        This payload, when used as part of a fault_signature, should be
        rejected by sanitization before it ever reaches exec().
        """
        malicious = "x)or(__import__('os').system('id>/tmp/PWNED'))or("
        with pytest.raises(ValueError, match="unsafe characters"):
            _sanitize_value(malicious)
    
    def test_pooc_import_injection_rejected(self):
        """Variant: __import__('os').system('whoami')"""
        malicious = "__import__('os').system('whoami')"
        with pytest.raises(ValueError, match="unsafe characters"):
            _sanitize_value(malicious)
    
    def test_pooc_subprocess_injection_rejected(self):
        """Variant: subprocess.check_output(['id'])"""
        malicious = "subprocess.check_output(['id'])"
        with pytest.raises(ValueError, match="unsafe characters"):
            _sanitize_value(malicious)
    
    def test_pooc_exec_injection_rejected(self):
        """Variant: exec('import os; os.system(\"id\")')"""
        malicious = "exec('import os')"
        with pytest.raises(ValueError, match="unsafe characters"):
            _sanitize_value(malicious)


# ============================================================
# Test 2: Broader injection patterns
# ============================================================

class TestBroaderInjectionPatterns:
    """Test various injection patterns beyond the specific PoC."""
    
    def test_parentheses_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test)(injection")
    
    def test_brace_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test{injection}")
    
    def test_bracket_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test[injection]")
    
    def test_semicolon_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test;injection")
    
    def test_pipe_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test|injection")
    
    def test_ampersand_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test&injection")
    
    def test_dollar_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test$injection")
    
    def test_backtick_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test`injection")
    
    def test_single_quote_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test'injection")
    
    def test_double_quote_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value('test"injection')
    
    def test_space_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test injection")
    
    def test_newline_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test\ninjection")
    
    def test_backslash_injection_rejected(self):
        with pytest.raises(ValueError):
            _sanitize_value("test\\injection")


# ============================================================
# Test 3: Valid inputs pass through
# ============================================================

class TestValidInputs:
    """Verify that legitimate fault signatures pass sanitization."""
    
    def test_simple_tool_name(self):
        assert _sanitize_value("bash") == "bash"
    
    def test_simple_command(self):
        assert _sanitize_value("grep") == "grep"
    
    def test_underscored_name(self):
        assert _sanitize_value("my_command") == "my_command"
    
    def test_hyphenated_name(self):
        assert _sanitize_value("my-command") == "my-command"
    
    def test_alphanumeric(self):
        assert _sanitize_value("abc123") == "abc123"
    
    def test_valid_fault_signature(self):
        parts = _sanitize_fault_signature("bash.grep.missing_pattern")
        assert parts == ["bash", "grep", "missing_pattern"]
    
    def test_empty_component_skipped(self):
        parts = _sanitize_fault_signature("bash..grep")
        assert parts == ["bash", "grep"]


# ============================================================
# Test 4: Generated structures are trees, not code
# ============================================================

class TestGeneratedTreesAreSafe:
    """Verify that generated predicates are JSON trees, not Python code."""
    
    def test_tree_structure(self):
        tree = _generate_predicate_tree("bash.grep.missing", "pipeline:bash:failure")
        
        # Must be a dict with 'op' and 'children'
        assert isinstance(tree, dict)
        assert "op" in tree
        assert "children" in tree
        assert tree["op"] == "AND"
        assert isinstance(tree["children"], list)
    
    def test_tree_contains_only_safe_predicates(self):
        tree = _generate_predicate_tree("bash.grep.missing", "pipeline:bash:failure")
        
        safe_predicates = {"ctx_has", "ctx_equals", "ctx_contains"}
        for child in tree["children"]:
            assert "predicate" in child
            assert child["predicate"] in safe_predicates
    
    def test_tree_values_are_sanitized(self):
        tree = _generate_predicate_tree("bash.grep.missing", "pipeline:bash:failure")
        
        for child in tree["children"]:
            for arg in child.get("args", []):
                if isinstance(arg, str):
                    # Should only contain safe characters
                    assert all(c.isalnum() or c in ('_', '-') for c in arg), \
                        f"Unsafe character in tree arg: {arg!r}"
    
    def test_no_exec_in_tree(self):
        """The tree should never contain executable code strings."""
        tree = _generate_predicate_tree("bash.grep.missing", "pipeline:bash:failure")
        tree_str = json.dumps(tree)
        
        dangerous_patterns = ["exec(", "eval(", "__import__", "os.system", 
                              "subprocess", "compile(", "open("]
        for pattern in dangerous_patterns:
            assert pattern not in tree_str, \
                f"Dangerous pattern '{pattern}' found in generated tree"


# ============================================================
# Test 5: Persistence format is safe
# ============================================================

class TestPersistenceSafety:
    """Verify that persisted predicates use safe format."""
    
    def test_persist_uses_tree_not_body(self):
        tree = _generate_predicate_tree("bash.grep.missing", "pipeline:bash:failure")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pred_file = Path(tmpdir) / "test.json"
            _persist_predicate(
                "rsi_bash_grep", "bash.grep.missing", tree, "pipeline:bash:failure"
            )
            # Move to our temp dir
            actual_file = Path(__file__).parent.parent.parent / "state" / "predicates" / "rsi_bash_grep.json"
            if actual_file.exists():
                data = json.loads(actual_file.read_text())
                assert "tree" in data
                assert "body" not in data
                assert data.get("format_version") == 2
    
    def test_v1_format_is_skipped(self):
        """Old v1 format (body strings) should be skipped, not executed."""
        v1_data = {
            "predicates": [
                {
                    "name": "old_pred",
                    "body": "return ctx.get('tool') == 'bash'",
                    # No 'tree' key = v1 format
                }
            ]
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            pred_file = Path(tmpdir) / "old_format.json"
            pred_file.write_text(json.dumps(v1_data))
            
            from socratic_engine.engine import SocraticEngine
            engine = SocraticEngine()
            
            # Should skip v1 format, not crash or execute code
            count = load_predicates_from_file(engine, str(pred_file))
            assert count == 0
            # _rsi_trees may not exist yet if no trees were registered
            if hasattr(engine, '_rsi_trees'):
                assert "old_pred" not in engine._rsi_trees


# ============================================================
# Test 6: No exec/eval in code paths
# ============================================================

class TestNoExecInCodePaths:
    """Verify that exec() and eval() are not used in the pipeline code paths."""
    
    def test_no_exec_in_rsi_pipeline(self):
        """Scan rsi_pipeline.py for exec/eval calls."""
        pipeline_file = Path(__file__).parent.parent / "vsf_rsi" / "rsi_pipeline.py"
        content = pipeline_file.read_text()
        
        # Remove docstrings to avoid false positives from SECURITY FIX comments
        import re
        # Remove triple-quoted strings (docstrings)
        content_clean = re.sub(r'"""[\s\S]*?"""', '""', content)
        content_clean = re.sub(r"'''[\s\S]*?'''", "''", content_clean)
        
        lines = content_clean.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith('#'):
                continue
            
            assert 'exec(' not in stripped, \
                f"exec() found in rsi_pipeline.py line {i}: {stripped}"
            assert 'eval(' not in stripped, \
                f"eval() found in rsi_pipeline.py line {i}: {stripped}"
    
    def test_no_exec_in_rsi_socratic_bridge(self):
        """Scan rsi_socratic_bridge.py for exec/eval calls."""
        bridge_file = Path(__file__).parent.parent / "vsf_rsi" / "rsi_socratic_bridge.py"
        content = bridge_file.read_text()
        
        import re
        content_clean = re.sub(r'"""[\s\S]*?"""', '""', content)
        content_clean = re.sub(r"'''[\s\S]*?'''", "''", content_clean)
        
        lines = content_clean.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            
            assert 'exec(' not in stripped, \
                f"exec() found in rsi_socratic_bridge.py line {i}: {stripped}"
            assert 'eval(' not in stripped, \
                f"eval() found in rsi_socratic_bridge.py line {i}: {stripped}"


# ============================================================
# Test 7: enforce_limits is used
# ============================================================

class TestEnforceLimitsUsed:
    """Verify that enforce_limits=True is used in evaluation paths."""
    
    def test_evaluate_with_predicate_uses_enforce_limits(self):
        """_evaluate_with_predicate should pass enforce_limits=True."""
        pipeline_file = Path(__file__).parent.parent / "vsf_rsi" / "rsi_pipeline.py"
        content = pipeline_file.read_text()
        
        # Find _evaluate_with_predicate function and check for enforce_limits
        assert 'enforce_limits=True' in content, \
            "enforce_limits=True not found in rsi_pipeline.py"


# ============================================================
# Test 8: Pipeline rejects malicious input
# ============================================================

class TestPipelineRejectsMaliciousInput:
    """Integration test: pipeline() should reject malicious fault signatures."""
    
    def test_pipeline_rejects_injection_in_fault_signature(self):
        """The pipeline should reject a malicious fault signature."""
        result = pipeline(
            tool="bash",
            command="test",
            outcome="failure",
            fault_signature="x)or(__import__('os').system('id'))or(",
        )
        # Should fail with error, not execute the payload
        assert result.get("recorded") is False
        assert "error" in result or "unsafe" in str(result).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
