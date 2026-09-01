#!/usr/bin/env python3
"""RSI Pipeline — Orchestrates the full evolution cycle.

Flow:
    action → record → learn → generate → register → evaluate

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from vsf_rsi.scenario_memory import record, adapt, learn

# Directory for persisted predicates
PREDICATES_DIR = Path(__file__).parent.parent / "state" / "predicates"
PREDICATES_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("vsf_rsi.pipeline")

# Minimum occurrences to trigger predicate generation
MIN_OCCURRENCES = int(os.environ.get("RSI_MIN_OCCURRENCES", "2"))

# Quality threshold — patterns below this are candidates for improvement
QUALITY_THRESHOLD = float(os.environ.get("RSI_QUALITY_THRESHOLD", "0.5"))


def _generate_predicate_name(fault_signature: str) -> str:
    """Convert fault signature to valid Python identifier."""
    return "rsi_" + fault_signature.replace(".", "_").replace("-", "_").replace(" ", "_")


def _generate_predicate_body(fault_signature: str, correction_path: str) -> str:
    """Generate predicate body from pattern.

    This is a simplified generator — the real generator (rsi_predicate_generator.py)
    uses AST analysis and pattern detection. This is the fast path for the pipeline.
    """
    # Extract meaningful parts from fault signature
    parts = fault_signature.split(".")

    # Build a predicate that checks for the fault condition
    body_parts = []
    if len(parts) >= 2:
        if parts[0]:
            body_parts.append(f"ctx.get('tool') == '{parts[0]}'")
        if len(parts) > 1 and parts[1]:
            body_parts.append(f"'{parts[1]}' in ctx.get('command', '')")

    condition = " and ".join(body_parts) if body_parts else "True"

    return f"""return (
    _context is not None
    and {condition}
)"""


def _persist_predicate(predicate_name: str, fault_signature: str, body: str, correction_path: str) -> str:
    """Persist predicate to disk for future loading."""
    pred_file = PREDICATES_DIR / f"{predicate_name}.json"
    data = {
        "name": predicate_name,
        "fault_signature": fault_signature,
        "body": body,
        "correction_path": correction_path,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    pred_file.write_text(json.dumps(data, indent=2))
    return str(pred_file)


def _load_predicates(engine) -> int:
    """Load all persisted predicates into socratic-engine."""
    from vsf_rsi.rsi_socratic_bridge import register_rsi_predicate

    count = 0
    for pred_file in PREDICATES_DIR.glob("*.json"):
        try:
            data = json.loads(pred_file.read_text())
            name = data["name"]
            body = data["body"]

            # Create function
            func_code = f"def {name}(*args, _context=None, **kwargs):\n    ctx = _context or {{}}\n    {body}"
            namespace = {}
            exec(func_code, namespace)
            func = namespace.get(name)

            if func and register_rsi_predicate(engine, name, func):
                count += 1
        except Exception as e:
            logger.warning(f"Failed to load predicate {pred_file}: {e}")

    return count


def _register_predicate(predicate_name: str, fault_signature: str, body: str, correction_path: str) -> bool:
    """Register a generated predicate in socratic-engine + persist."""
    try:
        from socratic_engine.engine import SocraticEngine
        from vsf_rsi.rsi_socratic_bridge import register_rsi_predicate

        engine = SocraticEngine()

        # Load existing predicates first
        _load_predicates(engine)

        # Create predicate function
        func_code = f"def {predicate_name}(*args, _context=None, **kwargs):\n    ctx = _context or {{}}\n    {body}"
        namespace = {}
        exec(func_code, namespace)
        func = namespace.get(predicate_name)

        if func:
            # Register in engine
            registered = register_rsi_predicate(engine, predicate_name, func)

            # Persist to disk
            _persist_predicate(predicate_name, fault_signature, body, correction_path)

            return registered
        return False

    except Exception as e:
        logger.warning(f"Failed to register predicate: {e}")
        return False


def _evaluate_with_predicate(predicate_name: str, context: Dict[str, Any]) -> Optional[bool]:
    """Evaluate a tree using the registered predicate."""
    try:
        from socratic_engine.engine import SocraticEngine

        engine = SocraticEngine()

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

        result = engine.evaluate(tree, context=context)
        return result.truth.value == "true"

    except Exception as e:
        logger.warning(f"Evaluation failed: {e}")
        return None


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
    sig = fault_signature or f"{tool}.{command.split()[0] if command else 'unknown'}"
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

        # Phase 3: Generate predicate from best pattern
        best = learnable[0]
        pred_name = _generate_predicate_name(best["fault_signature"])
        pred_body = _generate_predicate_body(best["fault_signature"], best["correction_path"])

        result["predicate_name"] = pred_name
        result["predicate_generated"] = True
        result["pattern_used"] = {
            "fault_signature": best["fault_signature"],
            "count": best["count"],
            "avg_quality": best["avg_quality"],
        }
        logger.info(f"Generated predicate: {pred_name}")

        # Phase 4: Register in socratic-engine
        registered = _register_predicate(pred_name, best["fault_signature"], pred_body, best["correction_path"])
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
