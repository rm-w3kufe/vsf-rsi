#!/usr/bin/env python3
"""RSI Pipeline — Orchestrates the full evolution cycle.

Flow:
    action → record → learn → generate → register → evaluate

SECURITY FIX (2026-09-01): Eliminated exec()-based code generation.
Predicates are now represented as structured condition trees evaluated
by socratic-engine's safe evaluator — never as dynamically generated
Python code. See RSI-RCE-FIX-2026-09-01 IR for details.

Usage:
    from vsf_rsi.rsi_pipeline import pipeline

    # Simple: just record an action
    result = pipeline("bash", "grep 'missing' file.py", "failure")

    # With context for evaluation
    result = pipeline(
        "bash", "grep 'missing' file.py", "failure",
        context={"tool": "bash", "command": "grep 'missing' file.py", "outcome": "failure"}
    )

    # Check if any patterns were learned
    if result.get("predicate_registered"):
        print(f"New predicate: {result['predicate_name']}")
"""
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from vsf_rsi.scenario_memory import record, adapt, learn

# Directory for persisted predicates
PREDICATES_DIR = Path(__file__).parent.parent / "state" / "predicates"
PREDICATES_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("vsf_rsi.pipeline")

# Minimum occurrences to trigger predicate generation
MIN_OCCURRENCES = int(os.environ.get("RSI_MIN_OCCURRENCES", "2"))

# Quality threshold — patterns below this are candidates for improvement
QUALITY_THRESHOLD = float(os.environ.get("RSI_QUALITY_THRESHOLD", "0.5"))

# ============================================================
# SECURITY: Input sanitization
# ============================================================

# Characters allowed in fault_signature components (after split on '.')
# Alphanumeric, underscore, hyphen — NO quotes, parens, braces, semicolons
_SAFE_VALUE_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')

# Maximum length for any value injected into a tree
_MAX_VALUE_LENGTH = 200


def _sanitize_value(value: str) -> str:
    """Sanitize a value for safe use in condition trees.
    
    Raises ValueError if value contains unsafe characters.
    This prevents injection attacks via fault_signature or command strings.
    """
    if not value:
        return value
    if len(value) > _MAX_VALUE_LENGTH:
        raise ValueError(f"Value too long ({len(value)} > {_MAX_VALUE_LENGTH})")
    if not _SAFE_VALUE_RE.match(value):
        raise ValueError(
            f"Value contains unsafe characters: {value!r}. "
            f"Only alphanumeric, underscore, hyphen allowed."
        )
    return value


def _sanitize_fault_signature(fault_signature: str) -> List[str]:
    """Parse and sanitize a fault signature into safe components.
    
    Returns list of sanitized components.
    Raises ValueError if any component is unsafe.
    """
    parts = fault_signature.split(".")
    return [_sanitize_value(p) for p in parts if p]


# ============================================================
# Predicate tree generation (SAFE — no exec/eval)
# ============================================================

def _generate_predicate_name(fault_signature: str) -> str:
    """Convert fault signature to valid Python identifier."""
    # Only allow safe characters in identifiers
    safe = re.sub(r'[^a-zA-Z0-9_]', '_', fault_signature)
    return "rsi_" + safe


def _generate_predicate_tree(fault_signature: str, correction_path: str) -> Dict[str, Any]:
    """Generate a structured condition tree from a fault signature.
    
    This is the SAFE replacement for _generate_predicate_body().
    Instead of generating Python code that gets exec()'d, we generate
    a JSON tree that socratic-engine evaluates safely.
    
    The tree uses only built-in predicates:
      - ctx_has(key): checks if context has a non-empty key
      - ctx_equals(key, value): checks ctx[key] == value (exact match)
      - ctx_contains(key, substring): checks substring in ctx[key]
    
    SECURITY: All values are sanitized before being placed in the tree.
    """
    components = _sanitize_fault_signature(fault_signature)
    
    children: List[Dict[str, Any]] = []
    
    # Guard: context must exist and have 'tool'
    children.append({
        "predicate": "ctx_has",
        "args": ["tool"],
        "inject_context": True,
    })
    
    if len(components) >= 1 and components[0]:
        # First component: tool name (exact match)
        children.append({
            "predicate": "ctx_equals",
            "args": ["tool", components[0]],
            "inject_context": True,
        })
    
    if len(components) >= 2 and components[1]:
        # Second component: command substring (contains match)
        children.append({
            "predicate": "ctx_contains",
            "args": ["command", components[1]],
            "inject_context": True,
        })
    
    if len(components) >= 3 and components[2]:
        # Third component: additional detail substring
        children.append({
            "predicate": "ctx_contains",
            "args": ["command", components[2]],
            "inject_context": True,
        })
    
    return {
        "op": "AND",
        "children": children,
        "inject_context": True,
    }


