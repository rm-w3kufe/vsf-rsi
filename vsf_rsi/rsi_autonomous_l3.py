#!/usr/bin/env python3
"""
RSI Autonomous L3 — Orchestrator for the autonomous L3 cycle.

Cycle: detect complex faults → GA generates strategies →
       shadow mode validates → activate with rollback.

This module is the entry point for autonomous strategy generation.
It runs without agent invocation — triggered by the observer when
complex faults are detected.

Part of the L3 Autonomous Cycle.
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("vsf_rsi.autonomous_l3")

# ── Configuration ──────────────────────────────────────────────────
L3_DIR = Path(os.environ.get(
    "RSI_L3_DIR",
    str(Path(__file__).parent.parent.parent / "state" / "l3_autonomous")
))
L3_STATE_FILE = L3_DIR / "l3_state.json"

# GA parameters
STRATEGIES_PER_FAULT = 5
MAX_GENERATIONS = 3
MUTATION_RATE = 0.3


@dataclass
class L3CycleResult:
    """Result of one L3 autonomous cycle."""
    cycle_id: str
    fault_id: str
    strategies_generated: int
    strategies_passed_shadow: int
    strategy_activated: Optional[str]
    status: str  # completed → activated / no_candidate / rolled_back
    started_at: str
    completed_at: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AutonomousL3:
    """Orchestrates the autonomous L3 cycle.

    Components:
      - FaultDetector: identifies complex faults
      - StrategyGenerator: GA generates candidate strategies
      - ShadowMode: validates strategies before activation
      - RollbackManager: monitors activated strategies

    Usage:
        l3 = AutonomousL3(engine)
        result = l3.run_cycle(fault)
        # or run continuously:
        l3.run_continuous()
    """

    def __init__(self, engine: Any, metrics: Any = None):
        self.engine = engine
        self.metrics = metrics

        # Import components lazily
        from .rsi_fault_detector import FaultDetector
        from .rsi_shadow_mode import ShadowMode
        from .rsi_rollback import RollbackManager

        self.detector = FaultDetector()
        self.shadow = ShadowMode(engine, metrics)
        self.rollback = RollbackManager(engine, metrics)

        self._cycles: Dict[str, L3CycleResult] = {}
        self._load_state()

    def run_cycle(self, fault: Any = None) -> L3CycleResult:
        """Run one complete L3 cycle.

        Args:
            fault: FaultSignature from detector. If None, checks for pending faults.

        Returns:
            L3CycleResult with cycle outcome
        """
        cycle_id = f"cycle-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc).isoformat()

        # Get fault to process
        if fault is None:
            pending = self.detector.get_pending_faults()
            if not pending:
                return L3CycleResult(
                    cycle_id=cycle_id,
                    fault_id="none",
                    strategies_generated=0,
                    strategies_passed_shadow=0,
                    strategy_activated=None,
                    status="no_faults",
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            fault = pending[0]

        logger.info(f"L3 Cycle {cycle_id}: processing fault {fault.fault_id}")

        # Mark fault as being processed
        self.detector.update_fault_status(fault.fault_id, "generating")

        # Step 1: Generate candidate strategies
        candidates = self._generate_strategies(fault)
        logger.info(f"Generated {len(candidates)} candidate strategies")

        # Step 2: Evaluate baseline
        test_cases = self._build_test_cases(fault)
        baseline_accuracy, baseline_latency = self.shadow.evaluate_baseline(
            self._build_default_tree(fault),
            test_cases,
        )
        logger.info(f"Baseline: accuracy={baseline_accuracy:.1%}, "
                    f"latency={baseline_latency:.1f}ms")

        # Step 3: Shadow mode evaluation
        passed = []
        for candidate in candidates:
            result = self.shadow.evaluate_strategy(
                candidate, test_cases, baseline_accuracy, baseline_latency,
            )
            if result.passed:
                passed.append((candidate, result))

        logger.info(f"Shadow: {len(passed)}/{len(candidates)} strategies passed")

        # Step 4: Activate best strategy (if any passed)
        activated_id = None
        if passed:
            # Sort by improvement, take best
            passed.sort(key=lambda x: x[1].improvement_pct, reverse=True)
            best_candidate, best_result = passed[0]

            # Activate with rollback monitoring
            monitored = self.rollback.activate(
                strategy_id=best_candidate.strategy_id,
                fault_id=fault.fault_id,
                tree=best_candidate.tree,
                baseline_accuracy=baseline_accuracy,
            )

            activated_id = best_candidate.strategy_id
            self.detector.update_fault_status(fault.fault_id, "active")

            logger.info(f"Activated: {activated_id} "
                       f"(improvement={best_result.improvement_pct:+.1%})")

            # Register in scenario memory for future matching
            self._record_scenario(fault, best_candidate, best_result)
        else:
            self.detector.update_fault_status(fault.fault_id, "no_candidate")
            logger.info(f"No strategy passed shadow for {fault.fault_id}")

        # Build result
        result = L3CycleResult(
            cycle_id=cycle_id,
            fault_id=fault.fault_id,
            strategies_generated=len(candidates),
            strategies_passed_shadow=len(passed),
            strategy_activated=activated_id,
            status="activated" if activated_id else "no_candidate",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            details={
                "baseline_accuracy": baseline_accuracy,
                "baseline_latency_ms": baseline_latency,
                "candidates": [c.strategy_id for c in candidates],
            },
        )

        self._cycles[cycle_id] = result
        self._save_state()

        return result

    def run_continuous(self, max_cycles: int = 10):
        """Run L3 cycle continuously for pending faults.

        Args:
            max_cycles: Maximum number of cycles to run (safety limit)
        """
        for i in range(max_cycles):
            pending = self.detector.get_pending_faults()
            if not pending:
                logger.info("No pending faults — L3 cycle idle")
                break

            result = self.run_cycle(pending[0])
            logger.info(f"Cycle {i+1}/{max_cycles}: {result.status}")

            if result.status == "no_faults":
                break

    def process_event(self, event: Any) -> Optional[L3CycleResult]:
        """Process an observer event through the L3 cycle.

        This is the integration point with the observer.
        Called after each evaluation to check if a complex fault is detected.

        Returns:
            L3CycleResult if a cycle was triggered, None otherwise
        """
        # Feed event to fault detector
        fault = self.detector.observe(event)

        if fault is None:
            return None

        # Complex fault detected — run L3 cycle
        logger.info(f"Complex fault detected: {fault.fault_id} — starting L3 cycle")
        return self.run_cycle(fault)

    def _generate_strategies(self, fault: Any) -> List[Any]:
        """Generate candidate strategies for a fault using Genome V3.

        Uses the enriched genome representation:
          1. Random genome creation with variadic operations
          2. Feature chaining (d1 can reference d0)
          3. Crossover between genomes
          4. Mutation (swap operations, adjust thresholds)
          5. Convert to socratic tree for evaluation

        Returns:
            List of StrategyCandidate objects
        """
        from .rsi_shadow_mode import StrategyCandidate
        from .rsi_genome_v3 import (
            create_random_genome_v3, crossover_v3, mutate_v3,
        )

        candidates = []
        source = fault.source

        # Available features based on fault source
        features = ["input_value", "threshold", "latency_ms"]
        if "pred" in source:
            features.append("prediction")

        # Generate random genomes
        for i in range(STRATEGIES_PER_FAULT):
            try:
                # Create random genome
                genome = create_random_genome_v3(
                    genome_id=f"l3-{source}-{i}-{uuid.uuid4().hex[:4]}",
                    available_features=features,
                    n_derived=3,
                    tree_depth=2,
                )

                # Convert genome to socratic tree
                tree = self._genome_to_tree(genome)
                if tree:
                    candidates.append(StrategyCandidate(
                        strategy_id=genome.id,
                        fault_id=fault.fault_id,
                        tree=tree,
                        source=source,
                        description=f"Genome V3: {genome.id}",
                    ))
            except Exception as e:
                logger.debug(f"Genome generation failed: {e}")
                continue

        # Add some crossover combinations
        if len(candidates) >= 2:
            for i in range(min(2, len(candidates) - 1)):
                try:
                    g1 = candidates[i]
                    g2 = candidates[i + 1]
                    # Simple tree crossover: swap children
                    tree = self._crossover_trees(g1.tree, g2.tree)
                    if tree:
                        candidates.append(StrategyCandidate(
                            strategy_id=f"cross-{uuid.uuid4().hex[:8]}",
                            fault_id=fault.fault_id,
                            tree=tree,
                            source=source,
                            description=f"Crossover: {g1.strategy_id} + {g2.strategy_id}",
                        ))
                except Exception as e:
                    logger.debug(f"Crossover failed: {e}")

        # Limit to STRATEGIES_PER_FAULT
        return candidates[:STRATEGIES_PER_FAULT]

    def _genome_to_tree(self, genome: Any) -> Optional[Dict[str, Any]]:
        """Convert a GenomeV3 to a socratic tree for evaluation.

        The genome's features are converted to comparison predicates.
        Each feature becomes a comparison node (gt, lt, eq) with appropriate
        thresholds based on the genome's operations.
        
        Only uses features that exist in the context (input_value, threshold, latency_ms).
        Filters out contradictory conditions (e.g., gt AND lt on same field).
        
        Uses socratic-engine format: "predicate" (not "op"), "args" (not "kwargs"),
        and "inject_context": True.
        """
        if not genome.features:
            return None

        # Map genome operations to comparison predicates
        op_map = {
            'add': 'gt',      # Addition → check if sum > threshold
            'sub': 'lt',      # Subtraction → check if diff < threshold
            'mul': 'gt',      # Multiplication → check if product > threshold
            'max': 'gt',      # Max → check if max > threshold
            'min': 'lt',      # Min → check if min < threshold
            'mean': 'gt',     # Mean → check if mean > threshold
            'sign': 'gt',     # Sign → check if positive
            'parity': 'eq',   # Parity → check if even (0) or odd (1)
            'count_neg': 'lt', # Count negatives → check if count < threshold
            'xor2': 'eq',     # XOR → check if equal to expected
        }

        # Valid fields that exist in context
        valid_fields = {'input_value', 'threshold', 'latency_ms'}

        # Build tree from genome features
        children = []
        used_fields = {}  # field -> (predicate, threshold) for contradiction detection
        
        for feature in genome.features[:3]:  # Limit to 3 features
            op = feature.op if hasattr(feature, 'op') else 'ctx_has'
            args = feature.args if hasattr(feature, 'args') else []

            # Map to comparison predicate
            pred = op_map.get(op, 'gt')
            
            # Use first arg as field (must be valid)
            field_name = args[0] if args else 'input_value'
            if field_name not in valid_fields:
                continue  # Skip invalid fields (d0, d1, etc.)
            
            threshold = 0.5  # Default threshold
            
            # Check for contradictions
            if field_name in used_fields:
                existing_pred, existing_threshold = used_fields[field_name]
                # gt and lt on same field with same threshold = contradiction
                if (pred == 'gt' and existing_pred == 'lt') or \
                   (pred == 'lt' and existing_pred == 'gt'):
                    if threshold == existing_threshold:
                        continue  # Skip contradictory condition
                # gt and lte, or lt and gte are also contradictory
                if (pred == 'gt' and existing_pred == 'lte') or \
                   (pred == 'lt' and existing_pred == 'gte'):
                    if threshold == existing_threshold:
                        continue
                # eq and gt/lt on same field can be contradictory
                if pred == 'eq' or existing_pred == 'eq':
                    continue  # Skip eq if other comparison exists
            
            used_fields[field_name] = (pred, threshold)
            
            # Create predicate node
            children.append({
                "predicate": pred,
                "args": [field_name, threshold],
                "inject_context": True,
            })

        if not children:
            return None

        # Combine with AND operator
        if len(children) == 1:
            return children[0]
        return {
            "op": "AND",
            "children": children,
            "inject_context": True,
        }

    def _crossover_trees(self, tree1: Dict, tree2: Dict) -> Optional[Dict[str, Any]]:
        """Simple crossover: swap children between two trees."""
        if not tree1 or not tree2:
            return None

        if tree1.get("op") == tree2.get("op") == "AND":
            children1 = tree1.get("children", [])
            children2 = tree2.get("children", [])
            if children1 and children2:
                # Take first child from tree1, rest from tree2
                new_children = [children1[0]] + children2[1:]
                return {"op": "AND", "children": new_children}

        # Different operators — return tree1 as-is
        return tree1

    def _build_test_cases(self, fault: Any) -> List[Dict[str, Any]]:
        """Build test cases from fault's sample events.
        
        Generates test cases with expected values based on the fault type.
        For BLOCKING faults, expected=False (fault events are errors).
        For non-fault events, expected=True (successful evaluations).
        
        Uses socratic-engine format with comparison predicates.
        """
        test_cases = []
        
        # Add test cases from fault sample events (expected=False for errors)
        for ev in fault.sample_events:
            test_cases.append({
                "tree": {"predicate": "gt", "args": ["input_value", 0.5], "inject_context": True},
                "ctx": {"input_value": 0.5, "threshold": 0.7},
                "expected": False,  # Fault events are errors
            })
        
        # Add default test cases with varying inputs
        # These represent "normal" behavior that should pass
        for val in [0.3, 0.5, 0.7, 0.9]:
            test_cases.append({
                "tree": {"predicate": "gt", "args": ["input_value", 0.5], "inject_context": True},
                "ctx": {"input_value": val, "threshold": 0.5},
                "expected": val > 0.5,  # Expected: True if value > threshold
            })
        
        # Add edge cases
        test_cases.extend([
            {"tree": {"predicate": "gt", "args": ["input_value", 0.5], "inject_context": True},
             "ctx": {"input_value": 0.0, "threshold": 0.5}, "expected": False},
            {"tree": {"predicate": "gt", "args": ["input_value", 0.5], "inject_context": True},
             "ctx": {"input_value": 1.0, "threshold": 0.5}, "expected": True},
        ])
        
        return test_cases

    def _build_default_tree(self, fault: Any) -> Dict[str, Any]:
        """Build a default tree for baseline evaluation.
        
        Uses a simple comparison predicate that checks if input_value > threshold.
        """
        return {"predicate": "gt", "args": ["input_value", 0.5], "inject_context": True}

    def _build_threshold_tree(self, source: str, delta: float) -> Optional[Dict[str, Any]]:
        """Build a tree with adjusted threshold.
        
        Creates a tree that checks if input_value and threshold exist in context,
        then applies the delta adjustment to the threshold.
        
        Args:
            source: The predicate source name
            delta: Amount to adjust threshold (positive = increase, negative = decrease)
        
        Returns:
            Tree dict in socratic-engine format, or None if invalid
        """
        if not source or not isinstance(delta, (int, float)):
            return None
        
        return {
            "op": "AND",
            "children": [
                {"predicate": "ctx_has", "args": ["input_value"], "inject_context": True},
                {"predicate": "ctx_has", "args": ["threshold"], "inject_context": True},
                {"predicate": "threshold_adjusted", "args": [source, delta], "inject_context": True},
            ],
            "inject_context": True,
        }

    def _build_operator_tree(self, source: str, op: str) -> Optional[Dict[str, Any]]:
        """Build a tree with a different operator.
        
        Creates a tree that checks if input_value exists and applies the
        specified comparison operator.
        
        Args:
            source: The predicate source name
            op: Comparison operator (gt, lt, eq, gte, lte)
        
        Returns:
            Tree dict in socratic-engine format, or None if invalid
        """
        valid_ops = {"gt", "lt", "eq", "gte", "lte"}
        if not source or op not in valid_ops:
            return None
        
        return {
            "op": "AND",
            "children": [
                {"predicate": "ctx_has", "args": ["input_value"], "inject_context": True},
                {"predicate": "ctx_has", "args": ["threshold"], "inject_context": True},
                {"predicate": f"compare_{op}", "args": ["input_value", "threshold"], "inject_context": True},
            ],
            "inject_context": True,
        }

    def _record_scenario(self, fault: Any, candidate: Any, result: Any):
        """Record successful strategy in scenario memory."""
        try:
            from .scenario_memory import record
            record(
                decision={
                    "fault_id": fault.fault_id,
                    "strategy_id": candidate.strategy_id,
                    "tree": candidate.tree,
                    "improvement": result.improvement_pct,
                },
                outcome="success",
                correction_path=None,
            )
        except Exception as e:
            logger.warning(f"Failed to record scenario: {e}")

    def _load_state(self):
        try:
            if L3_STATE_FILE.exists():
                with open(L3_STATE_FILE) as f:
                    data = json.load(f)
                for cid, cdata in data.get("cycles", {}).items():
                    self._cycles[cid] = L3CycleResult(**cdata)
        except Exception as e:
            logger.warning(f"Failed to load L3 state: {e}")

    def _save_state(self):
        try:
            L3_DIR.mkdir(parents=True, exist_ok=True)
            with open(L3_STATE_FILE, "w") as f:
                json.dump({
                    "cycles": {cid: c.to_dict() for cid, c in self._cycles.items()},
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save L3 state: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get L3 autonomous cycle statistics."""
        total = len(self._cycles)
        activated = sum(1 for c in self._cycles.values() if c.status == "activated")
        failed = sum(1 for c in self._cycles.values() if c.status == "no_candidate")

        return {
            "total_cycles": total,
            "activated": activated,
            "failed": failed,
            "activation_rate": activated / total if total > 0 else 0.0,
            "pending_faults": len(self.detector.get_pending_faults()),
            "monitored_strategies": len(self.rollback.get_monitored()),
            "confirmed_strategies": len(self.rollback.get_confirmed()),
            "rolled_back": len(self.rollback.get_rolled_back()),
        }


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m vsf_rsi.rsi_autonomous_l3 <command>")
        print("Commands:")
        print("  cycle  — run one L3 cycle for pending faults")
        print("  stats  — show L3 autonomous statistics")
        print("  faults — show detected faults")
        sys.exit(1)

    from socratic_engine.engine import SocraticEngine
    engine = SocraticEngine()
    l3 = AutonomousL3(engine)

    cmd = sys.argv[1]
    if cmd == "cycle":
        result = l3.run_cycle()
        print(f"Cycle: {result.cycle_id}")
        print(f"  Status: {result.status}")
        print(f"  Generated: {result.strategies_generated}")
        print(f"  Passed shadow: {result.strategies_passed_shadow}")
        print(f"  Activated: {result.strategy_activated}")
    elif cmd == "stats":
        stats = l3.get_stats()
        for k, v in stats.items():
            print(f"  {k}: {v}")
    elif cmd == "faults":
        faults = l3.detector.get_all_faults()
        for f in faults:
            print(f"  [{f.status}] {f.fault_id}: source={f.source}, errors={f.count}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
