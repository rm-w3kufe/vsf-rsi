"""RSI ↔ Socratic Engine Bridge

Connects vsf-rsi predicate generation to socratic-engine dynamic registration.

SECURITY FIX (2026-09-01): Eliminated exec()-based code generation.
Predicates are now represented as structured condition trees evaluated
by socratic-engine's safe evaluator — never as dynamically generated
Python code. See RSI-RCE-FIX-2026-09-01 IR for details.

Usage:
    from vsf_rsi.rsi_socratic_bridge import register_rsi_predicate, register_rsi_tree

    # Register a generated tree (SAFE)
    register_rsi_tree(engine, 'my_tree', tree_dict)

    # Load predicates from file (SAFE — only v2 tree format)
    load_predicates_from_file(engine, 'state/predicates/my_pred.json')
"""
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("vsf_rsi.socratic_bridge")


def register_rsi_predicate(
    engine,
    name: str,
    func: Callable,
    inject_context: bool = True,
) -> bool:
    """Register a vsf-rsi-generated predicate in socratic-engine.
    
    DEPRECATED: Prefer register_rsi_tree() for new code.
    This function is kept for backward compatibility with existing predicates
    that are actual Python functions (not exec-generated strings).
    
    Args:
        engine: SocraticEngine instance
        name: predicate name (must be unique)
        func: predicate function (must accept _context kwarg)
        inject_context: whether to inject context (default True)
    
    Returns:
        True if registered, False if name already exists
    """
    if name in engine.predicates:
        return False
    
    # Ensure function accepts _context
    import inspect
    try:
        sig = inspect.signature(func)
        if '_context' not in sig.parameters and '**kwargs' not in sig.parameters:
            # Wrap function to accept _context
            original_func = func
            def wrapped(*args, _context=None, **kwargs):
                return original_func(*args, **kwargs)
            wrapped.__name__ = name
            wrapped.__doc__ = f"RSI-generated predicate: {name}"
            func = wrapped
    except (ValueError, TypeError):
        pass  # Can't inspect — let it through, engine will handle
    
    engine.register(name)(func)
    return True


def register_rsi_tree(
    engine,
    name: str,
    tree: Dict[str, Any],
) -> bool:
    """Register a vsf-rsi-generated tree for evaluation.
    
    Trees are stored in engine._rsi_trees and can be retrieved by name.
    This is the SAFE way to register RSI-generated conditions.
    """
    if not hasattr(engine, '_rsi_trees'):
        engine._rsi_trees = {}
    
    if name in engine._rsi_trees:
        return False
    
    engine._rsi_trees[name] = tree
    return True


def get_rsi_tree(engine, name: str) -> Optional[Dict[str, Any]]:
    """Retrieve a registered RSI tree by name."""
    if not hasattr(engine, '_rsi_trees'):
        return None
    return engine._rsi_trees.get(name)


def list_rsi_predicates(engine) -> list:
    """List all RSI-generated predicates registered in the engine."""
    if not hasattr(engine, '_rsi_predicates'):
        return []
    return list(engine._rsi_predicates.keys())


def load_predicates_from_file(engine, path: str) -> int:
    """Load predicates from a JSON file and register them.
    
    SECURITY: Only loads v2 format (structured trees).
    Old v1 format (exec-based code strings) is SKIPPED with a warning.
    
    File format (v2):
    {
        "predicates": [
            {"name": "my_pred", "tree": {"op": "AND", "children": [...]}},
            ...
        ]
    }
    
    Old format (v1 — NO LONGER LOADED):
    {
        "predicates": [
            {"name": "my_pred", "body": "return ctx.get('x', False)"},
            ...
        ]
    }
    
    Returns: number of predicates registered
    """
    p = Path(path)
    if not p.exists():
        return 0
    
    data = json.loads(p.read_text())
    count = 0
    
    for pred in data.get("predicates", []):
        name = pred.get("name")
        tree = pred.get("tree")
        
        if not name:
            continue
        
        # SECURITY: Skip v1 format (old exec-based predicates)
        if not tree:
            logger.warning(
                f"Skipping predicate '{name}' in {path}: "
                f"v1 format (exec-based) no longer supported. "
                f"Delete this file or regenerate with v2 pipeline."
            )
            continue
        
        # Register as a named tree (safe — evaluated by engine, not exec'd)
        if register_rsi_tree(engine, name, tree):
            count += 1
    
    return count


def register_rsi_tree_from_file(
    engine,
    tree_path: str,
    name: Optional[str] = None,
) -> bool:
    """Load a .vsm tree file and register it in socratic-engine.
    
    Parses the VSM file to extract the tree structure and registers
    it for evaluation.
    """
    p = Path(tree_path)
    if not p.exists():
        return False
    
    content = p.read_text()
    
    # Try to extract tree from VSM (look for tree structure)
    # For now, support JSON trees embedded in VSM
    try:
        # Try parsing as pure JSON first
        tree = json.loads(content)
    except json.JSONDecodeError:
        # Try extracting JSON from VSM block
        import re
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            tree = json.loads(json_match.group(1))
        else:
            return False
    
    tree_name = name or p.stem
    return register_rsi_tree(engine, tree_name, tree)


def load_generated_trees(engine, directory: str) -> int:
    """Load all generated trees from a directory."""
    d = Path(directory)
    if not d.exists():
        return 0
    
    count = 0
    for p in d.glob("*.json"):
        if register_rsi_tree_from_file(engine, str(p)):
            count += 1
    
    return count