# ============================================================
# Persistence (safe — stores trees, not code)
# ============================================================

def _persist_predicate(predicate_name: str, fault_signature: str,
                       tree: Dict[str, Any], correction_path: str) -> str:
    """Persist predicate tree to disk for future loading.
    
    SECURITY: Stores the tree structure, NOT executable code.
    Old format (body as string) is NOT loaded — see _load_predicates().
    """
    pred_file = PREDICATES_DIR / f"{predicate_name}.json"
    data = {
        "name": predicate_name,
        "fault_signature": fault_signature,
        "tree": tree,  # NEW: structured tree, not code string
        "correction_path": correction_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "format_version": 2,  # v2 = tree-based (safe)
    }
    pred_file.write_text(json.dumps(data, indent=2))
    return str(pred_file)


def _load_predicates(engine) -> int:
    """Load all persisted predicates into socratic-engine.
    
    SECURITY: Only loads v2 format (structured trees). 
    Old v1 format (body strings with exec()) is SKIPPED with a warning.
    """
    count = 0
    for pred_file in PREDICATES_DIR.glob("*.json"):
        try:
            data = json.loads(pred_file.read_text())
            name = data.get("name", "")
            
            # SECURITY: Skip v1 format (old exec-based predicates)
            if "tree" not in data:
                logger.warning(
                    f"Skipping predicate {pred_file.name}: "
                    f"v1 format (exec-based) no longer supported. "
                    f"Delete this file or regenerate with v2 pipeline."
                )
                continue
            
            tree = data["tree"]
            
            if not name or not tree:
                continue
            
            # Register as a predicate that evaluates the tree
            if name not in engine.predicates:
                # Create a closure that captures the tree
                def make_evaluator(tree_dict):
                    def evaluator(**kwargs):
                        from socratic_engine.engine import PredicateResult, Truth
                        ctx = kwargs.get('_context', {})
                        try:
                            result = engine.evaluate(tree_dict, context=ctx)
                            return PredicateResult(
                                truth=result.truth,
                                certified=result.certified,
                                evidence=result.evidence or {},
                                source=name,
                            )
                        except Exception as e:
                            return PredicateResult(
                                truth=Truth.UNKNOWN,
                                certified=False,
                                evidence={'error': str(e)},
                                source=name,
                            )
                    return evaluator
                
                engine.register(name)(make_evaluator(tree))
                count += 1
                
        except Exception as e:
            logger.warning(f"Failed to load predicate {pred_file}: {e}")

    return count


def _register_predicate(predicate_name: str, fault_signature: str,
                        tree: Dict[str, Any], correction_path: str) -> bool:
    """Register a generated predicate tree in socratic-engine + persist.
    
    SECURITY: Registers a tree for evaluation, NOT a code string for exec().
    """
    try:
        from vsf_rsi.rsi_socratic_bridge import register_rsi_tree

        engine = _get_or_create_engine()

        # Load existing predicates first
        if not engine._rsi_trees:
            _load_predicates(engine)

        # Register as a named tree (safe — evaluated by engine, not exec'd)
        registered = register_rsi_tree(engine, predicate_name, tree)
        
        if registered:
            # Persist to disk
            _persist_predicate(predicate_name, fault_signature, tree, correction_path)
            
        return registered
        
    except Exception as e:
        logger.warning(f"Failed to register predicate: {e}")
        return False


