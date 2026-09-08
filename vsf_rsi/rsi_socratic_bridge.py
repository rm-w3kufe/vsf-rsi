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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("vsf_rsi.socratic_bridge")


def register_rsi_predicate(
    engine,
    name: str,
    func: Callable,
) -> bool:
    """Register a vsf-rsi-generated predicate in socratic-engine.
    
    DEPRECATED: Prefer register_rsi_tree() for new code.
    This function is kept for backward compatibility with existing predicates
    that are actual Python functions (not exec-generated strings).
    
    Args:
        engine: SocraticEngine instance
        name: predicate name (must be unique)
        func: predicate function (must accept _context kwarg)
    
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


# ═══════════════════════════════════════════════════════════════════════════════
# P3: GOVERNANCE — Approval Queue
# ═══════════════════════════════════════════════════════════════════════════════

QUEUE_DIR = Path(os.environ.get(
    "RSI_QUEUE_DIR",
    str(Path(__file__).parent.parent.parent / "state" / "queue")
))


def enqueue_predicate(
    name: str,
    tree: Dict[str, Any],
    source: str = "rsi_pipeline",
    description: str = "",
) -> Path:
    """P3.1: Add a predicate to the approval queue instead of activating directly.
    
    Predicates in queue/ are NOT registered in the engine.
    They require human approval via approve_predicate() before activation.
    
    Args:
        name: Predicate name
        tree: Socratic tree structure
        source: Where this predicate was generated
        description: Human-readable description
    
    Returns:
        Path to queue file
    """
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    
    queue_entry = {
        "name": name,
        "tree": tree,
        "source": source,
        "description": description,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",  # pending → approved → activated | rejected
    }
    
    queue_file = QUEUE_DIR / f"{name}.json"
    queue_file.write_text(json.dumps(queue_entry, indent=2))
    
    logger.info(f"Predicate '{name}' added to approval queue: {queue_file}")
    return queue_file


def approve_predicate(name: str, engine: Any = None) -> bool:
    """P3.1: Approve a predicate from the queue and activate it.
    
    Args:
        name: Predicate name to approve
        engine: Optional SocraticEngine to register immediately
    
    Returns:
        True if approved and activated
    """
    queue_file = QUEUE_DIR / f"{name}.json"
    if not queue_file.exists():
        logger.warning(f"Predicate '{name}' not found in queue")
        return False
    
    entry = json.loads(queue_file.read_text())
    
    if entry["status"] != "pending":
        logger.warning(f"Predicate '{name}' is not pending (status: {entry['status']})")
        return False
    
    # Approve
    entry["status"] = "approved"
    entry["approved_at"] = datetime.now(timezone.utc).isoformat()
    queue_file.write_text(json.dumps(entry, indent=2))
    
    # Register in engine if provided
    if engine is not None:
        register_rsi_tree(engine, name, entry["tree"])
        entry["status"] = "activated"
        entry["activated_at"] = datetime.now(timezone.utc).isoformat()
        queue_file.write_text(json.dumps(entry, indent=2))
        logger.info(f"Predicate '{name}' approved and activated")
    else:
        logger.info(f"Predicate '{name}' approved (no engine provided)")
    
    return True


def reject_predicate(name: str, reason: str = "") -> bool:
    """P3.1: Reject a predicate from the queue."""
    queue_file = QUEUE_DIR / f"{name}.json"
    if not queue_file.exists():
        return False
    
    entry = json.loads(queue_file.read_text())
    entry["status"] = "rejected"
    entry["rejected_at"] = datetime.now(timezone.utc).isoformat()
    entry["rejection_reason"] = reason
    queue_file.write_text(json.dumps(entry, indent=2))
    
    logger.info(f"Predicate '{name}' rejected: {reason}")
    return True


def list_queue(status: str = "pending") -> list:
    """P3.1: List predicates in the approval queue."""
    if not QUEUE_DIR.exists():
        return []
    
    results = []
    for p in QUEUE_DIR.glob("*.json"):
        entry = json.loads(p.read_text())
        if entry.get("status") == status:
            results.append(entry)
    
    return results


def get_queue_stats() -> Dict[str, int]:
    """P3.1: Get queue statistics."""
    if not QUEUE_DIR.exists():
        return {"pending": 0, "approved": 0, "activated": 0, "rejected": 0}
    
    stats = {"pending": 0, "approved": 0, "activated": 0, "rejected": 0}
    for p in QUEUE_DIR.glob("*.json"):
        entry = json.loads(p.read_text())
        status = entry.get("status", "pending")
        if status in stats:
            stats[status] += 1
    
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# P3: GOVERNANCE — Diff Review
# ═══════════════════════════════════════════════════════════════════════════════

def diff_predicate(name: str) -> Optional[Dict[str, Any]]:
    """P3.2: Show diff between current and proposed predicate.
    
    Returns:
        Dict with current_tree, proposed_tree, and changes
    """
    queue_file = QUEUE_DIR / f"{name}.json"
    if not queue_file.exists():
        return None
    
    entry = json.loads(queue_file.read_text())
    proposed_tree = entry.get("tree", {})
    
    # Try to find current tree in state/predicates/
    current_tree = None
    pred_dir = Path(__file__).parent.parent.parent / "state" / "predicates"
    pred_file = pred_dir / f"{name}.json"
    if pred_file.exists():
        current_data = json.loads(pred_file.read_text())
        current_tree = current_data.get("tree")
    
    return {
        "name": name,
        "current_tree": current_tree,
        "proposed_tree": proposed_tree,
        "source": entry.get("source", ""),
        "description": entry.get("description", ""),
        "queued_at": entry.get("queued_at", ""),
        "has_current": current_tree is not None,
    }
    
    return count