def _register_predicate(predicate_name: str, fault_signature: str,
                        tree: Dict[str, Any], correction_path: str) -> bool:
    """Register a generated predicate tree in socratic-engine + persist.
    
    SECURITY: Registers a tree for evaluation, NOT a code string for exec().
    """
    try:
        from vsf_rsi.rsi_socratic_bridge import register_rsi_tree

        engine = _get_or_create_engine()

        # Load existing predicates first
        _load_predicates(engine)

        # Register the tree (safe — engine evaluates it, no exec)
        registered = register_rsi_tree(engine, predicate_name, tree)

        # Persist to disk
        _persist_predicate(predicate_name, fault_signature, tree, correction_path)

        return registered

    except Exception as e:
        logger.warning(f"Failed to register predicate: {e}")
        return False


# Global engine instance
_engine = None

def _get_or_create_engine():
    """Get or create a socratic-engine instance with RSI predicates."""
    global _engine
    if _engine is not None:
        return _engine
    
    from socratic_engine.engine import SocraticEngine
    _engine = SocraticEngine()
    # Initialize RSI trees storage if not present
    if not hasattr(_engine, '_rsi_trees'):
        _engine._rsi_trees = {}
    # Register built-in RSI predicates if not already present
    _register_rsi_predicates(_engine)
    # Load persisted predicates
    _load_predicates(_engine)
    return _engine


def _register_rsi_predicates(engine) -> None:
    """Register safe built-in predicates for RSI condition evaluation.
    
    These replace the exec()-generated functions from v1.
    """
    from socratic_engine.engine import PredicateResult, Truth

    if "ctx_equals" not in engine.predicates:
        @engine.register("ctx_equals")
        def ctx_equals(key: str, expected: str, **kw) -> PredicateResult:
            """Check ctx[key] == expected (exact string match)."""
            ctx = kw.get("_context", {})
            actual = ctx.get(key, None)
            if actual is None:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing_key": key}, source="ctx_equals",
                )
            match = str(actual) == expected
            return PredicateResult(
                truth=Truth.TRUE if match else Truth.FALSE,
                certified=True,
                evidence={"key": key, "expected": expected, "actual": actual},
                source="ctx_equals",
            )

    if "ctx_contains" not in engine.predicates:
        @engine.register("ctx_contains")
        def ctx_contains(key: str, substring: str, **kw) -> PredicateResult:
            """Check substring in str(ctx[key])."""
            ctx = kw.get("_context", {})
            actual = ctx.get(key, None)
            if actual is None:
                return PredicateResult(
                    truth=Truth.UNKNOWN, certified=False,
                    evidence={"missing_key": key}, source="ctx_contains",
                )
            match = substring in str(actual)
            return PredicateResult(
                truth=Truth.TRUE if match else Truth.FALSE,
                certified=True,
                evidence={"key": key, "substring": substring, "actual": actual},
                source="ctx_contains",
            )


def _evaluate_with_predicate(predicate_name: str, context: Dict[str, Any]) -> Optional[bool]:
    """Evaluate a tree using the registered predicate.
    
    SECURITY: Uses enforce_limits=True to prevent DoS via deep/wide trees.
    """
    try:
        engine = _get_or_create_engine()

        if predicate_name not in engine.predicates:
            return None

        tree = {
            "op": "AND",
            "children": [
                {"predicate": "ctx_has", "args": ["tool"], "inject_context": True},
                {"predicate": predicate_name, "args": [], "inject_context": True},
            ],
            "inject_context": True,
        }

        # SECURITY: enforce_limits=True prevents DoS via deep/wide auto-generated trees
        result = engine.evaluate(tree, context=context, enforce_limits=True)
        return result.truth.value == "true"

    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")
        return None


# ============================================================
# Main pipeline
# ============================================================

def pipeline(
    tool: str,
    command: str,
    outcome: str,
    context: Optional[Dict[str, Any]] = None,
    fault_signature: Optional[str] = None,
    quality: float = 0.5,
) -> Dict[str, Any]:
    """Execute the full RSI evolution pipeline.

    Args:
        tool: Tool name (bash, write, edit, etc.)
        command: Command or file path
        outcome: Result (success, failure)
        context: Optional context for evaluation
        fault_signature: Optional custom fault signature
        quality: Quality score for this action (0.0-1.0)

    Returns:
        Dict with pipeline results
    """
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "command": command[:100],
        "outcome": outcome,
        "recorded": False,
        "patterns_found": 0,
        "predicate_generated": False,
        "predicate_registered": False,
        "predicate_name": None,
        "evaluation": None,
    }

    # Phase 1: Record the action
    # SECURITY: Sanitize fault signature components
    raw_sig = fault_signature or f"{tool}.{command.split()[0] if command else 'unknown'}"
    try:
        # Validate the signature doesn't contain injection attempts
        _sanitize_fault_signature(raw_sig)
        sig = raw_sig
    except ValueError as e:
        logger.error(f"Rejected unsafe fault signature: {e}")
        result["error"] = f"unsafe_fault_signature: {e}"
        return result

    try:
        sid = record(
            decision=f"{tool}:{command[:50]}",
            outcome=outcome,
            correction_path=f"pipeline:{tool}:{outcome}",
            fault_signature=sig,
        )
        adapt(sid, quality=quality, learned_from_failure=(outcome == "failure"))
        result["recorded"] = True
        result["scenario_id"] = sid
        logger.info(f"Recorded: {sid} ({sig})")
    except Exception as e:
        logger.error(f"Record failed: {e}")
        return result

    # Phase 2: Learn from patterns
    try:
        patterns = learn(min_occurrences=MIN_OCCURRENCES)
        result["patterns_found"] = len(patterns)

        # Find patterns that need improvement
        learnable = [
            p for p in patterns
            if p["avg_quality"] < QUALITY_THRESHOLD and p["count"] >= MIN_OCCURRENCES
        ]

        if not learnable:
            logger.info("No learnable patterns found")
            return result

        # Phase 3: Generate tree from best pattern (SAFE — no exec)
        best = learnable[0]
        pred_name = _generate_predicate_name(best["fault_signature"])
        pred_tree = _generate_predicate_tree(best["fault_signature"], best["correction_path"])

        result["predicate_name"] = pred_name
        result["predicate_generated"] = True
        result["pattern_used"] = {
            "fault_signature": best["fault_signature"],
            "count": best["count"],
            "avg_quality": best["avg_quality"],
        }
        logger.info(f"Generated predicate tree: {pred_name}")

        # Phase 4: Register in socratic-engine (SAFE — tree, not code)
        registered = _register_predicate(pred_name, best["fault_signature"], pred_tree, best["correction_path"])
        result["predicate_registered"] = registered

        if registered:
            logger.info(f"Registered: {pred_name}")

            # Phase 5: Evaluate if context provided
            if context:
                eval_result = _evaluate_with_predicate(pred_name, context)
                result["evaluation"] = eval_result
                logger.info(f"Evaluation: {eval_result}")

    except Exception as e:
        logger.error(f"Pipeline error: {e}")

    return result


def run_batch(actions: list) -> Dict[str, Any]:
    """Run pipeline on a batch of actions.

    Args:
        actions: List of (tool, command, outcome) tuples

    Returns:
        Summary of batch processing
    """
    results = []
    predicates_generated = 0
    predicates_registered = 0

    for tool, command, outcome in actions:
        r = pipeline(tool, command, outcome)
        results.append(r)
        if r.get("predicate_generated"):
            predicates_generated += 1
        if r.get("predicate_registered"):
            predicates_registered += 1

    return {
        "total": len(actions),
        "predicates_generated": predicates_generated,
        "predicates_registered": predicates_registered,
        "results": results,
    }


# CLI entry point
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python -m vsf_rsi.rsi_pipeline <tool> <command> <outcome>")
        print("Example: python -m vsf_rsi.rsi_pipeline bash 'grep missing file.py' failure")
        sys.exit(1)

    tool = sys.argv[1]
    command = sys.argv[2]
    outcome = sys.argv[3]

    result = pipeline(tool, command, outcome)
    print(json.dumps(result, indent=2))
